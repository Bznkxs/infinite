import json

import pytest

from infinite.agent import Agent
from infinite.config import Config
from infinite.model import ToolCall
from infinite.workspace import Workspace

from .fake_model import FakeModel


@pytest.fixture
def agent(tmp_path):
    config = Config(max_register_length=60, max_special_length=120, max_step_half_length=60, max_canvas_length=200, summary=False, bash_timeout=5.0)
    built = Agent(
        config=config,
        workspace=Workspace(tmp_path / "run"),
        model=FakeModel([]),
        instruction="do the thing",
    )
    built.step = 1
    yield built
    built.bash.close()


def call(name, **params):
    return ToolCall(id="toolu_test", name=name, input=params)


def run(agent, name, **params):
    result = agent.tools.execute(call(name, **params))
    if result.register_id is not None:
        agent.registers.store(result.register_id, result.payload)
    agent.registers.store(0, result.status)
    return result


# --- bash ----------------------------------------------------------------
def test_bash_writes_output_to_register_and_file(agent):
    result = run(agent, "bash", command="echo hello", register_id=5)
    assert agent.registers.values[5].strip() == "hello"
    saved = json.loads((agent.workspace.root / result.status).read_text())
    assert saved["command"] == "echo hello"
    assert "hello" in saved["output"]
    assert result.record["file"] == result.status


def test_bash_output_is_truncated_into_the_register_but_not_the_file(agent):
    result = run(agent, "bash", command="printf 'x%.0s' $(seq 1 500)", register_id=5)
    assert len(agent.registers.values[5]) == 60
    assert agent.registers.truncated[5] is True
    assert len(result.record["output"]) == 500


def test_bash_refuses_a_special_destination_without_running(agent):
    result = run(agent, "bash", command="touch should-not-exist", register_id=0)
    assert "special register" in result.status
    assert not (agent.workspace.root / "should-not-exist").exists()


def test_bash_can_write_files_in_the_workspace(agent):
    run(agent, "bash", command="echo '{\"a\": 1}' > out.json", register_id=5)
    assert json.loads((agent.workspace.root / "out.json").read_text()) == {"a": 1}


# --- load ----------------------------------------------------------------
def test_load_pages_through_a_file(agent):
    (agent.workspace.root / "long.txt").write_text("abcdefgh" * 20)  # 160 chars

    first = run(agent, "load", path="long.txt", start=0, register_id=5)
    assert agent.registers.values[5] == ("abcdefgh" * 20)[:60]
    assert "length=160" in first.status
    assert first.record["display_length"] == 60

    run(agent, "load", path="long.txt", start=150, register_id=5)
    assert agent.registers.values[5] == ("abcdefgh" * 20)[150:]


def test_load_past_the_end_gives_an_empty_register(agent):
    (agent.workspace.root / "short.txt").write_text("abc")
    agent.registers.store(2, "previous")
    run(agent, "load", path="short.txt", start=3, register_id=5)
    assert agent.registers.values[5] == ""


def test_load_uses_the_canvas_limit_for_the_canvas(agent):
    (agent.workspace.root / "long.txt").write_text("z" * 5000)
    run(agent, "load", path="long.txt", start=0, register_id=32)
    assert len(agent.registers.values[32]) == 200


def test_load_reports_bad_paths_and_arguments(agent):
    assert "does not exist" in run(agent, "load", path="nope", start=0, register_id=5).status
    assert "is a directory" in run(agent, "load", path=".", start=0, register_id=5).status
    (agent.workspace.root / "f.txt").write_text("x")
    assert "'start'" in run(agent, "load", path="f.txt", start=-1, register_id=5).status


# --- set -----------------------------------------------------------------
def test_set_stores_strings_and_converts_other_values(agent):
    run(agent, "set", value="remember this", register_id=6)
    assert agent.registers.values[6] == "remember this"
    run(agent, "set", value={"page": 2}, register_id=7)
    assert agent.registers.values[7] == '{"page": 2}'


def test_set_rejects_oversized_values_without_a_file(agent):
    run(agent, "set", value="k", register_id=6)
    before = agent.workspace._output_counter
    result = run(agent, "set", value="x" * 61, register_id=6)
    assert "error" in result.status and "unchanged" in result.status
    assert agent.registers.values[6] == "k"  # untouched
    # The error goes straight to register 0 (clipped to that register's length).
    assert result.status.startswith(agent.registers.values[0])
    assert agent.workspace._output_counter == before  # no file generated


def test_set_rejects_special_destinations(agent):
    assert "special register" in run(agent, "set", value="x", register_id=1).status


# --- errors --------------------------------------------------------------
def test_unknown_tool_is_reported_not_raised(agent):
    assert "unknown tool" in run(agent, "nav", n=10).status


def big_register_agent(tmp_path):
    """Register 0 must be able to hold the notice, so use the real geometry."""
    built = Agent(
        config=Config(summary=False, bash_timeout=5.0),
        workspace=Workspace(tmp_path / "run"),
        model=FakeModel([]),
        instruction="do the thing",
    )
    built.step = 1
    return built


def test_a_truncated_result_says_so_in_register_0(tmp_path):
    """0.0.7a's run re-read the same file for 435 steps because it never learned
    that the register, not the command, was what limited what it saw."""
    agent = big_register_agent(tmp_path)
    try:
        agent._run_tool(call("bash", command="printf 'x%.0s' $(seq 1 5000)", register_id=5))
        notice = agent.registers.values[0]
    finally:
        agent.bash.close()

    assert "CUT: 5000 chars, register 5 kept 1024" in notice
    assert "canvas (register 32, 20000)" in notice  # the way out
    assert "Re-running the command shows no more." in notice
    assert notice.startswith("tool_output/")  # the path is still first
    assert len(agent.registers.values[5]) == 1024
    assert agent.registers.truncated[5] is True


def test_a_result_that_fits_gets_no_warning(tmp_path):
    agent = big_register_agent(tmp_path)
    try:
        agent._run_tool(call("bash", command="echo short", register_id=5))
        assert "CUT:" not in agent.registers.values[0]
    finally:
        agent.bash.close()


def test_a_truncated_canvas_result_points_at_paging_not_the_canvas(tmp_path):
    """The canvas is already the biggest register; the way out there is `load`."""
    agent = big_register_agent(tmp_path)
    try:
        agent._run_tool(call("bash", command="printf 'y%.0s' $(seq 1 21000)", register_id=32))
        notice = agent.registers.values[0]
    finally:
        agent.bash.close()

    assert "load(start=N)` in pieces" in notice and "canvas (register" not in notice
