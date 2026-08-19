"""The special registers: the target, and the automatic record of the last step.

The summary in register 4 has its own file; here it is off, so these tests see
the registers a run keeps for itself.
"""

import json

import pytest

from infinite.agent import CUT_OFF_ACTION, NO_ACTION, Agent
from infinite.config import STEP_REGISTER, SUMMARY_REGISTER, TARGET_REGISTER, Config
from infinite.model import ToolCall
from infinite.workspace import Workspace

from .fake_model import FakeModel, step, text, tool_use

FIRST_FREE = 5


def make_agent(tmp_path, script, **overrides):
    config = Config(
        max_register_length=200, max_special_length=400, max_step_half_length=200, max_canvas_length=800, summary=False,
        bash_timeout=5.0, **overrides,
    )
    model = FakeModel(script)
    agent = Agent(
        config=config,
        workspace=Workspace(tmp_path / "run"),
        model=model,
        instruction="do the thing",
    )
    return agent, model


def write_response(agent, payload=None):
    escaped = json.dumps(payload or {"ok": True}).replace("'", "'\\''")
    return tool_use(
        "bash",
        command=f"printf '%s' '{escaped}' > {agent.response_path.name}",
        register_id=FIRST_FREE,
    )


def thinking(value):
    return {"type": "thinking", "thinking": value, "signature": "sig"}


def step_register(context):
    """Register 3 as a step actually saw it, pulled back out of the dump."""
    body = context.split("--- register 3 ", 1)[1].split("\n", 1)[1]
    return body.split("\n--- register 4 ", 1)[0]


# --- set_target --------------------------------------------------------
def test_set_target_writes_the_target_register(tmp_path):
    agent, model = make_agent(tmp_path, [])
    model.script = [
        step(tool_use("set_target", content="find the gammas, then count them")),
        step(write_response(agent)),
    ]
    agent.run()

    assert agent.registers.values[TARGET_REGISTER] == "find the gammas, then count them"
    context = model.requests[1]["messages"][0]["content"]
    assert "--- register 2 (32/400 chars; target, special) ---" in context
    assert "find the gammas, then count them" in context


def test_the_target_survives_every_later_step(tmp_path):
    agent, model = make_agent(tmp_path, [])
    model.script = [
        step(tool_use("set_target", content="THE PLAN")),
        step(tool_use("set", value="noise", register_id=FIRST_FREE)),
        step(tool_use("bash", command="echo more noise", register_id=FIRST_FREE)),
        step(write_response(agent)),
    ]
    agent.run()

    # Nothing but set_target touches it, so it is still there three steps later.
    assert agent.registers.values[TARGET_REGISTER] == "THE PLAN"
    assert "THE PLAN" in model.requests[3]["messages"][0]["content"]


def test_set_target_replaces_rather_than_appends(tmp_path):
    agent, model = make_agent(tmp_path, [])
    model.script = [
        step(tool_use("set_target", content="first plan")),
        step(tool_use("set_target", content="second plan")),
        step(write_response(agent)),
    ]
    agent.run()

    assert agent.registers.values[TARGET_REGISTER] == "second plan"


def test_set_target_rejects_a_non_string(tmp_path):
    agent, _ = make_agent(tmp_path, [])
    try:
        result = agent.tools.execute(
            ToolCall(id="t", name="set_target", input={"content": {"plan": 1}})
        )
    finally:
        agent.bash.close()

    assert "'content' must be a string" in result.status
    assert agent.registers.values[TARGET_REGISTER] == ""


def test_set_target_rejects_an_oversized_value_and_changes_nothing(tmp_path):
    agent, _ = make_agent(tmp_path, [])
    try:
        agent.tools.execute(ToolCall(id="t", name="set_target", input={"content": "keep me"}))
        result = agent.tools.execute(
            ToolCall(id="t", name="set_target", input={"content": "x" * 500})
        )
    finally:
        agent.bash.close()

    assert "unchanged" in result.status
    assert agent.registers.values[TARGET_REGISTER] == "keep me"


def test_no_other_tool_can_write_the_special_registers(tmp_path):
    agent, _ = make_agent(tmp_path, [])
    try:
        for register_id in (TARGET_REGISTER, STEP_REGISTER, SUMMARY_REGISTER):
            result = agent.tools.execute(
                ToolCall(id="t", name="set", input={"value": "mine", "register_id": register_id})
            )
            assert "special register" in result.status
            assert agent.registers.values[register_id] == ""
    finally:
        agent.bash.close()


# --- register 3: the last step, in one register -------------------------
def test_thinking_and_action_are_handed_to_the_next_step(tmp_path):
    agent, model = make_agent(tmp_path, [])
    model.script = [
        step(
            thinking("I should look at the corpus first."),
            tool_use("bash", command="wc -l corpus.txt", register_id=FIRST_FREE),
        ),
        step(write_response(agent)),
    ]
    agent.run()

    # The step that produced them could not see them; the next one can.
    assert "I should look at the corpus first." not in model.requests[0]["messages"][0]["content"]
    context = model.requests[1]["messages"][0]["content"]
    assert "I should look at the corpus first." in context
    assert 'bash({"command": "wc -l corpus.txt", "register_id": 5})' in context
    # One register, two labelled halves, in that order.
    assert step_register(context) == (
        "[thinking]\nI should look at the corpus first.\n"
        '[action]\nbash({"command": "wc -l corpus.txt", "register_id": 5})'
    )
    assert agent.registers.values[SUMMARY_REGISTER] == ""  # summaries are off here


def test_it_describes_only_the_step_immediately_before(tmp_path):
    agent, model = make_agent(tmp_path, [])
    model.script = [
        step(thinking("first thought"), tool_use("set", value="a", register_id=FIRST_FREE)),
        step(thinking("second thought"), tool_use("set", value="b", register_id=FIRST_FREE)),
        step(write_response(agent)),
    ]
    agent.run()

    context = model.requests[2]["messages"][0]["content"]
    assert "second thought" in context
    assert "first thought" not in context  # overwritten, not accumulated


def test_prose_without_thinking_still_reaches_the_next_step(tmp_path):
    """With thinking off there are no thinking blocks, so text carries the step."""
    agent, model = make_agent(tmp_path, [], thinking=False)
    model.script = [
        step(text("Plan: grep, then count."), tool_use("set", value="x", register_id=FIRST_FREE)),
        step(write_response(agent)),
    ]
    agent.run()

    assert "Plan: grep, then count." in model.requests[1]["messages"][0]["content"]


def test_thinking_and_prose_are_both_kept(tmp_path):
    agent, model = make_agent(tmp_path, [])
    model.script = [
        step(thinking("reasoning"), text("narration"), tool_use("set", value="x", register_id=FIRST_FREE)),
        step(write_response(agent)),
    ]
    agent.run()

    assert "reasoning\nnarration" in model.requests[1]["messages"][0]["content"]


def test_every_call_of_a_multi_call_step_is_recorded(tmp_path):
    agent, model = make_agent(tmp_path, [])
    model.script = [
        step(
            tool_use("bash", command="echo one", register_id=FIRST_FREE),
            tool_use("bash", command="echo two", register_id=FIRST_FREE + 1),
        ),
        step(write_response(agent)),
    ]
    agent.run()

    context = model.requests[1]["messages"][0]["content"]
    assert 'bash({"command": "echo one", "register_id": 5})' in context
    assert 'bash({"command": "echo two", "register_id": 6})' in context


def test_a_step_with_no_tool_call_says_so(tmp_path):
    agent, model = make_agent(tmp_path, [])
    model.script = [step(text("just thinking")), step(write_response(agent))]
    agent.run()

    assert model.requests[1]["messages"][0]["content"].count(NO_ACTION) == 1


def test_a_cut_off_step_keeps_its_thinking_but_reports_no_action(tmp_path):
    agent, model = make_agent(tmp_path, [])
    model.script = [
        step(
            thinking("I had got as far as this"),
            tool_use("bash", command="touch never-ran", register_id=FIRST_FREE),
            stop_reason="max_tokens",
        ),
        step(write_response(agent)),
    ]
    agent.run()

    context = model.requests[1]["messages"][0]["content"]
    # The work in progress survives, and nothing claims the call happened.
    assert "I had got as far as this" in context
    assert CUT_OFF_ACTION in context
    assert "never-ran" not in context
    assert not (agent.workspace.root / "never-ran").exists()


def test_an_overlong_generation_is_truncated_not_dropped(tmp_path):
    agent, model = make_agent(tmp_path, [])
    model.script = [
        step(thinking("y" * 900), tool_use("set", value="x", register_id=FIRST_FREE)),
        step(write_response(agent)),
    ]
    agent.run()

    context = model.requests[1]["messages"][0]["content"]
    assert "; last step, special, truncated) ---" in context
    assert "y" * 200 in context  # the head survives, the tail is gone
    assert "y" * 201 not in context


def test_a_long_deliberation_cannot_crowd_out_the_action(tmp_path):
    """The halves get their own budgets, so the action is never what is lost."""
    agent, model = make_agent(tmp_path, [])
    model.script = [
        step(thinking("y" * 5000), tool_use("set", value="keep-me", register_id=FIRST_FREE)),
        step(write_response(agent)),
    ]
    agent.run()

    context = model.requests[1]["messages"][0]["content"]
    value = step_register(context)
    assert value.count("y") == 200
    assert value.endswith('[action]\nset({"value": "keep-me", "register_id": 5})')
    assert "; last step, special, truncated) ---" in context


def test_the_last_step_register_survives_a_resume(tmp_path):
    agent, model = make_agent(tmp_path, [], max_steps=1)
    model.script = [step(thinking("mid-task reasoning"), tool_use("set", value="x", register_id=FIRST_FREE))]
    agent.run()

    resumed = Agent.resume(
        workspace=Workspace(tmp_path / "run"), model=FakeModel([]), agent_id=agent.agent_id,
        overrides={"max_steps": 1},
    )
    resumed.model.script = [write_response_step(resumed)]
    resumed.run()

    assert "mid-task reasoning" in resumed.model.requests[0]["messages"][0]["content"]


def write_response_step(agent):
    return step(write_response(agent))


# --- resuming across a layout change -----------------------------------
def rewritten_run(tmp_path, config_edits, register_edits=()):
    """A finished run, with its recorded layout edited to an older one."""
    agent, model = make_agent(tmp_path, [], max_steps=1)
    model.script = [step(tool_use("set", value="my note", register_id=FIRST_FREE))]
    agent.run()

    path = agent.trajectory.path
    records = [json.loads(line) for line in path.read_text().splitlines()]
    for key, value in config_edits.items():
        if value is None:
            records[0]["config"].pop(key, None)
        else:
            records[0]["config"][key] = value
    for record in records:
        if record["role"] in ("assistant", "final"):
            values = record.get("registers_before") or record.get("registers")
            if values:
                for register_id, value in register_edits:
                    values[register_id] = value
    path.chmod(0o644)
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    return agent.agent_id


def older_layout_run(tmp_path):
    """A trajectory recorded when 2-4 were the agent's own scratch registers."""
    return rewritten_run(
        tmp_path,
        {
            "num_special_registers": 2,
            "max_special_length": None,
            "max_step_half_length": None,
            "register_layout": None,
        },
        [(TARGET_REGISTER, "an old scratch note")],
    )


def layout_3_run(tmp_path):
    """A 0.0.3 trajectory: five specials, but 3 and 4 were thinking and action."""
    return rewritten_run(
        tmp_path,
        {"register_layout": None},
        [(SUMMARY_REGISTER, 'set({"value": "my note", "register_id": 5})')],
    )


def test_resuming_across_a_layout_change_is_refused(tmp_path):
    agent_id = older_layout_run(tmp_path)

    with pytest.raises(ValueError, match="2 special registers"):
        Agent.resume(
            workspace=Workspace(tmp_path / "run"), model=FakeModel([]), agent_id=agent_id
        )


def test_the_0_0_3_layout_is_refused_too(tmp_path):
    """Same five registers, different meanings — the count cannot tell them apart."""
    agent_id = layout_3_run(tmp_path)

    with pytest.raises(ValueError, match="layout unnumbered"):
        Agent.resume(
            workspace=Workspace(tmp_path / "run"), model=FakeModel([]), agent_id=agent_id
        )


def test_the_layout_change_can_be_accepted_explicitly(tmp_path):
    agent_id = older_layout_run(tmp_path)

    resumed = Agent.resume(
        workspace=Workspace(tmp_path / "run"), model=FakeModel([]), agent_id=agent_id,
        overrides={"max_steps": 1}, upgrade_registers=True,
    )
    try:
        assert resumed.config.num_special_registers == 5
        assert resumed.config.register_layout == 4
        # The old scratch value is kept, but it is the target now.
        assert resumed.registers.values[TARGET_REGISTER] == "an old scratch note"
        relayout = resumed._resume_note["registers_relayout"]
        assert relayout["num_special_registers"] == [2, 5]
        # clamped into the run's own geometry, not this scaffold's default
        assert relayout["max_special_length"] == 800 == resumed.config.max_canvas_length
        assert relayout["max_step_half_length"] == (800 - 21) // 2
    finally:
        resumed.bash.close()


def test_upgrading_clears_the_summary_register(tmp_path):
    """Register 4 held an action, and an action is not a summary of anything."""
    agent_id = layout_3_run(tmp_path)

    resumed = Agent.resume(
        workspace=Workspace(tmp_path / "run"), model=FakeModel([]), agent_id=agent_id,
        overrides={"max_steps": 1}, upgrade_registers=True,
    )
    try:
        assert resumed.registers.values[SUMMARY_REGISTER] == ""
        assert resumed._resume_note["registers_relayout"]["summary_register"] == "cleared"
    finally:
        resumed.bash.close()


def test_the_relayout_is_recorded_in_the_trajectory(tmp_path):
    agent_id = older_layout_run(tmp_path)

    resumed = Agent.resume(
        workspace=Workspace(tmp_path / "run"), model=FakeModel([]), agent_id=agent_id,
        overrides={"max_steps": 1}, upgrade_registers=True,
    )
    resumed.model.script = [write_response_step(resumed)]
    resumed.run()

    seam = next(r for r in resumed.trajectory.read() if r["role"] == "resume")
    assert seam["registers_relayout"]["num_special_registers"] == [2, 5]
