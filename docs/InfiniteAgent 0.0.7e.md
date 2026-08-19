# InfiniteAgent 0.0.7e-simple

Every run in this series has spent **1.8 tool calls per step**, and none of them
knew it. That is the whole letter.

## What the runs showed

Measured across four reconstruct runs, 1,320 steps in total:

```
                steps   calls   per step   0 / 1 / 2 / 3 / 4 / 5+ calls
0.0.6            106     203     1.92       0  30  67   5   1   3
0.0.7a           517     968     1.87       0  67 449   1   0   0
0.0.7b           264     504     1.91       3  24 231   6   0   0
0.0.7d           433     751     1.73       0 129 292  10   2   0
```

The distribution is the finding, not the mean: **two calls is a ceiling, not an
average.** 0.0.7a made exactly two calls on 449 steps and three on one.

What that costs is visible in a single child from the 0.0.7d run, which spent
**226 steps producing a 145-line module** — 319 reads, 12 writes, 24 test runs.
It was not looping and it finished with a valid response; it simply bought 1.4
calls per generation for 226 generations. At six calls a step the same work is
about fifty.

The scaffold was quietly making that worse. Batching means choosing a destination
register per call, and register 0 shows only the *last* result — so a step with
four reads needs four registers allocated up front, and the guidance for all of
this was one clause at the end of the system message: *"When several calls are
independent, make them in the same step."* True, unmotivated, and ignored 1,300
times.

## The change

One paragraph, replacing that clause:

> **One step is one generation, however many calls it contains.** Four reads in
> one step cost one generation; the same four reads in four steps cost four, and
> four steps out of your budget. So when you already know what you need — several
> ranges of a file, several files, a read and the command that follows from it —
> ask for all of it in one step, each result in its own register. You have 27
> registers to land results in (5-31, plus the canvas); using several in a step
> is what they are for. Save one-call steps for when the next thing you do
> genuinely depends on what this call returns.

It states the price, names the resource that makes batching possible, and says
when *not* to batch — the sequential case is real, and a rule that ignored it
would trade one waste for another.

This pairs with 0.0.7d's `[Step] N of M`: a step budget you can see is only
useful if you also know what a step buys.

## How it is being measured

0.0.7e runs **alongside** 0.0.7d on the same task, one variable between them, so
the comparison is head-to-head rather than against a remembered number:

- **calls per step**, and the shape of the distribution — the direct target;
- **steps per module** — what the calls were for;
- modules built, prose written, and whether the run finishes at all.

If calls per step does not move, the honest conclusion is that two calls is a
property of the model rather than of the prompt, and the next letter has to make
batching structural — a tool that takes a list of reads, say — rather than
advisory.

## Not in 0.0.7e

- **Nothing enforces batching.** The scaffold does not refuse a one-call step or
  suggest calls the agent did not ask for.
- **`spawn` is still synchronous**, so a root that fans out five children still
  runs them one after another. That is the other multiplier, and it is a change
  to the step loop rather than to a paragraph — a later letter if this one lands.
