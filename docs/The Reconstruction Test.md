# The Reconstruction Test

*The scaffold builds itself. One or two files condense a version of InfiniteAgent
into everything normative about it, an agent running under that version is given
them and an empty directory, and what it has to produce is that version, from
scratch, and then a real run of the thing it just built.*

This is the hardest task the project has, and it is the one every letter of the
0.0.7 series was judged by. It is written down here because it had stopped being
run: the probes in `eval/benchmarks/` each measure one clause of the [Design
Test](Design%20Tests%20(Top%20Down).md) in twenty minutes, and between 0.0.7j
and 0.0.8d nobody spent the three hours on the test that measures all of them at
once. [Writing a Version](Writing%20a%20Version.md) now says a version attempts
it once its other tests pass.

---

## 1. What it tests that the probes do not

Each probe holds everything constant but one axis, which is what makes it a
measurement and also what makes it small. `volume` writes 106KB with a
twenty-line regex. `width` implements one module against nine that already
exist. Both are one agent's afternoon, both are graded by one command, and both
were carved *out of* a reconstruction — `width`'s corpus is nine modules a
reconstruct run wrote.

The reconstruction is the whole thing at once, and four properties are unique to
it:

- **It is long.** Hours, hundreds of steps, a tree of agents. The failures that
  only appear at length were found here: register 4 losing a fixed refusal and
  an agent re-learning it five times over 34 steps (0.0.7a); 269 consecutive
  steps measuring a length with nothing in the scaffold to say so (0.0.7e); a
  parent's counter moving by one however many steps its child spends (0.0.7j).
- **It is wide *and* deep *and* voluminous.** Thirteen modules that call into
  each other, a 114KB specification no context holds, and 5,500 lines of output.
  No probe combines them, and the axis [Depth, Volume and
  Width](Depth,%20Volume%20and%20Width.md) names is the combination.
- **The deliverable cannot be faked.** A grader command can be satisfied by an
  agent that writes the program that satisfies it. Here the acceptance test is
  the reconstruction *running*, on a real task, against a real API — so the only
  way to pass is for the artefact to work.
- **It is the scaffold's own claim, turned on the scaffold.** "Complete tasks
  however complicated they are, while context stays the same size" is a sentence
  about a model working inside the thing. A version that cannot rebuild itself
  under its own geometry has not met it, whatever the probes say.

What it is not is a *measurement*. It is one run, of one task, with enormous
variance, and it takes three hours — so it settles pass or fail and it does not
attribute anything. Attribution is what the probes are for. Run the probes to
learn why; run this to find out whether.

## 2. How to build one

Four things exist before a run: the condensed spec, the decision about how much
else is given, the workspace, and `TASK.md`.

### 2.1 Condense the version into one or two files

**One file is the spec.** `docs/InfiniteAgent <version>-simple (condensed
spec).md`, inside the workspace, containing everything normative from 0.0.1
through the version under test and nothing else. The 0.0.7f-simple one is 114KB
and 2,338 lines, which is the right order of magnitude: five times what any
context holds, so the agent has to page it, and small enough that paging it is
not the whole run.

Four rules, each of which a run has already been lost to:

- **Organised by version, later parts winning.** Each part is the argument that
  version made, so the reader can see *why* a number is what it is — and the
  front matter states the precedence explicitly, part by part, because a spec
  assembled from eleven design docs contradicts itself constantly. 0.0.7f-simple
  says it three times: Part 6 beats Part 5 on summariser settings, Part 7 beats
  everything on anything, and Part 10's table is the config as it must end up.
- **A final part that is the config as it must end up.** One table, every field,
  every default. Prose in an early part will disagree with it; the table wins,
  and saying so in the front matter is cheaper than reconciling the prose.
- **Nothing normative dropped.** Defaults, limits, error behaviours, field names,
  the literal text of the dump. The point of the exercise is faithfulness, not a
  system that merely works, and a detail left out of the spec is a deviation the
  grader cannot fairly count.
- **Nothing in it that is not the specification.** No results, no run logs, no
  open questions. The version documents are arguments about what to build next;
  the spec is what to build.

**The second file, if there is one, is a way into the first.** Two shapes have
been used, and either is legitimate as long as the choice is recorded (§2.2):

| file | what it is | what it costs |
| --- | --- | --- |
| `docs/RECON_NOTES.md` | an index: every heading, its line number in the spec, and the one sentence it settles | nothing — it is the spec's table of contents, and it removes a search the run would otherwise pay for every time |
| `API.md` | the interface: every public name in every module, with its real signature, grouped by module | a great deal — see below |

**Two files is the ceiling, and it is a real one.** A third file is a thing the
run has to discover, read, and reconcile, and the 0.0.6 run's failure mode was
exactly this in reverse: given one 80KB spec it wrote itself a 42KB "contract"
and then a second one, and spent the run on documents about the task. Adding
files to the workspace is doing that failure on the agent's behalf.

### 2.2 Decide how much else is given, and write it down

`API.md` and `BUILD_PLAN.md` are not neutral. `API.md` hands the agent the forty
signatures that 0.0.7i's two children spent 240 steps failing to hold at once;
`BUILD_PLAN.md` hands it the ordering and the acceptance check for each package.
Both make the task easier, and both make a pass mean less.

So the rule is not "don't", it is **state the staging in the version document,
and never change it silently between runs.** What has been used:

| staging | given | used by |
| --- | --- | --- |
| **bare** | the condensed spec alone | 0.0.7a-0.0.7f, **0.0.8d** |
| **indexed** | spec + `RECON_NOTES.md` | the 0.0.7i corpus as it stands |
| **contracted** | spec + `API.md` + `BUILD_PLAN.md`, with `config.py` already implemented | 0.0.7i |

There is a fourth thing to state alongside the staging, and 0.0.8d is why:
**what the root's `check` is.** It is not part of the spec and it is not part of
the workspace, but it decides what the run is told about itself every step, and a
run whose checks only test `import` is a run with no integration signal anywhere
(0.0.8d §10.1). 0.0.8d's root was given none at all.

Bare is the test. Anything above it is a concession, made because a version is
being asked a narrower question — 0.0.7i's was about output budget, not about
whether the agent could infer an interface — and a version that passes
*contracted* has passed something weaker than 0.0.7f did. Say which.

### 2.3 The workspace

A directory under `runs/`, which is gitignored, holding only:

```
runs/reconstruct_infinite_<version>/
  TASK.md                                    # §2.4; the instruction file
  schema.json                                # the response schema
  docs/InfiniteAgent <v>-simple (condensed spec).md
  docs/RECON_NOTES.md                        # optional, §2.1
  .venv/                                     # 3.12 + anthropic, jsonschema,
  .uvpython/                                 #   python-dotenv, pytest
  .uvcache/
  pytest.ini
```

Four properties of that environment, each of which has cost a run:

- **The interpreter lives inside the workspace, and so does the CPython it links
  to.** The firewall makes the workspace the only readable place, so a venv whose
  `pyvenv.cfg` points anywhere else is a venv that cannot start — which is why
  0.0.7i's `.uvpython/` holds its own `cpython-3.12`, with `UV_PYTHON_INSTALL_DIR`
  and `UV_CACHE_DIR` pointed inside the workspace when it was created. Everything
  is installed up front: `pip` inside that venv is not available to the agent and
  there is no writable package cache, so `TASK.md` says so rather than letting a
  run discover it.
- **The reconstruction runs with its own firewall off.** macOS will not nest one
  seatbelt sandbox inside another — `sandbox_apply: Operation not permitted`,
  and it takes the bash session down with it. `TASK.md` must say this, must say
  it is a property of the environment and not of the agent's code, and must still
  require the firewall to be implemented and its policy logic tested offline.
- **The key comes from the environment.** `ANTHROPIC_API_KEY` is inherited by
  every command the agent runs; there is no `.env` in the workspace and `TASK.md`
  forbids writing one or printing the key.
- **The network is open,** because the acceptance run needs a corpus to download.
  The firewall governs the filesystem, not the socket.

### 2.4 `TASK.md`

The instruction file, and the five sections
`runs/reconstruct_infinite_0.0.7i/TASK.md` uses are the template:

1. **What to build** — the spec file by name, the module layout to use, an
   enumeration of the parts so that no subsystem can be quietly skipped, and the
   sentence that sets the standard: *where the spec states a default, a limit, an
   error behaviour or a field name, match it exactly — the point of this exercise
   is a faithful reconstruction, not a system that merely works.* Then the
   precedence rules from the spec's front matter, restated.
2. **Then use it** — §3.2 below, in four numbered steps.
3. **The environment** — the four properties in §2.3, plus: keep long-running
   processes in the background with a timeout, and the run record
   (`trajectory-*.jsonl`, `tool_output/`) is read-only.
4. **Order of work** — explicitly *so that if you run out of steps the most
   valuable part exists*: the working agent first, the acceptance run second,
   then the summariser, the firewall and resume, the offline test suite, the
   viewer and a README. Getting one real end-to-end run early rather than late is
   the instruction that matters, because it is the one that turns a partial
   failure into a partial result.
5. **What to report** — `response-<agent id>.json` against `schema.json`, written
   once, at the end.

## 3. How to test it

### 3.1 Running it

```bash
uv run infinite -f runs/reconstruct_infinite_<version>/TASK.md \
    -w runs/reconstruct_infinite_<version> \
    --schema runs/reconstruct_infinite_<version>/schema.json \
    --frame --max-steps 500 \
  2>&1 | tee runs/r_<version>.log
```

The geometry flag is the version under test — `--frame` for the 0.0.8 series,
`--wide-output` for 0.0.7i, and nothing at all for a version whose defaults are
the thing being tried. That is the point of the exercise: the scaffold rebuilds
itself *under its own configuration*, so a run that quietly widens the context to
get through has tested a scaffold nobody ships.

Everything else is fixed by precedent rather than by argument, and moving any of
it makes the run incomparable to the ones in §4: 500 steps at the root, the
production model at high effort, and `spawn` left to the agent.

Budget hours, not minutes: the one pass took 2h43m over 580 steps and twelve
agents, and the failures took longer — 0.0.7e ran 17.5 hours and 1,368 steps
before it died. Tokens follow from that and from the geometry, so they are not
comparable across letters: 0.0.7f's 580 steps at up to 30,300 tokens a request is
a different order of spend from the same run under `--frame`, whose largest
request across 0.0.8d's five live runs was 8,099 tokens. Watch the clock rather than the meter,
and do not start one in the last hour of a session.

### 3.2 The acceptance run

**The reconstruction is not the deliverable; a run of the reconstruction is.**
When the package exists, the agent runs *its own* implementation on a
reading-comprehension task over a very long text — the job the design exists for —
in four steps, all inside the same session:

1. Download a large article into `data/` — 200KB or more of wikitext, far more
   than the canvas holds, so the agent's implementation genuinely has to page.
2. Write a question whose ground truth it establishes **independently, with
   shell commands, before the run**: a count, a date, a name, a figure stated in
   one place. Specific enough to grade exactly.
3. Run the reconstruction on that question — a real API call, a return schema —
   with the reconstruction's own firewall off, for the nesting reason in §2.3.
4. Grade the answer against the ground truth and report both.

If it fails, fix the implementation and run it again. The step-2-before-step-3
ordering is the same rule [Writing a Version](Writing%20a%20Version.md) applies
to §3 of a version document, for the same reason, and it is enforced only by the
instruction — a grader reading the response afterwards cannot tell the order the
agent did it in.

### 3.3 The three gates

A pass is all three. Anything less is a failure that names its own next change,
which is what the 0.0.7 series ran on.

| gate | how it is checked | 0.0.7f, the one pass |
| --- | --- | --- |
| **complete** | every module in the spec's layout exists and the package imports; the offline suite runs | 5,529 lines, all thirteen modules, 5,017 lines of test, 677 passing |
| **works** | the acceptance run happened, against a real corpus, and the answer matches the ground truth established before it | a three-part question over a 367KB export, answered in five steps, every answer quoted with its source sentence |
| **faithful** | defaults, limits, error behaviours, field names and the literal dump text match the spec; the trajectory it writes is a valid v3 file | its trajectory parses as v3 with `spawn_workers` in the config |

Faithfulness is the gate that needs a person. Spot-check it rather than trying
to check it exhaustively: the config table, the dump's literal header form, the
rejected-write behaviour, and two or three error strings. The schema requires the
agent to declare its own `deviations` and `unfinished`, and an honest declaration
is worth more than a clean one — a run that lists what it did not build has told
you where to look, and the two arms of 0.0.8 that reported a module they had not
written are why the grade is never the response alone.

### 3.4 What to record either way

The measures are 0.0.7a's, and they are what makes a failed run a result:

- **lines of code in the workspace, and which of the spec's modules exist** — the
  only measure of the goal;
- **bytes of prose written that are not code** — the 0.0.6 failure, as a number;
- steps, agents, tree depth, and how long ancestors spend blocked;
- summariser retries, truncations, share of wall clock, output tokens a step;
- repeated identical actions and repeated tool errors, which is where a loop
  shows up first — and, since 0.0.8d, the stall streaks the handoff already
  carries.

Distil them into `eval/results/reconstruct-<version>.json` and cite that file,
because `runs/` does not survive a clone.

## 4. The record

Every entry is checkable against the document named.

| version | outcome | what it showed |
| --- | --- | --- |
| 0.0.6 | **failed** | 106 steps, 5 agents, 536 lines — and a 42KB re-transcription of the spec. The agents re-describe the task instead of doing it ([0.0.7a](InfiniteAgent%200.0.7a.md)) |
| 0.0.7a-d | **failed** | each in a way that named the next letter; the series is that loop |
| 0.0.7e | **failed** | 3,981 lines over 17.5 hours and 1,368 steps, then died on an `overloaded_error` ([0.0.7f](InfiniteAgent%200.0.7f.md)) |
| **0.0.7f** | **passed** | 2h43m, 580 steps, 12 agents, all thirteen modules, and an acceptance run that was right. The only pass the project has ([0.0.7f](InfiniteAgent%200.0.7f.md)) |
| 0.0.7f-short | **failed** | five children ran out of steps on a 115KB blueprint; 936 lines after four hours ([0.0.7f-short](InfiniteAgent%200.0.7f-short.md)) |
| 0.0.7g, 0.0.7h | **failed** | would not finish at 8,000 tokens a generation ([0.0.7i](InfiniteAgent%200.0.7i.md)) |
| 0.0.7i | **failed** | ten modules and 820 lines at 10.3 lines a step, then two children spent 240 steps on `step_loop.py` and wrote nothing. That failure is the corpus the `width` probe is cut from |
| 0.0.8, 0.0.8a-c | **never run** | |
| **0.0.8d** | **failed** | bare, `--frame`. Stopped at 472 of 500 budget units with the root livelocked: 103 of its 120 steps changed nothing, worst streak 31. 10 of 17 modules, 2,330 lines, no tests, six acceptance-run attempts and no answer. The largest request was 9,026 tokens against a 16,852 ceiling, so the context was never what bound it — it died on **seams**, seven of them found one at a time, behind checks that only tested `import` ([0.0.8d §5.1](InfiniteAgent%200.0.8d.md), [`eval/results/reconstruct-0.0.8d.json`](../eval/results/reconstruct-0.0.8d.json)) |

**One pass, at 46,684 tokens a generation**, and every configuration since has
been smaller. That was the standing question this test existed to answer, and
0.0.8d answered it: **an 18,000-token frame did not rebuild the scaffold.** But
read the failure before reading the verdict, because it does not say what the
question assumed it would. The run's largest request was 9,026 tokens — barely
half its own ceiling — and eight agents across three depths spanned 1,886. **The
context was never the binding constraint.** What bound it was that ten modules
written by four agents did not agree at their seams, that every `check` in the
run tested `import` and so passed on a package that could not construct an
agent, and that the root then spent a hundred steps re-reading two files instead
of editing one. None of that is a context size. The next attempt should change
the checks before it changes the geometry.

## 5. Building the next one

**Read 0.0.8d §10 first.** The 0.0.8d attempt failed for reasons that were
mostly *staging*, not scaffold, and three of them are cheap to not repeat:

- **Give the root a `--check`, and make every `check` construct rather than
  import.** An import check is a syntax check with extra steps: 0.0.8d's phase-1
  child returned `ok=True`, with a green heartbeat, on a package with seven
  signature mismatches in it. A check that instantiates the top object, or runs
  `--help`, or drives one step against a fake model, turns every one of those
  into a `[Check] FAILS` line on the step it is introduced.
- **Do not let the brief split a module from the modules it calls.** Four of
  0.0.8d's five seam errors are agent boundaries: `agent.py` was written by one
  child and four of its six callees by two others.
- **Expect the condensed spec to be much bigger than the guidance above.**
  0.0.8d's is 199KB against 0.0.7f-simple's 114KB, and the canvas it must be
  paged through is 4,096 characters rather than 20,000 — so §2.1's "five times
  what any context holds" was nineteen times. That ratio is the thing to state in
  the version document, not to engineer away.

For a version after 0.0.8d, the work is:

1. **Extend the condensed spec.** 0.0.7f-simple stops at Part 10. The 0.0.8
   series adds the structured brief and its `check`, charged children, no depth
   ceiling, destination registers, the registers reachable from the shell, and
   0.0.8d's progress tiers — plus a new final table, since every geometry number
   moved. Expect it to grow by a third, and expect the *precedence* front matter
   to be the part that takes the thought.
2. **Choose the staging (§2.2) and record it.** Bare is the test; anything else
   is answering a narrower question, and the version document says which.
3. **Build the workspace (§2.3) and write `TASK.md` (§2.4)** from the 0.0.7i one.
4. **Run it (§3.1), grade it (§3.3), record it either way (§3.4)**, and add a row
   to §4.

The one thing not to do is reuse a workspace. Every run is a fresh directory: a
compiled module or a stale `.scratch` from an earlier attempt is a fact the new
run did not pay for, and `width`'s `materialise` strips `__pycache__` for exactly
that reason.
