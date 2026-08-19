"""0.0.8a §4 — the destination register is eating the working set.

Every tool call used to name a destination and the write was unconditional. At
0.0.7g's geometry there are five free registers, so a five-call step — which is
precisely what 0.0.7e's batching advice asks for — overwrote all five. The
scaffold told the agent to batch and charged it its entire memory for complying.

7.2 asked for pinned registers. What it needed was not something added but
something removed: any register the agent declines to name is pinned by
construction, and the agent decides which.
"""

import json

from infinite.config import Config

from .conftest import agent, build_agent, run  # noqa: F401


def test_bash_without_a_destination_keeps_the_register_it_did_not_name(agent):
    agent.registers.store(6, "a working set I am not finished with")
    result = run(agent, "bash", command="echo noise")

    assert agent.registers.values[6] == "a working set I am not finished with"
    # The status still lands, so the result file is still reachable.
    assert result.status.startswith("tool_output/")
    assert json.loads((agent.workspace.root / result.status).read_text())["output"].strip() == "noise"


def test_load_without_a_destination_still_reports_the_length(agent):
    (agent.workspace.root / "big.txt").write_text("x" * 5000)
    result = run(agent, "load", path="big.txt", start=0)

    assert "length=5000" in result.status
    assert result.register_id is None
    assert all(v == "" for i, v in enumerate(agent.registers.values) if i != 0)


def test_a_five_call_step_can_leave_every_register_standing(agent):
    """The case 0.0.8a §4 is about, in one step."""
    for i in range(5, 10):
        agent.registers.store(i, f"fact {i}")
    before = agent.registers.snapshot()

    for command in ("echo a", "echo b", "echo c", "echo d", "echo e"):
        run(agent, "bash", command=command)

    assert agent.registers.snapshot()[5:] == before[5:]


def test_a_named_destination_still_lands(agent):
    run(agent, "bash", command="echo landed", register_id=7)
    assert agent.registers.values[7].strip() == "landed"


def test_set_still_needs_a_register_because_that_is_what_it_does(agent):
    result = run(agent, "set", value="a plan")
    assert "'register_id' is required by `set`" in result.status


def test_a_named_but_impossible_destination_is_still_refused(agent):
    result = run(agent, "bash", command="touch should-not-exist", register_id=0)
    assert "special register" in result.status
    assert not (agent.workspace.root / "should-not-exist").exists()


def test_the_schemas_say_the_destination_is_optional(agent):
    for spec in agent.tools.specs():
        required = spec["input_schema"]["required"]
        if spec["name"] == "set":
            assert "register_id" in required  # the one tool whose job it is
        else:
            assert "register_id" not in required, spec["name"]


def test_the_target_is_advertised_at_its_own_length_not_the_wide_one(tmp_path):
    """A live 0.0.8 run had `set_target` rejected twice for the same reason.

    `max_target_length` splits register 2 from register 4 — 704 against 1,536 at
    the 0.0.8 geometry — and both the schema and the system message were still
    quoting the shared number. `set_target` rejects rather than truncates, so an
    agent told the wrong limit loses the whole write and writes it again.
    """
    built = build_agent(
        tmp_path, max_target_length=200, max_special_length=240, summary=True
    )
    try:
        message = built.system_message()
        assert "2 holds 200, 4 holds 240" in message
        spec = next(s for s in built.tools.specs() if s["name"] == "set_target")
        assert spec["input_schema"]["properties"]["content"]["description"] == (
            "At most 200 chars."
        )
    finally:
        built.bash.close()


def test_a_shared_limit_is_still_said_once(tmp_path):
    built = build_agent(tmp_path, summary=True)  # no max_target_length: they share
    try:
        assert "2 and 4 hold 240" in built.system_message()
    finally:
        built.bash.close()
