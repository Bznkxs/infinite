"""A failing check must not look like progress — 0.0.8e §2.6.

`Progress` counts a changed check verdict as progress, which is right: an import
that starts working is the run getting somewhere. What it compared, until this
test existed, was the *line the agent reads*, and that line ends in the result
file of the run that produced it — `tool_output/<id>-step041-0362-check.json`, a
different string every step.

So a frame whose check was red counted as having made progress on every step of
the loop it was stuck in, and the measure was inert in exactly the state it
exists for. The 0.0.8d reconstruction is the evidence, and it is not subtle:

    f2bd5386  root, no check    120 steps   103 stalls
    404a2f38  child, red check  120 steps     1 stall

A passing check was never affected, because it renders the constant `passes.`.
"""

from __future__ import annotations

import json

from infinite.agent import Agent
from infinite.config import Config
from infinite.model import ModelResponse
from infinite.workspace import Workspace


class ScriptedModel:
    """Returns one canned generation per step; no network, no tools run."""

    def __init__(self, steps):
        self.steps = list(steps)
        self.requests = []

    def generate(self, *, system, tools, messages, max_tokens, **kw):
        self.requests.append(messages)
        blocks = self.steps.pop(0) if self.steps else [{"type": "text", "text": "idle"}]
        return ModelResponse(blocks=blocks, tool_calls=[], stop_reason="end_turn")


def build(tmp_path, check, steps=6):
    workspace = Workspace(tmp_path)
    # The surcharge off, so the step count is the step count: with it on, a run
    # of nothing correctly buys fewer steps, which is a different test.
    config = Config(
        num_registers=8, max_steps=steps, firewall=False, summary=False,
        stall_surcharge=0,
    )
    return Agent(
        config=config,
        workspace=workspace,
        model=ScriptedModel([[{"type": "text", "text": f"step {i}"}] for i in range(steps)]),
        instruction="do nothing at all",
        check=check,
    )


def stalls(result_agent):
    records = [
        json.loads(line)
        for line in result_agent.trajectory.path.read_text().splitlines()
        if line.strip()
    ]
    steps = [r for r in records if r.get("role") == "assistant"]
    return sum(1 for r in steps if not r["progress"]["moved"]), len(steps)


def test_a_failing_check_does_not_manufacture_progress(tmp_path):
    """The regression. Every step does nothing; every step must be a stall."""
    agent = build(tmp_path, check="exit 3")
    agent.run()
    stalled, total = stalls(agent)
    assert total == 6
    assert stalled == total, "a red check made a run of nothing look like progress"


def test_a_passing_check_was_never_the_problem(tmp_path):
    agent = build(tmp_path, check="true")
    agent.run()
    stalled, total = stalls(agent)
    assert stalled == total


def test_a_verdict_that_genuinely_changes_is_progress(tmp_path):
    """Red to green is the run getting somewhere, and must still count."""
    flag = tmp_path / "green"
    agent = build(tmp_path, check=f"test -f {flag.name}", steps=6)

    real = agent._run_check_now
    seen = []

    def flip():
        result = real()
        seen.append(agent._check_state)
        # Half way through, the work starts passing.
        if len(seen) == 3:
            flag.write_text("x")
        return result

    agent._run_check_now = flip
    agent.run()
    stalled, total = stalls(agent)
    assert stalled < total, "a check going green is progress and was not counted"
    # ...and only the step it flipped on, plus the file it wrote.
    assert stalled >= total - 2


def test_the_line_the_agent_reads_still_names_its_result_file(tmp_path):
    """The path is useful to the agent; it just must not be what is compared."""
    agent = build(tmp_path, check="exit 3", steps=2)
    agent.run()
    assert agent._check_line.startswith("FAILS (exit 3)")
    assert "tool_output/" in agent._check_line
    assert "tool_output/" not in (agent._check_state or "")
    assert agent._check_state.startswith("exit 3")
