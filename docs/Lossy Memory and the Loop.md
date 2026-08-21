# Lossy Memory and the Loop

*Register 4 is the run's memory of itself, and it was built to be the thing that
stops a run repeating itself. The 0.0.8d reconstruction is the first long run
where it can be checked against that job, and it does not do it — it made the
loop worse. This document is the diagnosis and what to build instead. It is
input to 0.0.9 and is not a version document; `InfiniteAgent 0.0.9.md` is
written by hand and nothing here belongs in it.*

Evidence throughout is the root agent `f2bd5386` of
[the 0.0.8d reconstruction](InfiniteAgent%200.0.8d.md) (§5.1,
[`eval/results/reconstruct-0.0.8d.json`](../eval/results/reconstruct-0.0.8d.json)):
120 steps, 103 of which changed nothing durable, worst streak 31.

---

## 1. The claim register 4 was built on

[Part 4](InfiniteAgent%200.0.4.md) introduced it as the bridge between step 40
and step 3: *"the facts a later step would otherwise have to redo work to
recover"*, and the summariser's own system message still says, in order of what
a later step would most regret losing:

> - what has been decided and what has been tried, **including what failed and
>   why, so the agent does not repeat it**.

That sentence is the whole hypothesis. A run cannot see its own history, so a
model reads the history and hands back the part that matters, and the part that
matters includes *what has already been tried*. If that worked, the loop in §5.1
could not happen: an agent whose memory says "you have tried this and it failed"
does not try it thirty more times.

## 2. What it actually did

The root spent steps 62 to 120 on one defect — `agent.py:98` calls
`BashSession(...)` with arguments its constructor does not take. Here is what
register 4 said about that single fact, step by step, condensed to its verdict:

| steps | what the run's memory said |
| --- | --- |
| 62-68 | signature mismatch identified |
| **69** | **"Fixed BashSession constructor signature"** |
| 70-89 | signature mismatch identified (again) |
| **90-93** | **"signature mismatch fixed" / "fixed step 85"** |
| 94-100 | "still need verification"; "fails with TypeError" |
| **101-105** | **"TypeError resolved" / "resolved in step 101"** |
| **109** | **"confirms Agent instantiation issue, not BashSession signature mismatch as earlier suspected"** |
| 112-120 | signature mismatch identified (again) |

**One fact, restated in 58 consecutive summaries, with its truth value flipping
four times.** The bug was never fixed. Every "fixed" is the summariser
faithfully recording that the agent *believed* it had fixed it.

This is not a memory that failed to prevent a loop. It is a memory that
**sustained** one: each time it asserted the bug was resolved, the next steps
went looking for a different cause — at step 105 it invented a blocker outright
(*"bash.py module still missing from infinite_agent/"*; there is no such module
in the layout) — and each time reality reasserted itself, the cycle restarted.

Two supporting numbers:

- **The root saw a `[Check]` line in 0 of its 120 dumps.** It was given no
  check (0.0.8d §10.1), so the oscillating summary was its *only* standing
  signal about whether the bug was fixed. The one lossy party was unopposed.
- **Median step-to-step similarity between consecutive summaries is 0.73**, and
  24 steps rewrote more than 40% of it. The run's memory of itself is being
  substantially re-rolled every step.

## 3. Why — three structural properties, not a bad prompt

The instinct is to fix the summariser's instructions. That will not work, and
the reason is that all three failures are properties of the *shape* of the
mechanism.

### 3.1 It is a Markov chain, so it cannot count

The summariser is given: the instruction, the target, **the previous summary**,
and **one step**. That is all. So the only representation it has of forty steps
of history is whatever survived forty successive rewrites.

A rewrite cannot accumulate. "We tried this and it failed" stated at step 70 and
again at step 71 produces a summary indistinguishable from the one where it was
stated once — because the input at step 71 is *the summary* plus *step 71*, and
neither of them carries the number 2. **Nothing in the summariser's input has
ever contained a count of anything**, so no instruction can make it report one.
The word "again" is not available to it.

This is why, across 58 restatements of the same defect, not one summary says how
long it had been going on.

### 3.2 A rewrite resamples rather than consolidates

Every step the summary is regenerated whole and a fact survives only if the
model re-emits it. So a fact's presence is re-rolled every step, and with it a
fact's *content*: "identified" can become "fixed" on any step where the agent's
thinking sounded confident, and once "fixed" is in the summary it persists by
re-emission until something contradicts it.

Repetition should make a fact harder to dislodge. Under a rewrite it makes it
**easier**, because each restatement is a fresh chance to paraphrase it into
something slightly different — which is exactly what the 58-row table above
shows happening in slow motion.

### 3.3 It compresses the wrong axis

Read what the summaries actually spend their characters on: absolute workspace
paths, byte counts (`249960`), line numbers, ground-truth values, full CLI flag
lists, module inventories. **Detail is what survives.** What is discarded is
duration, repetition, and the history of what has been attempted.

That is compression of *history into state*. And state is precisely what does
not break a loop: a perfectly accurate description of where you are is
compatible with having been there for thirty steps.

The register is also writing 1,470 characters median against a 600-character
budget — it is not short of room. It is spending the room on the wrong axis.

## 4. What a human's lossy memory does differently

The point the loop makes is that human memory is *more* lossy than this and
still keeps people out of loops, so lossiness is not the problem. Three
differences, stated as design targets rather than as claims about neuroscience:

- **Forgetting is detail-first.** A person debugging this would not retain
  `agent.py:98` or the argument list; they would retain *"I keep going round on
  this constructor."* The summariser has it exactly inverted — it keeps the line
  number and loses the going-round.
- **Repetition consolidates instead of resampling.** The tenth time you hit the
  same wall, the memory of hitting it is *stronger*, not independently
  re-derived. Under a rewrite there is no accumulation channel at all.
- **There is a signal about the process, not the content.** Frustration is not a
  fact about the bug; it is a fact about the *effort spent on* the bug, it is
  cheap, and it is what triggers "stop, do something else". The scaffold now
  measures the equivalent — the stall streak — and does not put it anywhere near
  the run's memory.

That last one is the actionable version of the whole document. **The scaffold
already computes the thing the summary is missing, and does not give it to the
summariser.** `Progress.record` returns `moved`, `stall_streak` and the paths
touched. `Summariser.update` receives none of it.

## 5. What to build

Ranked by evidence behind them and by cost. Each names the property from §3 it
fixes and how it could be shown to be wrong.

### 5.1 Give the summariser the progress record (fixes §3.1, partly §3.3)

One argument, already computed. The summariser's input gains `moved`,
`stall_streak`, and the paths this step touched, and its instructions gain one
rule:

> When the step changed nothing, do not restate the situation. Age it: carry a
> line of the form *"no progress on X for N steps"* and increment N.

This is the smallest change that makes a count representable at all, because the
count now arrives in the input instead of having to survive a rewrite.

**How it could be wrong:** the model may still paraphrase the aged line into
prose and lose the number. If that happens, the counter has to be scaffold-owned
(§5.2) rather than model-owned, which is the more likely right answer anyway.

### 5.2 A ledger the model does not write (fixes §3.1 and §3.2)

The deeper fix is that **anything that must accumulate cannot be maintained by a
rewrite.** So split the run's memory by who writes it:

| | written by | shape | what it holds |
| --- | --- | --- | --- |
| register 4 | the summariser | rewritten whole | what is true now |
| **the ledger** | **the scaffold** | **append-only, counted** | **what has been attempted and what it cost** |

The ledger is machine-measured, so it cannot flip: one row per (check verdict,
or goal) with the step it was first seen and the number of steps since it last
changed. `[Check] FAILS: X` unchanged for 31 steps is a fact the scaffold knows
exactly and the model cannot argue with. It renders as one line, and unlike the
summary it is monotonic.

Note this is the same shape as the fix `facts.md` needed and got — one writer,
one interface — and the same shape as the argument for the check: **put the
thing that must be true under the machine, and leave the model the part that
needs judgement.**

**How it could be wrong:** it may be read past exactly as the `[Stall]` line was
(0.0.8d §10.7). The ledger is a different object from a scold — it is evidence —
but that is a hypothesis, and it should be tested separately from §5.3.

### 5.3 Forbid the summary from claiming a machine verdict (fixes §3.2)

"Fixed step 85" is a claim about the world that the summariser had no way to
check and that cost this run perhaps forty steps. The `[Check]` line is the
machine and the summary is second-hand, so:

> The summary must not assert that anything builds, imports, passes or is fixed.
> Record what was attempted; the check reports what is true.

Cheap, and it directly removes the failure mode in §2's table. It also composes
with 0.0.8d §10.1 — **a check would have contradicted the summary within one
step**, and the root had none.

### 5.4 Age the register instead of only the sentence (fixes §3.3)

If §5.1 lands, the natural extension is that the summary's *structure* carries
duration rather than its prose: a fixed slot at the top, maintained across
rewrites, of the form

```
Working on: <one line>   |  unchanged for: 31 steps  |  last progress: step 85
```

That is three facts, all scaffold-computed, in about 80 characters — against the
1,470 the summary is already spending, and against a `[Stall]` line of 249. It
is what a person retains when they have forgotten everything else.

## 6. What not to do

- **Do not lengthen the summariser's prompt.** §3 is three structural
  properties; none of them is addressable by asking more carefully. The
  instruction to keep *"what failed and why, so the agent does not repeat it"*
  is already there, and it is 58 rows of that table old.
- **Do not give it more room.** It is writing 1,470 characters against a
  600-character budget and spending them on paths and byte counts. The axis is
  wrong, not the size — and 0.0.8 §7.4 already showed it expands to about 80% of
  whatever ceiling it is given.
- **Do not give it the whole history.** The flat per-step cost is the reason the
  mechanism is affordable at all (Part 5), and a summariser that reads the
  trajectory is a summariser whose price grows with the run. The count is a
  scalar; it does not need the history to be carried, only computed.
- **Do not merge this with the stall notice.** §5.2 and 0.0.8d §10.3's
  tool-withdrawal tier attack the same failure from opposite ends — memory and
  affordance — and if they ship together the next run cannot say which one
  worked. That is the mistake 0.0.8d §7.1 opens by confessing.

## 7. The one-line version

The summariser was asked to be the run's memory and it is a **status board**: it
keeps where you are and discards how long you have been there. A memory that
stops a loop has to be the other way round, and the scaffold already computes
the number it is missing.
