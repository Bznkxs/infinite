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

That sentence is the brief for 0.0.8d, and it is the second version of it. The
first said the task turned on *when a run starts writing*; §4.1 measures that
and it is false — both frames that produced a working module wrote in the last
fifth of their budget. Two other things have happened under this heading: the
numbers in the 0.0.8 note were re-derived from the trajectories and several
moved (§7), and `lookup` was removed outright (§4.0).

## 1. The ground

```
src/infinite/
  agent.py       the loop; the check; charging; spawn/resume
  config.py      every geometry and knob; the presets (SHORT, WIDE_OUTPUT, FRAME)
  registers.py   the register file and the dump
  regfile.py     0.0.8a: the registers as $R0.. and $REGDIR/0.. around bash
  prompt.py      the system message, and `build_brief`
  tools.py       bash, load, set, set_target, spawn, resume
  workspace.py   the shared directory, and facts.md
eval/
  run.py         benchmark harness  (--profile frame)
  analyse.py     reads §8's measures off a run's trajectories
test/
  infinite_0_0_1_simple/   the 0.0.7 suite, updated
  infinite_0_0_8_frames/   the 0.0.8 suite (90 tests)
eval/results/
  steploop-0.0.8.json      the five probe arms, distilled (runs/ is gitignored)
```

```bash
uv run pytest test                      # 262 tests, offline, ~18s — 261 pass, see §4.6
python -m eval.analyse runs/<workspace> # what a run actually did
python -m eval.run babilong --config 1M --split qa2 -n 1 --profile frame
```

Everything 0.0.8 adds has a flag to turn it off, so any of it can be A/B'd:
`--no-shell-registers`, `--no-charge`, `--no-checks`, `--no-live-check`,
`--max-depth N`. There is no `--no-lookup` any more; see §4.0.

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

**0.0.8d's mechanism, in three tiers, cheapest first.** (1) The scaffold
measures progress: every step records what durable state it changed, and
`analyse.py` reports the stall streaks per agent. (2) The dump says so once a
streak passes a threshold — one line, beside the budget line, which is the one
piece of state five runs show the agent actually responds to. (3) *Not yet*: a
stall streak charged against the budget, the way `charge_children` prices
delegation. Held until (1) says what the streaks are, by §6's one-variable rule.

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
What is left is the question the bug was hiding: does a memo table an agent can
actually see change what it does, or is `grep`-before-you-look a habit no
sentence installs? That is a re-run, not a design question — and it is now
`test_memo_table.py` rather than a claim.

### 4.6 One test fails, and it is about `python3` under the firewall

`test_scratch.py::test_an_agents_shell_puts_temporary_files_inside_the_workspace`
fails deterministically: 270 of 271 pass. Neither the test nor `firewall.py` has
changed since the baseline commit, so this is the environment moving, not 0.0.8.

The cause matters more than the test. Under `uv run`, `python3` resolves to
`.venv/bin/python3` → `~/.local/share/uv/python/cpython-3.13.14-.../bin/python3.13`,
and `SYSTEM_READ_DARWIN` in `firewall.py` does not list that path — so the
sandboxed shell's interpreter cannot read its own stdlib and dies with
`ModuleNotFoundError: No module named 'encodings'`. The probe swallows stderr,
so the register lands empty and the assert fires.

This is a live-run hazard, not just a red test. Every `check` in the 0.0.8 arms
was a `python3 -c 'import …'`, and they worked only because those runs resolved
`python3` to `/usr/bin/python3` (whose real prefix is under `/Applications`,
which *is* allowed). An agent that reaches for the project's own interpreter gets
`Operation not permitted` and no explanation. The fix is to add the running
interpreter's `sys.base_prefix` to the readable set, which is also what makes
the test environment-independent.

Relatedly and cosmetically: every check emits two
`python3: error: couldn't create cache file '…/xcrun_db-…' (errno=Operation not
permitted)` lines into its `tool_output`, and the `[Check]` dump line has an
unbalanced opening parenthesis.

### 4.7 Two Design Tests have no evidence at all

[Design Tests (Top Down)](Design%20Tests%20(Top%20Down).md) asks for
**computational completeness** and for **stack mode without recursion**. The
build note §4 argues the first is architecturally supplied and admits no run has
tested it; the second was answered for the scaffold by 0.0.8c and never put to
the model, which is what the test actually asks. And its second half — stacked
file reads, several files open with the status of each kept — is a real gap:
`load(path, start)` is stateless and there is no open-file table anywhere.

## 5. What to do next

Ordered by what each buys, cheapest first.

0. **Fix 4.6; it is one line.** Add the running interpreter's `sys.base_prefix`
   to the firewall's readable roots. It turns the suite green and stops `python3`
   being a coin flip inside the sandbox. (4.0 and 4.5 are already done.)
1. **Re-run the probe on the 4.0 geometry before anything else is read out of
   it.** Removing `lookup` moved the fixed half of every request, so none of the
   five arms is a like-for-like comparison any more. Two runs of plain `--frame`
   re-establish the baseline, and they also answer 4.5's question for free: with
   `facts.md` present from step one and no tool filling it, either the agent
   appends to it or it does not.
2. **Replicate the headline while you are there.** Everything in §2 about the
   probe is n=1 per arm on a task with enormous variance. Three runs of plain
   `--frame` on the 4.0 geometry would turn "2 of 5 passed" into a number worth
   quoting, and they are the same runs item 1 asks for.
3. **Settle 4.3.** Three runs of the probe with a *gradient* check against three
   with a binary one — e.g. a check that counts remaining stub bodies and prints
   the count, versus one that only passes at zero. Costs six 80-step runs and
   could change what `check` is for. Use `--check` on the root; the harness is
   `runs/steploop_0.0.8*` and the workspace recipe is in §6.
4. **Make progress observable (4.1).** 0.0.8d's subject, and now the first
   item rather than the fourth — everything above it is a measurement that
   cannot be read without it. Steps treat a `grep` and a module as equal;
   charging made delegation visible by making it *cost* something the agent
   watches. The analogue is not a price on reading, which would tax a strategy
   that works, but a price on *not moving*: a stall costs nothing, a streak of
   them costs budget. Measure first (the trajectories on disk are enough), show
   second, charge third.
5. **Decide depth (4.4).** The choice is between a frame surcharge, a reserve a
   parent must keep, and leaving it unlegislated with the sentence doing the
   work. Whichever, it should be settled by running the probe at
   `--max-depth 0/1/none` more than once each.
6. **Run the flagship.** The full reconstruct task
   (`runs/reconstruct_infinite_0.0.7i/TASK.md`) has never been run under 0.0.8.
   About three hours. It is the only test that exercises fan-out, and it is how
   every previous letter in this series was judged.
7. **SWE-bench under `--frame`.** Never run; 0.0.7 `--short` scored 3/7.
8. **The two Design Tests (4.7).** Both are new probes rather than changes. The
   Turing test in particular is small: a tape on disk, a transition table the
   agent may not hold, `--max-steps none`.

## 6. Pitfalls that cost time

- **Never launch a run with `nohup … &`.** It gets orphaned and reaped mid-run;
  an 80-step run died at step 23 that way. Use the harness's own background
  mechanism and let the process be the foreground of that call.
- **Change one variable per arm.** Two arms of the 0.0.8 A/B got a stricter
  `check` than the other two, which cost the whole comparison; a fifth run was
  needed to repair it.
- **`python` is not on PATH here; `python3` is.** A parent that writes
  `python -c …` as a child's `check` burns the child's entire budget on exit 127.
  The scaffold now says so, but the brief still has to be right. And *which*
  `python3` matters under the firewall: `/usr/bin/python3` works, the venv's does
  not, because its real prefix is outside `SYSTEM_READ_DARWIN`. See 4.6.
- **The token figures in the 0.0.8 note were `max_request_chars / 2.6`, not
  measurements.** They have been replaced with the `usage` records, which is what
  `python -m eval.analyse` should learn to report; it currently reports request
  *chars* only. Anything you quote as "tokens" should come from `usage`.
- **Rebuild the probe workspace from `runs/reconstruct_infinite_0.0.7i`** — the
  nine sibling modules plus the 99-line stub — and strip `__pycache__`. A
  workspace reused across arms carries the previous arm's scratch files.
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
5. [0.0.7i](InfiniteAgent%200.0.7i.md) and
   [0.0.7j](InfiniteAgent%200.0.7j.md) — the two that set up 0.0.8, if you want
   the immediate history rather than all of it.

The git history is one commit per change with the evidence in the message; `git
log --oneline` from the baseline (`b9a3a4c`) is a readable account of the
iteration.
