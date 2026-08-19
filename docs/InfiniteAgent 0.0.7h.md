# InfiniteAgent 0.0.7h — a child is a process, not a shot

Two runs at a small context lost **nine children** to their step bounds without
finishing anything. Each time the parent was told one sentence — *no valid
response in 70 steps* — and each time it re-dispatched the whole job, so the
reading the dead child had done was paid for again.

0.0.7h is three changes, all from the same measurement.

## What the runs showed

Two of the children, taken apart:

```
child A:  70 steps   75 bash reads :  3 writes   21% of generations cut off
child B: 160 steps  212 bash reads :  7 writes   27% of generations cut off
```

Both ended the same way. Child B's last thinking:

> *With only two steps remaining, I need to be strategic: I should prioritize
> writing a minimal but functional set of the remaining modules and tests in this
> step* —

and that generation was cut off at the token cap before a single call ran.
0.0.7d gave the agent `[Step] N of M` so it could see its budget; what both
children did with that knowledge was defer, then lose everything to one
truncation.

Across all three runs of the series so far there were **162 cut-off
generations**. In 44 of them the model had written more than one tool call, and
since a call block only exists because the one before it finished, **56 finished
calls were thrown away** by a rule written when truncation was rare.

## The changes

| | before | after |
| --- | --- | --- |
| a child that runs out | one sentence to the parent | **`handoff-<id>.json`**: its target, its summary, its last step, its step count |
| that child's work | re-dispatched from scratch | **`spawn(resume="<id>", max_steps=N)`** continues it |
| a cut-off generation | every call discarded | **the finished calls run**; only the one it was writing is dropped |
| what the agent learns from a cut-off | register 1 flips to True | **register 0 says so**, in 155 chars |

### The handoff

An agent that stops without a response now writes what it knew: the target it set
itself, the summary of what it established, the last step it took, and the line
that continues it. Register 0 names that path **first**, because in the short
geometry a register holds 208 characters and the path is the only part that
reliably survives — the same reasoning as 0.0.7b's truncation notice.

### Resume, from the parent

`--resume` has existed since 0.0.2 for a person at a terminal. A parent can now
reach it: the child keeps its registers, its files and its step count, and its
trajectory gets a `resume` seam — one child, one history, two segments. At a
small geometry, where a step buys less of everything, running out stops being an
exception and becomes ordinary, and a mechanism that treats it as fatal wastes
most of a run.

### Salvaging a cut-off generation

0.0.1 ruled that a cut-off generation runs nothing, because it may hold a
half-written call. That was right when a step could generate 8,192 tokens and
truncation was rare. At 0.0.7g's 1,920 a quarter of generations are cut off, and
the rule discards work that is provably complete: **every call but the last is
whole**, because a later block only exists because the earlier one finished. So
those run, and only the last is dropped.

The cost of this letter is honest and small: `spawn`'s new `resume` parameter is
sent in every request forever, and the ceiling from 0.0.7g refused the first
launch because of it. It was paid for out of three tool descriptions, which is
the trade this scaffold now has to make explicitly.

## Not in 0.0.7h

- **Nothing decides *when* to resume.** The parent has to notice the handoff and
  choose; the scaffold does not re-dispatch anything by itself.
- **Nothing helps the 110 cut-off generations that held a single call.** They
  were cut in the middle of the only thing they were doing, and the step is
  still spent. Writing less per step is advice, not a mechanism.
- **A resumed child gets no more context than it had.** If it ran out because
  the job does not fit its geometry, more steps will not change that.
