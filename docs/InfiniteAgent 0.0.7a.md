# InfiniteAgent 0.0.7a-simple

0.0.7 is an **iteration series**, not a design: one goal, one letter per attempt,
each one a measured change against the run before it. The goal is the hardest
task the scaffold has been given — **the agent reconstructs the scaffold from its
own specification** — and the series ends when a run does that.

Where 0.0.4 → 0.0.6 fixed the summariser, this series is about what the steps are
spent on. The summariser is now a minor cost (47% of wall-clock in 0.0.6, from
94%, and 1,376 output tokens a step, from 15,000), and it is no longer what
stands between a run and a finished reconstruction.

## What the 0.0.6 run showed

106 steps, 5 agents, ~60 minutes, and this is everything it produced:

```
infinite_agent/config.py      196 lines
infinite_agent/registers.py   340 lines
.scratch/builder/contract.md  42,358 bytes   <- a re-transcription of the spec
.scratch/builder/part7_*.md    9,309 bytes   <- more of the same
```

536 lines of code from 106 steps, against a 51KB document describing code that
does not exist. Three findings, each one a change below:

1. **The agents re-describe the task instead of doing it.** The spec is 80KB and
   the canvas holds 20KB, so it does not fit; the response was to copy it into a
   "contract" — which does not fit either, and costs the steps that were meant to
   write the modules. Nothing in the scaffold told them that `load` re-reads a
   file whenever they want, so copying buys nothing.
2. **A deep tree serialises and pays to brief itself.** `max_depth` was 3, and
   the run built a four-level chain: root → d1 → d2 → d3, with the three
   ancestors sitting `blocked` for 25+ minutes because `spawn` is synchronous.
   Every level wrote a briefing document for the next.
3. **A step could not hold a module.** `workspace_tokens` was 8192; the two
   modules that did get written are 196 and 340 lines, which with thinking is
   most of a step. A step that should write one file wrote part of one.

Two smaller things the same run established, both fixed here:

4. **`spawn` at the depth floor is a tool that cannot succeed**, and it was
   offered anyway. One agent called it five separate times over 34 steps — steps
   4, 11, 17, 21, 25, 28 — because the refusal lives only in register 4, which is
   rewritten every step (§ below).
5. **The summary budget is still slightly too generous.** At 3000 against a 4096
   register, the median first attempt was 3570 and a quarter of steps bought a
   retry.

## The changes

| | 0.0.6 | 0.0.7a | Why |
| --- | --- | --- | --- |
| `max_depth` | 3 | **1** | Root fans out to leaves and no further. No chains, no serialised ancestors, one briefing hop. |
| `workspace_tokens` | 8192 | **16384** | A step can write a whole module. |
| `summary_target_chars` | 3000 | **2400** | The ordinary overshoot then lands inside the register. |
| `spawn` at `depth == max_depth` | offered, refused on call | **not offered** | See below. |
| system message | — | **two sentences on where steps go** | See below. |

### No `spawn` tool at the floor

`Agent.can_spawn` is now `can_spawn and depth < config.max_depth`, so an agent
that cannot recurse does not see the tool. The plumbing already existed — it was
built for 0.0.4's summariser sub-agent — and this is the same argument 0.0.4 made
for that: *a tool that is merely undocumented is not a tool that is unavailable.*

An agent that asks for it anyway gets told **why**, not that the tool is unknown:

```
error: no `spawn` tool at depth 1 (max_depth=1); do this work yourself
```

This also fixes a decay the run made visible. The refusal was recorded in
register 4 at step 4, paraphrased shorter each step, gone by step 9 — with 800
characters of the register still free — and the plan it contradicted came back.
Learned again at 11, gone by 14, tried again at 17, 21, 25, 28. **A summary
rewritten whole every step has no mechanism for permanence**: a fact survives
only by being re-selected every single generation, and re-framing loses it long
before truncation would. Nothing here fixes that in general; it removes the one
instance that a fixed property of the scaffold should never have depended on a
summary for.

### Two sentences about where steps go

Appended to the system message:

> Spend your steps on the thing you were asked for. Files you can read are not
> context you have to save: `load` re-reads any file from any offset, as many
> times as you like, so copying source material into a file of your own buys
> nothing — read the part you need when you need it. Write plans, notes and
> specifications only where they change what you do next, and keep them short; a
> step that produces the deliverable is worth more than a step that produces a
> description of it.

This is the one prompt change in 0.0.7a, and it is deliberately about *paging
being cheap* rather than about being brief. The transcription is a rational
response to a false belief — that what leaves the canvas is lost — and stating
the truth is a smaller intervention than forbidding the behaviour.

## What is unchanged

Registers, the register layout (**4**, so 0.0.4–0.0.6 runs still resume), the
five tools minus the floor rule, the summariser mechanism, the firewall, the
scratch directory, the trajectory format (**v3**), termination. 0.0.7a changes
three numbers, one tool list, and one paragraph.

## How the series is measured

Per run, on the reconstruct task:

- **lines of code written** in the workspace, and how many of the spec's modules
  exist — the only measure of the goal;
- **bytes of prose written that are not code** — the 0.0.6 failure, as a number;
- steps used, agents spawned, tree depth and how long ancestors spend blocked;
- summariser: retries, truncations, share of wall-clock, output tokens per step;
- repeated identical actions and repeated tool errors, which is where a loop
  shows up first.

A letter ends when its run either reconstructs the scaffold or fails in a way
that names the next change.

## Not in 0.0.7a

- **Nothing about the decay of register 4 in general** (finding 5 above). The
  fix — a part of the summary the model cannot rewrite — is a register-layout
  change, and this letter is deliberately small.
- **`spawn` is still synchronous.** With `max_depth: 1` a blocked ancestor is one
  level deep and waits for one child at a time, which is a smaller version of the
  same cost, not its removal.
- **No change to how the spec is delivered.** It is still one 80KB file the agent
  has to page through; whether that is the right shape for the task is a
  question for a later letter, and the first one to answer is whether an agent
  that knows paging is cheap stops copying it.
