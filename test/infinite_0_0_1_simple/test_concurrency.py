"""0.0.7f: what a step does at the same time as something else.

Two things stopped being serial. A step's `spawn` calls run side by side, since
they were asked for in one step and the scaffold used to run them one after
another; and the summariser that keeps register 4 runs alongside the *next*
generation instead of between two steps.
"""

import json
import re
import threading
import time

from infinite.agent import Agent
from infinite.config import SUMMARY_REGISTER, Config
from infinite.workspace import Workspace

from .fake_model import step, text, tool_use

FIRST_FREE = 5
SUMMARIZER_MARK = "You keep the running summary"


def make_config(**overrides) -> Config:
    return Config(
        max_register_length=400,
        max_special_length=800,
        max_step_half_length=200,
        max_canvas_length=2000,
        bash_timeout=5.0,
        step_retry_seconds=0.0,
        **overrides,
    )


def response_path_in(system: str) -> str:
    return system.lower().split("final response to <")[1].split(">")[0]


class Clock:
    """Every model call, with the window it occupied and who made it."""

    def __init__(self):
        self.lock = threading.Lock()
        self.calls: list[dict] = []
        self.live = 0
        self.most_at_once = 0

    def enter(self, kind: str) -> dict:
        with self.lock:
            self.live += 1
            self.most_at_once = max(self.most_at_once, self.live)
            entry = {"kind": kind, "start": time.monotonic(), "end": None}
            self.calls.append(entry)
            return entry

    def leave(self, entry: dict) -> None:
        with self.lock:
            entry["end"] = time.monotonic()
            self.live -= 1

    def of(self, kind: str) -> list[dict]:
        return [c for c in self.calls if c["kind"] == kind]


def overlap(a: dict, b: dict) -> float:
    return min(a["end"], b["end"]) - max(a["start"], b["start"])


class ThreadedModel:
    """Thread-safe: the parent's script, a child that answers, a slow summariser.

    A child is any call whose system message names a response file other than
    the parent's; it takes `child_delay` seconds and then writes that file.
    """

    def __init__(
        self,
        script,
        *,
        parent_response,
        child_delay=0.0,
        summary_delay=0.0,
        parent_delay=0.0,
    ):
        self.script = list(script)
        self.parent_delay = parent_delay
        #: The register dump of each parent step, in order.
        self.dumps: list[str] = []
        self.parent_response = parent_response
        self.child_delay = child_delay
        self.summary_delay = summary_delay
        self.clock = Clock()
        self.lock = threading.Lock()

    def generate(
        self, *, system, tools, messages, max_tokens, model=None, effort=None, thinking=None
    ):
        if SUMMARIZER_MARK in system:
            entry = self.clock.enter("summary")
            time.sleep(self.summary_delay)
            said = re.search(r"Step (\d+): what it thought", messages[0]["content"])
            self.clock.leave(entry)
            return step(text(f"summary through step {said.group(1) if said else '?'}"))

        response = response_path_in(system)
        if response != self.parent_response:
            entry = self.clock.enter("child")
            time.sleep(self.child_delay)
            self.clock.leave(entry)
            return step(
                tool_use(
                    "bash",
                    command=f"printf '%s' '{{\"done\": true}}' > {response}",
                    register_id=FIRST_FREE,
                )
            )

        entry = self.clock.enter("parent")
        with self.lock:
            self.dumps.append(messages[0]["content"])
            reply = self.script.pop(0) if self.script else step(text("script exhausted"))
        time.sleep(self.parent_delay)
        self.clock.leave(entry)
        return reply


def make_agent(
    tmp_path, script, *, child_delay=0.0, summary_delay=0.0, parent_delay=0.0, **overrides
):
    workspace = Workspace(tmp_path / "run")
    agent_id = workspace.new_agent_id()
    model = ThreadedModel(
        script,
        parent_response=workspace.response_path(agent_id).name,
        child_delay=child_delay,
        summary_delay=summary_delay,
        parent_delay=parent_delay,
    )
    agent = Agent(
        config=make_config(**overrides),
        workspace=workspace,
        model=model,
        instruction="build the thing",
        agent_id=agent_id,
    )
    return agent, model


def write_response(agent, payload):
    escaped = json.dumps(payload).replace("'", "'\\''")
    return tool_use(
        "bash",
        command=f"printf '%s' '{escaped}' > {agent.response_path.name}",
        register_id=FIRST_FREE,
    )


def spawn(register_id, **extra):
    return tool_use(
        "spawn",
        prompt="do a piece of it",
        return_schema={"type": "object"},
        register_id=register_id,
        **extra,
    )


# --- children of one step ------------------------------------------------
def test_the_spawns_of_one_step_run_at_the_same_time(tmp_path):
    agent, model = make_agent(tmp_path, [], child_delay=0.4, summary=False)
    model.script = [
        step(spawn(6), spawn(7), spawn(8)),
        step(write_response(agent, {"ok": True})),
    ]
    clock = time.monotonic()
    result = agent.run()
    elapsed = time.monotonic() - clock

    assert result.ok
    assert model.clock.most_at_once == 3
    assert elapsed < 3 * 0.4  # the slowest child, not the sum of them
    # Each child answered into its own register, and register 0 holds the last
    # call of the step rather than whichever child finished first.
    for register_id in (6, 7, 8):
        assert json.loads(agent.registers.values[register_id])["response"]["content"]
    last = json.loads(agent.registers.values[8])["response"]["file"]
    assert f"last result, special) ---\n{last}" in model.dumps[1]


def test_no_more_children_at_once_than_spawn_workers(tmp_path):
    agent, model = make_agent(tmp_path, [], child_delay=0.2, spawn_workers=2, summary=False)
    model.script = [
        step(spawn(6), spawn(7), spawn(8), spawn(9)),
        step(write_response(agent, {"ok": True})),
    ]
    agent.run()

    assert model.clock.most_at_once == 2
    assert len(model.clock.of("child")) == 4


def test_calls_that_are_not_spawns_keep_their_order(tmp_path):
    """One shell, one order: only a run of spawns is allowed to go concurrent."""
    agent, model = make_agent(tmp_path, [], summary=False)
    model.script = [
        step(
            tool_use("bash", command="printf 'one\\n' > log.txt", register_id=6),
            tool_use("bash", command="printf 'two\\n' >> log.txt", register_id=7),
            spawn(8),
            tool_use("bash", command="printf 'three\\n' >> log.txt", register_id=9),
        ),
        step(write_response(agent, {"ok": True})),
    ]
    agent.run()

    assert (agent.workspace.root / "log.txt").read_text() == "one\ntwo\nthree\n"
    assert model.clock.most_at_once == 1


# --- a budget for a child ------------------------------------------------
def test_a_parent_can_bound_its_child(tmp_path):
    """0.0.7e's root asked for a digest and got 278 steps of one; now it can say."""
    agent, model = make_agent(tmp_path, [], summary=False)
    idle = step(tool_use("bash", command="echo thinking", register_id=FIRST_FREE))
    model.script = [step(spawn(6, max_steps=2)), step(write_response(agent, {"ok": True}))]

    # A child that never answers stops after the two steps it was given.
    model.child_delay = 0.0
    original = model.generate

    def generate(**request):
        if SUMMARIZER_MARK not in request["system"] and response_path_in(
            request["system"]
        ) != model.parent_response:
            model.clock.leave(model.clock.enter("child"))
            return idle
        return original(**request)

    model.generate = generate
    agent.run()

    stored = json.loads(agent.registers.values[6])
    assert "no valid response in 2 steps" in stored["response"]["error"]
    assert stored["response"]["steps"] == 2
    record = agent.trajectory.read()[1]["observation"]["results"][0]
    assert record["max_steps"] == 2
    assert record["agent_id"] and record["agent_id"] != agent.agent_id


def test_a_child_with_no_budget_of_its_own_inherits_the_parents(tmp_path):
    agent, model = make_agent(tmp_path, [], max_steps=7, summary=False)
    model.script = [step(spawn(6)), step(write_response(agent, {"ok": True}))]
    agent.run()

    child = json.loads(agent.registers.values[6])["trajectory"]
    header = json.loads((agent.workspace.root / child).read_text().splitlines()[0])
    assert header["config"]["max_steps"] == 7


def test_a_bad_step_budget_is_refused_before_the_child_starts(tmp_path):
    agent, model = make_agent(tmp_path, [], summary=False)
    model.script = [step(spawn(6, max_steps=0)), step(write_response(agent, {"ok": True}))]
    agent.run()

    error = agent.trajectory.read()[1]["observation"]["results"][0]["error"]
    assert "'max_steps' must be an integer >= 1" in error
    assert model.clock.of("child") == []


# --- the summariser and the next step ------------------------------------
def test_the_summariser_runs_while_the_next_step_is_generated(tmp_path):
    agent, model = make_agent(tmp_path, [], summary_delay=0.3)
    model.script = [
        step(tool_use("bash", command="echo one", register_id=6)),
        step(tool_use("bash", command="echo two", register_id=7)),
        step(write_response(agent, {"ok": True})),
    ]
    result = agent.run()

    assert result.ok
    first_summary = model.clock.of("summary")[0]
    second_step = model.clock.of("parent")[1]
    # The summary of step 1 is written during the generation of step 2.
    assert overlap(first_summary, second_step) > 0
    assert first_summary["start"] < second_step["end"]


def test_every_step_still_carries_the_summary_that_followed_it(tmp_path):
    agent, model = make_agent(tmp_path, [], summary_delay=0.05, parent_delay=0.2)
    model.script = [
        step(tool_use("bash", command="echo one", register_id=6)),
        step(tool_use("bash", command="echo two", register_id=7)),
        step(write_response(agent, {"ok": True})),
    ]
    agent.run()

    records = [r for r in agent.trajectory.read() if r.get("role") == "assistant"]
    assert [r["step"] for r in records] == [1, 2, 3]
    assert records[0]["summary"]["summary"] == "summary through step 1"
    assert records[1]["summary"]["summary"] == "summary through step 2"
    assert "summary" not in records[2]  # the last step is not summarised
    # Its cost is recorded where it was paid: on its own step, and as the wait
    # the next step had for it.
    assert records[0]["timing"]["summary_s"] >= 0.05
    # A generation longer than the summary means the loop waited for none of it.
    assert records[1]["timing"]["summary_wait_s"] < 0.05


def test_a_summary_still_in_flight_when_the_segment_ends_is_recorded(tmp_path):
    """A budget that runs out mid-summary must not lose it: resume reads it."""
    agent, model = make_agent(tmp_path, [], max_steps=2, summary_delay=0.2)
    model.script = [
        step(tool_use("bash", command="echo one", register_id=6)),
        step(tool_use("bash", command="echo two", register_id=7)),
    ]
    result = agent.run()

    assert not result.ok and "no valid response in 2 steps" in result.error
    assert agent.registers.values[SUMMARY_REGISTER] == "summary through step 2"
    final = agent.trajectory.read()[-1]
    assert final["role"] == "final"
    assert final["registers"][SUMMARY_REGISTER] == "summary through step 2"
    # Both steps are on record, each with its own summary, and in order.
    steps = [r for r in agent.trajectory.read() if r.get("role") == "assistant"]
    assert [r["summary"]["summary"] for r in steps] == [
        "summary through step 1",
        "summary through step 2",
    ]


# --- continuing a child rather than redoing it ---------------------------
def test_a_child_that_runs_out_leaves_an_account_of_itself(tmp_path):
    """Three children in a row ran out at a small geometry and the parents were
    told only that. What the child knew is in its registers."""
    agent, model = make_agent(tmp_path, [], summary=False)
    model.script = [step(spawn(6, max_steps=2)), step(write_response(agent, {"ok": True}))]
    original = model.generate

    def generate(**request):
        if SUMMARIZER_MARK not in request["system"] and response_path_in(
            request["system"]
        ) != model.parent_response:
            model.clock.leave(model.clock.enter("child"))
            return step(tool_use("set_target", content="read the corpus, then answer"))
        return original(**request)

    model.generate = generate
    agent.run()

    record = agent.trajectory.read()[1]["observation"]["results"][0]
    handoff = agent.workspace.root / record["content"]["response"]["handoff"]
    note = json.loads(handoff.read_text())
    assert note["steps"] == 2
    assert note["target"] == "read the corpus, then answer"
    assert note["resume_with"].startswith('spawn(resume="')
    # And register 0 names the file before it explains itself.
    assert model.dumps[1].split("---\n")[1].startswith(f"handoff-{note['agent_id']}.json")


def test_a_parent_can_resume_a_child_where_it_stopped(tmp_path):
    agent, model = make_agent(tmp_path, [], summary=False)
    seen: list[str] = []

    def child(request):
        dump = request["messages"][0]["content"]
        seen.append(dump.splitlines()[0])
        if len(seen) < 3:
            return step(tool_use("set", value=f"working {len(seen)}", register_id=6))
        path = response_path_in(request["system"])
        return step(
            tool_use("bash", command=f"printf '%s' '{{\"done\": true}}' > {path}", register_id=6)
        )

    def generate(**request):
        if SUMMARIZER_MARK not in request["system"] and response_path_in(
            request["system"]
        ) != model.parent_response:
            model.clock.leave(model.clock.enter("child"))
            return child(request)
        return model.script.pop(0) if model.script else step(text("done"))

    model.script = [
        step(spawn(6, max_steps=2)),          # the child runs out
        step(spawn(7, resume="PLACEHOLDER")),  # rewritten below, once its id is known
        step(write_response(agent, {"ok": True})),
    ]
    model.generate = generate

    # The parent cannot know the child's id before it spawns it, so the second
    # step is patched from what the first one returned — which is what a real
    # agent reads out of register 0.
    real_spawn = agent.tools._spawn

    def spawning(call):
        if call.input.get("resume") == "PLACEHOLDER":
            call.input["resume"] = agent._last_child
        result = real_spawn(call)
        agent._last_child = result.record.get("agent_id") or agent._last_child
        return result

    agent._last_child = ""
    agent.tools._spawn = spawning
    result = agent.run()

    assert result.ok
    # Two segments of the same child: it stopped after step 2 and finished at 3.
    starts = [line.split(" (")[0] for line in seen]
    assert starts == ["[Step] step 1 of 2", "[Step] step 2 of 2", "[Step] step 4 of 5"]
    record = agent.trajectory.read()[2]["observation"]["results"][0]
    assert record["resume"] == record["agent_id"]
    assert record["content"]["response"]["content"] == {"done": True}
    # One child, one trajectory, with a resume seam in it.
    trajectories = list(agent.workspace.root.glob("trajectory-*.jsonl"))
    assert len(trajectories) == 2  # the parent and the one child
    roles = [
        json.loads(line)["role"]
        for line in (agent.workspace.root / record["content"]["trajectory"]).read_text().splitlines()
    ]
    assert roles.count("resume") == 1


# --- what the whole run has spent ----------------------------------------
def test_the_step_line_counts_the_run_once_there_is_more_than_one_agent(tmp_path):
    """A parent's counter moves by one however many steps its child spends.

    Five reconstruct runs opened by delegating a digest, and from where the
    parent sat that cost one step. It cost 124.
    """
    agent, model = make_agent(tmp_path, [], summary=False)
    idle = step(tool_use("bash", command="echo working", register_id=FIRST_FREE))
    model.script = [
        step(spawn(6, max_steps=4)),
        step(write_response(agent, {"ok": True})),
    ]
    original = model.generate

    def generate(**request):
        if SUMMARIZER_MARK not in request["system"] and response_path_in(
            request["system"]
        ) != model.parent_response:
            model.clock.leave(model.clock.enter("child"))
            return idle
        return original(**request)

    model.generate = generate
    agent.run()

    # Step 1 is the only agent in the run so far, so it says nothing extra.
    assert "this run has spent" not in model.dumps[0]
    # By step 2 the child has spent four, and the parent can see them.
    assert "[Step] step 2 of 40 (39 left, including this one); this run has spent 6 steps across 2 agents" in model.dumps[1]
    assert agent.workspace.spent() == (6, 2)
