# InfiniteAgent 0.0.7d-simple

Two runs of 0.0.7c's code, same task, same binary. One reached 8 of 15 modules
and 2,974 lines. The other spent 48 steps writing 268KB of documents and produced
**no code at all**. The difference was the plan each root happened to pick on its
first step, and the scaffold had nothing to say about it either way.

0.0.7d gives the agent the two facts it was missing to notice that for itself.

## What the 0.0.7c runs showed

The retry work was vindicated the hour it landed: the API was overloaded at
launch, both runs met sustained `overloaded_error`s, and neither crashed. The
first shape of the change — four attempts, 35 seconds of patience — was not
enough and both segments ended on step 1; with the budget made *time* (15
minutes), both ran through the same outage without losing a step. A crash that
cost a whole run in 0.0.7b cost nothing here.

What the fresh run then exposed was not a mechanism at all. Its root reasoned:

> *Rather than trying to read the entire 97KB spec myself given my context
> limits, I should spawn a sub-agent to digest the full spec and produce a
> condensed brief.*

and its child spent forty-four steps on that brief, ending here:

> *BRIEF-A.md is currently over 22000 characters, but BRIEF-A-new.md comes in at
> 21811 characters, which should work.*

That is **the 0.0.5 summariser loop, reproduced by the agent on itself**: writing
a file, measuring it with `wc -c`, rewriting it to hit a character budget. 0.0.5
removed the summariser's tools because "a model cannot hit a character budget by
generating, and giving it the means to check turns that into an iteration it has
no way to win". The agent has bash, so it can always give itself that iteration —
and it did, to fit a file into the 20,000-char canvas.

It did not need to. `load(path, start)` pages any file of any size.

## The changes

### 1. The dump says which step this is

```
[Step] step 48 of 500 (453 left, including this one)
[Registers]
--- register 0 (…) ---
```

Until now **nothing in the context said what step it was.** The system message
described the per-step token budget and the register limits; the step budget —
the one resource a long run actually has to ration — was invisible. An agent
forty-eight steps into five hundred with nothing built could not tell that from
step three, and the summary is not going to tell it either: the summariser sees
one step at a time.

One line, first in the dump, before the registers. An uncapped run gets `[Step]
step 7` with no total, because there is no total to give.

### 2. A file does not have to fit in a register

Added to the system message:

> A file does not have to fit in a register. `load(path, start)` reads any file
> of any size from any offset, so nothing is ever too big to read — it is only
> too big to read *at once*. Never rewrite or shrink a file to make it fit a
> register or the canvas; that is a length you cannot hit by generating, and
> paging costs one call.

The same shape as 0.0.7b's truncation notice and for the same reason: the agent
was pursuing an impossible goal because nothing had told it the goal was
unnecessary. 0.0.7a's sentence ("copying source material buys nothing") was aimed
at the wrong thing — condensing a 97KB spec into a working extract is often
sensible, and the run that succeeded did exactly that. Resizing a file to fit a
container it never had to fit is the part that cannot work.

## What this does not claim

Plan variance is not solved by two sentences, and 0.0.7d does not pretend the
scaffold now steers the plan. It states two true things the agent could not see.
If the next run still spends a fifth of its budget on a document, the honest
reading is that visibility is not enough, and the next letter has to either make
the deliverable itself measurable to the agent or stop leaving the plan to chance.

## Not in 0.0.7d

- **No progress signal.** The scaffold knows how many steps have passed but not
  whether anything came of them, and it says nothing about that.
- **Nothing rate-limits or reviews a plan.** A root that decides to spend its run
  writing documents is free to.
- **`[Step]` is not in the trajectory as its own field.** It is part of the
  rendered dump, which the trajectory already stores verbatim in
  `model_input.messages`, so the format is unchanged (**v3**).
