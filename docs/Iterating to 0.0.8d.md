# Iterating to 0.0.8d

*Read this first if you are picking the project up. It is the state of play
after 0.0.8: what was built, what was measured, what broke, what is unanswered,
and what to do next. Everything in it is checkable against the repository —
where a number appears, the run that produced it is named.*

---

## 0. Ninety seconds

InfiniteAgent keeps a model's active context to a fixed set of registers and
puts everything else on disk. The 0.0.7 series got reading right — a 10MB corpus
answered in nine steps at an 8,000-token context — and then failed, four times,
on one task: implement a module that calls into six others. [Depth, Volume and
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
> that task is *when a run starts writing*, and nothing in 0.0.8 makes it start
> sooner.

That sentence is the brief for 0.0.8d.

## 1. The ground

```
src/infinite/
  agent.py       the loop; the check; charging; spawn/resume
  config.py      every geometry and knob; the presets (SHORT, WIDE_OUTPUT, FRAME)
  registers.py   the register file and the dump
  regfile.py     0.0.8a: the registers as $R0.. and $REGDIR/0.. around bash
  index.py       7.1: the AST index behind `lookup`
  prompt.py      the system message, and `build_brief`
  tools.py       bash, load, set, set_target, lookup, spawn, resume
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
uv run pytest test                      # 271 tests, offline, ~17s
python -m eval.analyse runs/<workspace> # what a run actually did
python -m eval.run babilong --config 1M --split qa2 -n 1 --profile frame
```

Everything 0.0.8 adds has a flag to turn it off, so any of it can be A/B'd:
`--no-lookup`, `--no-shell-registers`, `--no-charge`, `--no-checks`,
`--no-live-check`, `--max-depth N`.

## 2. What 0.0.8 achieved

**The probe passed.** `step_loop.py` — the module that defeated 0.0.7 four times
— was implemented and imported in **56 steps at 8,053 tokens of input**
(`runs/steploop_0.0.8`), and again in 50 at 8,226 (`runs/steploop_0.0.8_live2`).
The 0.0.7 attempt that managed it at all needed **22,460** tokens of input and
82 steps, 68 of them spent by a child writing a digest first
(`runs/steploop_control`). At 6,063 tokens 0.0.7 spent 240 steps and wrote
nothing.

**Reading did not move**, which is what §8 predicted, since nothing in 7.1-7.4
touches depth. Six of six under `--frame`, four of them in fewer steps than
0.0.7g — including a 10M-token BABILong instance in nine steps against
seventeen.

**The fixed-context property holds and is now a test rather than a claim.**
`test_fixed_context.py` scales steps, depth, bytes read and lines written and
asserts the largest request does not move. Live, one run put five agents at five
depths on the API and their largest requests spanned 1,025 tokens.

**Three questions the letters left open are now answered:**

- *Does transit cost anything?* (0.0.8a §7.1) **No.** Zero of 34,042 generated
  argument characters were values already sitting in a register. Registers-as-
  files stands on the working set, not on saved output tokens.
- *Does the brief pay for its schema?* (0.0.8c §9.1) **Yes, nine characters
  against a 4.7× saving.** `spawn`'s schema went 1,681 → 1,690 chars; generated
  briefing fell from a median 2,545 chars over 34 spawns to 545 over 9.
- *Is the canvas what a working set must land in?* (0.0.8a §5, 7.6) **No** —
  see §4 below.

**And 7.4's actual ask is met**: `Config.context_tokens` reports usable working
set beside the total. `--frame` is 5,840 characters of agent-controlled space
inside a ~16,400-token generation, against 0.0.7g's 3,280 inside 7,453.

## 3. What was tested, so you do not redo it

| | how | result |
| --- | --- | --- |
| every mechanism in the letters | 86 offline tests in `test/infinite_0_0_8_frames/` | pass |
| the fixed-context property | `test_fixed_context.py`, four axes | pass |
| reading | 6 BABILong / ∞Bench instances, `--profile frame` | 6/6 |
| the width probe | 5 live runs of `step_loop.py`, 80 steps each | 3 wrote a module, 2 passed |
| 7.6's canvas bisection | one run at canvas 12,288 | negative |
| transit, brief cost | read off trajectories | answered |

The five probe arms are in `runs/steploop_0.0.8*`; `runs/steploop_0.0.8-diag`
and `-aborted` are earlier diagnostic runs kept because §7 of the build note
cites them. **`runs/` is gitignored** — those workspaces are 13MB of trajectory
and live only on the machine that produced them — so the arms are distilled into
`eval/results/steploop-0.0.8.json`, which is in the repository and carries the
per-agent numbers every claim here rests on. If you are on a fresh clone, that
file is your evidence.

## 4. The problems, ranked

### 4.1 A run does not start writing until it thinks it has every fact

This is the one that matters, and it is what the probe measures. Of five arms,
two interleaved reading and writing and both passed; three spent between 79 and
80 of their 80 steps acquiring signatures — building up to fifteen scratch files
of `grep '^def'` output — and one of those wrote its whole 457-line module in a
single generation on step 80, failed the check on a one-line import error, and
had nothing left to fix it (`runs/steploop_0.0.8_d1`).

Charging prices delegation. Nothing prices deliberation. A step that runs one
`grep` and a step that writes a module cost the same, and the budget line says
nothing about what the steps were *for*.

### 4.2 The canvas is not the binding constraint

0.0.8a §5 argued the working set has to land in one register whole, and set the
canvas to 4,096 on that argument. 7.6 asked for the bisection. It was run
(`runs/steploop_0.0.8_wide`): canvas 12,288, working set 14,032 characters,
input 11,386 tokens — and it wrote no more code than 4,096 did. Whatever binds
this task, it is not the size of the one wide register.

Two candidates survive: the binding quantity is the *whole* input rather than
one register (0.0.7 succeeded at 22,460 and every 0.0.8 arm was under 12,000),
or it is not a context quantity at all.

### 4.3 A check that cannot get closer may be worse than none

The strongest untested signal in the data, and cheap to settle. Both arms given
`python3 -c 'import …'` wrote a working module; both arms given that **and**
`! grep -q NotImplementedError` wrote no implementation at all in eighty steps.
The compound check cannot move until the last stub body is gone, so it is a
verdict without a gradient.

One run per cell, so this is a hypothesis. It is the only item on this list that
could change a mechanism rather than a constant.

### 4.4 Unbounded depth produced a pass-through cascade

Removing `max_depth` (0.0.8c §6) had a root forward its entire goal at step 4,
its child forward the same goal at step 12, and so on to depth four — budget
decaying 80 → 58 → 32 → 15 → 8, with 39% of the run spent by frames orienting
themselves and then delegating, and no frame writing anything
(`runs/steploop_0.0.8-diag`).

Charging bounded it, exactly as 0.0.8c §6 promised: the chain terminated on
budget rather than on a ceiling. It did not *deter* it, because forwarding a goal
is free under charging — it costs the parent what doing the work would have
cost, minus the steps the child spends re-orienting, which the parent never
sees. The system message now names the move ("handing a child your own goal
unchanged is not a descent") and the cascade did not recur, but that is one
observation and it is advice, which five runs have said does not land.

0.0.8c §9.4 asked whether depth wants a price rather than freedom, and said the
evidence for `max_depth = 1` was a real run. So is the evidence against
unbounded depth.

### 4.5 `facts.md` is read and never written

0.0.8b §4's memo table exists, is named in the system message, and was `cat`ed
repeatedly by agents that never appended a line to it. Meanwhile the same agents
hand-built the same artefact as scratch files, over and over. A table nobody
writes is a table nobody can read.

### 4.6 Two Design Tests have no evidence at all

[Design Tests (Top Down)](Design%20Tests%20(Top%20Down).md) asks for
**computational completeness** and for **stack mode without recursion**. The
build note §4 argues the first is architecturally supplied and admits no run has
tested it; the second was answered for the scaffold by 0.0.8c and never put to
the model, which is what the test actually asks. And its second half — stacked
file reads, several files open with the status of each kept — is a real gap:
`load(path, start)` is stateless and there is no open-file table anywhere.

## 5. What to do next

Ordered by what each buys, cheapest first.

1. **Settle 4.3.** Three runs of the probe with a *gradient* check against three
   with a binary one — e.g. a check that counts remaining stub bodies and prints
   the count, versus one that only passes at zero. Costs six 80-step runs and
   could change what `check` is for. Use `--check` on the root; the harness is
   `runs/steploop_0.0.8*` and the workspace recipe is in §6.
2. **Replicate the headline.** Everything in §2 about the probe is n=1 per arm on
   a task with enormous variance. Three more runs of the plain `--frame`
   configuration would turn "2 of 5 passed" into a number worth quoting.
3. **Price deliberation (4.1).** The design question is what a budget should be
   denominated in. Steps treat a `grep` and a module as equal; charging made
   delegation visible by making it *cost* something the agent watches. The
   analogue for reading is not obvious and is the most interesting thing on this
   list — 0.0.8d's subject, probably.
4. **Decide depth (4.4).** The choice is between a frame surcharge, a reserve a
   parent must keep, and leaving it unlegislated with the sentence doing the
   work. Whichever, it should be settled by running the probe at
   `--max-depth 0/1/none` more than once each.
5. **Run the flagship.** The full reconstruct task
   (`runs/reconstruct_infinite_0.0.7i/TASK.md`) has never been run under 0.0.8.
   About three hours. It is the only test that exercises fan-out, and it is how
   every previous letter in this series was judged.
6. **SWE-bench under `--frame`.** Never run; 0.0.7 `--short` scored 3/7.
7. **The two Design Tests (4.6).** Both are new probes rather than changes. The
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
  The scaffold now says so, but the brief still has to be right.
- **Rebuild the probe workspace from `runs/reconstruct_infinite_0.0.7i`** — the
  nine sibling modules plus the 99-line stub — and strip `__pycache__`. A
  workspace reused across arms carries the previous arm's scratch files.
- **`runs/steploop_control` is the 0.0.7 comparison and it is not `--short`.** It
  ran at 22,460 tokens of input. Anything that compares against "0.0.7" should
  say which geometry it means.

## 7. Reading order

1. [Depth, Volume and Width](Depth,%20Volume%20and%20Width.md) — the diagnosis,
   and §7's numbered list, which everything since refers to as 7.1-7.6.
2. [Design Tests (Top Down)](Design%20Tests%20(Top%20Down).md) — one page, and
   the only statement of what "done" means.
3. [0.0.8a](InfiniteAgent%200.0.8a.md), [0.0.8b](InfiniteAgent%200.0.8b.md),
   [0.0.8c](InfiniteAgent%200.0.8c.md) — the letters.
4. [0.0.8](InfiniteAgent%200.0.8.md) — the build note, which scores each claim in
   those letters against the runs. §9 is the table to argue with.
5. [0.0.7i](InfiniteAgent%200.0.7i.md) and
   [0.0.7j](InfiniteAgent%200.0.7j.md) — the two that set up 0.0.8, if you want
   the immediate history rather than all of it.

The git history is one commit per change with the evidence in the message; `git
log --oneline` from the baseline (`b9a3a4c`) is a readable account of the
iteration.
