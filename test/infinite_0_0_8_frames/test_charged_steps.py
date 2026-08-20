"""0.0.8c §5 — a child's steps debit the parent's remaining budget.

0.0.7j made the price of a child *visible*: the dump says how many steps the run
has spent across how many agents. It did not make it *charged*. A parent's own
counter still moved by one however many steps its child burned, so from where
the parent sat, commissioning a hundred-step digest and running one `grep` cost
the same — and a run has already spent 124 steps on a digest and a checklist
under exactly those incentives.

Then `max_steps` stops being a wish and becomes an allocation, and unbounded
depth becomes safe: a chain that never bottoms out still runs out of budget.
"""

import json

from .conftest import agent, build_agent, run  # noqa: F401
from test.infinite_0_0_1_simple.fake_model import step, text, tool_use


def spawning(register_id=6, **extra):
    return tool_use(
        "spawn", goal="a piece of it", check="true",
        return_schema={"type": "object"}, register_id=register_id, **extra,
    )


def idle(_request=None):
    return step(text("the child works and does not answer"))


def test_what_a_child_spends_comes_out_of_its_parent(tmp_path):
    parent = build_agent(tmp_path, max_steps=10)
    parent.model.script = [
        step(spawning(max_steps=3)),
        idle(), idle(), idle(),
        step(tool_use("bash", command="printf '{}' > " + parent.response_path.name)),
    ]
    result = parent.run()

    assert result.ok
    assert parent.charged == 3
    # Two steps of its own and three of its child's: five of ten.
    assert result.segment_steps == 2 and result.cost == 5


def test_a_parent_that_spends_its_run_on_children_runs_out(tmp_path):
    """The incentive, made real: a fan-out you cannot afford ends the segment."""
    # `stall_surcharge=0`: this measures charging, and an idling FakeModel
    # child is a stand-in for a busy one rather than a livelock. Leaving
    # 0.0.8d's price on would measure two mechanisms at once — §6's rule.
    parent = build_agent(tmp_path, max_steps=5, stall_surcharge=0)
    parent.model.script = [step(spawning(max_steps=4))] + [idle()] * 4
    result = parent.run()

    assert not result.ok
    assert parent.charged == 4
    # One step of its own plus four charged is the whole allowance, so there is
    # no second step in which to write a response.
    assert result.segment_steps == 1 and result.cost == 5


def test_an_allocation_larger_than_what_is_left_is_cut_to_it(tmp_path):
    parent = build_agent(tmp_path, max_steps=4)
    parent.model.script = [step(spawning(max_steps=100))] + [idle()] * 4
    parent.run()

    record = next(
        r for r in parent.trajectory.read()
        if r.get("role") == "assistant"
    )["observation"]["results"][0]
    assert record["max_steps"] == 3  # four, less the step doing the spawning


def test_a_parent_with_nothing_left_cannot_commission_anything(tmp_path):
    parent = build_agent(tmp_path, max_steps=1)
    parent.model.script = [step(spawning())]
    parent.run()

    error = parent.trajectory.read()[1]["observation"]["results"][0]["error"]
    assert "no steps left to give a child" in error


def test_the_debit_is_transitive(tmp_path):
    """A grandchild's steps reach the root, because each frame charges its own."""
    root = build_agent(tmp_path, max_steps=12)
    root.model.script = [
        step(spawning(max_steps=6)),                    # root step 1
        step(spawning(register_id=5, max_steps=2)),     # child step 1: a grandchild
        idle(), idle(),                                 # the grandchild's two steps
        idle(),                                         # child step 2, then it runs out
        idle(),
        step(tool_use("bash", command="printf '{}' > " + root.response_path.name)),
    ]
    result = root.run()

    assert result.ok
    # The child spent 4 steps of its own and was charged 2 for the grandchild;
    # all six land on the root, on top of the one step the root spent itself.
    assert root.charged == 6
    assert result.segment_steps == 1 and result.cost == 7


def test_the_dump_says_what_went_to_children(tmp_path):
    parent = build_agent(tmp_path, max_steps=10)
    parent.model.script = [
        step(spawning(max_steps=3)),
        idle(), idle(), idle(),
        step(tool_use("bash", command="printf '{}' > " + parent.response_path.name)),
    ]
    parent.run()

    second = [
        r for r in parent.trajectory.read() if r.get("role") == "assistant"
    ][1]["model_input"]["messages"][0]["content"]
    assert (
        "[Step] depth 0, step 2 of 10 (6 left, including this one; "
        "3 of your budget went to children)"
    ) in second


def test_charging_can_be_turned_off_to_measure_what_it_buys(tmp_path):
    """0.0.7j's accounting: the price is shown, and not charged."""
    # `stall_surcharge=0`: this measures charging, and an idling FakeModel
    # child is a stand-in for a busy one rather than a livelock. Leaving
    # 0.0.8d's price on would measure two mechanisms at once — §6's rule.
    parent = build_agent(tmp_path, max_steps=5, charge_children=False, stall_surcharge=0)
    parent.model.script = [
        step(spawning(max_steps=4)),
        idle(), idle(), idle(), idle(),
        step(tool_use("bash", command="printf '{}' > " + parent.response_path.name)),
    ]
    result = parent.run()

    assert result.ok
    assert parent.charged == 0
    assert result.segment_steps == 2


def test_a_resumed_child_is_charged_too(tmp_path):
    parent = build_agent(tmp_path, max_steps=12)
    parent.model.script = [
        step(spawning(max_steps=2)),
        idle(), idle(),
        step(tool_use("resume", agent_id="PLACEHOLDER", max_steps=2, register_id=7)),
        idle(), idle(),
        step(tool_use("bash", command="printf '{}' > " + parent.response_path.name)),
    ]
    real_spawn, real_resume = parent.tools._spawn, parent.tools._resume
    seen = {}

    def spawning_(call):
        result = real_spawn(call)
        seen["id"] = result.record["agent_id"]
        return result

    def resuming(call):
        call.input["agent_id"] = seen["id"]
        return real_resume(call)

    parent.tools._spawn = spawning_
    parent.tools._resume = resuming
    result = parent.run()

    assert result.ok
    assert parent.charged == 4  # two segments of the one child
    assert result.cost == 7
