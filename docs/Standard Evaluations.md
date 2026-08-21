# Standard Evaluations

*Every evaluation this project runs, in one place: what it poses, the command
that runs it, what the grade actually checks, and — stated rather than left to
be rediscovered — what it does not check and what has no script at all.*

Nine evaluations, of which **six have a command, one is hand-built, and two do
not exist.** Gaps are marked **MISSING** where they arise and collected twice:
**§3 is what has no script**, **§4 is what has no correctness check**. Nothing
here implements any of them — they are recorded so that a version's §3 can name
what it is about to run, and so a reader can tell a measurement from an
assumption.

Related: [Design Tests (Top Down)](Design%20Tests%20(Top%20Down).md) is what
these are evaluating against; [Evaluation](Evaluation.md) is the detail on the
three public benchmarks; [The Reconstruction
Test](The%20Reconstruction%20Test.md) is the detail on the flagship; [Writing a
Version](Writing%20a%20Version.md) is when each is run.

---

## 1. The battery

| # | evaluation | tests | command | verdict comes from |
| --- | --- | --- | --- | --- |
| 1 | **offline suite** | the scaffold does not grow — steps, depth, bytes read, lines written | `uv run pytest test` | 332 assertions against a `FakeModel` |
| 2 | **`width`** | infinite complexity | `python -m eval.run width -n 3 --profile frame` | the module imports, and no `NotImplementedError` is left |
| 3 | **`volume`** | infinite writing | `python -m eval.run volume --config 120 --profile frame`, then `--config 1200` | every field of every card, against the seeded answers |
| 4 | **BABILong** | infinite reading, 0k to 10M tokens | `python -m eval.run babilong --config 1M --split qa2 -n 1 --profile frame` | the gold string appears in the answer |
| 5 | **∞Bench** | infinite reading, whole novels | `python -m eval.run infinitebench --config longbook_choice_eng -n 3` | the chosen letter, or ≥50% token overlap |
| 6 | **SWE-bench Verified** | generality, on someone else's task | `python -m eval.run swebench -n 5 --profile frame` | the held-out `FAIL_TO_PASS` / `PASS_TO_PASS` tests |
| 7 | **the Reconstruction Test** | all of it at once | **MISSING** — hand-built workspace, see §3.1 | three gates, one of which needs a person. 0.0.8d **failed** it ([`reconstruct-0.0.8d.json`](../eval/results/reconstruct-0.0.8d.json)) |
| 8 | **computational completeness** | the agent is Turing-complete | **MISSING** — no probe exists | — |
| 9 | **stack mode without recursion** | an open-file table the agent manages itself | **MISSING** — no probe exists | — |

Two commands sit beside them and are not evaluations:

```bash
python -m eval.run --report          # every results.jsonl, grouped, with the largest request
python -m eval.analyse runs/<ws>     # what one run did: reads/writes, stalls, request sizes
```

`--profile` picks the geometry under test (`frame`, `wide`, `short`, `full`) and
`--arm` picks one variable off the baseline. One arm is one flag, deliberately:
two arms of the 0.0.8 A/B differed in two things and cost the whole comparison.

## 2. What each one grades, and what it cannot see

### 2.1 The offline suite

`uv run pytest test` — 332 tests, ~21 seconds, no network and no key. The four
axes of the fixed-context claim are asserted directly in
`test/infinite_0_0_8_frames/test_fixed_context.py`: the request does not grow
with the number of steps, with stack depth, with the size of what is read, or
with the size of what is written.

**What it cannot see:** every one of those tests drives a `FakeModel`. They prove
the *scaffold* does not grow, which is a real property and is not the claim —
"complete tasks however complicated they are" is about a model working inside
the thing. The offline suite can never fail in the way the project cares about.

### 2.2 `width` — infinite complexity

`infinite_agent/step_loop.py` is a 99-line stub in a package whose nine other
modules are written; the module calls into six of them, so implementing it means
holding some forty signatures and field names true at once. 80 steps, which is
what all five 0.0.8 arms were given.

**What it grades** (`eval/benchmarks/width.py:161`): the module imports under a
real interpreter, and `NotImplementedError` no longer appears in it. It also
reports `lines`, `untouched`, `stubs_left` and the import error, so a run that
wrote 457 lines that do not import is a different row from one that wrote
nothing.

**What it cannot see: whether the module works.** This is the largest correctness
hole in the battery and it sits on the flagship clause — see §4.1.

**Not reproducible on a fresh clone.** The corpus is copied out of
`runs/reconstruct_infinite_0.0.7i`, `runs/` is gitignored, and
`INFINITE_WIDTH_SOURCE` is the override. An absent corpus is a loud failure with
the recipe in it rather than a run that grades zero for the wrong reason — but it
does mean nobody else can run clause 4. See §4.3.

### 2.3 `volume` — infinite writing

`records.md` holds N records generated from a seed; the agent writes `cards.md`,
one seven-line card per record, in order. Run at N=120 and again at N=1,200: the
claim is not that either run succeeds, it is that the largest request does not
move while the output does.

**What it grades** (`eval/benchmarks/volume.py:210`): **correctness in full.**
Every card is parsed and all six fields are compared against the answers built
from the same seed, and coverage and accuracy are reported separately because
they fail separately — `coverage` (how far through the corpus it got), `exact` /
`accuracy` (how many cards had every field right), `first_wrong` (the first key
and which fields), `duplicate_keys`, and `output_bytes`. A run that wrote 1,200
cards with wrong fields proves the writing claim and fails the task, and the row
says so. The grader is deliberately lenient about layout and strict about
fields.

**What it cannot see — and this one is a real gap: the agent's own check has no
correctness in it.** The acceptance command the scaffold runs every step is
`test $(grep -c '^### ' cards.md) -eq N` (`volume.py:104`). It counts cards. A
file of 1,200 cards with every field wrong satisfies it, and the run is told it
is done. The task text warns the agent about exactly this — *"it counts cards; it
does not check them… check your own work against the records before you answer"*
— which is a warning standing in for a check. Both 0.0.8d rows came back 120/120
and 1200/1200 so it has never bitten, and it is the handoff's §4.3 — "a check
that cannot get closer may be worse than none" — in the one place it would be
cheap to fix. See §4.2 below.

**Also unmeasured: whether the content is irreducible.** Both rows were won with
a twenty-line regex, so what they show is a context holding still while an
artefact outgrows it — not a run producing output that needs a generation per
unit. The harder probe — content a script cannot derive, so the number of
*generations* scales with the output — does not exist. Nor, despite the module
docstring saying so, does the row show which route a run took: see §3.5.

### 2.4 BABILong, ∞Bench, SWE-bench

Detail is in [Evaluation](Evaluation.md); what matters here is what the verdicts
mean.

- **BABILong** grades by the benchmark's own metric: the gold string's members
  appear in the answer. Exact match is reported alongside, because the two
  differing is worth seeing.
- **∞Bench** multiple choice is an exact letter. **Free-form is token overlap ≥
  0.5**, which is the benchmark's shape and a weak grader: a wrong answer that
  reuses the reference's words can pass, and a right one phrased differently can
  fail. Treat a free-form row as an indication, not a result.
- **SWE-bench** is the strongest grader in the battery — held-out tests the agent
  never saw, with the test patch applied after the run and every file it touches
  reset first, so an agent that edits tests gains nothing. It is also the only
  one that verifies *itself*: on a failure the official gold patch is applied and
  graded, and an instance whose gold patch does not pass is excluded as
  unreproducible rather than counted against the agent. Instances before 2022
  are refused with the reason stated.

### 2.5 The Reconstruction Test

The agent rebuilds InfiniteAgent from a condensed specification of itself and
then runs what it built. Three gates — complete, works, faithful — and the
[full document](The%20Reconstruction%20Test.md) is how to build one.

**There is no script.** See §3.1. It is also the only evaluation whose third gate
cannot be automated: faithfulness to a specification is a person spot-checking
the config table, the literal dump text, the rejected-write behaviour and a few
error strings.

## 3. What has no script

### 3.1 The Reconstruction Test — MISSING

Everything else in §1 is one command. This is a directory assembled by hand: a
condensed spec written for the version, `TASK.md`, `schema.json`, and a venv and
a CPython installed *inside* the workspace because the firewall makes it the
only readable place. It is not in `eval/benchmarks/`, has no
`load`/`materialise`/`grade`, and cannot be run through `eval.run`.

What a `eval/benchmarks/reconstruct.py` could do, when someone writes it: build
the workspace from a named spec file, launch the run, and grade the two
mechanical gates — the module layout exists and imports, and the acceptance run
happened and its answer matches the ground truth in the response. What it cannot
do is condense the spec (that is the version's own writing) or grade
faithfulness. So the script would remove the setup errors, which is most of what
has gone wrong: every pitfall in the 0.0.8d handoff's §6 is a workspace that was
built wrong.

**To implement later.** Not now.

0.0.8d's attempt is the argument for doing it sooner. Of the four things that
went wrong, two were staging rather than scaffold — the root was given no
`--check`, and every child's check tested `import`, which passes on a package
whose modules do not agree at their seams (0.0.8d §10.1). A script that built the
workspace would not have made those mistakes, because the check would have been
part of the harness rather than a thing an operator remembers.

### 3.2 A command that runs the standard set — MISSING

`eval.run` takes one benchmark per invocation. The standard battery exists only
as a list of commands in prose, in three places (the README, the handoff's §1,
and §1 above), so "the standard evaluations were run" is a claim nobody can
check and a skipped probe leaves no trace. There is no `--all`, no `Makefile`,
no ordering, and nothing that fails if one is missing.

**To implement later:** one entry point that runs the battery at a given profile
and prints the table, so a version's §4 can cite a single invocation.

### 3.3 Distilling `eval/results/*.json` — MISSING

[Writing a Version](Writing%20a%20Version.md) requires a figure in a version
document to be backed by `eval/results/<probe>-<version>.json`, because `runs/`
is gitignored and a fresh clone has none of it. The three files that exist —
`steploop-0.0.8.json`, `volume-0.0.8d.json`, `width-0.0.8d.json` — were written
by hand from `results.jsonl`. Nothing generates them, nothing checks that a
distilled figure matches the run it names, and nothing notices when a document
quotes a number that is in neither.

**To implement later:** a `python -m eval.distil <benchmark> <version>` that
reads `runs/eval/<benchmark>/results.jsonl` and writes the file, so the citation
and the run cannot drift.

### 3.4 A regression gate — MISSING

`--report` aggregates everything that has ever been run and prints it. Nothing
stores an expectation, so nothing fails when a number moves: a regression is
noticed only by a person comparing the table to a document. The offline suite is
the exception — it asserts the fixed-context property directly and does fail.

**To implement later, and lower priority than the rest:** the live numbers have
enormous variance at n=3, so a naive threshold would mostly produce false
alarms. The honest version is probably a recorded baseline per probe and a
report that shows the delta, not a gate that fails.

### 3.5 `generated_chars` is not in the row — MISSING plumbing

`volume`'s whole argument for not forbidding the program route is that the route
is *measured*: a file far larger than everything the model generated was emitted
by a script, one where they are comparable was written out. The module docstring
says the grade reports it. It does not — `generated_chars` is computed by
`eval/analyse.py:163`, a separate command over the workspace, and no key of that
name appears in `runs/eval/volume/results.jsonl`. So the distinction the probe
rests on has to be recovered by hand, and the 4.8× figure in 0.0.8d §5 was.

**To implement later:** carry it in `measure()` beside `max_request_tokens`, so
every row of every probe says how much of its output passed through a
generation. Small, and it makes a claim in three documents checkable.

## 4. What has no correctness evaluation

### 4.1 `width` grades "it imports", not "it works"

`grade()` runs `python -c 'import infinite_agent.step_loop'` and counts
`NotImplementedError`. Both are necessary; neither is sufficient. **A
`step_loop.py` that imports cleanly, has no stub bodies left, and runs not one
step correctly scores `correct: true`** — and clause 4 of the Design Test, the
one this whole series is shaped by, currently rests on that verdict. 0.0.8d's
3/3 means three modules that import.

The mitigation in place is real but partial: the machine decides rather than the
response, which is why the probe exists at all — two 0.0.8 arms reported a module
they had not written, one returning `ok=True` while its own response said the
stub was untouched. Import-and-no-stubs catches those. It catches nothing subtler.

Note that the corpus does not close this for free: the 0.0.7i workspace ships a
`tests/` directory, but it has no `test_step_loop.py` — the module the probe
targets is the one module with no behavioural test — and `width`'s `COPY` does
not include `tests/` anyway.

**To implement later:** a behavioural check to run in `grade()` after the import
— drive the reconstructed loop for one step against a fake model and assert the
trajectory record it writes. Until then, every `width` result in this repository
should be read as *imports and is fully implemented*, not as *correct*.

### 4.2 `volume`'s in-run check counts, it does not verify

§2.3 above. The post-hoc grader checks every field; the check the agent sees
counts `### ` lines. The gap is between what the run is told and what the row
records, so a run can finish "successfully" and grade 0% accurate.

**To implement later:** a check that verifies a sample of cards against
`records.md` and prints how many were right, which is also the gradient the
handoff's §4.3 asks for — the verdict changing is itself progress, so a gradient
check and the stall measure test the same hypothesis from two directions.

### 4.3 `width` cannot be run by anyone else

Its corpus is a gitignored directory on one machine. That is not a correctness
gap in the grader, but it has the same effect on the result: the clause cannot be
independently reproduced.

**To implement later:** either check a minimal corpus in — the nine written
modules, the stub, `API.md` and the spec, without the trajectories that make the
directory hundreds of megabytes — or generate one deterministically the way
`volume` does.

### 4.4 ∞Bench free-form is graded by word overlap

§2.4 above. Reported as `f1` so the row shows what it is; still not a correctness
verdict. Prefer the multiple-choice configuration when the point is a number.

### 4.5 Two Design Tests have no evaluation of any kind

Computational completeness, and stack mode without recursion. Both are new probes
rather than changes to the scaffold. The Turing one is small — a tape on disk, a
transition table the agent may not hold, `--max-steps none`. The second half of
the stack test is a real gap in the scaffold and not only in the evaluation:
`load(path, start)` is stateless and there is no open-file table anywhere.

## 5. Reading a row honestly

Three things are true of every live number in this repository and are easy to
forget when a table is short:

- **n is small.** Three runs of `width` and one of each `volume` size. The
  variance on the hard task is enormous — 0.0.8 went 2/5 on it — so a 3/3 is a
  result and not a rate.
- **`correct` means what §2 says it means for that probe**, and the four
  meanings are not comparable: held-out tests (SWE-bench), every field checked
  (`volume`), a substring (BABILong), an import (`width`).
- **The number the Design Test turns on is not `correct` at all.** It is
  `max_request_tokens`, the largest request the run put on the API, and a probe
  is passing that clause when the task grows and that number does not. A sum
  cannot show it, and until 0.0.8d the harness did not record it.
