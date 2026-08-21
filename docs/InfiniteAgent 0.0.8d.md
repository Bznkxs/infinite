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

### What the two probes are

Both names come from the [Design Tests](Design%20Tests%20(Top%20Down).md), whose
Infinite Context Test states them in one line each. They are the same sentence
with a different thing made large:

> **Infinite writing:** produce as much as required, while context stays the same
> size.
>
> **Infinite complexity:** complete tasks however complicated they are, while
> context stays the same size.

"While context stays the same size" is the operative half of both, and it does
not mean the context is *small*. It means it does not **grow** with the task — so
neither clause is tested by one run at one size. Each needs the task made bigger
and the request measured against it, and the number that decides is the **largest
request the run put on the API**, read off the `usage` records in the trajectory
— which the harness did not record until this iteration (§8). A sum cannot show
it, because a sum grows with the length of a run whatever the geometry does.

| probe | the task it poses | made large by | passes if |
| --- | --- | --- | --- |
| `volume` — infinite writing | `records.md` holds N generated records; write `cards.md`, one seven-line card per record, in order, every field right | running it at N=120 and again at N=1,200 | the output grows tenfold and the largest request does not |
| `width` — infinite complexity | `infinite_agent/step_loop.py` is a 99-line stub in a package whose nine other modules are written; implement it against them | the module calling into six siblings — some forty signatures and field names true at once, not a bigger file | three runs produce it, and the largest request does not move between them |

Two things about that table are the whole design of these probes.

**The hard thing in `width` is width, not size.** Nothing in the task is long.
What defeats a fixed context is the number of facts that must hold simultaneously
— [Depth, Volume and Width](Depth,%20Volume%20and%20Width.md)'s diagnosis — and
`step_loop.py` is the smallest task the project has found with that property. It
is also the only one with a history, which is what makes three runs of it mean
something.

**`volume`'s corpus is generated from a seed, `width`'s is not.** `volume` runs on
a fresh clone; `width` copies its package out of `runs/reconstruct_infinite_0.0.7i`,
which is gitignored, and says so loudly if it is missing.

Both are graded by the machine and not by the response: `volume` parses
`cards.md` against the records it generated from the seed, and `width` runs the
interpreter. The width table below says why that distinction is not pedantry.

The other two clauses of the same test — fixed context, and infinite reading —
are not probed here. They were already measured, and §6 puts all four in one
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

### The reconstruction test

*This section was written when the answer was "not attempted", and that text
stands below because it is the argument for running it. What follows it is the
staging the attempt was given, written before the run, and §5.1 is what the run
did.*

**Every probe 0.0.8d set out to run passed, and then the run that would have
meant something was not made.** [The Reconstruction
Test](The%20Reconstruction%20Test.md) — the agent rebuilding InfiniteAgent from a
condensed specification of itself, in an empty directory, under 0.0.8d's own
geometry, and then running what it built on a real reading-comprehension task —
was not attempted at 0.0.8d, and has not been attempted at any letter of 0.0.8.
**0.0.8d has not passed it.**

That test is written down for the first time in the document linked above: how
to condense a version into the one or two files that are the whole of what the
agent is given, how to build the workspace, and the three gates — complete,
works, faithful — it is graded by. The reason for writing it down is this row:
the probes in `eval/benchmarks/` are each one clause of the Design Test in
twenty minutes, they are what a version is tuned against, and between 0.0.7j and
here they quietly replaced the test they were carved out of. `width`'s corpus is
literally nine modules a reconstruct run wrote.

Three things follow, and none of them is softened by five of five above:

- **The last version to pass it was 0.0.7f, at 46,684 tokens a generation.** Every
  configuration since is smaller, and none has tried at any size. Whether the
  `--frame` geometry — 18,000 tokens the ceiling on a whole generation — can
  rebuild the whole scaffold is not a close call that went the wrong way; it is
  unknown.
- **§6's four "held" verdicts are all probes.** Each holds one axis still and
  varies one. The reconstruction is the only task the project has that is long,
  wide, deep and voluminous at once, and it is the axis [Depth, Volume and
  Width](Depth,%20Volume%20and%20Width.md) actually names.
- **Nothing blocked it.** Not a dependency, not a missing mechanism, not a
  result that had to come first — three hours of wall clock, and they were spent
  elsewhere. [Writing a Version](Writing%20a%20Version.md) now makes this the
  last test a version takes, so the next one cannot end this way by omission.

Building it for 0.0.8 is more than the run: the condensed spec stops at 0.0.7f,
so the structured brief and its `check`, charged children, the removed depth
ceiling, destination registers, the shell-reachable registers and this letter's
progress tiers all have to go into it, with a new final config table since every
geometry number moved. §9 item 7.

#### The staging, stated before the run

[The Reconstruction Test](The%20Reconstruction%20Test.md) §2.2 says the staging
is not neutral and must be written down, so:

| | |
| --- | --- |
| **staging** | **bare** — the condensed spec alone. No `RECON_NOTES.md`, no `API.md`, no `BUILD_PLAN.md`, nothing pre-implemented. This is the test rather than a narrower question, and it is what §9 item 7 asked for |
| spec | `docs/InfiniteAgent 0.0.8d-simple (condensed spec).md`, 199KB and 3,904 lines in thirteen parts. Parts 1-7 are 0.0.7f-simple unchanged; Part 8 is 0.0.7g-j, Part 9 is 0.0.8a-c, Part 10 is this version, Part 11 the trajectory format, Part 12 the README, Part 13 the config table that wins over everything |
| geometry | `--frame`, which is the version under test: one generation up to **16,852 tokens** (8,660 in, 8,192 out) against the preset's 18,000 ceiling, `working_set_chars` 5,840 |
| budget | 500 steps at the root, production model at high effort, `spawn` left to the agent — §3.1's fixed parameters, so the run is comparable to the 0.0.7 ones |
| workspace | `runs/reconstruct_infinite_0.0.8d`, fresh, with a 3.12 venv whose CPython lives inside it so the firewall can reach it |
| graded by | §3.3's three gates — complete, works, faithful — all three or it is a failure |

Two things about the spec are worth stating because they are the cost of doing
this at this geometry, and neither was true of the run that passed. It is **75%
larger** than 0.0.7f-simple's 114KB, against the "grow by a third" the test
document guessed, because the 0.0.8 series is three design letters and two build
notes of mechanism. And the canvas it has to be paged through is **4,096
characters** rather than 20,000 — so the ratio the test document calls the right
order of magnitude, five times what a context holds, is **nineteen times** here.
That is not a flaw in the staging; it is the question the run is being asked.

### 5.1 It was attempted, and it failed

**0.0.8d does not pass the Reconstruction Test.** Stopped by hand at **472 of
500 budget units** — 29 left — after the root had spent **103 of its 120 steps
changing nothing durable**. Measures in
[`eval/results/reconstruct-0.0.8d.json`](../eval/results/reconstruct-0.0.8d.json);
1h18m, 8 agents, 3 depths, 409 steps, 2.92M tokens in and 299K out.

| gate | verdict | |
| --- | --- | --- |
| **complete** | **no** | 10 of 17 modules, 2,330 lines against 0.0.7f's 5,529. The package imports. No summariser, no firewall, no `progress.py`, no `regfile.py`, no viewer — and **no tests at all**, against 0.0.7f's 5,017 lines of them |
| **works** | **no** | the acceptance run was attempted **six times** and never completed. The setup was right — a 250KB World War II article, and a question gradeable to the digit (the case-sensitive count of `Stalingrad`) — and every attempt died inside the reconstruction's own import path |
| **faithful** | **not gradeable** | too much of the system does not exist. Of what does: register 4 is unimplemented, and the root printed the first eight characters of `ANTHROPIC_API_KEY` at step 106, which `TASK.md` forbids |

**The one thing that held is the property the version is about.** The largest
request any agent made was **9,026 tokens against a 16,852 ceiling**, and eight
agents across three depths spanned **1,886 tokens**. The run never came near its
own geometry. Whatever bound it, the size of the context is not it — which is
the same shape as §6's table and, this time, on the task that is all four
clauses at once.

#### What the loop actually was

Not "it got confused". **Seven seam mismatches, discovered one at a time.**
`agent.py` and `main.py` were written by different agents from the ones that
wrote their callees, and each acceptance-run attempt surfaced exactly one
disagreement:

```
Config.from_args          — does not exist          rc1/run.log  (twice)
ModelClient.from_config   — does not exist          rc1/run_final.log
RegisterFile.value        — does not exist          rc2/run.log
Trajectory.open           — does not exist          rc2/run3.log
BashSession.__init__() got an unexpected keyword argument 'cwd'   rc2/run2.log
```

Each fix bought exactly one more line of traceback. On the seventh the root
stopped fixing and started circling: **31 consecutive steps**, then 26, cycling
three files and editing neither of the two that had to agree — `sed` of
`agent.py:85-115` eight times, `tail` of `run2.log` nine times, `sed` of
`bash_tool.py:1-60` three times, `grep` for `BashSession(` or `def __init__`
five times.

It was not lost. Step 112's thinking states the fix correctly and then does not
make it:

> *There's an error about BashSession not accepting a 'cwd' keyword argument. I
> need to check the actual signature in bash_tool.py and fix the call in
> agent.py around line 98, so let me grep for the class definition first.*

and step 108 shows the shape of the deferral — *"there's a note about something
already being patched, so I should verify what state that's in before making
changes"*. Every step re-derived the same diagnosis and bought one more read
before acting.

#### A correction, found later: the measure worked here by accident

**0.0.8e §2.6 found that a *failing* check was counted as progress**, because
`Progress` compared the verdict line and that line ends in a per-step result
path. The root above had **no check**, so its 103 stalls are real. Its children
did, and were red for most of their lives, so their near-zero stall counts —
`404a2f38`, 120 steps and **one** stall — are the artefact rather than health.

Two things in this document have to be read with that in mind: **§5's `width`
stall rates (5.6%, 8.5%, 4.8%) are largely the artefact**, and the livelock
below was caught only because the root was unchecked — which is the same setup
error §10.1 criticises. Tier 1 is confirmed on that root and on nothing else.

#### The loop is invisible to a repetition detector, and this is the proof

§3 argued that re-reading predicts nothing, off five arms of one probe. This run
is the clean case, and it is stronger than the argument that produced it:

| | root, across 120 steps |
| --- | ---: |
| bash calls | 141 |
| **distinct commands** | **139 (99%)** |
| byte-identical outputs | 4 (3%) |
| **steps that changed nothing durable** | **103 (86%)** |

The agent varied the command every single step — `sed -n '85,115p'`, then
`'86,125p'`, then `'90,110p'`; `tail -30`, then `-40`, then `-c 600`, then
`cat` — while re-reading the same regions of the same three files. **A
repetition detector scores this root at 1% and calls it healthy.** The progress
measure scores it 103 stalls in 120 steps and is right. That is the design
decision of §4 confirmed on a task it was not fitted to, and it is the one
unambiguous win in this run.

#### What the mechanism did not do

The measure **detected** and did not **deter**, and both tiers failed:

- **Tier 2, the notice.** The `[Stall]` line was in the dump for most of 103
  steps. The root read past it every time.
- **Tier 3, the price.** The surcharge collected **76 budget units** on this one
  agent, against **14 across all five live 0.0.8d probe runs**. §7.2 wondered
  whether the pressure is what got `volume` row 1 out of a twelve-step loop at
  step 18. On a 31-step loop, being told and charged the whole way, the answer
  is **no**.

So the honest reading of §7.2 is now two runs and a split: the price is
well-aimed — invisible when a run is working, expensive when it is not — and
there is no evidence it changes behaviour. It bounds a livelock's cost. It does
not end one.

#### And the memo table was used, which makes its failure interesting

`facts.md` reached 17 lines, unprompted, and two of them record a seam mismatch
of **exactly the kind that killed the run**:

```
RegisterFile.__init__ takes only (config); RegisterFile.create(regdir, config)
added at end of registers.py as classmethod patch for Agent.create.
```

So §7.3's mechanism worked: a fact was resolved once, written down, and reused.
What it cannot do is help here, and the reason is structural — **the table
records facts after they are resolved, and a livelock is the state in which
nothing gets resolved.** It is empty exactly where it is needed.

#### The digest habit, unchanged, at scale

The agents wrote **209,683 bytes** of chunk-by-chunk spec re-transcription into
`.scratch/` across 20 files — *more than the 199KB spec itself*. That is the
0.0.6 failure the whole 0.0.7 series argued against, reproduced at 0.0.8d's
geometry, and it is a second reason not to read §5's 3/3 as generality: the
probes are small enough that the habit has nowhere to go.

## 6. The first Design Test, clause by clause

[Design Tests (Top Down)](Design%20Tests%20(Top%20Down).md) opens with the
Infinite Context Test and nobody had ever scored it one clause at a time.

| clause | scaffold | model | verdict |
| --- | --- | --- | --- |
| **fixed context** | `test_fixed_context.py`, four axes | five agents at five depths spanned 1,389 tokens; §5's three width runs span 232; **§5.1's eight agents at three depths span 1,886** | **held** |
| **infinite reading** | 4KB to 4MB, request flat | 6/6 under `--frame`; a 10M-token instance in nine steps | **held** |
| **infinite writing** | 10,000 lines, request flat | 2/2, ten times the output, request 5.1% smaller | **held** |
| **infinite complexity** | more steps do not grow the request | 3/3 on the hard task; **failed the Reconstruction Test (§5.1)** | **not held** |

Three limits, stated rather than buried:

1. **Complexity is the clause this version fails.** `step_loop.py` is the task
   this series was shaped by, so passing it three times says the shape is right
   and does not say the scaffold is general — and §5.1 is what happens when the
   same clause is asked on a task that is *also* long, deep and voluminous. The
   verdict moved from "held, on one task" to **not held**, and the reason is
   worth being exact about: the request stayed flat (9,026 tokens against a
   16,852 ceiling), so the *scaffold* half of the clause held. What failed is the
   half the clause is actually about — **more steps stopped buying progress**,
   which is the sentence §3 says the whole measure exists for. SWE-bench under
   `--frame` has still never been run.
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
7. **The reconstruction was attempted, and it failed (§5.1).** That overturns
   §6's fourth clause rather than refining it, and it makes items 1 to 6 less
   urgent than item 8: they argue about which mechanism earned 3/3 on the probe,
   and §5.1 says the probe was not the test.

## 10. How to stop the loop in §5.1

The failure has two layers and they want different fixes. **The loop is the
symptom; the seams are the disease.** Ranked by evidence behind them, not by how
interesting they are.

### 10.1 The check was the wrong shape, and this is the whole ballgame

Every check in the run was an **import**. The phase-1 child that built the entire
core was judged by:

```
import infinite_agent.config, …registers, …prompt, …trajectory, …workspace,
       …model, …bash_tool, …tools, …agent, …main; print('ok')
```

**That passes with all seven seam mismatches present**, because importing a
module never calls `Agent.create`. So the child returned `ok=True` on a package
that could not construct an agent, its heartbeat said `[Check] passes.` for
twenty steps, and the mismatches were left for the acceptance run to find one
crash at a time. An import check is a **syntax check with extra steps**.

The fix is a check that **constructs**: instantiate the top object, or run
`--help`, or drive one step against a fake model. Every one of the seven would
have surfaced on step one as a `[Check] FAILS` line — which is exactly what
0.0.8 §7.5 built the heartbeat for, and this run is the heartbeat pointed at the
wrong thing.

This is also the check §10.5's last item asked for and could not name. Arms C and
D warned that a verdict which cannot move until the work is finished is worse
than none; a construction check is the opposite — it moves *monotonically* as
seams are fixed, one traceback closer every time. It can get closer.

**And the root had no check at all.** `--check` was not passed, so the one frame
that could see the whole tree was the only one with no heartbeat, and it spent
its last 103 steps hand-running the integration a check would have run for it
every step. Either `--check` should be required for a run of this size, or the
absence of one should be as loud as a failure.

### 10.2 The brief split a caller from its callees, which the system message forbids

`agent.py` calls into six siblings. Four of them — `config`, `registers`,
`trajectory`, `model` — were written by *different agents*, and four of the five
seam errors are exactly those boundaries:

| error | caller written by | callee written by |
| --- | --- | --- |
| `Config.from_args` | 86b29c95 | f843bc9f |
| `ModelClient.from_config` | 86b29c95 | be64270c |
| `RegisterFile.value` | 86b29c95 | f843bc9f |
| `Trajectory.open` | 86b29c95 | be64270c |
| `BashSession(cwd=…)` | 86b29c95 | **86b29c95** |

§9.2 of the spec says *descend at a working-set boundary: when the subgoal needs
facts you do not have, and you will not need its facts once it returns.* A
caller and its six callees are the maximally **wrong** place to cut: they share
every fact. The scaffold states the rule and the run broke it, so the rule is
advice that did not land — the same finding the whole 0.0.7 series kept making
about advice.

Note the last row. Even *within* one agent the seam broke, because 86b29c95
wrote four modules in 28 steps. So "don't split callers from callees" is
necessary and not sufficient; the sufficient version is 10.1, where the machine
checks the seam instead of an agent remembering it.

### 10.3 If a price does not deter, take the option away

§5.1 is the clean refutation of tier 3 as a deterrent: 76 budget units charged,
the `[Stall]` line in the dump the whole time, 31 consecutive steps, no change in
behaviour. Raising the surcharge is not the answer — the run would simply die
sooner, which is a cap wearing a price's clothes.

What has *ever* changed this agent's behaviour is **removing a tool**. 0.0.7a's
depth floor is the precedent: a refusal that lived in a register was ignored five
times in thirty-four steps, and taking `spawn` out of the schema ended it at
once. The analogue here is a fourth tier: **at a streak of N, a read-only step is
refused.** `load` and read-shaped `bash` return *you have read N times without
changing anything; this step must write*, and the agent gets its tools back the
moment something moves.

The objection is real and should be written down rather than waved off: this is
the scaffold having an opinion about the *shape* of the work, which §9.8 removed
the depth ceiling to avoid. The distinction the counter-argument needs is that a
livelock is not a shape, it is a defect — §4's own definition — and the scaffold
already presumes to name it. Having named it, refusing to keep selling reads into
it is not a new kind of opinion. **This is the one item here that could be wrong,
and it is an A/B, not an argument.**

### 10.4 The mechanisms that would have helped existed and went unused

*Register 4 is the largest of these and it gets its own document:
[Lossy Memory and the Loop](Lossy%20Memory%20and%20the%20Loop.md). The short
version is that the run's memory restated the same defect in **58 consecutive
summaries** and flipped its truth value four times — "fixed step 85" about a bug
that was never fixed — because a summary rewritten whole from (previous summary
+ one step) has no channel through which anything can accumulate. It keeps where
the run is and discards how long it has been there.*


Two, and they rhyme with 0.0.8's `facts.md` finding:

- **Pinned registers.** §9.4 makes a destination optional precisely so a working
  set survives a step. The two facts the root needed — the signature and the call
  site — are about 2KB together and would have fitted in two pinned registers.
  The root never pinned anything; it re-read both, in a differently-worded
  command, every step.
- **The memo table.** It was used, and well — 17 lines, including a note about a
  seam mismatch of exactly this kind. But it records facts *after* they are
  resolved, and a livelock is the state where nothing is resolved. It is empty
  precisely where it is needed.

The pattern across both is the one 0.0.8 §9 already named: **what a fixed context
is short of is continuity, not room**, and the mechanisms that offer continuity
are all opt-in. Something that made the last step's reads sticky *by default*
during a stall streak is the shape of the missing mechanism.

### 10.5 What not to conclude

- **Not that the context was too small.** The largest request was 9,026 tokens
  against a 16,852 ceiling and eight agents spanned 1,886. The run never came
  near its geometry, and 4,096 characters of canvas would have held both facts.
- **Not that the measure failed.** It was the only thing that saw the loop, and
  §5.1 shows a repetition detector would have scored the same root at 1% and
  called it healthy. Tier 1 is confirmed on a task it was not fitted to. Tiers 2
  and 3 are what failed.
- **Not that the spec was too long.** 199KB is real and the digest habit is real
  (209,683 bytes of it), but the run got a package written and imported. It died
  on seams, and a shorter spec does not fix a seam.

### 10.6 The move it should have made was `spawn`, and the scaffold priced it out

The correct move at root step 85 is not a better `grep`. It is one child:

```
spawn(goal:  "agent.py's BashSession(...) call matches bash_tool.py's signature",
      read:  ["infinite_agent/agent.py", "infinite_agent/bash_tool.py"],
      write: "infinite_agent/agent.py",
      check: "./.venv/bin/python -c 'from infinite_agent.agent import Agent'",
      max_steps: 6)
```

That is §9.2's working-set boundary exactly: the subgoal needs two facts the
parent cannot hold across a step, and the parent needs none of them once it
returns. A fresh context holds both files at 4,096 characters with room to spare.

**One distinction decides whether this works, and it is not obvious.** The child
must be an *executor*, not a *reporter*. A child that reads two files and returns
a condensed summary hands the facts back into the same lossy context that could
not hold them — which is the digest habit with an agent wrapped around it, and
this run already wrote 209KB of that. §9.2's licence is *"you will not need its
facts once it returns"*, and that is only true if the child **makes the check
pass**. The return value should be a verdict, not a description.

So why didn't it? The budget line says most of it:

```
[Step] depth 0, step 85 of 500 (90 left, including this one; 276 of your budget
went to children, 50 to steps that changed nothing)
```

Ninety steps left — easily enough for a six-step child. But **276 already gone to
children, two of whom died without a response** after burning 49 and 120 steps.
From where the root sat, `spawn` had a measured track record of costing a
hundred steps and returning nothing, while a `grep` cost one. §9.7's price worked
exactly as designed and pushed the run away from the one move that was right.
**Charging deters delegation, and here delegation was the fix.** That is the
sharpest thing this run says about 0.0.8c, and it is not something the five
probe arms could have shown.

Three ways to encourage it, cheapest first:

1. **Make the price directional during a livelock.** A flat surcharge taxes the
   stalled step and, by shrinking the allowance, taxes the child too — so it
   prices "keep reading" and "descend and fix" *the same*, and then makes the
   second one harder. A `spawn` issued at or above the stall threshold should be
   **rebated**: charge it at a discount, or refund the surcharge already paid if
   the child's check passes. That is one number and it turns the mechanism from a
   tax into a gradient.
2. **Render the brief instead of recommending one.** By the time the notice
   fires, the scaffold knows more than the frame does: `progress.py` has the
   paths, the check has its failing line, and the trajectory has what was read
   how often. It can put a *filled-in* `spawn` call in the `[Stall]` line — goal
   from the failing check, `read` from the two most re-read paths, `check` from
   the frame's own. This is 0.0.8c's argument one level down: a lossy frame
   cannot author a brief, and here the **scaffold** can, because it holds the
   trace the frame does not.
3. **Nothing needs building for the reward.** A child's writes land in the shared
   workspace, so the parent's next scan sees them and its streak resets. The
   escape already pays; what it lacks is a visible price cut on the way in.

### 10.7 How to tell a frame it is looping, when it has read past the last hundred

The `[Stall]` line was in the dump for most of 103 steps and changed nothing, so
the question is not whether to warn but what a warning that works would have to
be. Four properties, and the first two are free:

**Specific, not generic.** The current line says *3 steps in a row have changed
no file, no target and no fact*. The scaffold can say what actually happened,
because it recorded it:

```
[Stall] 31 steps with nothing changed. Since the check last moved you have read
agent.py 8 times, run2.log 9, bash_tool.py 3 — and [Check] has said the same
thing for 31 steps.
```

Advice can be argued with; a frame's own trace cannot. This costs a histogram
the measure is already keeping.

**Escalating in kind, not in volume.** Steps 3 and 31 currently get the identical
sentence, and anything a model reads thirty times becomes wallpaper. The ladder
should change *type*: notice → the evidence above → the rendered brief (§10.6.2)
→ withdrawal of the read tools (§10.3). Each rung is a different kind of object,
so none of them can be habituated to.

**Naming the belief, not the behaviour.** Step 112's thinking is *"I need to …
fix the call in agent.py around line 98, so let me grep for the class definition
first."* The defect is not that it read; it is that it believed one more read was
free. A line that says *you have said "one more look" 31 times* attacks the
belief. This is speculative and should be marked as such.

**And one rejected.** The obvious place for a warning the agent cannot skip is
register 2, the target — the one register that survives untouched and that the
agent reads as its own. **Do not put it there.** *Only `set_target` writes
register 2* is load-bearing: it is the one address whose contents the agent can
trust it authored, and a scaffold that writes there takes that away to win one
argument.

**The honest caveat on all of this.** The strongest single finding of the 0.0.7
series and of 0.0.8 §10.2 is that **no sentence installs a habit**. The `[Stall]`
line is a sentence, and a better sentence is still a sentence. So these should be
tried, and they should be tried *separately from* §10.3, because if the warning
and the withdrawal ship together the next run cannot say which one worked — which
is the mistake §7.1 of this very document opens by confessing.
