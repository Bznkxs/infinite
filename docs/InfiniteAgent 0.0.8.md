# InfiniteAgent 0.0.8 — what the frame scaffold did

*The build note for the three design letters:
[0.0.8a](InfiniteAgent%200.0.8a.md) (values move without a generation),
[0.0.8b](InfiniteAgent%200.0.8b.md) (precise at the frame, lossy above it) and
[0.0.8c](InfiniteAgent%200.0.8c.md) (the brief is the frame). Those are
arguments; this is what happened when they were run.*

---

## 1. What shipped

| letter | change |
| --- | --- |
| 8a §3 | the register file is `$R0…$RN` and `$REGDIR/0…N` around every `bash` call; 0-4 refuse a write |
| 8a §4 | `register_id` is optional on every tool but `set` — an unnamed register is pinned |
| 8a §5 | `--frame`: 0.0.7i's input with a 4,096-char canvas |
| 8a §6 | `goal_file`: a brief by reference |
| 8b §2 | the invariant as four sentences of system message |
| 8b §4 | `facts.md`, the run's memo table, and 7.1's `lookup` beside it |
| 8c §2 | `spawn(goal, read, write, check, …)` — the scaffold renders the brief |
| 8c §3 | the scaffold runs `check` when a response lands; a return that fails it is refused |
| 7.3 | and after every step, with the verdict one line above the register dump |
| 8c §5 | a child's steps debit its parent's budget |
| 8c §6 | no depth ceiling; the agent sees its depth; a parent may allow one |

## 2. What it cost

7.4 asked for the trade to be made explicitly rather than discovered, so:

| | 0.0.7g | 0.0.8 |
| --- | ---: | ---: |
| system message | 4,034 chars | 5,700 |
| tool schemas | 3,924 | 5,600 |
| **fixed constant** | **3,060 tokens** | **~4,340** |
| dump ceiling (`--frame`) | 6,429 chars | 10,225 |
| **agent-controlled working set** | **3,280 chars** | **5,840** |
| one generation | 7,453 tokens | ~16,400 |

The fixed half grew 42%. Two schemas are new (`lookup`, `resume`), `bash` carries
the sentence that makes the registers reachable, and the frame discipline is
four sentences. Against that, the space the agent controls grew 78%. Both
numbers are now reported by `Config.context_tokens`, which is 7.4's actual ask.

### The brief pays for its schema, and it is not close

0.0.8c §9.1 asked for this to be measured the way 0.0.7g measured prose — fixed
tokens before and after, against briefing tokens generated before and after —
and it comes out one-sided.

| | fixed cost | generated per spawn |
| --- | ---: | ---: |
| 0.0.7 `prompt` | 1,681 chars of schema | median 2,545 chars (n=34) |
| 0.0.8 named brief | 1,690 chars of schema | median 545 chars (n=9) |

The fields replaced a long `prompt` description almost exactly, so the schema is
**nine characters** more expensive, and what a parent generates to brief a child
fell by a factor of 4.7. The 42% growth in the fixed half above is `lookup`,
`resume` and the frame prose; none of it is the brief.

## 3. Reading did not move, which is the prediction

§8 said the reading results should not move, because nothing in 7.1-7.4 touches
depth. They did not.

| instance | 0.0.7g `--short` | 0.0.8 `--frame` |
| --- | --- | --- |
| babilong 1M-qa2-0 | PASS, 10 steps | PASS, 8 |
| babilong 10M-qa2-0 | PASS, 17 | PASS, 9 |
| babilong 512k-qa3-1 | PASS, 11 | PASS, 18 |
| ∞Bench longbook_choice-0 | PASS, 13 | PASS, 9 |
| ∞Bench longbook_choice-1 | PASS, 6 | PASS, 8 |
| ∞Bench longbook_qa-0 | PASS, 10 | PASS, 7 |

Six of six, four of them in fewer steps. A 10MB corpus is still answered in nine
steps at a fixed 8,400-token input.

## 4. The fixed-context property, measured rather than asserted

The suite includes a set of tests that scale a task along each axis and assert
the largest request does not move: forty steps against four, a five-frame stack
against a one-frame stack, a 4MB read against a 4KB one, ten thousand lines
written. It holds, and it holds in the live runs too — the diagnostic run below
put five agents at five different depths on the API and the largest request any
of them made was 7,742 tokens against a smallest-largest of 6,717.

## 5. Transit costs nothing, so §3 stands on §4 alone

0.0.8a's first open question was whether transit — "output tokens spent on
literals that already existed verbatim in a register" — costs anything
measurable. Every step now records it. Over 34,042 characters of generated tool
arguments in the step_loop run, the answer is **zero**: not one register value
was retyped, and the shell reached a register four times.

So registers-as-files is justified by the working set (§4) and not by the
copying it saves, exactly as the letter's own fallback said. The mechanism stays
— it is one sentence and it removes four schemas that were never written — but
it should not be sold as saving output tokens.

## 6. The step_loop probe

The control is 0.0.7i's failure: `infinite_agent/step_loop.py`, a stub in a
workspace whose nine sibling modules are already written, a module that calls
into six of them. Two 0.0.7 children spent 240 steps on it and wrote nothing.
§8's target is *implemented in fewer than 60 steps*.

One reference point had been misread until this run measured it. The 0.0.7
attempt that *succeeded* on this task was not at `--short`: it ran at **22,460
tokens of input**, the full 0.0.7f geometry, and it took 82 steps across two
agents — one of which spent 68 of them writing a digest of Part 7 before the
implementer got 14. So the interval to close was 6,063 (fails) to 22,460
(succeeds), and 0.0.8's `--frame` sits at 8,053.

| run | input | steps | outcome |
| --- | ---: | ---: | --- |
| 0.0.7g/i `--short` | 6,063 | 240 across two children | nothing written |
| 0.0.7f, the control | 22,460 | 82 across two agents | passed |
| **0.0.8 A, `--frame`** | **8,053** | **56 of its own, 80 charged** | **391 lines, check passed** |
| 0.0.8 B, `--frame --max-depth 1` | 8,304 | 80 | 457 lines at step 80, refused |

Arm A is §8's target met at a third of the input the 0.0.7 success needed, and
its whole subtree — including a 24-step child that failed — came out of one
80-step budget.

Arm B is the more instructive one. It wrote the entire module in a single
generation on step 80, the check ran for the first and only time, and it failed:

```
ImportError: cannot import name 'ToolRegistry' from 'infinite_agent.tools'
```

Seventy-nine steps of acquisition, one of writing, none of correcting, and a
one-line error it never got to see. The diagnostic run before it died the same
way with the same error at depth two. That is what §7.5 below is about.

## 7. What the runs said that the letters did not

Four findings, all from trajectories rather than from argument.

### 7.1 A goal in a file is a goal the agent forgets

The worst 0.0.8 child reproduced 0.0.7i's failure exactly — 27 steps, no
output — and the trajectory says why, and it is not width. It re-read the same
four files on almost every step: its own instruction, its parent's `goal_file`,
the stub, `facts.md`. 0.0.8a's argument-by-reference had moved the goal off the
parent's generation and onto the child's disk, and nothing in the child's
context held it.

So the frame is now *in the system message*: the one-sentence goal, where the
work goes, and the check. All three are names the caller already held and all
three are what 0.0.8b §2 says must be true at every model call. The long form
stays by reference in the brief, which is read once.

### 7.2 Pass-through delegation, and what unbounded depth did

With `max_depth` removed, the root forwarded its entire goal at step 4, its
child forwarded the same goal at step 12, and so on to depth four. The budget
decayed 80 → 58 → 32 → 15 → 8 and no frame wrote the module. Roughly 39% of the
run went on frames orienting themselves and then delegating.

Charging worked as 0.0.8c §6 promised — the chain terminated on budget rather
than on a ceiling — but it did not *deter*, because forwarding a goal is free
under charging: it costs the parent what doing the work would have cost, minus
the steps the child spends re-orienting, which the parent never sees.

Part of this was the scaffold's own wording. "Spawn when the subgoal needs facts
you do not have" is trivially true of every subgoal at the start of a run, when
you have no facts. The rule now names the move it was meant to forbid: *handing
a child your own goal unchanged is not a descent.*

### 7.3 `lookup` was not used, because a symbol is the wrong unit

Not once, in either long run. Asked to implement a module that calls into six
others, the agent ran one `grep` for every `def` in the package and put 75 lines
in a scratch file — which is 7.1's artefact, built by hand, in one call.

What it wanted was not a fact but a *surface*: the interface of a module, all at
once. One symbol at a time is six calls to get what one grep gets. So `lookup`
now takes a path or a dotted module name and returns every definition in it,
which is what the grep was reaching for and, unlike the grep, carries real
signatures rather than first lines.

### 7.4 Two things a live run finds that a test cannot

- `set_target` was advertised at 1,536 characters and rejects at 704, because
  `max_target_length` splits register 2 from register 4 and both the schema and
  the system message still quoted the shared number. Two whole steps lost to it
  in the first six. A 0.0.7g bug.
- The summariser overshot its register on thirteen attempts across two runs,
  median 1,598 characters against a 1,536 limit and a 600-character budget it
  was told. That is 0.0.5's lesson at this scale — the material sets the length,
  not the prompt — so register 4 is 2,048 in `--frame` and the overshoot is free
  again.

### 7.5 The check was a gate when it needed to be a signal

Arm B and the diagnostic run both wrote a module that was one line from passing
and died against a check they had never run. 0.0.8c §3 makes the check the thing
that stops a lossy caller being unsafe, and it does — but only at the pop, which
is after the work.

7.3 is the other half and had been left as advice: *a human learns a signature
faster from a failed import than from reading the file.* That is only true if
the failed import happens. So the scaffold now runs the check after every step
and puts one line at the top of the dump:

```
[Check] FAILS (exit 1): ImportError: cannot import name 'ToolRegistry' … — tool_output/…
```

It is affordable for the reason 0.0.8b §1 gives: a check is a machine operation,
so it is unbounded and costs no width. A check slower than `check_live_seconds`
stops being run that way and says so, because a test suite is a fine acceptance
test and a poor heartbeat.

The stub in this task carries that `ToolRegistry` import error itself, so under
the heartbeat the agent is told the first real interface mismatch on step one —
the fact the other arms spent forty steps grepping six modules to find.

## 8. Results

| arm | input | heartbeat | check | outcome |
| --- | ---: | --- | --- | --- |
| **A** unbounded depth | 8,053 | no | import | **passed, 56 steps** (80 charged) |
| **B** `--max-depth 1` | 8,304 | no | import | 457 lines on step 80, refused on one import |
| **C** live check | 8,302 | yes | import + no `NotImplementedError` | 80 steps, nothing written |
| **D** canvas 12,288 (7.6) | 11,386 | yes | import + no `NotImplementedError` | 80 steps, nothing written |
| **E** live check, A's check | 8,226 | yes | import | **passed, 50 steps** (77 charged) |

Three things have to be said about that table before anything is read out of it.

**It is one run per arm, on a task with enormous variance.** Three arms wrote a
complete module and two wrote none; the same scaffold, the same task, the same
budget. At 0.0.7's geometry the score was nothing written in two attempts of 150
steps each, so 3-of-5 is a real move — but 3-of-5 is not a number to tune
against.

**A/B and C/D did not get the same check.** A and B were given
`python3 -c 'import …'`; C and D were given that *and* `! grep -q
NotImplementedError`, which the stub fails outright. That was an error in
setting the experiment up: arm C cannot be read as a measurement of the live
check, because two variables moved. Arm E is the repair — the heartbeat with A's
check exactly — and it passed in 50 steps, six fewer than A, having spawned one
child that also finished. So the heartbeat costs nothing and is not what
distinguishes the arms.

**What does line up with the outcome is the check string, and it lines up
completely.** Both arms given `import` alone wrote a working module and one more
came within a single import of it; both arms given the compound check wrote no
implementation at all in eighty steps. With one run per cell that is a
coincidence as easily as a cause, and it is worth stating as a hypothesis rather
than a result: a verdict that cannot move until the work is finished is not a
gradient, and `! grep -q NotImplementedError` cannot move until the last stub
body is gone. An acceptance test that is also a heartbeat may need to be able to
get *closer*, not only to pass or fail.

**Arm D is the one result the confound does not spoil, and it is negative.**
Tripling the canvas — 1,536 → 4,096 → 12,288, a working set of 14,032
characters, an input of 11,386 tokens — produced no more code than 4,096 did.
Whatever binds this task, 7.6's bisection says it is not the size of the one
register a working set can land in. That is 0.0.8a §5's argument, and it does
not survive its first test.

What the failing arms have in common is where the steps went. C spent 80 steps
and 33 `load`s building fifteen scratch files of signatures; D spent 80 steps
and 53 writes doing the same into a bigger canvas; B spent 79 steps on it and
then wrote the whole module in one generation and never got to correct it. A and
E interleaved, and A and E passed. The failure is not that the facts do not
fit — it is that a run does not start writing until it believes it has all of
them, and nothing in 0.0.8 makes it start sooner.

## 9. What is actually left, after the runs

The letters attacked width from three directions and the runs say which of them
moved.

| | claim | verdict |
| --- | --- | --- |
| 8a §3 | values should move without a generation | works, and buys nothing: transit was 0% |
| 8a §4 | a forced destination eats the working set | works, and is free |
| 8a §5 | the canvas is what a working set must land in | **refuted by arm D** |
| 8b §2 | precise at the frame, lossy above | the frame in the context fixed a real failure |
| 8b §4 | a memo table, written by key | `facts.md` was read and never written |
| 8c §2 | a brief should name, not describe | briefs came out well-formed every time |
| 8c §3 | the check is what makes a lossy caller safe | true, and too late — hence 7.3 |
| 7.3 | verify instead of read, every step | costs nothing; did not change the strategy |
| 8c §5 | a child's steps should be charged | works; bounded the depth-4 cascade |
| 8c §6 | the scaffold should have no opinion on depth | the one run of it produced the cascade |
| 7.1 | a signature should cost a line | five calls in five runs |

The honest summary is that 0.0.8 removed a set of *clerical* costs — a forced
write, a re-typed value, an unbounded chain, a brief a parent could not author —
and that none of them is what the axis turns on. What decides the step_loop task
is when the run starts writing, and every mechanism here is available to a run
that never does.

Two of them did decide something, and it is worth separating them from the rest:
the frame in the context (§7.1), which turned a child that re-read its own goal
27 times into one that has it, and charged steps (8c §5), which turned an
unbounded chain from a hazard into a thing that runs out. Both are about
*forgetting* rather than about width. That may be the more useful reading of the
whole letter series: what a fixed context is short of is not room but continuity,
and the things that helped are the ones that gave a step something the step
before it had.

## 10. Open questions for 0.0.8d

1. **Does depth want a price rather than freedom?** 0.0.8c §9.4 asked it and
   said the evidence for `max_depth = 1` was a real run. So is the evidence
   against unbounded depth. A frame is not free — the child arrives empty and
   spends its first steps learning where it is — and the scaffold charges zero
   for that. Whether the right answer is a frame surcharge, a reserve the parent
   must keep, or something that is not a constant at all is unanswered.
2. **What makes a memo table get written?** `facts.md` exists, is named in the
   system message, and was read repeatedly by an agent that never wrote to it.
   A table nobody writes is a table nobody can read.
3. **If not the canvas, what?** 7.6's bisection ran and came back negative:
   12,288 characters of canvas wrote no more than 4,096 did. The remaining
   candidates are that the binding quantity is the *whole* input rather than the
   one wide register (0.0.7f succeeded at 22,460 and every 0.0.8 arm was under
   12,000), or that it is not a context quantity at all.
4. **How does a run get made to start writing?** Four of five arms spent between
   half and all of their budget acquiring before producing a line, and the two
   that passed are the two that interleaved. Charging prices delegation and
   nothing prices deliberation. A budget that is visibly *for* producing —
   rather than a step counter that treats a `grep` and a module as one step
   each — may be the shape of it.
