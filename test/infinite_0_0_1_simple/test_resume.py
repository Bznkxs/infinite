"""Resuming a run that ran out of budget."""

import json

import pytest

from infinite.agent import Agent
from infinite.config import Config
from infinite.workspace import Workspace

from .fake_model import FakeModel, step, text, tool_use

CONFIG = dict(max_register_length=200, max_special_length=400, max_step_half_length=200, max_canvas_length=800, summary=False, bash_timeout=5.0)


def start(root, script, *, max_steps=2, instruction="find the answer"):
    agent = Agent(
        config=Config(max_steps=max_steps, **CONFIG),
        workspace=Workspace(root),
        model=FakeModel(script),
        instruction=instruction,
    )
    return agent, agent.run()


def resume(root, script, **overrides):
    agent = Agent.resume(
        workspace=Workspace(root),
        model=FakeModel(script),
        agent_id=_only_agent(root),
        overrides=overrides,
    )
    return agent, agent.run()


def _only_agent(root):
    return next(Workspace(root).root.glob("trajectory-*.jsonl")).stem.removeprefix(
        "trajectory-"
    )


def finish(agent, payload=None):
    escaped = json.dumps(payload or {"answer": 42}).replace("'", "'\\''")
    return step(
        tool_use(
            "bash",
            command=f"printf '%s' '{escaped}' > {agent.response_path.name}",
            register_id=5,
        )
    )


def busywork(n):
    return [step(tool_use("set", value=f"working {i}", register_id=6)) for i in range(n)]


def test_a_run_that_exhausts_its_budget_can_be_continued(tmp_path):
    root = tmp_path / "run"
    agent, result = start(root, busywork(5), max_steps=2)
    assert not result.ok and result.steps == 2

    resumed = Agent.resume(
        workspace=Workspace(root), model=FakeModel([]), agent_id=agent.agent_id,
        overrides={"max_steps": 3},
    )
    resumed.model.script = [*busywork(1), finish(resumed)]
    again = resumed.run()

    assert again.ok
    assert again.response == {"answer": 42}
    # Numbering continues past the closing marker: steps 1,2 then 4,5.
    assert again.steps == 5
    assert [r["step"] for r in resumed.trajectory.read() if r["role"] == "assistant"] == [1, 2, 4, 5]


def test_the_continuation_lands_in_the_same_trajectory(tmp_path):
    root = tmp_path / "run"
    agent, _ = start(root, busywork(5), max_steps=2)

    resumed = Agent.resume(
        workspace=Workspace(root), model=FakeModel([]), agent_id=agent.agent_id,
        overrides={"max_steps": 2},
    )
    resumed.model.script = [finish(resumed)]
    resumed.run()

    records = agent.trajectory.read()
    assert [r["role"] for r in records] == [
        "user", "assistant", "assistant", "final", "resume", "assistant", "final",
    ]
    assert [r["step"] for r in records if r["role"] == "assistant"] == [1, 2, 4]
    assert records[-1]["ok"] is True
    # No two *steps* share a number; the seam's final and resume are one
    # boundary and sit together at 3, and step 4 continues past it.
    assert [r["step"] for r in records] == [0, 1, 2, 3, 3, 4, 5]
    # The seam records where it picked up and how much rope it was given.
    assert records[4]["resumed_from_step"] == 2
    assert records[4]["max_steps"] == 2
    assert records[4]["registers_from"] == "final"


def test_registers_survive_the_seam(tmp_path):
    root = tmp_path / "run"
    agent, _ = start(
        root,
        [step(tool_use("set", value="remember this", register_id=10)), *busywork(3)],
        max_steps=2,
    )

    resumed = Agent.resume(
        workspace=Workspace(root), model=FakeModel([]), agent_id=agent.agent_id
    )
    try:
        assert resumed.registers.values[10] == "remember this"
        # and the model is shown that state on its very first resumed step
        resumed.model.script = [finish(resumed)]
        resumed.run()
    finally:
        resumed.bash.close()
    assert "remember this" in resumed.model.requests[0]["messages"][0]["content"]


def test_the_new_budget_counts_only_the_new_steps(tmp_path):
    root = tmp_path / "run"
    agent, _ = start(root, busywork(9), max_steps=3)

    resumed, result = resume(root, busywork(9), max_steps=2)
    assert not result.ok
    # Two more steps were run, not two in total and not the script's nine.
    assert "no valid response in 2 steps" in result.error
    assert len([r for r in resumed.trajectory.read() if r["role"] == "assistant"]) == 5


def test_max_steps_none_means_no_cap(tmp_path):
    root = tmp_path / "run"
    agent, _ = start(root, busywork(3), max_steps=1)

    resumed = Agent.resume(
        workspace=Workspace(root), model=FakeModel([]), agent_id=agent.agent_id,
        overrides={"max_steps": None},
    )
    resumed.model.script = [*busywork(20), finish(resumed)]
    result = resumed.run()

    assert result.ok
    # 21 steps past a budget that was 1 — the cap really is gone.
    assert len([r for r in resumed.trajectory.read() if r["role"] == "assistant"]) == 22


def test_the_stored_config_survives_unless_overridden(tmp_path):
    root = tmp_path / "run"
    agent, _ = start(root, busywork(3), max_steps=1)
    assert agent.config.max_register_length == 200

    resumed = Agent.resume(
        workspace=Workspace(root), model=FakeModel([]), agent_id=agent.agent_id,
        overrides={"max_steps": 5},
    )
    try:
        # Register geometry has to match the values being restored, so it is
        # taken from the trajectory, not from Config's defaults.
        assert resumed.config.max_register_length == 200
        assert resumed.config.max_steps == 5
        assert resumed.instruction == "find the answer"
    finally:
        resumed.bash.close()


def test_a_killed_run_resumes_from_the_last_step(tmp_path):
    """No final record — the last step is re-done rather than state invented."""
    root = tmp_path / "run"
    agent, _ = start(root, busywork(3), max_steps=2)

    path = agent.trajectory.path
    records = [json.loads(line) for line in path.read_text().splitlines()]
    kept = [r for r in records if r["role"] != "final"]
    path.chmod(0o644)
    path.write_text("\n".join(json.dumps(r) for r in kept) + "\n")

    resumed = Agent.resume(
        workspace=Workspace(root), model=FakeModel([]), agent_id=agent.agent_id
    )
    try:
        assert resumed.step == 2
        assert resumed._resume_note["registers_from"] == "last-step"
    finally:
        resumed.bash.close()


def test_resuming_something_that_never_ran_is_refused(tmp_path):
    root = tmp_path / "run"
    Workspace(root)

    with pytest.raises(FileNotFoundError):
        Agent.resume(workspace=Workspace(root), model=FakeModel([]), agent_id="deadbeef")
