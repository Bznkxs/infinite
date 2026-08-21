# Iterating to 0.0.8d

*Read this first if you are picking the project up. It is the state of play
after 0.0.8: what was built, what was measured, what broke, what is unanswered,
and what to do next. Everything in it is checkable against the repository —
where a number appears, the run that produced it is named.*

---

## 0. Ninety seconds

InfiniteAgent keeps a model's active context to a fixed set of registers and
puts everything else on disk. The 0.0.7 series got reading right — a 10MB corpus
answered in seventeen steps at an 8,000-token context, and in nine once 0.0.8
landed — and then failed, four times, on one task: implement a module that calls
into six others. [Depth, Volume and
Width](Depth,%20Volume%20and%20Width.md) diagnosed why, and named the axis:
a fixed context is defeated not by the *size* of the corpus but by the number of
facts that must be true at once.

0.0.8 is three design letters answering that
([a](InfiniteAgent%200.0.8a.md), [b](InfiniteAgent%200.0.8b.md),
[c](InfiniteAgent%200.0.8c.md)) and the build note for them
([0.0.8](InfiniteAgent%200.0.8.md)). It shipped, it is tested, and the honest
verdict is:

> **The clerical costs are gone and the axis is unmoved.** Every mechanism in
> the letters works. None of them is what the hard task turns on. What decides
> that task is whether a run *makes progress* — whether each step leaves
> something behind that outlives it — and nothing in 0.0.8 can tell a step that
> did the work from a step that did not.

That was the brief for 0.0.8d, and it is the second version of it: the first said
the task turned on *when a run starts writing*, which §4.1 measures and refutes —
both frames that produced a working module wrote in the last fifth of their
budget, and so did all three that did it again in §4.8.

**Where it ended up is further along than the brief.** The hard task now passes
three times out of three (§4.8), the writing clause has its first live evidence
at two scales (§4.9), and for the first time every clause of the Infinite Context
Test has a number against it rather than an argument. What is *not* established is
why: four things changed at once, and the mechanism this letter is named for
collected two budget units across those three runs, so it is the least likely
cause of its own success. §5 item 1 is the arm that separates them.

**And 0.0.8d has not passed the reconstruction test.** Every probe it set out to
run passed, so by the convention [Writing a
Version](Writing%20a%20Version.md) now records it should have gone on to the one
test that is the claim rather than a component of it — the agent rebuilding
InfiniteAgent from a condensed spec of itself, under 0.0.8d's own geometry. It
was never attempted. The task is written down for the first time in [The
Reconstruction Test](The%20Reconstruction%20Test.md) — how to build one for a
version, and the three gates it is graded by — and building it for the 0.0.8
series is §5 item 6. The last version to pass it was 0.0.7f, at 46,684 tokens a
generation; nothing since has tried at any size.

Three other things happened under this heading: the numbers in the 0.0.8 note
were re-derived from the trajectories and several moved (§7), `lookup` was removed
outright (§4.0), and the eval harness turned out never to have passed a `check`
(§6) — so every benchmark number in the repository predating this letter was
measured without the heartbeat it was supposed to have.

## 1. The ground

```
src/infinite/
  agent.py       the loop; the check; charging; spawn/resume
  config.py      every geometry and knob; the presets (SHORT, WIDE_OUTPUT, FRAME)
  registers.py   the register file and the dump
  regfile.py     0.0.8a: the registers as $R0.. and $REGDIR/0.. around bash
  prompt.py      the system message, and `build_brief`
  progress.py    0.0.8d §4.1: what a step left behind, and the stall streak
  tools.py       bash, load, set, set_target, spawn, resume
  workspace.py   the shared directory, and facts.md
eval/
  run.py         benchmark harness  (--profile frame, --arm)
  analyse.py     reads §8's measures off a run's trajectories
  benchmarks/width.py   the step_loop probe, as a command rather than a recipe
  benchmarks/volume.py  the infinite-writing probe (new; 2/2, §4.9)
test/
  infinite_0_0_1_simple/   the 0.0.7 suite, updated
  infinite_0_0_8_frames/   the 0.0.8 suite
eval/results/
  steploop-0.0.8.json      the five probe arms, distilled (runs/ is gitignored)
  volume-0.0.8d.json       the two infinite-writing rows, likewise
  width-0.0.8d.json        the three width runs of 4.8, likewise
```

```bash
uv run pytest test                      # 332 tests, offline, ~18s, all pass
python -m eval.analyse runs/<workspace> # what a run actually did
python -m eval.run babilong --config 1M --split qa2 -n 1 --profile frame
python -m eval.run width -n 3 --profile frame            # the hard task, x3
python -m eval.run width -n 3 --profile frame --arm no-stall-charge
python -m eval.run volume --config 120  --profile frame # writing, and then
python -m eval.run volume --config 1200 --profile frame # ten times as much
python -m eval.run --report                             # largest request, worst streak
```

Everything 0.0.8 adds has a flag to turn it off, so any of it can be A/B'd:
`--no-shell-registers`, `--no-charge`, `--no-checks`, `--no-live-check`,
`--max-depth N`, and 0.0.8d's `--no-stall-charge` / `--no-stall-notice`. There is
no `--no-lookup` any more; see §4.0. `eval/run.py`'s `ARMS` names one flag each,
because §6's first rule is one variable per arm and naming them is cheaper than
remembering.

## 2. What 0.0.8 achieved

**The probe passed.** `step_loop.py` — the module that defeated 0.0.7 four times
— was implemented and imported in **56 steps, largest request 8,233 tokens**
(`runs/steploop_0.0.8`), and again in 50 at 8,419 (`runs/steploop_0.0.8_live2`).
The 0.0.7 attempt that managed it at all peaked at **23,251** tokens and took 82
steps, 68 of them spent by a child writing a digest first
(`runs/steploop_control`). The four 0.0.7i children that failed peaked at ~5,400
and spent **420 steps** between them (150, 110, 90, 70) writing nothing — one of
them returning `ok=True` while its own response said the stub was untouched.

Every token figure in this document is the largest request the run actually put
on the API, summed from the `usage` records in the trajectories. The 0.0.8 write-
up originally quoted 8,053 / 8,226 / 22,460, which were `max_request_chars /
2.6` and run ~2% low; and 6,063 for the 0.0.7 failure, which was never a
measurement of that run at all — it is 0.0.7i's figure for the geometry, and the
children that failed peaked between 5,316 and 5,455.

**Reading did not move**, which is what §8 predicted, since nothing in 7.1-7.4
touches depth. Six of six under `--frame`, four of them in fewer steps than
0.0.7g — including a 10M-token BABILong instance in nine steps against
seventeen.

**The fixed-context property holds and is now a test rather than a claim.**
`test_fixed_context.py` scales steps, depth, bytes read and lines written and
asserts the largest request does not move. Live, one run put five agents at five
depths on the API and their largest requests spanned **1,389** tokens
(6,534 / 7,881 / 7,923 / 7,830 / 7,158, deepest not largest).

**Three questions the letters left open are now answered:**

- *Does transit cost anything?* (0.0.8a §7.1) **No.** Zero of **300,423**
  generated argument characters, across all six 0.0.8 step_loop runs and every
  depth, were values already sitting in a register. Registers-as-files stands on
  the working set, not on saved output tokens.
- *Does the brief pay for its schema?* (0.0.8c §9.1) **Yes, nine characters
  against a 3.7× saving.** `spawn`'s schema went 1,681 → 1,690 chars, which is
  exact; generated briefing fell from a median 2,070 chars over 34 spawns in
  0.0.7g/h/i to 563 over 10 in 0.0.8. Pooling all 0.0.7 runs gives 4.4×. The
  "4.7×" first published rested on two medians (2,545 and 545) that no subset of
  the runs reproduces.
- *Is the canvas what a working set must land in?* (0.0.8a §5, 7.6) **No** —
  see §4 below.

**And 7.4's actual ask is met**: `Config.context_tokens` reports usable working
set beside the total. `--frame` is 5,840 characters of agent-controlled space,
against 0.0.7g's 3,280. Mind which ruler the surrounding tokens are quoted in:
`context_tokens` divides by four and reports 8,447 in / 16,639 total for
`--frame`; the 0.0.8 note's cost table divides by 2.6, which is closer to how
the schemas tokenise, and gets ~4,510 fixed and ~16,700 total. Same geometry,
two rulers — compare the character counts.

## 3. What was tested, so you do not redo it

| | how | result |
| --- | --- | --- |
| every mechanism in the letters | 81 offline tests in `test/infinite_0_0_8_frames/` | pass |
| `lookup` gone, memo table kept | `test_memo_table.py` (0.0.8d, §4.0) | pass |
| the fixed-context property | `test_fixed_context.py`, four axes | pass |
| reading | 6 BABILong / ∞Bench instances, `--profile frame` | 6/6 |
| the width probe | 5 live runs of `step_loop.py`, 80 steps each | 3 wrote a module, 2 passed |
| 7.6's canvas bisection | one run at canvas 12,288 | negative |
| stall streaks (0.0.8d, §4.1) | proxy over the 7 frames of the 5 arms | separates pass from fail |
| progress, the notice, the price | `test_progress.py` (28 tests) | pass |
| the probe as a harness | `test_width_probe.py`, synthetic corpus | pass |
| the writing probe | `test_volume_probe.py` (27 tests) | pass |
| infinite writing, live | `volume` at 120 and 1,200 records, `--profile frame` | **2/2, request flat** |
| infinite complexity, live | `width` x3 on the 0.0.8d geometry (4.8) | **3/3, request spans 232 tokens** |
| the probe pipeline end to end | scripted model, live check, real grade, no API | pass |
| every arm of every probe is a command the CLI accepts | `test_volume_probe.py` | pass |
| §4.6's firewall hole | the suite, which is green | fixed |
| transit, brief cost | read off trajectories | answered |

Read that table with §4.0 in mind: the five probe arms ran with `lookup`
available, so they are the last measurements of a scaffold that no longer
exists. What they say about depth, charging and the check still holds — none of
those touched the index — but the fixed half of every request is smaller now.

The five probe arms are in `runs/steploop_0.0.8*`; `runs/steploop_0.0.8-diag`
and `-aborted` are earlier diagnostic runs kept because §7 of the build note
cites them. **`runs/` is gitignored** — those workspaces are 13MB of trajectory
and live only on the machine that produced them — so the arms are distilled into
`eval/results/steploop-0.0.8.json`, which is in the repository and carries the
per-agent numbers every claim here rests on. If you are on a fresh clone, that
file is your evidence.

## 4. The problems, ranked

### 4.0 `lookup` is removed — done, not pending

0.0.8's 7.1 gave the agent `lookup(symbol)`: one line per definition, out of an
AST index the scaffold kept over the workspace. The shape was right and the
implementation could not be. **The index only parsed Python.** The one tool
meant to turn width into depth — forty facts as forty lines instead of forty
pages — worked for one language, in a scaffold whose whole claim is that it is
indifferent to what is on disk. A `lookup` that answers for `.py` and shrugs at
Go, Rust, SQL or a config file is not a primitive; it is a special case wearing
a primitive's schema. And the agent does not need it: `grep` is
language-agnostic, the agent already has it, and `bash` is deliberately
unbounded (0.0.8b §1), so a signature has always been one command away.

The runs agree. In five arms `lookup` was called ten times, by two agents out of
twelve. The arm that had it spent 29 read calls and fifteen hand-built signature
files anyway (`runs/steploop_0.0.8_live`), and the two arms that *passed* never
called it once. 0.0.8's §7.3 read this as "a symbol is the wrong unit" and
widened `lookup` to take a path; the wider reading is that the tool was never
the thing doing the work.

So it is gone: `index.py` deleted, the schema and handler removed, the
`lookup`/`lookup_max_matches`/`lookup_max_outline` knobs removed, `--no-lookup`
removed, its sixteen tests replaced by `test_memo_table.py`. Six tools where
there were seven, and the fixed half of every request went 11,738 → **11,102**
characters: the schemas lost 718 and the system message gained 82, because the
memo-table sentence had to stop leaning on a tool to explain itself. Net 636
characters, about 245 tokens a step — a real saving and a small one. The reason
to do it is that the tool was Python-only, not that it was expensive.

**`facts.md` stays, and is now honest.** It was 0.0.8b §4's mechanism, not
7.1's, and it is language-agnostic in a way the index never was. `lookup` had
been its only writer, so removing the tool would have left a table with no
writer at all — instead `Workspace` now creates it with its header, and the
whole interface is `>>` to write and `grep` to read. That also repairs the bug
in the old 4.5, below.

### 4.1 A run can stop making progress, and then steps stop being a resource

This is the one that matters, and it is the one that breaks the first Design
Test. "Infinite complexity: complete tasks however complicated they are, while
context stays the same size" is a claim about *steps* buying progress. A run
that loops fails at 80 steps and would fail at 800 — and then infinite
complexity is false for a reason that has nothing to do with the size of the
context.

An earlier draft of this section said the defect was that a run does not start
writing until it has every fact. The trajectories say that is wrong, and the
measurements are worth keeping because each one kills a detector you would
otherwise build.

**Writing late is not the defect.** Both frames that produced a working module
wrote it in the final fifth of their own budget: arm A's child at step 23 of 24,
arm E's child at step 22 of 27. Arm B wrote at step 80 of 80 and failed. Late
writing is what passing looked like.

**Writing *something* is not the test either.** The two arms that left the
99-line stub untouched were the busiest writers — 43 and 53 write calls, 33,490
and 38,841 generated characters — against passing arm E's root at 30 and 27,373.
Any "did it produce output" detector reads C and D as healthy for eighty steps.

**Re-reading is universal, so it is not the discriminator.** Every frame in the
five arms read a path it had already read on **75–93%** of its steps, and 12–26%
of its `bash` outputs were byte-identical to one that frame had already
received. Arm D read a 99-line file **52 times in 80 steps**; arm E's root — a
passing arm — was handed back **40,964 characters** it had already seen. This is
the fixed-context tax showing bare: a fact you do not write down you must
re-acquire. It is real waste and it predicts nothing on its own.

**What separated the arms was a condense-and-reset.** Both passing arms did the
same three things and no failing arm did any of them: read for ~45 steps, write
the reading into one brief (`.scratch/*/goal.md`, step 45 in both arms), then
spawn one child pointed at that brief (step 47 and 46) — and the child wrote the
module. The failing arms accumulated fragments, up to fifteen scratch files of
`grep '^def'` output, and never condensed or reset.

So the defect is neither a schedule nor a volume. It is that **a step can leave
nothing behind** — no file changed, no target rewritten, no fact recorded — and
the scaffold cannot tell that step from the one that did the work. Repetition is
a symptom, not the disease: a second read of a file is fine when something
happened in between and is a loop when nothing did.

**And stall streaks separate the arms, where nothing else did.** On a proxy
computed from the trajectories — a step counts as moving if it called
`set_target`/`spawn` or ran a shell command that writes — the seven frames split
with no overlap:

| frame | stalled steps | longest streak | streaks ≥ 3 |
| --- | --- | --- | --- |
| A root (pass) | 28.6% | 3 | 1 |
| A child (pass) | 41.7% | 4 | 1 |
| E root (pass) | 40.0% | 3 | 2 |
| E child (pass) | 29.6% | 4 | 1 |
| B root (fail) | 53.8% | **9** | 7 |
| C root (fail) | 50.0% | **6** | 5 |
| D root (fail) | 51.2% | **8** | 5 |

Every passing frame stalled at most four steps in a row, at most twice. Every
failing frame ran to six, eight, nine. Write timing did not separate these seven
frames, write volume did not, re-read rate did not; this does. Two caveats: it
is one run per arm, and the proxy is looser than the real thing — it reads
command text, so a `mkdir` that changes nothing counts as moving, which means
the true streaks are at least this long and probably longer.

Three terms, because the rest of this document needs them:

- **Progress** — a step leaves durable state: a file in the workspace created,
  modified or removed; the target register rewritten; a line appended to
  `facts.md`; the check's verdict changed. Everything else a step makes —
  registers, the summary — the next step or the one after overwrites.
- **Stall** — a step that makes no progress. Not a defect by itself: reading
  four files in one step to decide is a stall, and it is exactly what the system
  message asks for.
- **Livelock** — consecutive stalls. This is the thing that fails at 800 steps,
  and the only one of the three worth acting on.

Charging prices delegation. Nothing prices a livelock. A step that runs one
`grep` and a step that writes a module cost the same, and the budget line says
nothing about what the steps left behind.

**0.0.8d's mechanism, in three tiers — all three built.**

1. **Measured.** `progress.py`. Every step records what durable state it
   changed, into the trajectory; the streak goes in the handoff, so a parent
   deciding whether to resume a child knows whether that child was moving.
   `analyse.py` grew `stall / worst / lock` columns. One `stat` per file and no
   reads, so volume is free and only the *number* of files costs anything:
   0.6ms a step on a probe workspace, 124ms on the flagship reconstruction's
   6,400 files. The ignored trees are pruned rather than filtered, which is the
   whole of that — walking `tool_output/` and the trajectories and discarding
   them afterwards cost 350ms a step and 8.6 seconds on a pathological
   workspace. The cost is recorded per agent rather than capped, because a cap
   would degrade the measure exactly where a livelock is most expensive.

   Two things it deliberately does not count. A `spawn` is not progress by
   itself — the parent sees the child's files, handoff and response soon enough,
   and 4.4's cascade was four frames forwarding a goal and writing nothing.
   And the first verdict of a checked run is not progress, because the scaffold
   ran the check, not the agent; counting it made the opening step of every run
   look like it moved, which is the step that matters most.

   One limitation. The unit is the workspace and a workspace is shared, so while
   siblings run concurrently a file one writes counts for all of them. A parent
   is unaffected, since it takes no steps while it waits, and attribution is not
   possible anyway through a `bash` that is unbounded by design. In a fan-out the
   measure therefore has false negatives and no false positives: a frame told it
   has stalled has stalled.
2. **Shown.** A `[Stall]` line in the dump once the streak reaches
   `stall_notice` (3). It is state beside the budget line, not a sentence in the
   system message — which is the whole design argument: the budget line is the
   one piece of state five runs show the agent acting on, and the fixed half of
   every request did not grow by a character. A working run never sees it.
3. **Charged.** `stall_surcharge` (1). From the threshold on, a stalled step
   costs itself and one more, so a livelocked frame spends its allowance at
   twice the rate and dies at about half the steps. `charge_children` is the
   precedent and the argument — it is the one mechanism in the series the runs
   show an agent responding to, and the cascade of 4.4 terminated on budget
   because of it. A livelock is that failure inside one frame instead of four.

Three properties of the price are worth stating, because each was a decision:

- **It is a price, not a cap.** 0.0.8c §6 gave up the depth ceiling on the
  principle that the scaffold has an opinion about the resource and not about
  the shape of the work. A livelock ceiling would be the same mistake in a new
  place.
- **The threshold is what keeps it from taxing a strategy that works.** Reading
  four files in one step to decide is a stall and the system message asks for
  it; three in a row is free. On the five arms this prices health at about one
  step in fifty and a livelock at one in four.
- **A parent is not billed for its child's surcharge.** It is a rate inside the
  frame's own allowance, so a child cannot cost more than the allocation its
  parent made — 0.0.8c §5's invariant. What the parent gets instead is the
  streak, in the handoff, which it can act on because it is the only frame that
  can change the brief.

**Two live runs, and they say three things.** The `volume` rows (§4.9) are the
first runs under this mechanism, and they are worth more than the seven frames
the threshold was fitted to, because they are the real measure rather than a
proxy and they are a different task.

*The measure works, and the failure it names is real.* The run stalled 17 of 25
steps and ran a **twelve-step streak**, steps 6 to 17: it re-read its own
instruction file at 7, 14 and 16, re-read the head of the corpus at 6, 7, 9, 15
and 17, and re-counted its own output six times. Nothing was written for twelve
steps. That is the pathology exactly — not reading, not writing late, but a frame
going round without leaving anything behind — and the scaffold saw it as it
happened.

*A price and not a cap is the right instrument, and this run is why.* At step 18
it rewrote its generator, regenerated the file, and finished with all 120 cards
correct. Any ceiling low enough to catch that streak would have killed a run that
recovered.

*The threshold does not transfer, and the magnitude is aggressive.* A **passing**
frame ran twelve, where the width arms said four was the passing maximum — so
"longest streak separates pass from fail" is a fact about that task and not a
law, and `config.py` says so where the number is set. The surcharge took **11 of
the 40 budget units** on a run that was entirely correct, leaving four steps of
margin. Whether that pressure is what got it out of the loop at step 18, or
nearly killed a run that would have got out anyway, is one A/B —
`--arm no-stall-charge` against the baseline — and it is the top of §5.

The other four live runs moderate that, and they moderate it a long way. Across
`volume` row 2 and the three `width` runs of 4.8, the price collected **one
budget unit, zero, two and zero** — and the notice never fired at all in three of
them. Over all five runs of this letter the surcharge charged 14 units, and 11 of
those 14 fell on the single run that spent twelve steps re-reading its own
instruction file. That is what a well-aimed price looks like: invisible to a run
that is working, expensive for the one that is going in circles. So "the
magnitude is aggressive" was a claim about one run, and the fuller picture is
that the *threshold* is well placed and the magnitude has still only been tested
once in anger.

The default stays on, on the project's own convention that a new mechanism ships
with a flag rather than a decision. Both flags exist (`--no-stall-charge` keeps
the measure and the notice; `--no-stall-notice` drops both) and both arms are in
`eval/run.py`.

### 4.2 The canvas is not the binding constraint

0.0.8a §5 argued the working set has to land in one register whole, and set the
canvas to 4,096 on that argument. 7.6 asked for the bisection. It was run
(`runs/steploop_0.0.8_wide`): canvas 12,288, working set 14,032 characters,
largest request 11,273 tokens — and it wrote no more code than 4,096 did.
Whatever binds this task, it is not the size of the one wide register.

Two candidates survive: the binding quantity is the *whole* input rather than
one register (0.0.7f succeeded at 23,251 and every 0.0.8 arm peaked under
11,300), or it is not a context quantity at all. Note that both 0.0.8 passes
peaked around 8,300, well under their own ceiling, which argues against the
first.

### 4.3 A check that cannot get closer may be worse than none

The strongest untested signal in the data, and cheap to settle. Both arms given
`python3 -c 'import …'` wrote a working module; both arms given that **and**
`! grep -q NotImplementedError` wrote no implementation at all in eighty steps.
The compound check cannot move until the last stub body is gone, so it is a
verdict without a gradient.

One run per cell, so this is a hypothesis. It is the only item on this list that
could change a mechanism rather than a constant.

Two corrections before you build on it. First, `eval/results/steploop-0.0.8.json`
records the **compound** check as arm A's arm-level `check`, and that is wrong:
arm A's root ran `import` alone and authored the compound check for the child it
spawned. Read the per-agent `check` fields. Second, arms A and B predate the
heartbeat commit — their recorded config has no `check_every_step` key at all —
so "A vs E" moves the build as well as the flag. Their register geometry is
identical, so it is a weak confound, but it is one.

### 4.4 Unbounded depth produced a pass-through cascade

Removing `max_depth` (0.0.8c §6) had a root forward its entire goal at step 4,
its child forward the same goal at step 12, and so on to depth four — budget
decaying 80 → 58 → 32 → 15 → 8, with 39% of the run spent by frames orienting
themselves and then delegating, and no frame writing anything
(`runs/steploop_0.0.8-diag`).

One detail sharpens this. The decay was not imposed by charging — at step 4 the
root had 76 steps of allowance and handed down 58; at step 12 that child had 46
and handed down 32. The parents chose to shrink the budget and charging only
capped what they chose. Charging bounded the chain, exactly as 0.0.8c §6
promised: it terminated on budget rather than on a ceiling. It did not *deter* it, because forwarding a goal
is free under charging — it costs the parent what doing the work would have
cost, minus the steps the child spends re-orienting, which the parent never
sees. The system message now names the move ("handing a child your own goal
unchanged is not a descent") and the cascade did not recur, but that is one
observation and it is advice, which five runs have said does not land.

0.0.8c §9.4 asked whether depth wants a price rather than freedom, and said the
evidence for `max_depth = 1` was a real run. So is the evidence against
unbounded depth.

**Read this against 4.1, which reverses its sign.** Here delegation is the
disease; there it is the cure — the only move that got a module written. The
difference is not the tool, it is what was handed down. The cascade forwarded a
goal *unchanged, at step 4, before reading*. Arms A and E handed down a
*distilled* goal at step 46, after reading, with the facts in a file the child
was pointed at. That distinction is a better definition of a descent than the
sentence now in the system message, and unlike that sentence it is measurable:
did the parent write a brief before it spawned?

### 4.5 `facts.md` did not exist until `lookup` created it — **fixed**

This had been written up the wrong way round. The memo table *was* written — by
`lookup`, which appended every signature it resolved (`Workspace.remember`),
exactly as the README said. In arms C and E, where `lookup` ran, it reached 133
and 141 lines.

Nothing else created it. In arms A, B, D and the diagnostic run `lookup` was
never called, so `facts.md` did not exist in those workspaces at all — while the
system message told every one of them it was the run's memo table, because that
sentence was gated on `config.lookup`, not on the file. Three of those runs
opened with `cat facts.md 2>/dev/null`, got nothing, and then hand-built the
same artefact as scratch files, over and over.

`Workspace` now creates the file with its header, and 4.0 removed the tool that
was its only writer, so the table is the agent's to keep with `>>` and `grep`.
What was left was the question the bug was hiding: does a memo table an agent can
actually see change what it does, or is `grep`-before-you-look a habit no
sentence installs?

**The first re-run says yes, and says it about the specific fact that killed an
earlier arm.** `width` on the 0.0.8d geometry (4.8) passed with three agents, and
all three of them opened by `cat facts.md`. The table they built has five lines
in it, and these are the first two:

```
step_loop.py: stub imports ToolRegistry (nonexistent) -> real class is ToolDispatcher in tools.py
step_loop.py: stub imports name T from trajectory (nonexistent) -> use typing directly
```

Arm C died on exactly that. Its check said `ImportError: cannot import name
'ToolRegistry' from 'infinite_agent.tools'` on step 1 and it spent the remaining
eighty steps never resolving it, with `facts.md` not existing in its workspace at
all while the system message told it the file was the run's memo table. Here the
fact was resolved once, written down, and read by two frames that had not paid
for it.

One run, and the mechanism is a file and a sentence rather than a tool, so
attribution is soft. But this is the first evidence the memo table does anything,
and it is the best available candidate for what changed — see 4.8, which rules
out the other new mechanism.

### 4.6 `python3` under the firewall — **fixed**

`test_scratch.py::test_an_agents_shell_puts_temporary_files_inside_the_workspace`
failed deterministically, and the cause mattered more than the test. Under
`uv run`, `python3` resolves to `.venv/bin/python3` →
`~/.local/share/uv/python/cpython-3.13.14-.../bin/python3.13`, and
`SYSTEM_READ_DARWIN` did not list that path — so the sandboxed shell's
interpreter could not read its own stdlib and died with `ModuleNotFoundError: No
module named 'encodings'`. The probe swallows stderr, so the register landed
empty and the assert fired.

That was a live-run hazard and not just a red test. Every `check` in the 0.0.8
arms was a `python3 -c 'import …'`, and they worked only because those runs
resolved `python3` to `/usr/bin/python3`, whose real prefix is under
`/Applications`, which *is* allowed. An agent reaching for the project's own
interpreter got `Operation not permitted` and no explanation.

`firewall.system_read()` now adds the running interpreter's `sys.base_prefix` and
`sys.prefix` to the readable roots, which is also what makes the test
environment-independent rather than passing by luck. The suite has been green
since. It is exercised where it actually failed, too: the writing probe's
end-to-end test writes its output with a `python3` heredoc inside the sandbox.

The two cosmetic notes that hung off this are closed as well. The
`python3: error: couldn't create cache file '…/xcrun_db-…'` pair no longer
appears — a check's output is now empty on success, where it used to carry two
lines of sandbox noise into a register. And a `[Check]` line that has to be cut
says `[…]` rather than ending mid-path, which is where the unbalanced `(` came
from: it is the one line the agent reads every step, and a shortened error should
not read as a corrupt one.

### 4.7 Two Design Tests have no evidence at all

[Design Tests (Top Down)](Design%20Tests%20(Top%20Down).md) asks for
**computational completeness** and for **stack mode without recursion**. The
build note §4 argues the first is architecturally supplied and admits no run has
tested it; the second was answered for the scaffold by 0.0.8c and never put to
the model, which is what the test actually asks. And its second half — stacked
file reads, several files open with the status of each kept — is a real gap:
`load(path, start)` is stateless and there is no open-file table anywhere.

### 4.8 The hard task, three times, on this geometry

The width probe is the task 0.0.7 failed four times and 0.0.8 passed twice in
five arms. `eval.run width --offset 0 -n 3 --profile frame` on the 0.0.8d
geometry:

| run | module | steps | agents | largest request | stalls | worst streak | livelocks | charged | stall paid | wall |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 550 lines | 71 | 3 | 7,867 | 4/71 | 1 | 0 | 19 | 0 | 1,549s |
| 1 | 350 lines | 71 | 2 | 8,099 | 6/71 | 4 | 1 | 38 | 2 | 976s |
| 2 | 377 lines | 63 | 2 | 7,958 | 3/63 | 1 | 0 | 40 | 0 | 691s |

**Three of three.** Every module imports and none has a `NotImplementedError`
left, graded by running the interpreter rather than by reading the response —
which matters, because two 0.0.8 arms reported a module they had not written.

**The largest request across all three spans 232 tokens**, 7,867 to 8,099. That
is the fixed-context property on the hard task, live, at n=3: three runs that
produced 350 to 550 lines apiece and none of them asked for more context than
another.

**The descent is 4.1's pattern in all three.** Every run has a frame that reads,
writes a brief, and spawns — root wrote at 47 and spawned at 50 in run 0, wrote
at 26 and spawned at 28 in run 1, wrote at 19 and spawned at 21 in run 2 — and in
every case the *child* wrote the module. And it wrote it late in its own budget:
step 36 of 38, step 39 of 40, step 7 of 8. Writing late is not the defect. Twice
now.

**The stall rates are 5.6%, 8.5% and 4.8%, against 28.6–53.8% in the five 0.0.8
arms**, and the worst streaks are 1, 4 and 1 against 3 to 9. Something changed on
this task, and the size of it is not subtle.

**What it was is not established, and the mechanism this letter is about is the
least likely candidate.** Four things differ from the old arms at once — no
`lookup`, so the fixed half of every request is 636 characters smaller;
`facts.md` present from step one; the progress measure with its notice and price;
and a live `check` actually passed by the harness, which every eval run before
this silently lacked (§6). That is four variables in one arm, which is the
mistake §6 opens with. What can be ruled out is the price: it collected **two
budget units across all three runs**, and the notice never fired at all in runs 0
and 2. Whatever made these runs good, tiers 2 and 3 were not doing it. The memo
table is the better candidate and 4.5 has the specific evidence.

So: 3/3 is a result, not a cause. The A/B that separates the causes is §5 item 1,
and it is now the only thing between this and a finding.

### 4.9 Where the first Design Test actually stands

[Design Tests (Top Down)](Design%20Tests%20(Top%20Down).md) opens with the
Infinite Context Test, in four clauses. Nothing in this project has ever scored
them one at a time, so here they are, and this is the list 0.0.8d is trying to
close.

| clause | scaffold | model | verdict |
| --- | --- | --- | --- |
| **fixed context** — does not *grow* with the task | `test_fixed_context.py`, four axes; live, five agents at five depths spanned 1,389 tokens | — | **held** |
| **infinite reading** | `test_the_request_does_not_grow_with_the_size_of_what_is_read`, 4KB to 4MB | 6/6 under `--frame`; a 10M-token BABILong instance in nine steps | **held** |
| **infinite writing** | `test_the_request_does_not_grow_with_the_size_of_what_is_written`, 10,000 lines | two rows, both 100% correct: **ten times the output and the largest request fell 5.1%** | **held** |
| **infinite complexity** | more steps do not grow the request | **3 of 3** on the hard task (4.8); largest request spans 232 tokens across them | **held, on one task** |

**All four clauses now have live evidence, and this is the first time.** That is
the first Design Test met, on the terms it is written in — with three limits
stated rather than buried, below.

**The scaffold half was always the easy half.** Every one of those scaffold-side
tests drives a `FakeModel`. They prove the *scaffold* does not grow, which is a
real property and is not the claim. "Complete tasks however complicated they are"
is a claim about a model working inside the thing, and only a live run can speak
to it — which is why the table above has two columns and why the right-hand one
was empty for two of the four clauses until this letter.

**What "held" does not mean.** Three things, and none of them is a quibble:

1. **Complexity is one task.** `step_loop.py` is the task this whole series was
   shaped by, so passing it three times says the shape is right and does not say
   the scaffold is general. SWE-bench under `--frame` has never been run (§5),
   and the [Reconstruction Test](The%20Reconstruction%20Test.md) — the flagship,
   and the task `step_loop.py` was cut out of — has never been run under 0.0.8 at
   all. **0.0.8d has not passed it**, and that is the honest ceiling on this
   table: the probe passes on the one module, and the whole system it belongs to
   has not been rebuilt at this geometry.
2. **Writing is script-derivable.** Both `volume` rows were won by writing a
   regex, so what they show is a context holding still while an artefact outgrows
   it — not a run producing output that needs a generation per unit. The harder
   version is §5 item 4.
3. **Nothing here is attributed.** 3/3 against 2/5 is four changes at once
   (4.8). The measurement is sound; the explanation is not in hand.

**Infinite writing had no live evidence at all, and nobody noticed.** §4.7 lists
the two Design Tests with no evidence and this was not on the list, because the
offline test exists and reads like a result. It is not one: it asserts that
writing 10,000 lines through `bash` does not move the request, which was never in
doubt. What had never been run was a task whose *output* is the hard part.

That probe now exists — `eval/benchmarks/volume.py` — and it has been run, twice,
which is the point: the claim is not that either run succeeds but that
`max_request_tokens` does not move between the two rows while the output does.
That is the shape the reading test already uses offline — 4KB against 4MB, one
number asserted flat — and it is the only shape in which "infinite" means
anything measurable.

| | records | output | largest request | steps | wall clock | accuracy |
| --- | --- | --- | --- | --- | --- | --- |
| row 1 | 120 | 10,631 bytes | 6,795 tokens | 25 | 310s | 120/120 |
| row 2 | 1,200 | **106,274 bytes** | **6,446 tokens** | 15 | 144s | 1200/1200 |

**Ten times the output, and the largest request fell by 349 tokens — 5.1%.** Both
runs wrote every field of every card correctly, against a 16,530-token ceiling
neither came close to. The clause holds, and it holds on the measurement rather
than on the offline assertion.

Three things in those rows are worth more than the verdict.

**The bigger task was the easier one.** Row 2 did ten times the work in 15 steps
against row 1's 25, stalled 5 times against 17, and its longest streak was 3
against 12. Nothing about the geometry changed — what changed is that it went
straight to writing a program, where row 1 spent twelve steps circling before it
did. Size did not make this task harder; it made the shortcut obvious.

**The program route is the route, and it is quantified rather than forbidden.**
Row 2 generated 8,594 output tokens and produced 106,274 bytes — the file is
**4.8×** everything the model generated, so most of it never passed through a
generation at all. That is `bash` being unbounded by design (0.0.8b §1) doing
exactly what it is for, and it is why the offline test was never evidence: the
interesting question was never whether a scaffold can append, it is whether a run
can keep its context fixed while the artefact outgrows it. It can.

**It is two runs.** One per size, on a task where the winning move is a
twenty-line regex, and both found it. What this does not show is a writing task
where the content is irreducible — where each unit needs a generation, so the
*number of generations* scales with the output and the context still has to hold
still. That is the harder version of this clause and it is not written yet.

Two things about it are worth knowing before reading its results:

- **Coverage and accuracy are separate numbers, because they fail separately.** A
  run that wrote 1,200 cards with the wrong fields proved the writing claim and
  failed the task; a run that wrote 40 right ones proved nothing about volume.
  The acceptance command counts cards and cannot see whether they are right,
  which is §4.3's shape again — a verdict without a gradient — and the grader
  deliberately does not inherit its blind spot.
- **A program that emits the file is not cheating, and the grade says which
  happened.** Any output a grader can check mechanically is output a script could
  produce, and `bash` is deliberately unbounded (0.0.8b §1) — so an agent that
  writes a program has passed, because the scaffold's claim is about the context
  and not about where the characters came from. What separates the two routes is
  measured rather than forbidden: `generated_chars` against the bytes on disk.

The five live runs of this letter cost **61 minutes of wall clock and 1.8M tokens**
between them — 1,615,987 in and 189,188 out — which is the other thing worth
writing down: making the probes one command each (§1) is what turned "an
afternoon per arm" into an afternoon for the whole table.

The write-up for all of it is [InfiniteAgent
0.0.8d](InfiniteAgent%200.0.8d.md) — what shipped, what it cost, and every claim
in this document scored against the runs.

Credentials come from `.env` — `src/infinite/__init__.py` calls `load_dotenv()`,
so importing the package is enough and nothing needs exporting, as long as the
command is run from the repository. Worth knowing because the failure looks like
a scaffold bug: anything that touches the Anthropic SDK *without* importing
`infinite` first raises "Could not resolve authentication method", which reads
like a missing key rather than a missing import.

## 5. What to do next

Ordered by what each buys, cheapest first.

Items 0 and 4 are done — 4.6's one line, and 4.1's three tiers. Everything left
needs an API key, which is why it is a list rather than a result.

1. **Attribute 4.8's 3/3.** The baseline is run; what is missing is the
   comparison. Four things changed at once, and two arms separate them:
   `--arm no-stall-charge` x3 rules the price in or out (it collected two budget
   units across the three baseline runs, so the prior is "out"), and a run with
   `facts.md` withheld would test 4.5's candidate, which is the one the evidence
   currently points at. Three runs each, about 20 minutes apiece.
2. **Then decide whether tier 3 survives.** It has charged 14 budget units across
   five live runs and 11 of them fell on one run that was genuinely looping. That
   is the right shape and it is five runs. If `no-stall-charge` also goes 3/3, the
   price is buying nothing measurable and tier 1 alone is the honest ship.
3. **Settle 4.3.** Three runs with a *gradient* check against three with a
   binary one — a check that counts remaining stub bodies and prints the count,
   versus one that only passes at zero. It is the only item that could change a
   mechanism rather than a constant, and it is now cheaper than it was: the
   verdict changing is itself progress (`progress.py` counts it), so a gradient
   check and the stall measure test the same hypothesis from two directions.
4. **Write the *irreducible* writing probe (4.9).** `volume` is run and the
   clause holds, but both rows were won with a twenty-line regex, so what they
   show is that the scaffold holds still while an artefact outgrows it — not that
   a run can keep a fixed context while producing output that needs a generation
   per unit. Same shape, two sizes, content a script cannot derive: a translation,
   a per-record judgement, anything where the number of *generations* scales with
   the output. That is the version of this clause that is still open.
5. **Decide depth (4.4).** The choice is between a frame surcharge, a reserve a
   parent must keep, and leaving it unlegislated with the sentence doing the
   work. Whichever, it should be settled by running the probe at
   `--max-depth 0/1/none` more than once each.
6. **Run the flagship — 0.0.8d did not, and that is the open item that matters
   most.** [The Reconstruction Test](The%20Reconstruction%20Test.md) is how to
   build one and how to grade it; the 0.0.7i workspace
   (`runs/reconstruct_infinite_0.0.7i/TASK.md`) is the template. It has never been
   run under 0.0.8 at any letter, and the last version to pass it was 0.0.7f at
   46,684 tokens a generation — so whether the `--frame` geometry, with 18,000
   tokens the ceiling on a whole generation, can rebuild the whole scaffold is
   simply unknown. It is the only test that exercises fan-out,
   it is how every previous letter in this series was judged, and it is now the
   last test a version takes by convention (`Writing a Version`).

   The work is more than the run: the condensed spec stops at 0.0.7f, so the 0.0.8
   series — the structured brief and its `check`, charged children, no depth
   ceiling, destination registers, the shell-reachable registers, 0.0.8d's
   progress tiers — has to be condensed into it first, with a new final config
   table, since every geometry number moved. Budget a session for the spec, and
   for the run itself hours rather than minutes — the one pass took 2h43m over
   580 steps, and 0.0.7e's failure took 17.5 hours before it died.
7. **SWE-bench under `--frame`.** Never run; 0.0.7 `--short` scored 3/7.
8. **The two Design Tests (4.7).** Both are new probes rather than changes. The
   Turing test in particular is small: a tape on disk, a transition table the
   agent may not hold, `--max-steps none`.

## 6. Pitfalls that cost time

- **Until 0.0.8d the eval harness never passed a `check`.** Every one of the
  five 0.0.8 arms had one, `check_every_step` is on by default, and a run through
  `eval.run` got neither — so the heartbeat was inert in every benchmark result
  in this repository, and a "replication" through the harness would not have been
  one. `agent_command` passes a benchmark's `truth["check"]` now. A test asserts
  every arm of every probe is a command `infinite.main` accepts, because a flag
  the scaffold rejects is a three-hour run that dies in its first second.
- **`collect_overrides` read `sys.argv`, not its argument.** Two flags need the
  raw list because `None` is meaningful for them (`--max-depth`, `--max-steps`),
  and reading the process's argv meant the function answered about the process
  rather than about what it was given. Harmless for the CLI, wrong for anything
  driving it in-process — the `depth-1` arm looked like it did nothing. It takes
  `argv` now.
- **The summary tests share one fake model across two threads.** Since 0.0.7f
  the summary of step N is written while step N+1 is generated, so `SummaryModel`
  is called from both and every list on it — `script`, `summaries`, `prompts` —
  is shared. The race was latent until 0.0.8d put a workspace scan in front of
  the summary submit and shifted the timing; the suite then failed about one run
  in five, in whichever summary test lost. It is a lock now. If a summary test
  fails once and passes on re-run, suspect this shape rather than the scaffold.
- **Never launch a run with `nohup … &`.** It gets orphaned and reaped mid-run;
  an 80-step run died at step 23 that way. Use the harness's own background
  mechanism and let the process be the foreground of that call.
- **Change one variable per arm.** Two arms of the 0.0.8 A/B got a stricter
  `check` than the other two, which cost the whole comparison; a fifth run was
  needed to repair it. `eval/run.py`'s `ARMS` now names one flag each and a test
  asserts that each is one flag, so an arm is a word you type rather than a set
  of flags you remember.
- **`python` is not on PATH here; `python3` is.** A parent that writes
  `python -c …` as a child's `check` burns the child's entire budget on exit 127.
  The scaffold now says so, but the brief still has to be right. And *which*
  `python3` matters under the firewall: `/usr/bin/python3` works, the venv's does
  not, because its real prefix is outside `SYSTEM_READ_DARWIN`. See 4.6.
- **The token figures in the 0.0.8 note were `max_request_chars / 2.6`, not
  measurements.** They have been replaced with the `usage` records, and
  `eval.analyse` now reports those: its `max in` column sums the `usage` input
  fields and reproduces the re-derived 8,233 and 8,592 exactly. Anything you
  quote as "tokens" comes from there; `max_request_chars` is still in the JSON
  and is still chars.
- **Rebuild the probe workspace from `runs/reconstruct_infinite_0.0.7i`** — the
  nine sibling modules plus the 99-line stub — and strip `__pycache__`. A
  workspace reused across arms carries the previous arm's scratch files. This is
  `eval/benchmarks/width.py` now: it copies the corpus, strips the caches, puts
  the arm in the instance id so two arms cannot land in one directory, and
  `--dry-run` builds the workspace so the recipe can be checked without spending
  a run. Since `runs/` is gitignored the corpus is still only on the machine that
  produced it — `INFINITE_WIDTH_SOURCE` points elsewhere, and an absent corpus
  fails loudly with the recipe rather than grading zero.
- **The probe's own grader does not believe the response.** Two arms reported a
  module they had not written, one of them returning `ok=True` while its own
  response said the stub was untouched. `width.grade` runs the import and counts
  the remaining `NotImplementedError`, keeps what the agent claimed, and reports
  `untouched` separately — three of five arms ended there, and a run that wrote
  457 lines that do not import is a different failure from one that wrote
  nothing.
- **`runs/steploop_control` is the 0.0.7 comparison and it is not `--short`.** Its
  largest request was 23,251 tokens. Anything that compares against "0.0.7"
  should say which geometry it means.
- **0.0.7i's own write-up undercounts what it spent on this task.** It says "two
  children spent 240 steps"; the trajectories say four children were given
  `step_loop.py` and spent 420 (150, 110, 90, 70). One of the four returned
  `ok=True`. Do not take the 240 forward.

## 7. Reading order

1. [Depth, Volume and Width](Depth,%20Volume%20and%20Width.md) — the diagnosis,
   and §7's numbered list, which everything since refers to as 7.1-7.6.
2. [Design Tests (Top Down)](Design%20Tests%20(Top%20Down).md) — one page, and
   the only statement of what "done" means.
3. [0.0.8a](InfiniteAgent%200.0.8a.md), [0.0.8b](InfiniteAgent%200.0.8b.md),
   [0.0.8c](InfiniteAgent%200.0.8c.md) — the letters.
4. [0.0.8](InfiniteAgent%200.0.8.md) — the build note, which scores each claim in
   those letters against the runs. §9 is the table to argue with. Its numbers
   were re-derived from the trajectories on 2026-08-19 and several moved; where a
   figure was replaced the note says what the old one was and why it was wrong.
5. [0.0.8d](InfiniteAgent%200.0.8d.md) — the build note for this document's own
   iteration: the diagnosis in §4.1, the mechanism, the five live runs, the first
   Design Test scored clause by clause, and what the runs said that the design
   did not. Read it before §5 below, because it is what §5 is left over from.
6. [0.0.7i](InfiniteAgent%200.0.7i.md) and
   [0.0.7j](InfiniteAgent%200.0.7j.md) — the two that set up 0.0.8, if you want
   the immediate history rather than all of it.
7. [The Reconstruction Test](The%20Reconstruction%20Test.md) — the task every
   letter of 0.0.7 was judged by, written down: how to build one for a version,
   how to grade it, and the record of who has passed it. §5 item 6 is the one
   0.0.8d owes.

The git history is one commit per change with the evidence in the message; `git
log --oneline` from the baseline (`b9a3a4c`) is a readable account of the
iteration.
