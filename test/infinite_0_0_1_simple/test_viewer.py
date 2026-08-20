"""The viewer reads real trajectories, including pre-v1 ones."""

import json

import pytest

from infinite.agent import Agent
from infinite.config import Config
from infinite.viewer.reader import list_workspaces, load_trajectory, trajectory_path
from infinite.workspace import Workspace

from .fake_model import FakeModel, step, text, tool_use


def run_agent(root, instruction="read input.txt", script=None):
    config = Config(max_register_length=200, max_special_length=400, max_step_half_length=200, max_canvas_length=800, summary=False, bash_timeout=5.0)
    agent = Agent(
        config=config,
        workspace=Workspace(root),
        model=FakeModel([]),
        instruction=instruction,
    )
    payload = json.dumps({"ok": True})
    agent.model.script = list(script or []) + [
        step(
            text("done"),
            tool_use(
                "bash",
                command=f"printf '%s' '{payload}' > {agent.response_path.name}",
                register_id=5,
            ),
        )
    ]
    agent.run()
    return agent


@pytest.fixture
def runs(tmp_path):
    root = tmp_path / "runs"
    run_agent(root / "alpha", instruction="count the gammas")
    run_agent(root / "beta", script=[step(tool_use("set", value="note", register_id=6))])
    return root


def test_lists_every_workspace_and_agent(runs):
    workspaces = list_workspaces(runs)

    assert {w["workspace"] for w in workspaces} == {"alpha", "beta"}
    alpha = next(w for w in workspaces if w["workspace"] == "alpha")["agents"][0]
    assert alpha["ok"] is True and alpha["running"] is False
    assert alpha["instruction"] == "count the gammas"
    assert alpha["steps"] == 1


def test_a_directory_with_no_trajectory_is_not_a_workspace(runs, tmp_path):
    (runs / "empty").mkdir()
    assert "empty" not in {w["workspace"] for w in list_workspaces(runs)}
    assert list_workspaces(tmp_path / "missing") == []


def test_normalizes_a_step_into_dialogue_parts(runs):
    trajectory = load_trajectory(trajectory_path(runs, "beta", _agent_id(runs, "beta")), "beta")

    assert trajectory["reconstructed"] is False
    assert trajectory["format_version"] == 3
    assert [t["name"] for t in trajectory["context_template"]["tools"]] == [
        "bash", "load", "set", "set_target", "spawn", "resume",
    ]
    first, last = trajectory["steps"][0], trajectory["steps"][-1]
    assert first["tool_calls"][0]["name"] == "set"
    assert first["tool_calls"][0]["result"]["value"] == "note"
    assert last["text"] == ["done"]
    assert "[Registers]" in last["model_input"]["messages"][0]["content"]
    assert trajectory["final"]["ok"] is True


def test_a_live_trajectory_survives_a_half_written_line(runs):
    path = trajectory_path(runs, "alpha", _agent_id(runs, "alpha"))
    path.chmod(0o644)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write('{"step": 9, "role": "assis')

    trajectory = load_trajectory(path, "alpha")
    assert len(trajectory["steps"]) == 1


def test_pre_v1_trajectories_are_reconstructed_and_flagged(runs, tmp_path):
    """A trajectory without the recorded context still renders, clearly labelled."""
    path = trajectory_path(runs, "alpha", _agent_id(runs, "alpha"))
    records = [json.loads(line) for line in path.read_text().splitlines()]
    for record in records:
        record.pop("context_template", None)
        record.pop("model_input", None)
        record.pop("format_version", None)
    old = tmp_path / "old.jsonl"
    old.write_text("\n".join(json.dumps(r) for r in records))

    trajectory = load_trajectory(old, "alpha")
    assert trajectory["reconstructed"] is True
    assert trajectory["format_version"] is None
    assert "InfiniteAgent" in trajectory["context_template"]["system"]
    assert trajectory["steps"][0]["model_input"]["reconstructed"] is True
    assert trajectory["steps"][0]["model_input"]["messages"][0]["content"].startswith(
        "[Registers]"
    )


def stalled_then_finished(root):
    """A run that ran out of budget and was later continued to success."""
    config = Config(max_register_length=200, max_special_length=400, max_step_half_length=200, max_canvas_length=800, summary=False, bash_timeout=5.0, max_steps=2)
    agent = Agent(
        config=config,
        workspace=Workspace(root),
        model=FakeModel([step(tool_use("set", value=f"try {i}", register_id=6)) for i in range(2)]),
        instruction="finish the job",
    )
    agent.run()

    resumed = Agent.resume(
        workspace=Workspace(root), model=FakeModel([]), agent_id=agent.agent_id,
        overrides={"max_steps": 2},
    )
    payload = json.dumps({"done": True})
    resumed.model.script = [
        step(
            text("wrapping up"),
            tool_use(
                "bash",
                command=f"printf '%s' '{payload}' > {resumed.response_path.name}",
                register_id=5,
            ),
        )
    ]
    resumed.run()
    return agent.agent_id


def test_a_resumed_run_reads_as_one_history_with_a_seam(tmp_path):
    root = tmp_path / "resumed"
    agent_id = stalled_then_finished(root / "seg")

    trajectory = load_trajectory(trajectory_path(root, "seg", agent_id), "seg")
    roles = [s["role"] for s in trajectory["steps"]]

    assert roles == ["assistant", "assistant", "segment_end", "resume", "assistant"]
    assert trajectory["segments"] == 2
    assert trajectory["steps"][2]["final"]["ok"] is False  # where it gave up
    assert trajectory["steps"][3]["resumed_from_step"] == 2
    assert trajectory["steps"][3]["max_steps"] == 2
    assert trajectory["steps"][3]["registers_from"] == "final"


def test_the_outcome_is_the_last_final_not_the_first(tmp_path):
    root = tmp_path / "resumed"
    agent_id = stalled_then_finished(root / "seg")

    trajectory = load_trajectory(trajectory_path(root, "seg", agent_id), "seg")
    summary = next(w for w in list_workspaces(root) if w["workspace"] == "seg")["agents"][0]

    # A reader that stopped at the first `final` would call this run failed.
    assert trajectory["final"]["ok"] is True
    assert trajectory["final"]["response"] == {"done": True}
    assert summary["ok"] is True and summary["running"] is False
    assert summary["segments"] == 2


def test_steps_carry_their_timing(runs):
    trajectory = load_trajectory(trajectory_path(runs, "alpha", _agent_id(runs, "alpha")), "alpha")
    timing = trajectory["steps"][0]["timing"]

    assert timing["total_s"] >= 0
    assert trajectory["duration_total_s"] >= 0


def test_paths_cannot_escape_the_runs_directory(runs):
    with pytest.raises(ValueError):
        trajectory_path(runs, "../../etc", "abcd1234")
    with pytest.raises(ValueError):
        trajectory_path(runs, "alpha", "../secret")
    with pytest.raises(FileNotFoundError):
        trajectory_path(runs, "alpha", "deadbeef")


def _agent_id(runs, workspace):
    workspaces = list_workspaces(runs)
    return next(w for w in workspaces if w["workspace"] == workspace)["agents"][0]["agent_id"]
