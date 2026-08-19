"""0.0.8a's first open question: does transit actually cost anything?

"The scaffold can count it: output tokens spent on literals that already existed
verbatim in a register. If the answer is 'not much', §3 is justified by §4
alone." So it counts it, on every step, and a run can be asked afterwards.
"""

import json

from infinite.agent import MIN_TRANSIT_CHARS, _transit
from infinite.model import ToolCall

from .conftest import build_agent
from test.infinite_0_0_1_simple.fake_model import step, tool_use


def calls(*pairs):
    return [ToolCall(id="t", name=name, input=params) for name, params in pairs]


def test_a_value_copied_out_of_a_register_is_counted():
    before = ["", "", "", "", "", "a/rather/long/path/to/a/file.py", ""]
    measured = _transit(
        before, calls(("bash", {"command": "wc -l a/rather/long/path/to/a/file.py"})),
        shell=True,
    )
    assert measured["retyped"] == len(before[5])
    assert measured["registers"] == [5]
    assert measured["references"] == 0


def test_the_same_value_reached_through_the_shell_is_not():
    before = ["", "", "", "", "", "a/rather/long/path/to/a/file.py", ""]
    measured = _transit(
        before, calls(("bash", {"command": 'wc -l "$R5" > "$REGDIR/6"'})), shell=True
    )
    assert measured["retyped"] == 0
    assert measured["references"] == 2


def test_a_short_value_is_not_counted_because_it_may_be_a_coincidence():
    before = ["True", "", "", "", "", "ok", ""]
    measured = _transit(before, calls(("bash", {"command": "echo ok True"})), shell=True)
    assert measured["retyped"] == 0
    assert MIN_TRANSIT_CHARS > len("True")


def test_a_step_with_no_calls_measures_nothing():
    assert _transit(["x" * 40], [], shell=True) == {
        "generated": 0, "retyped": 0, "registers": [], "references": 0
    }


def test_every_step_records_it(tmp_path):
    agent = build_agent(tmp_path, max_steps=4)
    agent.model.script = [
        step(tool_use("set", value="the/path/that/is/long/enough.py", register_id=6)),
        step(tool_use("bash", command="ls the/path/that/is/long/enough.py")),
        step(tool_use("bash", command="printf '{}' > " + agent.response_path.name)),
    ]
    try:
        agent.run()
    finally:
        agent.bash.close()

    steps = [r for r in agent.trajectory.read() if r.get("role") == "assistant"]
    # Step 1 authored the value, so nothing was retyped; step 2 copied it back
    # out of the register, which is exactly what §3 is for.
    assert steps[0]["transit"]["retyped"] == 0
    assert steps[1]["transit"]["retyped"] == len("the/path/that/is/long/enough.py")
    assert steps[1]["transit"]["registers"] == [6]
    assert all(s["transit"]["generated"] > 0 for s in steps)
