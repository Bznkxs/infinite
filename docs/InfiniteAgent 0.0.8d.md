# InfiniteAgent 0.0.8d — what progress bought

*The build note for the iteration with no design letter. 0.0.8a-c were arguments
before a build; 0.0.8d is the other order — a diagnosis read off trajectories
that already existed, a mechanism fitted to it, and then the first live runs the
project has had since. [Iterating to 0.0.8d](Iterating%20to%200.0.8d.md) is the
working document: problems ranked, pitfalls, what to do next. This is what
happened.*

---

## 1. What shipped

| § | change |
| --- | --- |
| 4.0 | `lookup` and its AST index removed — the one primitive meant to turn width into depth parsed Python only |
| 4.5 | `facts.md` created with its header by `Workspace`, so the memo table exists from step one with the agent as its only writer |
| 4.6 | `firewall.system_read()` adds the running interpreter's `sys.base_prefix`, so `python3` under the sandbox can read its own stdlib |
| 4.1 (1) | `progress.py`: every step records what durable state it changed; the streak goes in the handoff |
| 4.1 (2) | a `[Stall]` line in the dump once `stall_notice` (3) consecutive steps have left nothing behind |
| 4.1 (3) | `stall_surcharge` (1): from that threshold on, a stalled step costs itself and one more |
| — | `eval/benchmarks/width.py`: the step_loop probe as a command instead of a recipe |
| — | `eval/benchmarks/volume.py`: the infinite-writing probe, which did not exist |
| — | `eval/run.py`: `--arm`, a live `--check`, the largest request and the streaks in every row |
| — | `eval/analyse.py`: `stall / worst / lock` columns, and `max in` from the `usage` records |

262 tests to **332**, and green — the suite had one deterministic failure at the
baseline and it was 4.6.

## 2. What it cost

**Nothing, in the half that is paid for every step.** The mechanism is entirely
scaffold-side: `grep -c 'stall\|progress'` over `prompt.py` and `tools.py` is
zero, because the notice is *state* and state goes in the dump beside the budget
line rather than into the fixed constant. The only thing that moved the fixed
half this iteration is 4.0 deleting a tool, which took it from 11,738 characters
to 11,102.

| | chars | when |
| --- | ---: | --- |
| fixed half, before 4.0 | 11,738 | every step |
| fixed half, after 4.0 and after the mechanism | 11,102 | every step |
| `[Stall]` line, with its prefix | 249 | only while a run is livelocked |
| dump ceiling (`--frame`) | 10,225 | unchanged |

(Those two figures are the handoff's, measured in its workspace. The system
message quotes absolute paths, so the count moves with the length of the
workspace path — the same build measures 11,068 under a `/var/folders` temporary
directory. 0.0.8 §2 gives the same warning. What is not workspace-dependent is
the difference, and the difference the mechanism makes is zero.)

So a run that is working never pays for the measure at all, and a run that is
looping pays about 96 tokens a step to be told so — out of a budget it is by
definition wasting.

**The measure itself is one `stat` per file and no reads**, so volume is free and
only the *number* of files costs anything: 0.6ms a step on a probe workspace,
124ms on the flagship reconstruction's 6,400 files. The ignored trees are pruned
rather than filtered, which is the whole of that — walking `tool_output/` and the
trajectories and discarding them afterwards cost 353ms a step and 8.6 seconds on
a pathological workspace. The cost is recorded per agent rather than capped: a
cap would degrade the measure exactly where a livelock is most expensive.

## 3. The diagnosis, and the three detectors it kills

0.0.8's §10.4 asked "how does a run get made to start writing?" The answer is
that the question is wrong, and each way of asking it kills a detector you would
otherwise build. All of this is off the five 0.0.8 arms already on disk.

**Writing late is not the defect.** Both frames that produced a working module
wrote in the final fifth of their own budget — arm A's child at step 23 of 24,
arm E's child at 22 of 27. Arm B wrote at step 80 of 80 and failed. Late writing
is what passing looked like, and §5 below makes that five frames across two
tasks.

**Writing *something* is not the test.** The two arms that left the 99-line stub
untouched were the busiest writers: 43 and 53 write calls, 33,490 and 38,841
generated characters, against passing arm E's root at 30 and 27,373. Any "did it
produce output" detector reads C and D as healthy for eighty steps.

**Re-reading is universal, so it predicts nothing.** Every frame in the five arms
read a path it had already read on **75-93%** of its steps, and 12-26% of its
`bash` outputs were byte-identical to one that frame already had. Arm D read a
99-line file **52 times in 80 steps**; arm E's root — a passing arm — was handed
back **40,964 characters** it had already seen. That is the fixed-context tax
showing bare, and it is real waste that separates nothing.

**What separated the arms was a condense-and-reset.** Both passing arms read for
~45 steps, wrote the reading into one brief (`.scratch/*/goal.md`, step 45 in
both), then spawned one child pointed at it (47 and 46) — and the child wrote the
module. No failing arm ever condensed.

So the defect is neither a schedule nor a volume: **a step can leave nothing
behind, and the scaffold cannot tell it from the step that did the work.**
Repetition is a symptom, not the disease — a second read of a file is fine when
something happened in between and a loop when nothing did, which is why the
second read is not the observable. The nothing in between is.

And the reason it matters is the first [Design
Test](Design%20Tests%20(Top%20Down).md). "Infinite complexity:
complete tasks however complicated they are, while context stays the same size"
is a claim about steps buying progress. A run that loops fails at eighty steps
and would fail at eight hundred, and then the claim is false for a reason that
has nothing to do with the size of the context.

## 4. The mechanism, in three tiers

Three words, and only the third names a defect:

- **Progress** — the step changed durable state: a file in the workspace, the
  target register, the memo table, the check's verdict. Everything else a step
  makes, the next step or the one after overwrites.
- **Stall** — a step that changed none of it. *Not a defect.* Reading four files
  in one step to decide is a stall and the system message asks for exactly that.
- **Livelock** — stalls in a row. The only one worth acting on.

Four decisions in the implementation, each of which could have gone the other
way:

**A price, not a cap.** 0.0.8c §6 gave up the depth ceiling on the principle that
the scaffold has an opinion about the resource and not about the shape of the
work. A livelock ceiling would be that mistake in a new place — and §7.2 is the
run that proves it, because any ceiling low enough to catch its twelve-step
streak would have killed a run that recovered.

**The threshold is what keeps the price off a strategy that works.** Three stalls
in a row are free. `charge_children` is the precedent and the argument: it is the
one mechanism in the series the runs show an agent responding to, and 4.4's
cascade terminated on budget because of it. A livelock is that failure inside one
frame instead of four.

**A parent is not billed for its child's surcharge.** It is a rate inside the
frame's own allowance, so a child still cannot cost more than the allocation its
parent made — 0.0.8c §5's invariant, which the first implementation broke. The
parent gets the streak in the handoff instead, which it can act on, being the
only frame that can change the brief.

**Two things deliberately do not count as progress.** A `spawn` by itself: the
parent sees the child's files, handoff and response soon enough, and 4.4's
cascade was four frames forwarding a goal and writing nothing. And the *first*
verdict of a checked run, because the scaffold ran the check, not the agent —
counting it made the opening step of every run look like it moved, which is the
step that matters most.

One limitation. The unit is the workspace and a workspace is shared, so while
siblings run concurrently a file one writes counts for all of them. A parent is
unaffected, since it takes no steps while it waits, and attribution is impossible
anyway through a `bash` that is unbounded by design. In a fan-out the measure has
false negatives and no false positives: a frame told it has stalled has stalled.

## 5. Results

Five live runs, `--profile frame`, `--arm baseline`: **1.6M input tokens, 189K
output, 61 minutes, five of five correct.** Both probes are one command each,
which is what turned "an afternoon per arm" into an afternoon for the whole
table.

### Infinite writing — `volume`, two sizes

| | records | output | largest request | steps | stalls | worst streak | accuracy |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| row 1 | 120 | 10,631 bytes | 6,795 | 25 | 17/25 | 12 | 120/120 |
| row 2 | 1,200 | **106,274 bytes** | **6,446** | 15 | 5/15 | 3 | 1200/1200 |

**Ten times the output and the largest request fell by 349 tokens — 5.1%**,
against a 16,530 ceiling neither run came near. The clause holds on a measurement
rather than on the offline assertion.

Three things in those rows are worth more than the verdict. **The bigger task was
the easier one** — 15 steps against 25, 5 stalls against 17 — because it went
straight to writing a program where row 1 circled first; size made the shortcut
obvious rather than the work harder. **The program route is quantified rather
than forbidden**: row 2's file is **4.8×** everything the model generated, so
most of it never passed through a generation, which is `bash` being unbounded by
design doing exactly what it is for. And **both rows were won with a twenty-line
regex**, so what they show is a context holding still while an artefact outgrows
it — not a run producing output that needs a generation per unit. That harder
version is unwritten.

### Infinite complexity — `width`, three times

The task 0.0.7 failed four times and 0.0.8 passed twice in five arms.

| run | module | steps | agents | largest request | stalls | worst | lock | charged | stall paid |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 550 lines | 71 | 3 | 7,867 | 4/71 | 1 | 0 | 19 | 0 |
| 1 | 350 lines | 71 | 2 | 8,099 | 6/71 | 4 | 1 | 38 | 2 |
| 2 | 377 lines | 63 | 2 | 7,958 | 3/63 | 1 | 0 | 40 | 0 |

**Three of three**, every module importing with no `NotImplementedError` left,
graded by running the interpreter rather than by reading the response — which
matters, because two 0.0.8 arms reported a module they had not written and one
returned `ok=True` while its own response said the stub was untouched.

**The largest request across the three spans 232 tokens.** That is the
fixed-context property on the hard task, live, at n=3: three runs producing 350
to 550 lines apiece and none asking for more context than another.

Stall rates 5.6%, 8.5%, 4.8% against **28.6-53.8%** in the five 0.0.8 arms; worst
streaks 1, 4, 1 against 3 to 9. Something changed on this task and the size of it
is not subtle. §7.1 is why this note does not say what.

## 6. The first Design Test, clause by clause

[Design Tests (Top Down)](Design%20Tests%20(Top%20Down).md) opens with the
Infinite Context Test and nobody had ever scored it one clause at a time.

| clause | scaffold | model | verdict |
| --- | --- | --- | --- |
| **fixed context** | `test_fixed_context.py`, four axes | five agents at five depths spanned 1,389 tokens; §5's three width runs span 232 | **held** |
| **infinite reading** | 4KB to 4MB, request flat | 6/6 under `--frame`; a 10M-token instance in nine steps | **held** |
| **infinite writing** | 10,000 lines, request flat | 2/2, ten times the output, request 5.1% smaller | **held** |
| **infinite complexity** | more steps do not grow the request | 3/3 on the hard task | **held, on one task** |

All four have live evidence for the first time. Three limits, stated rather than
buried:

1. **Complexity is one task.** `step_loop.py` is the task this series was shaped
   by, so passing it three times says the shape is right and does not say the
   scaffold is general. SWE-bench under `--frame` has never been run and the
   flagship reconstruct task has never been run under 0.0.8 at all.
2. **Writing is script-derivable**, as above.
3. **Nothing here is attributed.** See next.

**The scaffold half was always the easy half.** Every scaffold-side test in that
table drives a `FakeModel`. They prove the *scaffold* does not grow, which is a
real property and is not the claim; "complete tasks however complicated they are"
is a claim about a model working inside the thing, and only a live run speaks to
it. That is why the table has two columns and why the right-hand one was empty
for two of the four clauses until this iteration.

## 7. What the runs said that the design did not

### 7.1 The mechanism cannot claim its own success

3/3 against 2/5 is **four changes at once**: no `lookup`, so the fixed half is
636 characters smaller; `facts.md` present from step one; the progress mechanism;
and a live `check` actually passed by the harness, which every eval run before
this silently lacked (§8). That is the mistake §6 of the handoff opens with,
committed here.

What can be ruled out is the tier this note is named for. **The price collected
two budget units across all three width runs**, and the notice never fired at all
in runs 0 and 2. Whatever made those runs good, tiers 2 and 3 were not doing it.
The remaining candidates are the smaller fixed half, the memo table (7.3), and
variance. 3/3 is a result, not a cause.

### 7.2 The threshold does not generalise, and the magnitude has been tested once

The proxy over the five arms' seven frames separated pass from fail with no
overlap: passing frames stalled at most four steps in a row, failing frames ran
to six, eight, nine. That was fitted to one task and the first live run on
another refutes it as a predictor. `volume` row 1 passed with every field correct
and a **twelve-step streak** — steps 6 to 17, re-reading its own instruction file
at 7, 14 and 16, re-reading the corpus head at 6, 7, 9, 15 and 17, re-counting
its own output six times, writing nothing — and then rewrote its generator at
step 18 and finished.

So the measure caught a real livelock live, on its first run, and the run
recovered. `config.py` says this where the number is set, rather than citing the
fitted separation as though it were a law.

The magnitude is the other half. Across all five live runs the surcharge charged
**14 budget units, 11 of them on that one run** — 28% of its budget, leaving four
steps of margin — and one, zero, two, zero on the rest. That is what a
well-aimed price looks like: invisible to a run that is working, expensive for
one going in circles. Whether the pressure is what got row 1 out of its loop, or
nearly killed a run that would have got out anyway, is one A/B and has not been
run.

### 7.3 The memo table does something, and it is the best candidate

0.0.8 §10.2 asked whether a memo table an agent can *see* changes what it does,
or whether `grep`-before-you-look is a habit no sentence installs. All three
agents of width run 0 opened by `cat facts.md`, and the five-line table they
built starts:

```
step_loop.py: stub imports ToolRegistry (nonexistent) -> real class is ToolDispatcher in tools.py
step_loop.py: stub imports name T from trajectory (nonexistent) -> use typing directly
```

Arm C died on exactly that. Its check said `ImportError: cannot import name
'ToolRegistry' from 'infinite_agent.tools'` on step 1 and it spent the remaining
eighty steps never resolving it — in a workspace where `facts.md` did not exist
while the system message called it the run's memo table, because the sentence was
gated on `config.lookup` rather than on the file. Here the fact was resolved once,
written down, and read by two frames that had not paid for it.

One run, and the mechanism is a file and a sentence rather than a tool, so
attribution is soft. It is still the best available explanation for §5's numbers.

### 7.4 Condense-then-descend is the shape, now in five frames

Every width run has a frame that reads, writes a brief and spawns — 47/50 in run
0, 26/28 in run 1, 19/21 in run 2 — and in every case the *child* wrote the
module, at step 36 of 38, 39 of 40, and 7 of 8 respectively. Run 0 did it twice,
nested: root condensed and spawned, its child condensed and spawned, and the
grandchild wrote.

That is 4.4's cascade with the sign reversed, and the difference is not the tool
but what was handed down. The cascade forwarded a goal *unchanged, at step 4,
before reading*. These forwarded a *distilled* goal after reading, with the facts
in a file the child was pointed at. That distinction is a better definition of a
descent than the sentence now in the system message, and unlike that sentence it
is measurable: did the parent write a brief before it spawned?

## 8. What was broken and is not any more

Every one of these is a run that would have died in its first minute, or a number
that was wrong in the flattering direction.

**`python3` was a coin flip inside the sandbox.** Under `uv run` it resolves into
the uv-managed CPython, which `SYSTEM_READ_DARWIN` did not list, so the
interpreter could not read its own stdlib and died with `ModuleNotFoundError: No
module named 'encodings'` — with stderr swallowed, an empty register and no
explanation. Every `check` in the 0.0.8 arms was a `python3 -c 'import …'` and
they worked only because those runs happened to resolve `python3` to
`/usr/bin/python3`. Fixed, and exercised where it actually failed: the writing
probe's end-to-end test writes its output with a `python3` heredoc in the sandbox.

**The eval harness never passed a `check`.** All five 0.0.8 arms had one and
`check_every_step` is on by default, so the heartbeat was inert in every
benchmark result in this repository, and a "replication" through `eval.run` would
not have been one. A benchmark's `truth["check"]` now becomes the root's check,
and a test asserts every arm of every probe parses as a command `infinite.main`
accepts.

**`measure` summed tokens and never recorded the largest request** — the one
number the Design Test turns on, and one a total can never show, since a sum
grows with the length of a run whatever the geometry does.

**`collect_overrides` read `sys.argv` rather than its argument**, so the two flags
whose `None` is meaningful answered about the process. Harmless in the CLI, wrong
in-process: the `depth-1` arm looked inert.

**`run_one` gold-checked anything with a `materialise`**, which was SWE-bench's
property and not a general one.

**The summary tests shared one fake model across two threads.** Since 0.0.7f the
summary of step N is written while step N+1 is generated, so `SummaryModel` is
called from both and its lists were unguarded. Latent for two versions; the
workspace scan shifted the timing and the suite began failing about one run in
five, in whichever summary test lost.

**A cut `[Check]` line read as corrupt rather than shortened** — an unbalanced
`(` in the one line the agent sees every step. It says `[…]` now.

## 9. Open questions

1. **Attribute §5.** `--arm no-stall-charge` ×3 rules the price in or out — the
   prior is "out", since it collected two units across the baseline runs — and a
   run with `facts.md` withheld tests 7.3, which is where the evidence points.
   Three runs each, about twenty minutes apiece. Until then §5 is a result
   without an explanation.
2. **Then decide whether tier 3 survives at all.** If `no-stall-charge` also goes
   3/3, the price is buying nothing measurable and tier 1 alone is the honest
   ship. Keeping a mechanism because it is harmless is how a scaffold accretes.
3. **The irreducible writing probe.** Content a script cannot derive, so the
   number of *generations* scales with the output and the context still has to
   hold still. Same two-size shape. It is the version of that clause that is
   actually open.
4. **Is a stall the right unit, or is a stalled *frame* the right unit?** The
   measure is per step and the workspace is shared, so a fan-out has false
   negatives (§4). Nothing has been run at width where that would bite.
5. **4.2 and 4.3 are untouched.** The canvas bisection came back negative and
   the binding quantity is still unnamed; a check that cannot get closer may
   still be worse than none, and that is the only open item that could change a
   mechanism rather than a constant.
6. **The two Design Tests with no evidence** — computational completeness, and
   stack mode without recursion — are where they were. Both are new probes
   rather than changes, and the second half of the stack test is a real gap:
   `load(path, start)` is stateless and there is no open-file table anywhere.
