"""The property the whole thing is for: context does not grow with the task.

[Design Tests (Top Down)](../../docs/Design%20Tests%20(Top%20Down).md) asks for
three things, and they are all the same thing: reading, writing and complexity
should be unbounded while the context stays a fixed size. "Fixed" does not mean
small — it means it does not *grow*.

These tests are the property itself rather than a mechanism, so they measure the
one number a run is actually bought by: the largest request it makes. Each one
scales a different axis of the task and asserts that number does not move.
"""

import json

import pytest

from infinite.agent import Agent
from infinite.config import FRAME, Config, frame_config
from infinite.workspace import Workspace

from test.infinite_0_0_1_simple.fake_model import FakeModel, step, text, tool_use


def request_chars(model) -> list[int]:
    """The whole of every request this model was sent, in characters."""
    return [
        len(r["system"])
        + len(json.dumps(r["tools"], ensure_ascii=False))
        + sum(len(m["content"]) for m in r["messages"])
        for r in model.requests
    ]


def build(tmp_path, name="run", **overrides):
    config = frame_config(summary=False, **overrides)
    return Agent(
        config=config,
        workspace=Workspace(tmp_path / name),
        model=FakeModel([]),
        instruction="do the thing",
    )


def answer(agent):
    return step(
        tool_use("bash", command="printf '{}' > " + agent.response_path.name)
    )


# --- steps ---------------------------------------------------------------
@pytest.mark.parametrize("steps", [4, 40])
def test_the_request_does_not_grow_with_the_number_of_steps(tmp_path, steps):
    """Infinite complexity, in its crudest form: more of the same work."""
    agent = build(tmp_path, max_steps=steps + 2)
    agent.model.script = [
        step(
            text(f"working, step {i}"),
            tool_use("bash", command=f"echo step {i} >> log.txt", register_id=6),
        )
        for i in range(steps)
    ] + [answer(agent)]
    try:
        result = agent.run()
    finally:
        agent.bash.close()

    assert result.ok
    sizes = request_chars(agent.model)
    assert len(sizes) == steps + 1
    assert max(sizes) <= agent.context["input_tokens"] * 2.6
    # And it is flat, not merely bounded: the last step's request is no larger
    # than the first few, because there is no conversation history to grow.
    assert max(sizes) - min(sizes) < agent.config.dump_chars


def test_a_forty_step_run_is_the_same_size_as_a_four_step_one(tmp_path):
    def largest(steps):
        agent = build(tmp_path, name=f"run{steps}", max_steps=steps + 2)
        agent.model.script = [
            step(tool_use("bash", command=f"echo {i} >> log.txt", register_id=6))
            for i in range(steps)
        ] + [answer(agent)]
        try:
            agent.run()
        finally:
            agent.bash.close()
        return max(request_chars(agent.model))

    short, long = largest(4), largest(40)
    assert abs(long - short) < 200  # the step counter and its wording, and nothing else


# --- depth ---------------------------------------------------------------
class Chain(FakeModel):
    """Every agent descends until the chain is `depth` deep, then answers.

    One model for the whole tree, dispatching on what the dump says the depth
    is — the script FakeModel replays cannot express a tree, and a tree is the
    thing being measured.
    """

    def __init__(self, depth: int):
        super().__init__([])
        self.depth = depth
        #: Which frames have already descended once, by response file, so that
        #: a frame descends and then answers rather than descending forever.
        self.descended: set[str] = set()

    def generate(self, **request):
        self.requests.append(request)
        dump = request["messages"][0]["content"]
        here = int(dump.split("depth ", 1)[1].split(",", 1)[0])
        path = request["system"].split("response to <", 1)[1].split(">", 1)[0]
        if here < self.depth and path not in self.descended:
            self.descended.add(path)
            return step(
                tool_use(
                    "spawn", goal=f"frame {here + 1}", check="true",
                    return_schema={"type": "object"}, register_id=6,
                )
            )
        return step(tool_use("bash", command=f"printf '{{}}' > {path}"))


def descend(tmp_path, depth: int) -> tuple[int, object]:
    """Run a chain `depth` frames deep; return its largest request and its result."""
    agent = build(tmp_path, name=f"deep{depth}", max_steps=4 * depth + 8)
    agent.model = Chain(depth)
    try:
        result = agent.run()
    finally:
        agent.bash.close()
    return max(request_chars(agent.model)), result, agent


def test_a_five_frame_stack_costs_no_more_context_than_a_one_frame_stack(tmp_path):
    """0.0.8b §3: the depth of the stack is unbounded, the width is constant.

    The decomposition is not planned — it is discovered by descent — so what
    grows with the complexity of a task is the number of frames, and each one is
    a fresh context of the same size.
    """
    shallow, shallow_result, _ = descend(tmp_path, 1)
    deep, deep_result, deep_agent = descend(tmp_path, 5)

    assert shallow_result.ok and deep_result.ok
    # Five frames of descent, five children, and the same size of request.
    assert len(list(deep_agent.workspace.root.glob("trajectory-*.jsonl"))) == 6
    assert deep - shallow < 400
    # The steps of the whole subtree came home to the root.
    assert deep_result.cost >= 5


def test_the_root_never_sees_what_is_below_the_frame_it_called(tmp_path):
    """"nothing at all about what is below it or beside it" — 0.0.8b §2."""
    _, _, agent = descend(tmp_path, 4)
    root_dumps = [
        r["messages"][0]["content"]
        for r in agent.model.requests
        if r["messages"][0]["content"].startswith("[Step] depth 0,")
    ]
    # The root's own dumps mention its child's response file and nothing from
    # the three frames under it.
    assert all("depth 2" not in dump for dump in root_dumps)
    assert all("frame 3" not in dump for dump in root_dumps)


def test_a_deep_chain_is_bounded_by_the_budget_and_not_by_a_constant(tmp_path):
    """0.0.8c §6: charged steps make non-termination impossible without a ceiling."""
    agent = build(tmp_path, name="runaway", max_steps=6)
    assert agent.config.max_depth is None
    agent.model = Chain(depth=50)
    agent.model.descended = set()  # a chain that never means to bottom out
    try:
        result = agent.run()
    finally:
        agent.bash.close()

    assert not result.ok  # it ran out of budget, not out of permission
    assert result.cost <= 6
    depths = [
        json.loads(path.read_text().splitlines()[0]).get("depth", 0)
        for path in agent.workspace.root.glob("trajectory-*.jsonl")
    ]
    assert max(depths) > 1  # deeper than 0.0.7's ceiling of one, and it stopped anyway
    assert max(request_chars(agent.model)) < 40_000


# --- volume --------------------------------------------------------------
@pytest.mark.parametrize("kilobytes", [4, 4096])
def test_the_request_does_not_grow_with_the_size_of_what_is_read(tmp_path, kilobytes):
    """Infinite reading: paging is what makes depth free, and it always was."""
    agent = build(tmp_path, name=f"read{kilobytes}", max_steps=6)
    corpus = agent.workspace.root / "corpus.txt"
    corpus.write_text("abcdefgh" * 128 * kilobytes)
    canvas = agent.config.canvas_id
    agent.model.script = [
        step(tool_use("load", path="corpus.txt", start=0, register_id=canvas)),
        step(tool_use("load", path="corpus.txt", start=kilobytes * 512, register_id=canvas)),
        answer(agent),
    ]
    try:
        result = agent.run()
    finally:
        agent.bash.close()

    assert result.ok
    assert max(request_chars(agent.model)) <= agent.context["input_tokens"] * 2.6


def test_the_request_does_not_grow_with_the_size_of_what_is_written(tmp_path):
    """Infinite writing: the file is on disk and the context never held it."""
    agent = build(tmp_path, max_steps=12)
    agent.model.script = [
        step(tool_use("bash", command=f"seq {i * 1000} {i * 1000 + 999} >> out.txt"))
        for i in range(10)
    ] + [answer(agent)]
    try:
        result = agent.run()
    finally:
        agent.bash.close()

    assert result.ok
    assert len((agent.workspace.root / "out.txt").read_text().splitlines()) == 10_000
    sizes = request_chars(agent.model)
    assert max(sizes) - min(sizes) < 400


# --- the ceiling ---------------------------------------------------------
def test_the_ceiling_is_enforced_before_a_run_starts_not_discovered_in_a_bill(tmp_path):
    with pytest.raises(ValueError) as raised:
        Agent(
            config=frame_config(max_context_tokens=4000),
            workspace=Workspace(tmp_path / "refused"),
            model=FakeModel([]),
            instruction="do the thing",
        )
    assert "over the max_context_tokens of 4000" in str(raised.value)


def test_the_agents_own_share_is_reported_beside_the_total(tmp_path):
    """7.4: report *usable working set*, not just total."""
    agent = build(tmp_path)
    try:
        budget = agent.context
    finally:
        agent.bash.close()

    canvas = FRAME["max_canvas_length"]
    free = 5 * FRAME["max_register_length"]
    assert budget["working_set_chars"] == free + canvas + FRAME["max_target_length"]
    # 0.0.8a §5 argued the canvas is the register a working set has to land in
    # whole, and that 1,536 chars was the binding constraint rather than the
    # context as a whole. This preset is where that argument was cashed.
    assert canvas == 4096
    assert budget["total_tokens"] <= FRAME["max_context_tokens"]
