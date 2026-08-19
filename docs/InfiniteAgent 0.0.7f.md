# InfiniteAgent 0.0.7f-simple

0.0.7e's run is the closest the series has come: **3,981 lines, eleven of the
thirteen modules, faithful to the spec**. It did not finish, and the reason is
not that it ran out of steps. It ran out of *clock*: 17 and a half hours in, with
`agent.py` half written, the API went down for a quarter of an hour and both the
child writing it and the root waiting for it ended their segments.

So 0.0.7f is about the clock. Nothing here changes what a step contains — every
letter so far has done that — and everything here changes what a step costs while
the run stands still waiting for it.

## What the 0.0.7e run showed

0.0.7e's own change landed. Batching went from the 1.8 tool calls a step that
four runs had spent to **2.49**, and the children that did the writing ran at
2.7–3.8; steps with four, five and six calls in them stopped being rare. That is
the paragraph working, and it is not what this letter is about.

Where the 17.5 hours went:

```
1,368 steps across 11 agents
  10.8 h  generating          28.5 s a step
   5.3 h  the summariser      13.9 s a step, 32% of the total
   0.2 h  tools
```

```
root: 14 steps, 10 children, 16.3 h of them
  step  6   23,159s + 842s                      asked for together, run one at a time
  step  7    6,692s
  step 13   11,391 + 2,911 + 928 + 759 + 478s   five children, 4.6 h serial, 3.2 h if not
  step 14    5,837 + 5,652s
```

Three findings, one change each.

**1. The summariser is a third of the run, and all of it is dead time.** 0.0.6
made the call cheap in tokens — a small model, no effort — and it is cheap: 13.9
seconds against a 28.5-second generation. But it sits *between* two steps, so
every second of it is a second in which the run does nothing. Over 1,368 steps
that is 5.3 hours of a 17.5-hour run spent waiting for a paragraph.

**2. Children asked for together ran one after another.** 0.0.7e's own
paragraph tells the agent that a step is one generation however many calls it
holds, and to ask for everything it already knows it needs in one step. The root
did exactly that — five `spawn` calls in step 13 — and the scaffold ran them
serially. The advice was true for `bash` and `load` and false for `spawn`, and
the false half is the expensive one: 16.3 hours of spawns where the slowest child
of each step would have been 13.1.

**3. A child asked for a length spent six and a half hours failing to hit it.**
The root's spawn prompt said *"write a digest … (aim 6000-10000 characters,
dense)"*. That child ran **278 steps over 6.4 hours**, made one bash call in
264 of them, and **269 of its 278 steps measured a length** — `wc -c`, `awk
'{print length}'`, a Python one-liner summing the lines. It left 44 versions of
one 12KB file in its scratch: `v2`, `v5`, `v6`, `v9`, `v14`, `v15`, `v17`,
`v18`, `v21`, `d4`, `d5`, `d6`, `try`, `cand`, `cand2`, `new`, `new2`, `final`.

This is the 0.0.5 summariser loop for the third time — *a model cannot hit a
character budget by generating, and giving it the means to check turns that into
an iteration it has no way to win* — and 0.0.7d already wrote the sentence that
should have stopped it. That sentence said *never shrink a file to fit a register
or the canvas*, and this budget came from neither. It came from **the agent
above it**, which is a place the scaffold had never said anything about.

## The changes

| | 0.0.7e | 0.0.7f | Why |
| --- | --- | --- | --- |
| the summariser | between two steps | **alongside the next generation** | Finding 1: 32% of the wall-clock, none of it doing anything. |
| several `spawn` calls in one step | run one at a time | **run at the same time**, `spawn_workers` (4) at once | Finding 2: they were asked for together. |
| `spawn` | inherits the parent's whole step budget | **takes `max_steps`** | Finding 3: nothing bounded the 278-step child, and nothing reported on it until it returned. |
| `spawn`'s description | — | **"never ask for a given number of characters"** | Finding 3, at the place the mistake is made. |
| system message | "never shrink a file to fit a register or the canvas" | **"never rewrite a file to hit a character count"** | Finding 3, generalised past the container it was written about. |

### The summary of step N is written during step N+1

The summariser now runs on a thread of its own, started when a step ends and
collected after the *next* step's generation comes back. So the register the
agent reads is one step behind: the dump of step N+2 holds the summary through
step N.

**Nothing is lost by that**, and this is the argument the change stands on.
Register 3 always holds the step immediately before, so what the agent reads is a
pair: the summary through N, and step N+1 in full. Together they still cover
every step of the run. What the delay removes is the *overlap* the two used to
have — the summary of step N and register 3's copy of step N both described step
N — not any part of the history.

What it buys is all of finding 1. The generation is twice the summariser's
length, so the collection finds the thread already finished: measured on a real
run, `summary_wait_s` was **one millisecond** a step against 2–4.5 seconds of
summarising. The chain is unbroken — each summary is still written from the one
before it and one step, never the history — and the trajectory still carries one
line per step with the summary that followed it, because the line waits for it.

A summary still in flight when a segment ends is waited for and recorded, so the
`final` that `--resume` reads holds the register file as it really stood.

### Children of one step run as one step

Two or more consecutive `spawn` calls in a step are started together, at most
`spawn_workers` (4) at a time, and their registers are written afterwards in the
order the model asked for them — so a concurrent step leaves the register file
exactly where a serial one would, with register 0 holding the last call of the
step rather than the first child to finish.

Only a run of `spawn` calls goes concurrent. Everything else keeps the order it
was written in: a `bash` before a `spawn` may well be what the child is meant to
find on disk, and the shell is one session that cannot run two commands at once
anyway.

On a three-way fan-out over a 250KB article, three children summing 62.9 seconds
finished in 24.1 — the slowest of them, which is the whole point.

The ceiling is there because 0.0.7c already named the hazard: *nothing
rate-limits the fan-out, and a root that spawns five children in one step is part
of why the API pushed back.* Now that they are genuinely concurrent, five
children is five agents and five summarisers on the API at once, and
`spawn_workers` is the number that says how many.

### A parent can say how big a job it thinks it is asking for

`spawn` takes an optional `max_steps`. Omitted, the child inherits its parent's
budget, which is what it always did. Given, it is the child's budget, and a child
that runs out returns the error it always returned — the parent decides whether
to re-dispatch, ask for less, or do it itself.

This is not a fix for finding 3; the two sentences are. It is what makes the
finding *visible*: the root that lost 6.4 hours could not see the loop, because
the only thing a parent ever learns about a child is what it says when it comes
back. A budget is the one thing a parent can say in advance, and with children
now running concurrently it is also what bounds the whole fan-out — a step of
five children costs the slowest, so the slowest is the one worth bounding.

The parent also gets `steps` back in the spawn payload, and the child's
`agent_id` in the trajectory, so what a child cost is on record next to what it
returned.

## What the 0.0.7f run did

**The series goal is met.** Same task, same spec, one letter apart:

| | 0.0.7e | 0.0.7f |
| --- | --- | --- |
| wall-clock | 17.5 h | **2 h 43 m** |
| steps / agents | 1,368 / 11 | 580 / 12 |
| lines of the package | 3,981 | **5,529**, all thirteen modules |
| `agent.py`, `main.py` | never written | 772 and 423 lines |
| offline test suite | none | 5,017 lines, **677 passing** |
| the acceptance run | never reached | **ran, and was right** |
| how it ended | died on an `overloaded_error` | `ok: true` |

The acceptance test is the part the whole design exists for: the reconstruction
ran *itself* over a 367KB Wikipedia export and answered a three-part question —
92 of 102 counties, a 219-to-212 House vote, 23 March 2010 — in five steps,
paging the file with `grep` and `load` and never holding it whole. Every answer
checks against the article; every one is quoted with its source sentence. Its
trajectory is a valid v3 file with `spawn_workers` in its config.

The three changes, measured:

- **The summariser cost 2.62 hours and the loop paid 0.65 of them** — 75% of it
  written while the next generation was running. On the reading-comprehension
  run, where generations are longer than the summaries, the wait was one
  millisecond a step.
- **Four fan-out steps ran 11 children.** Their durations sum to 3.94 hours; the
  steps took 2.19. That 1.75 hours is the letter's second change, in one number.
- **Every child was given a budget** — 45, 55, 60, 70, 90, 120 steps — and every
  one of them came back. No agent spent a run of steps measuring a length: the
  77 `wc -c` calls in the run are confirmations after an append, not a rewrite
  loop.

Two things the run says that this letter did not predict. The root still
delegated three digest children before writing any code, and they produced 257KB
of contract from a 114KB spec — the instinct 0.0.6 named is structural, and
bounding and parallelising it made it cost twenty minutes rather than eight and
a half hours, which is containment and not a cure. And calls per step *fell*
slightly, 2.49 to 2.58 at the top but 1.91 for the root, because a root whose
steps are mostly `spawn` has less to batch.

## Not in 0.0.7f

- **Nothing detects a loop.** Three letters have now deferred this, and 0.0.7e's
  run made the case again: 269 steps in a row measured a length and the scaffold
  had nothing to say. This letter states the truth in two more places and
  bounds the damage with a budget; it does not notice.
- **A failed segment still needs a person.** The run that produced this letter
  ended because the API was down for fifteen minutes; `--resume` was built for
  exactly that and nothing ran it. Nothing here changes that either.
- **`max_depth` is still 1**, the register layout is still **4**, the trajectory
  format is still **v3** — `timing` gains `summary_wait_s` and `summary_s` moves
  off the step's own clock, which is a field added and a meaning documented, not
  a shape changed.
