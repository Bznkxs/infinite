"""0.0.8c §6 — the scaffold should stop having an opinion about depth.

`max_depth` was 1, and hard: the root fanned out to leaves and no further, and
the refusal named a number the scaffold chose. 0.0.7a set it there because deep
trees serialise and every level paid to brief the next; the second is what the
structured brief is for, and neither is a reason for the *scaffold* to pick the
number. What bounds a tree instead is that its steps are charged.

A user is a parent, though, and should get any control a parent has — so the
ceiling stays settable, and a parent may allow one for its own subtree.
"""

import dataclasses

from infinite.agent import Agent
from infinite.config import Config

from .conftest import agent, build_agent, run  # noqa: F401
from test.infinite_0_0_1_simple.fake_model import step, text, tool_use


def test_the_default_is_no_ceiling_at_all(tmp_path):
    assert Config().max_depth is None
    built = build_agent(tmp_path)
    try:
        deep = Agent(
            config=built.config, workspace=built.workspace, model=built.model,
            instruction="far down", depth=17,
        )
        assert deep.can_spawn is True
        assert "spawn" in [t["name"] for t in deep.tools.specs()]
        deep.bash.close()
    finally:
        built.bash.close()


def test_the_agent_can_see_how_deep_it_is(tmp_path):
    """It could not see it at all before; now it is a field on the [Step] line."""
    built = build_agent(tmp_path, max_steps=2)
    built.model.script = [
        step(tool_use("bash", command="printf '{}' > " + built.response_path.name))
    ]
    built.run()

    dump = built.model.requests[0]["messages"][0]["content"]
    assert dump.startswith("[Step] depth 0, step 1 of 2")


def test_a_child_sees_its_own_depth_and_not_its_parents(tmp_path):
    parent = build_agent(tmp_path, max_steps=6)
    parent.model.script = [
        step(
            tool_use(
                "spawn", goal="go one down", check="true",
                return_schema={"type": "object"}, max_steps=1, register_id=6,
            )
        ),
        step(text("the child idles")),
        step(tool_use("bash", command="printf '{}' > " + parent.response_path.name)),
    ]
    parent.run()

    dumps = [r["messages"][0]["content"] for r in parent.model.requests]
    assert dumps[0].startswith("[Step] depth 0,")
    assert dumps[1].startswith("[Step] depth 1,")


def test_a_parent_may_allow_a_depth_for_its_own_subtree(tmp_path):
    parent = build_agent(tmp_path, max_steps=6)
    parent.model.script = [
        step(
            tool_use(
                "spawn", goal="one level and no more", check="true", depth=0,
                return_schema={"type": "object"}, max_steps=1, register_id=6,
            )
        ),
        step(text("the child idles")),
        step(tool_use("bash", command="printf '{}' > " + parent.response_path.name)),
    ]
    parent.run()

    child_tools = [t["name"] for t in parent.model.requests[1]["tools"]]
    assert "spawn" not in child_tools and "resume" not in child_tools
    # The parent still has it: an allowance is passed down, not surrendered.
    assert "spawn" in [t["name"] for t in parent.model.requests[0]["tools"]]


def test_an_allowance_of_two_reaches_a_grandchild(tmp_path):
    built = build_agent(tmp_path)
    try:
        child_config = dataclasses.replace(built.config, max_depth=1 + 2)
        grandchild = Agent(
            config=child_config, workspace=built.workspace, model=built.model,
            instruction="a grandchild", depth=2, depth_from_parent=True,
        )
        assert grandchild.can_spawn is True
        grandchild.bash.close()
        floor = Agent(
            config=child_config, workspace=built.workspace, model=built.model,
            instruction="the floor", depth=3, depth_from_parent=True,
        )
        assert floor.can_spawn is False
        assert "your parent allowed depth 3" in floor.depth_refusal()
        floor.bash.close()
    finally:
        built.bash.close()


def test_the_refusal_names_the_run_when_the_run_set_it(tmp_path):
    built = build_agent(tmp_path, max_depth=0)
    try:
        assert built.can_spawn is False
        assert "this run allows depth 0" in built.depth_refusal()
        assert "the scaffold" not in built.depth_refusal()
    finally:
        built.bash.close()


def test_a_negative_ceiling_is_refused_at_construction():
    try:
        Config(max_depth=-1)
    except ValueError as exc:
        assert "max_depth must not be negative" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("a negative ceiling should be refused")
