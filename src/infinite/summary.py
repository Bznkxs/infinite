"""Register 4: a running summary of the run, kept by one model call.

Registers 0-3 hold the present — the last result, the last step, the target.
Nothing held anything older, so a step's own reasoning was the only bridge
between step 40 and step 3. Register 4 is that bridge: after every step the
previous summary and the step that just happened go in, and the summary that
replaces it comes out.

0.0.4 gave that job to a sub-agent — a whole agent with registers, tools, a
trajectory and a step budget, whose one job was to rewrite one register. The
judgement it was there for is real: deciding what to drop from a summary that is
already full is a choice, and truncation makes it badly. But an *agent* was the
wrong shape for the choice. Its answer had to fit register 4, and having tools it
could measure with, it would write the summary to a file, run `wc -c`, find it
over the limit, and write it again — five generations to a summary, or none at
all when the budget ran out first. Four of five summarisers in the run that
prompted this spent their whole budget that way and two never converged.

0.0.5 keeps the model and drops the agent. One generation, no tools, no steps,
no files: previous summary in, new summary out. There is nothing to measure with
and nothing to iterate against. The length rule that caused the loop belongs to
the scaffold now:

* a **budget** the model is given as though it were the limit, set below the
  register's real one so an ordinary overshoot still fits. 0.0.6 stopped naming
  the real limit in the prompt: told the ceiling, a model writes to the ceiling,
  and on the first long run of 0.0.5 that meant a summary at 4096 and two wasted
  retries on most steps;
* the register's **real limit**, checked here and never mentioned to the model;
* on an overrun, a **whole new generation** shown the previous summary, the step,
  and the attempt that was too long — a rewrite, not an edit, because asking a
  model to shorten its own text by counting is the loop again;
* and after the last attempt, **truncation**, because a summary that loses its
  tail is worth more than no summary at all.

The cost argument for a sub-agent survives intact: what goes in is one summary
and one step, never the history, so the price per step is flat however long the
run gets. What is gone is everything the agent wrapped around that.

0.0.6 makes the call cheap as well as small. It runs on a small model with no
effort at all, because rewriting a paragraph is not the work the run's model is
there for — and the same first long run of 0.0.5 spent most of its wall-clock
and output tokens keeping this one register.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from .config import Config
    from .model import Model

logger = logging.getLogger(__name__)

#: Enough of the parent's task for the summariser to know what matters, without
#: turning a long instruction into most of its context.
INSTRUCTION_EXCERPT = 2000

#: A model asked for prose sometimes hands it over wrapped. The register wants
#: the summary, not the wrapping.
_FENCES = ("```markdown", "```text", "```md", "```")


def _cut(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n[... cut after {limit} chars]"


def _section(title: str, body: str, empty: str = "(empty)") -> str:
    return f"## {title}\n\n{body.strip() if body.strip() else empty}\n"


def clean(text: str) -> str:
    """The reply, as the value it is about to become.

    Only the wrapping comes off. A model that ignores the instruction and
    introduces its summary keeps its preamble — silently deleting a first line
    would be guessing at which sentence was not meant to count.
    """
    value = text.strip()
    for fence in _FENCES:
        if value.startswith(fence) and value.endswith("```") and len(value) > len(fence) + 3:
            value = value[len(fence) : -3].strip()
            break
    return value


def describe_observations(results: list[Any], limit: int) -> str:
    """What the step's tool calls returned, one entry each, each one bounded."""
    if not results:
        return "(no tool call ran)"
    lines = []
    for i, result in enumerate(results, 1):
        error = (result.record or {}).get("error")
        lines.append(f"result {i}: {result.name} -> {error or result.status}")
        if result.payload:
            lines.append(_cut(result.payload, limit))
    return "\n".join(lines)


def system_message(*, agent_id: str, budget: int) -> str:
    """The summariser's whole role. Identical every step, so it caches.

    `budget` is the only length it is told. Register 4's real limit stays with
    the scaffold: a model told what the ceiling is writes to the ceiling, and
    then every step pays for the retries that overrun causes. Told a smaller
    number and nothing else, it aims there and the ordinary overshoot lands in
    headroom it does not know exists.
    """
    return f"""You keep the running summary of another agent's run. You are not that agent and you do not do its work: you are given one step of it and the summary so far, and you return the summary that replaces it.

The agent is `{agent_id}`, running inside InfiniteAgent — a scaffold that gives it a fixed set of registers and no conversation history. Register 4 holds your summary. It is the agent's only memory of anything older than the step it just took, so what you leave out is gone for it.

What to keep, in order of what a later step would most regret losing:

- what the run has established: findings, numbers, file paths, names — the facts a later step would otherwise have to redo work to recover;
- what has been decided and what has been tried, including what failed and why, so the agent does not repeat it;
- where the work has got to against its target, and what is left.

Leave out the agent's step-by-step narration, anything you cannot support from what you were given, and detail that is already one register away — register 0 has the last result and register 3 has the last step in full. Do not speculate about what the agent will do next, and do not invent facts to fill gaps.

Prefer keeping an older fact over the newest one when both do not fit: the newest step is still in the agent's other registers, and the oldest is only in yours.

Your summary must fit in {budget} characters, so that is the space you have. Use it — a summary well under it has thrown away room it could have kept a fact in — and do not exceed it. Write dense prose: notes, not narration.

Your entire reply is the new contents of the register. Do not introduce it, do not comment on it, do not wrap it in quotes or a code fence, and do not address the agent or the operator. Write the summary and nothing else."""


def build_input(
    *,
    step: int,
    instruction: str,
    target: str,
    previous_summary: str,
    thinking: str,
    action: str,
    observations: str,
    cut_off: bool,
    budget: int,
    rejected: str | None = None,
) -> str:
    """Everything the summariser is given: one step, and what it replaces.

    `rejected` is the attempt that came back too long. It is shown after the
    material rather than instead of it, because the retry is a fresh summary of
    the same input — not an edit of the text that failed. It is measured against
    `budget`, the length the summariser was given, and not against the
    register's own limit, which it is never told.
    """
    state = (
        "This step's generation was cut off at the workspace limit, so no tool call ran.\n"
        if cut_off
        else ""
    )
    body = f"""{_section("The agent's task", _cut(instruction, INSTRUCTION_EXCERPT))}
{_section("Its target, in its own words", target, "(it has not set one)")}
{_section("The summary so far, covering everything up to step " + str(step - 1), previous_summary, "(nothing yet — this is the first step)")}
{_section("Step " + str(step) + ": what it thought", state + thinking)}
{_section("Step " + str(step) + ": what it did", action)}
{_section("Step " + str(step) + ": what came back", observations)}
## What to return

The summary so far, updated to include step {step}. Replace it whole — you are rewriting, not appending, and you may drop or rewrite anything already in it.
"""
    if rejected is None:
        return body
    return body + f"""
## Your last attempt did not fit

It came back at {len(rejected)} characters, over the {budget} you have, so it was thrown away. Write the summary again from the material above — a new one, denser, not this one edited down. Cutting whole facts you judge least worth keeping is the right move; trimming words out of every sentence is not.

Here is what did not fit, so you do not have to reconstruct it:

{rejected}
"""


@dataclass
class SummaryUpdate:
    """What one step's summary rewrite came to, for register 4 and the record."""

    ok: bool
    summary: str = ""
    #: True when the last attempt was still over and the scaffold cut it.
    truncated: bool = False
    #: The length of every generation, in order — the record of what the retry
    #: rule actually cost, so a run that keeps overshooting is visible.
    attempts: list[int] = field(default_factory=list)
    target: int = 0
    limit: int = 0
    model: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def record(self) -> dict[str, Any]:
        """The step's `summary` field in the trajectory."""
        note: dict[str, Any] = {
            "ok": self.ok,
            "attempts": self.attempts,
            "target_chars": self.target,
            "limit": self.limit,
            "model": self.model,
            "usage": self.usage,
        }
        if self.ok:
            note["summary"] = self.summary
            note["chars"] = len(self.summary)
            note["truncated"] = self.truncated
        if self.error is not None:
            # Present alongside a summary when a call broke but an earlier,
            # over-long attempt was salvageable.
            note["error"] = self.error
        return note


def _sum_usage(total: dict[str, Any], usage: dict[str, Any]) -> dict[str, Any]:
    """Token counts across attempts, so a retry is not free in the record."""
    for key, value in (usage or {}).items():
        if isinstance(value, int):
            total[key] = total.get(key, 0) + value
    return total


class Summariser:
    """One tool-less generation per step, retried whole if it does not fit."""

    def __init__(self, config: "Config", model: "Model"):
        self.config = config
        self.model = model

    def update(
        self,
        *,
        agent_id: str,
        step: int,
        instruction: str,
        target: str,
        previous_summary: str,
        thinking: str,
        action: str,
        observations: str,
        cut_off: bool,
        limit: int,
    ) -> SummaryUpdate:
        budget = self.config.summary_target(limit)
        name = self.config.summary_model or self.config.model
        system = system_message(agent_id=agent_id, budget=budget)
        state = SummaryUpdate(ok=False, target=budget, limit=limit, model=name)

        rejected: str | None = None
        for attempt in range(1, self.config.summary_max_attempts + 1):
            message = build_input(
                step=step,
                instruction=instruction,
                target=target,
                previous_summary=previous_summary,
                thinking=thinking,
                action=action,
                observations=observations,
                cut_off=cut_off,
                budget=budget,
                rejected=rejected,
            )
            try:
                response = self.model.generate(
                    system=system,
                    tools=[],
                    messages=[{"role": "user", "content": message}],
                    max_tokens=self.config.summary_max_tokens,
                    model=self.config.summary_model,
                    effort=self.config.summary_effort,
                    thinking=self.config.summary_thinking,
                )
            except Exception as exc:  # the summary is memory, not the work
                return self._settle(state, rejected, f"{type(exc).__name__}: {exc}")

            state.usage = _sum_usage(state.usage, response.usage)
            candidate = clean(response.text)
            state.attempts.append(len(candidate))

            if not candidate:
                return self._settle(state, rejected, "the summariser returned no text")
            if len(candidate) <= limit:
                state.ok, state.summary = True, candidate
                return state

            logger.info(
                "agent %s step %d: summary attempt %d was %d chars, over %d",
                agent_id,
                step,
                attempt,
                len(candidate),
                limit,
            )
            rejected = candidate

        return self._settle(state, rejected, None)

    @staticmethod
    def _settle(
        state: SummaryUpdate, rejected: str | None, error: str | None
    ) -> SummaryUpdate:
        """How the attempts end when none of them fit.

        With an over-long attempt in hand, keep it and cut it: discarding a whole
        summary over its tail loses the oldest facts, which are the ones nothing
        else in the register file still holds. That holds however the attempts
        ran out — out of budget, or a retry that failed after a first draft came
        back long. Only with nothing at all to cut does the previous summary
        stand instead, which is the failure the register was always allowed.
        """
        if rejected:
            state.ok, state.truncated = True, True
            state.summary = rejected[: state.limit]
            # A truncation that happened because a call broke is not the same as
            # one that happened because the budget ran out; say which.
            state.error = error
        else:
            state.error = error or "the summariser returned nothing that fit"
        return state
