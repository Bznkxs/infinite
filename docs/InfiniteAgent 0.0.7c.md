# InfiniteAgent 0.0.7c-simple

0.0.7b was two thirds of the way through a reconstruction when the process died.
Not the agent — the *process*. One `overloaded_error` from the API raised out of
`Agent.run()`, and nothing caught it.

## What the 0.0.7b run showed

Everything 0.0.7b changed worked. Measured against the run before it, at
comparable step counts:

| | 0.0.6 | 0.0.7a | 0.0.7b |
| --- | --- | --- | --- |
| lines of code per step | 5.1 | 4.2 (final) | **27.2** |
| prose bytes per line of code | 96 | 195 | **18.6** |
| steps needing a summary retry | 26% | 55% | **0%** |
| a child finishing with a valid response | — | never, in 500 steps | **yes, 41 steps** |

The register-4 room fixed the summariser outright: **zero** retries in ninety-five
steps, against 274 of 500. The truncation notice and the bigger registers stopped
the re-reading loop: no agent in this run read the same file twice in a row. And
the `spawn` description change moved the work off the parent — the root wrote one
3KB outline instead of ten transcribed part files (108KB), briefed children with
paths, and the children coordinated through a shared `docs/API.md` they appended
to as they went.

Then, at 7 of 15 modules and 2,581 lines:

```
agent adc5fac8 step 7: spawn -> error: spawn failed: APIStatusError: overloaded_error
agent adc5fac8 step 7: spawning 2fa7b2d5 at depth 1
agent adc5fac8 step 7: spawn -> error: spawn failed: APIStatusError: overloaded_error
Traceback (most recent call last):
  File ".../src/infinite/agent.py", line 402, in run
    response = self.model.generate(
anthropic.APIStatusError: {'type': 'overloaded_error', 'message': 'Overloaded'}
```

The two `spawn` failures are *fine*: a tool that raises becomes an error in
register 0, exactly as specified, and the run continued. The third one is not,
because it happened on the step's own generation, where there was no handler at
all. Root and every child died together.

**The scaffold caught every failure except the one it cannot do without.** A tool
error goes to register 0. A summariser error leaves the old summary standing and
records `summary.ok: false`. A sub-agent that gives up returns an error message to
its parent. A step's own model call had nothing, and a run of a thousand steps
meets a transient API error eventually.

## The changes

| | 0.0.7b | 0.0.7c |
| --- | --- | --- |
| a step's generation raises | kills the process | **retried for `step_retry_seconds` (900), backing off 5s → 60s** |
| the patience runs out | — | **the segment ends with a `final` record and `--resume` continues it** |
| Anthropic client retries | SDK default (2) | **`api_max_retries` (8)** |

Three layers, each doing something the others cannot. The SDK's retries handle a
blip inside one request. The scaffold's patience handles an overload that outlasts
them. And the graceful ending handles the case where the API is simply down: the
run stops where it stood, with its registers on record in a `final`, which is the
state `--resume` was built to pick up.

**The budget is time, not attempts,** and that is the letter's one revision. The
first shape of this change was four attempts with a doubling backoff — 5s, 10s,
20s, or thirty-five seconds of patience. It was tested immediately and by
accident: the API was overloaded when 0.0.7c launched, and both the new run and
the resumed 0.0.7b run burned all four attempts on their *first* step and stopped.
No crash, no lost work, resume hints printed — the mechanism did its job — but
thirty-five seconds is not patience for a system whose premise is runs of a
thousand steps. Fifteen minutes of it, with the backoff capped at a minute, is.

The failure that produced this letter, and the outage that revised it, are the
same event seen twice: a scaffold that dies of a 529 loses a run; a scaffold that
waits thirty-five seconds loses a run more politely; a scaffold that waits a
quarter of an hour usually loses nothing at all.

A failed attempt is **not a step**. Nothing was generated, so nothing is recorded
and the step counter does not move; the trajectory a reader sees has no gap and no
phantom step, and the budget is not spent on a request that never returned.

## Not in 0.0.7c

- **The failure is still recorded only in the log and the `final`.** A resumed run
  does not know *why* the previous segment stopped unless a human reads it; the
  `resume` record has carried `previous_error` since 0.0.2, which is as far as
  this goes.
- **A dead child is still a dead child.** If a `spawn` fails, the parent gets an
  error and must decide to re-dispatch; nothing retries a sub-agent
  automatically, because a half-finished child has already written files and
  re-running its whole prompt is not obviously the right repair.
- **Nothing rate-limits the fan-out.** A root that spawns five children in one
  step is part of why the API pushed back; the scaffold does not police that.
