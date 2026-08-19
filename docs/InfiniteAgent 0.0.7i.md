# InfiniteAgent 0.0.7i — two budgets, not one

0.0.7g put a whole generation under 8,000 tokens and 0.0.7h made an unfinished
child recoverable, and the reconstruct task still would not finish at that size
while a 39MB corpus was answered in seventeen steps. This letter is why: the
scaffold had been treating input and output as one budget, and they are not the
same resource at all.

## What three configurations showed

Same task, same spec, one variable at a time:

| | input | output | reading | writing |
| --- | ---: | ---: | --- | ---: |
| 0.0.7f | 30,300 | 16,384 | ✅ | **9.5 lines a step** |
| 0.0.7g/h | 6,063 | 1,920 | ✅ *same answers, same mistakes* | **1.3 lines a step** |

On reading, the two are indistinguishable. The same BABILong and ∞Bench
instances at both ceilings give the same answers in two to four times the steps,
**including the same wrong answer** on the one they both miss — so where the
small configuration fails, the failure is the model's, not the context's.

On writing they are seven times apart, and the ratio is not mysterious: the
output caps are 16,384 and 1,920, and 5,500 lines of Python is about 70,000
output tokens however it is sliced. No amount of paging substitutes for room to
generate. The tax is visible directly, too — a quarter of generations were cut
off at 1,920 and **none at all** at 8,192.

## The change

`--wide-output`: 0.0.7g's input geometry, unchanged to the character, with a
generation of 8,192 tokens instead of 1,920. One request is at most 14,255
tokens.

```
input  6,063  (11 registers, canvas 1,536, summary 1,536 — exactly 0.0.7g)
output 8,192
```

`max_context_tokens` still exists and still refuses a configuration that
overruns, because knowing what a step costs is worth keeping. What changed is
the claim it makes: capping input *and* output together is what an 8,000-token
model would impose, and it binds the wrong quantity for anything that writes.
Long inputs are what degrade attention; a long generation does not share that
property.

## What it did

| | input | output | lines of code a step |
| --- | ---: | ---: | ---: |
| 0.0.7f | 30,300 | 16,384 | 9.5 |
| 0.0.7g/h | 6,063 | 1,920 | 1.3 |
| **0.0.7i** | **6,063** | **8,192** | **10.3** |

One child, eighty steps, 820 lines across ten modules. The input geometry is
identical to the configuration that managed 1.3 lines a step — the same eleven
registers, the same 1,536-character canvas, the same summary — and the writing
rate is 0.0.7f's, at a fifth of 0.0.7f's input.

**The active context was never what bounded writing.** Not one generation in the
run was cut off, against a quarter of them at 1,920.

## Three constraints, not two

The letter above claims input and output are separate resources, and they are —
but the 0.0.7i run found a third that neither of them covers.

Its children wrote ten modules at 10.3 lines a step: config, registers, prompt,
tools, trajectory, summariser, cli, viewer. Then two children spent **240 steps
on `step_loop.py` and wrote nothing at all.** The second of them, given 150
steps and 8,192 tokens a generation, made 345 tool calls of which almost all
were reads, used a median of 1,219 output tokens, and ended:

> *With only two steps remaining, I need to write the step_loop.py
> implementation now, even though I'm uncertain about the exact signatures for
> run_step, call_model, StepOutcome…*

It was not short of room to write. It was short of room to **hold an interface**.
`step_loop.py` calls into six other modules, so implementing it needs some forty
signatures and field names live at once, and 6,063 tokens cannot hold forty
facts. The summary register is 1,536 characters and cannot carry them between
steps either, so every step re-derived what the step before it had established.

The three costs a job can have, and how a small context meets each:

| what the work needs | at 6,063 in / 8,192 out |
| --- | --- |
| **one fact out of an enormous corpus** | fine — 39MB in seventeen steps |
| **a lot of output from a little input** | fine — 10.3 lines of code a step |
| **many interfaces live at once** | this is where it fails |

This also rehabilitates the habit five runs have been criticised for here. Every
one of them opened by writing a digest of the specification, against the
scaffold's advice, and it looked like avoidance. It is not: a digest is the
model's answer to interface breadth, and the run that succeeded at 46,684 tokens
did exactly this — its children were briefed from a fixed `notes/API.md`. The
difference is that at 46,684 the digest fits in the context that has to use it.
At 6,063 it gets written and still cannot be held, so it is read again every
step, and 240 steps produce nothing.

The honest conclusion is not that a small context cannot build software. It is
that **paging substitutes for context when the work is deep and not when it is
wide**, and nothing in this scaffold yet gives an agent a way to hold a wide
interface — registers are 208 characters, the canvas is 1,536, and the summary
is written by a model that cannot be told what to keep.

## What it does not fix

The first 0.0.7i run opened the way every run before it has: the root spawned a
child to write a digest of the specification, and then a second child to write a
checklist of its own six-kilobyte instruction. Truncation went to zero and the
strategy did not move an inch. Room to write is not the same as a reason to
write, and that is [0.0.7j](InfiniteAgent%200.0.7j.md)'s problem.
