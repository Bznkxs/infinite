"""0.0.8c — the brief is the frame, and the check is what makes it safe.

`spawn` was already a call: fresh context, own budget, own trajectory, a
schema-shaped return, the caller's registers left standing. What it did not do
was behave like one, because it asked the parent to author a precise
instruction out of a lossy context. Knowing what a child will need is knowledge
of the child's subtree, and the parent does not have it.

So the field that asked for prose is replaced by fields that ask for names, and
the reason a parent may be vague about method is that it is exact about
acceptance.
"""

import json

import pytest

from infinite.prompt import build_brief

from .conftest import agent, build_agent, call, run  # noqa: F401
from test.infinite_0_0_1_simple.fake_model import step, text, tool_use


# --- the brief -----------------------------------------------------------
def test_the_brief_is_rendered_from_names_the_parent_already_holds():
    brief = build_brief(
        goal="implement run_step",
        check="python -c 'import step_loop'",
        read=["src/registers.py", "notes/api.md#run_step"],
        write="src/step_loop.py",
    )

    assert brief.index("[Goal]") < brief.index("[Write]") < brief.index("[Check]")
    assert "implement run_step" in brief
    assert "src/step_loop.py" in brief
    assert "python -c 'import step_loop'" in brief
    assert "- src/registers.py" in brief and "- notes/api.md#run_step" in brief


def test_read_is_a_pointer_set_and_says_so():
    """If the parent's lossiness became the child's wall the invariant inverts."""
    brief = build_brief(goal="g", check="true", read=["a.py"])
    assert "Pointers, not limits" in brief
    assert "read anything you need" in brief


def test_a_long_goal_goes_by_reference_and_not_through_a_generation():
    brief = build_brief(goal="rebuild the scaffold", check="true", goal_file="spec.md")
    assert "Read spec.md before anything else." in brief
    # The file's contents are not in the brief: that is 0.0.8a's whole argument.
    assert len(brief) < 400


def test_a_goal_that_is_not_a_sentence_is_refused(agent):
    result = run(agent, "spawn", goal="   ", check="true", return_schema={"type": "object"})
    assert "'goal' must be a non-empty sentence" in result.status


def test_the_check_is_required_and_the_opt_out_has_to_be_typed(agent):
    for spec in agent.tools.specs():
        if spec["name"] == "spawn":
            assert set(spec["input_schema"]["required"]) == {
                "goal", "check", "return_schema"
            }

    result = run(agent, "spawn", goal="do it", check="", return_schema={"type": "object"})
    assert "'check' must be a command" in result.status
    assert 'use "true"' in result.status


# --- the check at the pop -------------------------------------------------
def spawning(goal="write the module", check="true", **extra):
    return tool_use(
        "spawn", goal=goal, check=check, return_schema={"type": "object"},
        register_id=6, **extra,
    )


def spawn_result(agent):
    """The spawn record from the trajectory: register 6 only holds as much as fits."""
    for record in agent.trajectory.read():
        for result in (record.get("observation") or {}).get("results", []):
            if result.get("tool") == "spawn":
                return result
    raise AssertionError("no spawn on record")


def child_writes(agent, payload="{}"):
    """A script entry that makes whichever agent is asked write its response."""

    def entry(request):
        system = request["system"]
        marker = "Write your final response to <"
        path = system.split(marker, 1)[1].split(">", 1)[0]
        return step(tool_use("bash", command=f"printf '%s' '{payload}' > {path}"))

    return entry


def test_a_response_that_fails_its_check_is_not_a_return(tmp_path):
    """The scaffold runs the command; a return that fails it is not a return."""
    parent = build_agent(tmp_path, max_steps=6)
    parent.model.script = [
        step(spawning(check="test -f built.txt")),
        child_writes(parent),   # child step 1: a response, but no built.txt
        step(tool_use("bash", command="touch built.txt")),  # child step 2: the fix
        step(tool_use("bash", command="printf '{}' > " + parent.response_path.name)),
    ]
    result = parent.run()

    assert result.ok
    child = spawn_result(parent)["content"]["response"]
    assert child["content"] == {}
    # Two child steps: the refused one, and the one that made the check pass.
    # The response file stands through the refusal, so fixing the work is
    # enough — the child does not have to write its answer twice.
    assert child["steps"] == 2


def test_the_refusal_names_the_file_that_says_why(tmp_path):
    parent = build_agent(tmp_path, max_steps=6)
    parent.model.script = [
        step(spawning(check="echo 'no module named step_loop' >&2; exit 1", max_steps=2)),
        child_writes(parent),
        step(text("the child gives up")),
        step(tool_use("bash", command="printf '{}' > " + parent.response_path.name)),
    ]
    parent.run()

    child_id = spawn_result(parent)["content"]["trajectory"]
    records = [
        json.loads(line)
        for line in (parent.workspace.root / child_id).read_text().splitlines()
    ]
    checks = [
        r["check"] for r in records if r.get("role") == "assistant" and "check" in r
    ]
    assert checks and checks[0]["exit_code"] == 1
    saved = json.loads((parent.workspace.root / checks[0]["file"]).read_text())
    assert "no module named step_loop" in saved["output"]
    assert saved["passed"] is False


def test_a_passing_check_lets_the_return_through_untouched(tmp_path):
    parent = build_agent(tmp_path, max_steps=6)
    parent.model.script = [
        step(spawning(check="true")),
        child_writes(parent, '{"answer": 42}'),
        step(tool_use("bash", command="printf '{}' > " + parent.response_path.name)),
    ]
    result = parent.run()

    assert result.ok
    assert spawn_result(parent)["content"]["response"]["content"] == {"answer": 42}


def test_the_check_cannot_move_the_session_it_borrowed(agent):
    """A subshell, pinned to the root: a check that `cd`s is still a check."""
    (agent.workspace.root / "sub").mkdir()
    agent.check = "cd sub"
    assert agent._check_failed() is None
    code, output = agent.run_check("pwd")
    assert code == 0 and output.strip().endswith(str(agent.workspace.root))


def test_checks_can_be_turned_off_for_a_comparison(tmp_path):
    built = build_agent(tmp_path, run_checks=False, max_steps=3)
    built.check = "false"
    built.model.script = [child_writes(built)]
    result = built.run()

    assert result.ok  # the check is advice in this configuration
    assert "Your response is refused unless" not in built.system_message()


def test_a_root_can_be_given_a_check_because_a_user_is_a_parent(tmp_path):
    built = build_agent(tmp_path, max_steps=4)
    built.check = "test -f done.txt"
    built.model.script = [
        child_writes(built),
        step(tool_use("bash", command="touch done.txt")),
        child_writes(built),
    ]
    result = built.run()

    # Two steps, not three: the response file is still on disk at step 2, so
    # the check that failed at step 1 is re-run against the fixed workspace and
    # the same response is accepted. A refused return leaves the work standing.
    assert result.ok and result.steps == 2
    assert "Your response is refused unless" in built.system_message()
    assert "test -f done.txt" in built.system_message()


# --- when the check itself is what is broken -----------------------------
def test_a_check_that_cannot_run_says_so_rather_than_blaming_the_work(tmp_path):
    """A parent wrote `python` on a machine that only has `python3`.

    The child then spent its whole budget being told its work was wrong. The
    check is the parent's and the child cannot change it, so the two failures
    have to read differently: 126 and 127 are a shell saying the command does
    not exist, which decides nothing about the work.
    """
    built = build_agent(tmp_path, max_steps=3, max_register_length=208)
    built.check = "definitely-not-a-command --version"
    built.model.script = [child_writes(built), step(text("stuck"))]
    result = built.run()

    assert not result.ok
    assert result.check_failure["exit_code"] == 127
    note = json.loads(result.handoff_path.read_text())
    assert note["last_check"]["command"] == "definitely-not-a-command --version"
    dump = built.model.requests[1]["messages"][0]["content"]
    # And it fits register 0 whole, which is what 0.0.7b's lesson costs here.
    assert "that command does not exist here" in dump
    assert "says nothing about your work" in dump
    assert built.registers.truncated[0] is False


def test_the_parent_is_told_which_check_its_child_died_against(tmp_path):
    parent = build_agent(
        tmp_path, max_steps=8, max_register_length=400,
        max_special_length=600, max_canvas_length=900,
    )
    parent.model.script = [
        step(spawning(check="no-such-binary", max_steps=2)),
        child_writes(parent),
        step(text("the child is stuck on a check it cannot pass")),
        step(tool_use("bash", command="printf '{}' > " + parent.response_path.name)),
    ]
    parent.run()

    record = spawn_result(parent)
    failure = record["content"]["response"]["check_failure"]
    assert failure["exit_code"] == 127 and failure["command"] == "no-such-binary"
    # And in register 0, which at a small geometry is all the parent reads.
    dump = parent.model.requests[-1]["messages"][0]["content"]
    assert "Its last check exited 127: `no-such-binary`" in dump
