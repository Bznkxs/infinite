# Depth, Volume and Width — what a fixed context can and cannot do

*Findings from the 0.0.7f–0.0.7j experiments, and what they imply for the goal:
a context that does not grow, however complicated the task.*

---

## 1. What was measured

Four configurations of the same scaffold, on the same tasks, one variable at a
time. "Total" is a whole generation — everything sent plus everything the model
may generate — counted with the API's own tokeniser.

| | input | output | total |
| --- | ---: | ---: | ---: |
| **0.0.7f** | 30,300 | 16,384 | 46,684 |
| **0.0.7g/h** (`--short`) | 6,063 | 1,920 | 7,853 |
| **0.0.7i** (`--wide-output`) | 6,063 | 8,192 | 14,255 |
| **control** | 29,442 | 16,384 | 45,826 |

Three kinds of work were run through them: reading questions over published
long-context benchmarks, writing self-contained modules, and implementing one
module that calls into six others.

### The three kinds of work, concretely

- **read** — answer a question about a corpus far larger than the context.
  *Example:* "which country sustained the most military deaths?" against a
  39.4MB document. One fact is needed; finding it is the whole job.
- **write** — produce a self-contained module. *Example:* `config.py`, whose
  content follows from the specification and calls almost nothing else.
- **integrate** — produce code that must agree with code that already exists.
  *Example:* `step_loop.py`, the module that drives the others. Writing one line
  of it —

  ```python
  dump = registers.render(step=n, max_steps=m, run=workspace.spent())
  ```

  — requires already knowing that function's exact name, its parameters, that
  they are keyword-only, and what it returns; and the same for
  `Trajectory.append`, `prompt.build_system_prompt`, `ToolDispatcher.dispatch`,
  `summariser.summarise` and `Config`. About forty such facts, spread over six
  files, all of which must be right *in one file at one time* or nothing runs.

### A note on "children"

The scaffold's `spawn` tool starts a **sub-agent**: a fresh agent in the same
workspace with its own empty registers, its own trajectory and its own step
budget, which the parent waits for. The reconstruct task is done this way — a
root agent delegates each module to a child.

"Four children" below therefore means the same job was given to four separate
sub-agents in turn, each starting from an empty context, with 70, 90, 150 and
110 steps, some of them handed a pre-written interface document. That is there
to rule out explanations other than the context: one failure could be a bad
plan or bad luck, but four independent attempts failing the same way — and one
attempt at a larger context succeeding immediately — leaves the context as the
variable.

## 2. Results

| work | 46k | 8k | 14k (wide output) |
| --- | --- | --- | --- |
| **read**: one fact from 245KB–39.4MB | ✅ | ✅ **same answers, same mistakes** | — |
| **write**: a self-contained module | 9.5 lines/step | 1.3 lines/step | **10.3 lines/step** |
| **integrate**: `step_loop.py`, six imports | **1,043 lines, complete, in one run** | 0 lines in 420 steps | 0 lines, 4 children |

Read: 23 of 24 reproducible benchmark instances at 7,853 tokens, corpora up to
39.4MB (17 steps, 172 seconds for the largest — five thousand times the
context). Run head-to-head at both ceilings, the answers are identical,
*including the one both get wrong*.

Write: raising only the output cap, with the input geometry unchanged to the
character, took code generation from 1.3 to 10.3 lines a step and truncated
generations from a quarter to none.

Integrate: four sub-agents in turn, 420 steps between them, each with 8,192
tokens of output room (median usage 1,219 — they were not short of room to
write) and the last of them with a pre-written `API.md`, produced nothing at
all; a fifth managed twenty lines in 110 steps. The control —
same file, same code on disk, same brief, same `API.md`, only the context larger
— replaced all six stubs with **1,043 lines carrying no `NotImplementedError`,
importing cleanly with eleven exports**, and smoke-ran the loop against a fake
client (five steps, cut-off handling correct, trajectory written) inside a
70-step budget. Verified independently afterwards, not taken on the agent's
word.

## 3. The three costs of a job

The results separate cleanly along three axes, and only one of them touches the
context.

### Depth — how much material there is

The corpus size. **Paging handles it completely.** `load(path, start)` reads any
file at any offset, so material of any size is reachable through a window of any
size; what grows is the number of reads, and reads batch (0.0.7e) and parallelise
(0.0.7f). The BABILong sweep is the proof: 245KB and 39.4MB cost 8 and 17 steps
respectively — a 160× increase in material for a 2× increase in work, because
`grep` narrows before the window is ever used.

**Context requirement: O(1).** Nothing about a bigger corpus asks for a bigger
context.

### Volume — how much has to be produced

The output size. **Steps handle it, given room to generate.** 5,500 lines is
about 70,000 output tokens however it is sliced; at 1,920 tokens a step that is
at minimum 36 perfect steps and in practice several hundred, at 8,192 it is
comfortable. The failure at 1,920 was not that the agent could not see enough —
it was that it could not *say* enough per turn, and a quarter of its generations
were cut off mid-sentence and discarded.

**Context requirement: O(1) input; the output cap is a throughput coefficient,
not a wall.** You can always write a file in more, smaller pieces.

### Width — how many facts must be true at once

The **working set**: the number of distinct facts that must be simultaneously
live to make one decision correctly. Implementing `step_loop.py` means calling
`RegisterFile.render`, `Trajectory.append`, `prompt.build_system_prompt`,
`tools.ToolDispatcher.dispatch`, `summariser.summarise`, `config.Config` — with
their exact names, argument orders, keyword-only markers, return shapes and error
behaviours. Roughly forty facts, and they must be *mutually consistent* in a
single generated file.

**This is the one that does not page**, and section 4 is why.

## 4. Why width resists paging, in detail

### It is a granularity problem, not a volume problem

Forty signatures is perhaps 2KB of text. That is not much material — the same
agent routinely reads 39MB. The difficulty is that those 2KB are *scattered
across six files* and the only retrieval primitive is a page.

At 0.0.7g's geometry the canvas is 1,536 characters. Getting one signature costs
one page — a page mostly full of code the agent did not need. Forty facts is
therefore forty pages, and forty pages is more than the working set of the whole
run. So the agent reads, and reads, and the earlier facts fall out of context
before the later ones arrive.

The 150-step child made **345 tool calls, of which almost all were reads**, and
finished with:

> *With only two steps remaining, I need to write the step_loop.py
> implementation now, even though I'm uncertain about the exact signatures for
> run_step, call_model, StepOutcome…*

That is not a model failing to try. It is a model that never accumulated enough
simultaneous certainty to commit, because nothing in the scaffold lets it *hold*
what it learned.

### The working set is much smaller than the context

The context is not the agent's memory. Most of it is spoken for:

| | 0.0.7f | 0.0.7g/i |
| --- | ---: | ---: |
| fixed prose (system message + tool schemas) | 5,017 tok | 3,361 tok |
| system-written registers (last result, cut-off flag, last step, summary) | ~4,734 tok | ~943 tok |
| **agent-controlled (canvas + free registers + target)** | **~20,689 tok** | **~1,261 tok** |

The nominal context ratio between the two is **5.9×**. The ratio of what the
agent can actually put something in and keep is **16.4×** — because the fixed
prose is a constant, and a constant is ruinous when the total is small. At
0.0.7g the scaffold's own explanation of itself is 43% of the request and the
agent's usable memory is 16%.

About 1,261 tokens holds perhaps twenty short interface facts, if the agent
spends every register on them and nothing else. It needs forty. **That is the
whole of the failure**, and it explains why the threshold sits between these two
configurations rather than somewhere more interesting.

### Why the digest does not rescue it

Every run in this series opened by writing a digest of the specification, against
the scaffold's explicit advice, and for five runs that looked like avoidance. It
is not. **A digest is the model's answer to width** — it is trying to build
exactly the compact interface record this section says is missing — and at 46k
it works, which is why the successful run's children were briefed from a fixed
`notes/API.md` and built from it.

At 6k it fails for the same reason the source files fail: the digest is 7.6KB and
the canvas is 1.5KB, so holding it costs five pages that displace each other. The
agent writes the right artefact and then cannot keep it open.

### The human comparison

No programmer holds forty signatures in their head either. They have
jump-to-definition, autocomplete, a type checker and a failing test that names
the exact mismatch. Their *working memory* is small and their *retrieval* is
precise and instantaneous.

This scaffold gave the agent a pager and no index. It is the retrieval that is
missing, not the memory.

## 5. What changes when the context grows

Not what one would expect. The value of extra context is a **threshold, not a
slope**.

| work | below the threshold | above it |
| --- | --- | --- |
| read | already fine at 8k | **no further benefit** — 46k answers no question 8k missed, and misses the same one |
| write | throttled by the output cap | **no benefit from input**; the fix was output, at constant input |
| integrate | thrashes, produces nothing at any step budget | works immediately |

Extra context buys nothing at all until the working set fits, and nothing more
once it does. The reading results prove the ceiling side (46k is not better than
8k over 39MB); the integration results prove the floor side (0 lines against 1,043 across
the same boundary).

This matters for the project's premise, because it means **"how much context"
is the wrong question**. The right question is "what is the working set of this
decision, and can the agent obtain and keep it".

## 6. Does any functionality *require* the context to grow?

The sharp version of the question: is there work whose context demand rises with
task complexity, so that a fixed context is eventually defeated?

### In principle: no

A fixed context plus unbounded reliable storage plus the ability to read and
write it is a Turing machine — the tape is the workspace and the head is the
step loop. The project's own design tests say so ([Design Tests (Top
Down)](Design%20Tests%20(Top%20Down).md)). No computable task is out of reach
for want of context; what grows is the number of **steps**, not the size of the
window.

So nothing in the evidence above is an information-theoretic wall. The control's
625 lines could in principle have been produced at 6k, by an agent that
serialised its own reasoning perfectly across four hundred steps.

### In practice: yes, unless something holds the working set

What defeats the small configuration is not computability but **convergence**.
Each re-derivation of a fact is an opportunity to get it wrong or to disagree
with a fact derived twenty steps ago; the agent can feel that risk, and the
rational response to uncertainty is to gather more rather than commit. So it
reads forever. Four children, 420 steps, no lines: not a machine that ran out of
tape, a machine that never became sure enough to write.

### But the demand is bounded by coupling, not by size

Here is the encouraging part, and the reason the project's goal is reachable.

**W is not a function of how big the system is. It is a function of how coupled
it is, and of how precisely facts can be retrieved.**

- A hundred-module system where each module calls three others has the *same*
  per-decision working set as a ten-module system with the same fan-out. Total
  size adds depth, which pages.
- Every decision has a *local* working set. Global properties are reached by
  composing local decisions, which is what modular design is for and what the
  fan-out of a call graph measures.
- Retrieval granularity is a scaffold property, not a task property. Forty facts
  at one page each will not fit any small context. Forty facts at one *line* each
  is 2KB and fits comfortably.

So the honest answer is: **no functionality requires the context to grow with
complexity, but several require the working set to be held somewhere, and this
scaffold currently offers nowhere to hold it.** The context is doing that job by
accident, which is why making the context smaller broke it.

Tasks with genuinely irreducible width do exist — dense constraint satisfaction,
global type inference, anything where every fact constrains every other. For
those, the working set must be externalised and *algorithmically* traversed
(the stack discipline the design docs describe), which costs steps rather than
context. That is the correct trade for this project.

## 7. What to do next

Ordered by expected value against the goal — fixed context, arbitrary task
complexity. Each item names the axis it attacks.

### 7.1 Precise retrieval — turn width into depth *(the main one)*

A `lookup(symbol)` tool backed by an index the scaffold maintains over the
workspace (Python: an AST walk; in general: ctags), returning one line — the
signature, its file and line, its return shape. Then:

- forty facts cost forty *lines*, about 2KB, not forty pages;
- with 0.0.7e's batching, six lookups fit in one step, so a working set is
  assembled in ~7 steps instead of ~40;
- the result fits in the canvas *at once*, which is the condition for committing.

This is the single change that converts the failing axis into the passing one,
and it needs no more context. It is also what every human tool does.

### 7.2 Pinned registers — let a working set survive

Registers are already the right idea and already too small and too volatile:
the free ones are 208 characters, and the two large ones are written by the
system (`3` the last step, `4` the summariser, which cannot be told what to
keep). Add a small number of **pinned** slots — agent-written, never overwritten
by anything else, exactly as register 2 already is for the target.

An agent could then accumulate its interface record across steps instead of
re-deriving it. The mechanism exists; it is one register generalised to K.

### 7.3 Verify instead of read — get the interface from the tooling

A human learns a signature faster from a failed import than from reading the
file. `python -c "import m"`, a type checker, or the test suite names the exact
mismatch in one line. Encouraging — or scaffolding — a write-then-verify loop
replaces *acquiring* forty facts up front with *correcting* the two that were
wrong, which is a working set of two.

### 7.4 Shrink the constant, not just the variables

At 8k, 43% of the request is the scaffold explaining itself and the agent
controls 16%. 0.0.7g already cut the fixed prose by a quarter; below about 6,000
tokens there is no room left to work in. Every further byte of system message and
tool schema is a byte of working set, and that trade should be made explicitly
from now on — the `max_context_tokens` ceiling makes it visible, and it should
be reported as *usable working set*, not just total.

### 7.5 Measure the working set, and predict the thrash

The scaffold can estimate W for a task before dispatching it: count the distinct
symbols a target file references, or the fan-out of the module in the call graph.
A parent could then decline to hand a wide job to a narrow child, or split it.
Nothing currently distinguishes "write `config.py`" (W small, succeeded in 40
steps) from "write `step_loop.py`" (W large, failed four times), though the call
graph says plainly which is which.

### 7.6 Find the actual threshold

The experiments bracket it crudely: fails at ~1,261 tokens of agent-controlled
memory, succeeds at ~20,689. Bisect it — run the same `step_loop.py` task with
the canvas at 4k, 8k and 12k characters, everything else fixed. The number
matters, because 7.1 and 7.2 are worth building in proportion to how far below
the threshold a small configuration actually sits.

## 8. How to tell whether it worked

The target is not a benchmark score; it is the disappearance of a specific
failure. After 7.1 and 7.2, at a fixed ~8,000-token context:

- `step_loop.py` — or any module with six-way fan-out — is implemented by one
  child in fewer than 60 steps;
- the reads-to-writes ratio of a coding child falls from 30:1 toward 3:1;
- no child spends more than a third of its steps establishing interfaces;
- the reading results do not move, because nothing in 7.1–7.4 touches depth;
- and the digest habit disappears on its own, because the artefact the model was
  reaching for is now something the scaffold provides.

The last of those is the real test. Five runs wrote a digest because the scaffold
had no answer to width. When it has one, they should stop.
