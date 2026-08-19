import dataclasses
import json

import pytest

from infinite.agent import Agent
from infinite.config import Config
from infinite.workspace import Workspace

from .fake_model import FakeModel, step, text, tool_use


def response_path_in(system: str) -> str:
    """The agent's own response file, as the system message names it."""
    return system.lower().split("final response to <")[1].split(">")[0]


def make_agent(tmp_path, script, *, instruction="summarize input.txt", **overrides):
    config = Config(
        max_register_length=200, max_special_length=400, max_step_half_length=200, max_canvas_length=800, summary=False, bash_timeout=5.0, step_retry_seconds=0.0, **overrides
    )
    model = FakeModel(script)
    agent = Agent(
        config=config,
        workspace=Workspace(tmp_path / "run"),
        model=model,
        instruction=instruction,
    )
    return agent, model


def write_response(agent, payload):
    escaped = json.dumps(payload).replace("'", "'\\''")
    return tool_use(
        "bash",
        command=f"printf '%s' '{escaped}' > {agent.response_path.name}",
        register_id=5,
    )


def test_finishes_when_the_response_file_appears(tmp_path):
    agent, model = make_agent(tmp_path, [])
    model.script = [
        step(tool_use("load", path=agent.instruction_path.name, start=0, register_id=5)),
        step(write_response(agent, {"summary": "done"})),
    ]
    result = agent.run()

    assert result.ok
    assert result.response == {"summary": "done"}
    assert result.steps == 2


def test_context_is_only_the_register_dump(tmp_path):
    agent, model = make_agent(tmp_path, [])
    model.script = [
        step(tool_use("set", value="note to self", register_id=8)),
        step(write_response(agent, {"ok": True})),
    ]
    agent.run()

    assert len(model.requests) == 2
    for request in model.requests:
        assert len(request["messages"]) == 1  # no conversation history
        assert request["messages"][0]["role"] == "user"
        content = request["messages"][0]["content"]
        # 0.0.7d put the budget above the dump; 0.0.8c put the depth above that.
        assert content.startswith("[Step] depth 0, step ")
        assert "\n[Registers]\n" in content
        assert request["max_tokens"] == agent.config.workspace_tokens
    # State carries over only through the registers.
    assert "note to self" in model.requests[1]["messages"][0]["content"]
    assert "summarize input.txt" not in model.requests[1]["messages"][0]["content"]


def test_instruction_is_only_reachable_through_a_file(tmp_path):
    agent, model = make_agent(tmp_path, [], instruction="the secret instruction")
    model.script = [
        step(tool_use("load", path=agent.instruction_path.name, start=0, register_id=5)),
        step(write_response(agent, {"ok": True})),
    ]
    agent.run()

    assert "the secret instruction" not in model.requests[0]["messages"][0]["content"]
    assert "the secret instruction" in model.requests[1]["messages"][0]["content"]
    assert agent.instruction_path.read_text() == "the secret instruction"


def test_register_zero_points_at_the_last_tool_result_only(tmp_path):
    agent, model = make_agent(tmp_path, [])
    model.script = [
        step(
            tool_use("bash", command="echo one", register_id=5),
            tool_use("bash", command="echo two", register_id=6),
        ),
        step(write_response(agent, {"ok": True})),
    ]
    agent.run()

    results = agent.trajectory.read()[1]["observation"]["results"]
    assert [r["command"] for r in results] == ["echo one", "echo two"]
    # Only the last of the two result files is tracked, in register 0.
    context = model.requests[1]["messages"][0]["content"]
    assert f"last result, special) ---\n{results[-1]['file']}" in context
    assert results[0]["file"] not in context


def test_truncated_generation_sets_the_flag_and_runs_no_tools(tmp_path):
    agent, model = make_agent(tmp_path, [])
    model.script = [
        step(
            text("I will start by"),
            tool_use("bash", command="touch never-ran", register_id=5),
            stop_reason="max_tokens",
        ),
        step(write_response(agent, {"ok": True})),
    ]
    result = agent.run()

    assert result.ok
    assert not (agent.workspace.root / "never-ran").exists()
    truncated_step = agent.trajectory.read()[1]
    assert truncated_step["stop_reason"] == "max_tokens"
    assert "observation" not in truncated_step
    # The flag was True in the context of the step that followed, then cleared.
    assert "--- register 1 (4/200 chars; cut off?, special) ---\nTrue" in model.requests[1]["messages"][0]["content"]
    assert agent.registers.values[1] == "False"


def test_a_step_without_tool_calls_is_nudged(tmp_path):
    agent, model = make_agent(tmp_path, [])
    model.script = [
        step(text("Thinking out loud, no tools.")),
        step(write_response(agent, {"ok": True})),
    ]
    agent.run()

    assert "no tool call" in model.requests[1]["messages"][0]["content"]


def test_gives_up_after_max_steps(tmp_path):
    agent, model = make_agent(tmp_path, [step(text("idle"))] * 5, max_steps=3)
    result = agent.run()

    assert not result.ok
    assert result.steps == 3
    assert "no valid response in 3 steps" in result.error
    assert agent.trajectory.read()[-1]["role"] == "final"


# --- response validation -------------------------------------------------
SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
}


def test_schema_violation_is_reported_and_retried(tmp_path):
    agent, model = make_agent(tmp_path, [])
    agent.return_schema = SCHEMA
    model.script = [
        step(write_response(agent, {"wrong": 1})),
        step(write_response(agent, {"answer": "42"})),
    ]
    result = agent.run()

    assert result.ok and result.response == {"answer": "42"}
    feedback = model.requests[1]["messages"][0]["content"]
    assert "does not match the required schema" in feedback


def test_invalid_json_is_reported(tmp_path):
    agent, model = make_agent(tmp_path, [])
    model.script = [
        step(tool_use("bash", command=f"echo 'not json' > {agent.response_path.name}", register_id=5)),
        step(write_response(agent, {"ok": True})),
    ]
    result = agent.run()

    assert result.ok
    assert "not valid JSON" in model.requests[1]["messages"][0]["content"]


def test_schema_appears_in_the_system_message(tmp_path):
    agent, _ = make_agent(tmp_path, [])
    agent.return_schema = SCHEMA
    assert '"required"' in agent.system_message()
    agent.bash.close()


# --- trajectory ----------------------------------------------------------
def test_trajectory_is_self_contained_and_read_only(tmp_path):
    agent, model = make_agent(tmp_path, [])
    model.script = [
        step(tool_use("set", value="x", register_id=7)),
        step(write_response(agent, {"ok": True})),
    ]
    agent.run()

    records = agent.trajectory.read()
    assert [r["role"] for r in records] == ["user", "assistant", "assistant", "final"]
    assert records[0]["content"] == "summarize input.txt"
    assert records[0]["config"]["max_steps"] == agent.config.max_steps
    assert records[1]["registers_before"] == [""] * 33 or records[1]["registers_before"][1] == "False"
    assert records[3]["response"] == {"ok": True}
    assert agent.trajectory.path.stat().st_mode & 0o222 == 0  # not writable

    session = agent.bash  # the model cannot append through bash
    session._start()
    name = agent.trajectory.path.name
    output = session.execute_command(f"echo hack >> {name}")
    # 0.0.2: the firewall denies the write outright ("operation not permitted"),
    # so the agent cannot chmod its way around the read-only bit either.
    undo = session.execute_command(f"chmod 644 {name}; echo rc=$?")
    session.close()
    assert "denied" in output.lower() or "not permitted" in output.lower()
    assert "rc=0" not in undo
    assert agent.trajectory.path.stat().st_mode & 0o222 == 0
    assert len(agent.trajectory.read()) == 4


# --- spawn ---------------------------------------------------------------
def test_spawn_runs_a_child_with_its_own_registers_and_trajectory(tmp_path):
    agent, model = make_agent(tmp_path, [])
    child_schema = {
        "type": "object",
        "properties": {"count": {"type": "integer"}},
        "required": ["count"],
    }

    def child_writes_response(request):
        # The child sees a fresh register file and its own response path.
        assert request["messages"][0]["content"].count("chars") == 33
        path = response_path_in(request["system"])
        return step(tool_use("bash", command=f"printf '%s' '{{\"count\": 7}}' > {path}", register_id=5))

    model.script = [
        step(
            tool_use(
                "spawn",
                goal="count the lines",
                check="true",
                return_schema=child_schema,
                register_id=9,
            )
        ),
        child_writes_response,
        step(write_response(agent, {"ok": True})),
    ]
    result = agent.run()

    assert result.ok
    stored = json.loads(agent.registers.values[9])
    assert stored["response"]["content"] == {"count": 7}
    assert (agent.workspace.root / stored["trajectory"]).exists()
    # requests: parent step 1, child step 1, parent step 2.
    assert f"last result, special) ---\n{stored['response']['file']}" in model.requests[2]["messages"][0]["content"]

    spawn_record = agent.trajectory.read()[1]["observation"]["results"][0]
    assert spawn_record["goal"] == "count the lines"
    # 0.0.8c: the parent names things and the scaffold renders the brief, so
    # what the child is given is not a string the parent generated.
    assert "[Goal]\ncount the lines" in spawn_record["brief"]
    assert spawn_record["content"]["response"]["content"] == {"count": 7}


def test_spawn_failure_becomes_an_error_message(tmp_path):
    # Five steps for the parent and two allocated to the child, because since
    # 0.0.8c the child's are the parent's: at max_steps=2 the spawn would take
    # the whole run.
    agent, model = make_agent(tmp_path, [], max_steps=5)
    model.script = [
        step(
            tool_use(
                "spawn", goal="do it", check="true", max_steps=2,
                return_schema={"type": "object"}, register_id=9,
            )
        ),
        step(text("child idles")),
        step(text("child idles")),
        step(write_response(agent, {"ok": True})),
    ]
    result = agent.run()

    assert result.ok
    # The payload is longer than register 9 holds, so it is read where it is
    # kept whole; the register has as much of it as fits, which is the rule.
    stored = agent.trajectory.read()[1]["observation"]["results"][0]["content"]
    assert "no valid response" in stored["response"]["error"]
    assert agent.registers.values[9] == json.dumps(
        stored, ensure_ascii=False, indent=2
    )[: agent.registers.limit(9)]
    # The parent sees the failure in register 0, and the handoff file first —
    # what the child had established, and how to continue it.
    dump = model.requests[3]["messages"][0]["content"]
    assert "error: sub-agent" in dump and "resume(agent_id=" in dump
    handoff = agent.workspace.root / stored["response"]["handoff"]
    assert handoff.exists()
    note = json.loads(handoff.read_text())
    assert note["steps"] == 2 and note["target"] == "" and "no valid response" in note["error"]


def test_an_agent_at_the_depth_floor_is_not_offered_spawn(tmp_path):
    """A tool that cannot succeed is not in the list — and says why if asked."""
    agent, model = make_agent(tmp_path, [], max_depth=0)
    model.script = [
        step(
            tool_use(
                "spawn", goal="go deeper", check="true",
                return_schema={"type": "object"}, register_id=9,
            )
        ),
        step(write_response(agent, {"ok": True})),
    ]
    agent.run()

    assert [t["name"] for t in agent.tools.specs()] == [
        "bash", "load", "set", "set_target", "lookup",
    ]
    error = agent.trajectory.read()[1]["observation"]["results"][0]["error"]
    # 0.0.8c §6: the refusal names whose allowance ran out, not a constant the
    # scaffold picked. Nobody set this one but the run, so it says so.
    assert "no `spawn` at depth 0" in error and "this run allows depth 0" in error


def test_the_refusal_says_a_parent_allowed_the_depth_when_a_parent_did(tmp_path):
    agent, _ = make_agent(tmp_path, [], max_depth=None)
    child = Agent(
        config=dataclasses.replace(agent.config, max_depth=1),
        workspace=agent.workspace,
        model=agent.model,
        instruction="a leaf",
        depth=1,
        depth_from_parent=True,
    )
    assert child.can_spawn is False
    assert "your parent allowed depth 1" in child.depth_refusal()
    child.bash.close()


def test_no_depth_ceiling_by_default(tmp_path):
    """0.0.8c §6: the constant is removed, not retuned."""
    agent, _ = make_agent(tmp_path, [], max_depth=None)
    deep = Agent(
        config=agent.config,
        workspace=agent.workspace,
        model=agent.model,
        instruction="far down",
        depth=9,
    )
    assert deep.can_spawn is True
    deep.bash.close()


def test_a_child_at_the_floor_loses_spawn_but_its_parent_keeps_it(tmp_path):
    agent, _ = make_agent(tmp_path, [], max_depth=1)

    assert agent.can_spawn is True
    assert "spawn" in [t["name"] for t in agent.tools.specs()]
    child = Agent(
        config=agent.config,
        workspace=agent.workspace,
        model=agent.model,
        instruction="a leaf",
        depth=1,
    )
    assert child.can_spawn is False
    assert "spawn" not in [t["name"] for t in child.tools.specs()]


@pytest.mark.parametrize("bad", [0, 1, 33, "2"])
def test_no_tool_may_target_a_special_or_missing_register(tmp_path, bad):
    agent, model = make_agent(tmp_path, [])
    model.script = [
        step(tool_use("set", value="x", register_id=bad)),
        step(write_response(agent, {"ok": True})),
    ]
    agent.run()

    error = agent.trajectory.read()[1]["observation"]["results"][0]["error"]
    assert error.startswith("error:")


class FlakyModel:
    """Fails the first `fail` generation calls, then replays a script."""

    def __init__(self, script, fail=0, exc=None):
        self.inner = FakeModel(script)
        self.fail = fail
        self.exc = exc or RuntimeError("Overloaded")
        self.attempts = 0

    def generate(self, **kwargs):
        self.attempts += 1
        if self.attempts <= self.fail:
            raise self.exc
        return self.inner.generate(**kwargs)


def flaky_agent(tmp_path, model, **overrides):
    return Agent(
        config=Config(summary=False, bash_timeout=5.0, step_retry_backoff=0.0, **overrides),
        workspace=Workspace(tmp_path / "run"),
        model=model,
        instruction="do the thing",
    )


def test_a_transient_generation_failure_is_retried_not_fatal(tmp_path):
    """0.0.7b lost a whole run to one `overloaded_error` on a step."""
    agent = None
    model = FlakyModel([], fail=2)
    agent = flaky_agent(tmp_path, model)
    model.inner.script = [step(write_response(agent, {"ok": True}))]

    result = agent.run()

    assert result.ok is True and result.response == {"ok": True}
    assert model.attempts == 3  # two failures, then the real call
    # The failed attempts are not steps: nothing was generated, so nothing is recorded.
    assert [r["step"] for r in agent.trajectory.read() if r.get("role") == "assistant"] == [1]


def test_generation_that_keeps_failing_ends_the_segment_resumably(tmp_path):
    model = FlakyModel([], fail=99)
    agent = flaky_agent(tmp_path, model, step_retry_seconds=0.0)

    result = agent.run()

    assert result.ok is False
    assert "generation failed at step 1" in result.error and "Overloaded" in result.error
    assert "gave up after 1 attempts" in result.error
    assert model.attempts == 1  # no patience budget: one try, then a clean stop
    # A `final` record closes the segment, which is what makes --resume possible.
    final = [r for r in agent.trajectory.read() if r.get("role") == "final"]
    assert len(final) == 1 and final[0]["ok"] is False
    assert final[0]["registers"], "the segment's registers are on record"


def test_a_later_step_can_fail_without_losing_the_earlier_ones(tmp_path):
    """The failed step is not recorded; everything before it is."""

    class OneGoodStep:
        def __init__(self):
            self.calls = 0
            self.inner = FakeModel([])

        def generate(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return step(tool_use("set", value="kept", register_id=9))
            raise RuntimeError("Overloaded")

    model = OneGoodStep()
    agent = flaky_agent(tmp_path, model, step_retry_seconds=0.0)
    result = agent.run()

    assert result.ok is False and "generation failed at step 2" in result.error
    assert agent.registers.values[9] == "kept"
    steps = [r for r in agent.trajectory.read() if r.get("role") == "assistant"]
    assert [r["step"] for r in steps] == [1]
    assert model.calls == 2  # the good step, then one failed attempt at step 2


# --- a cut-off generation ------------------------------------------------
def test_a_cut_off_generation_runs_the_calls_it_had_finished(tmp_path):
    """A call block exists only because the one before it finished.

    0.0.1 dropped every call of a cut-off generation, which was right when a
    step could generate 8192 tokens. At 0.0.7g's 1920 a quarter of generations
    are cut off, and across three runs that rule discarded 56 finished calls.
    """
    agent, model = make_agent(tmp_path, [])
    model.script = [
        step(
            tool_use("bash", command="printf 'one\n' > log.txt", register_id=5),
            tool_use("bash", command="printf 'two\n' >> log.txt", register_id=6),
            tool_use("bash", command="printf 'three\n' >> log.tx", register_id=7),
            stop_reason="max_tokens",
        ),
        step(write_response(agent, {"ok": True})),
    ]
    agent.run()

    # The first two ran; the third, which the cut landed in, did not.
    assert (agent.workspace.root / "log.txt").read_text() == "one\ntwo\n"
    assert not (agent.workspace.root / "log.tx").exists()
    assert agent.registers.truncated[1] is False and agent.registers.values[1] == "False"

    record = agent.trajectory.read()[1]
    assert record["stop_reason"] == "max_tokens"
    assert len(record["observation"]["results"]) == 2
    # And register 0 says what happened, where the agent always reads.
    dump = model.requests[1]["messages"][0]["content"]
    assert "cut off at the token limit" in dump
    assert "The 2 call(s) before it did run." in dump


def test_a_cut_off_generation_with_one_call_still_runs_nothing(tmp_path):
    """The only call is the one the cut landed in, so nothing is safe to run."""
    agent, model = make_agent(tmp_path, [])
    model.script = [
        step(
            tool_use("bash", command="printf 'x' > never.txt", register_id=5),
            stop_reason="max_tokens",
        ),
        step(write_response(agent, {"ok": True})),
    ]
    agent.run()

    assert not (agent.workspace.root / "never.txt").exists()
    assert "observation" not in agent.trajectory.read()[1]
    dump = model.requests[1]["messages"][0]["content"]
    assert "cut off at the token limit" in dump
    assert "did run" not in dump  # nothing to report as having run
