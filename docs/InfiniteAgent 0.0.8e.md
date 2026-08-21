# InfiniteAgent 0.0.8e — a memory that can count

*§1-3 are written before the implementation and before the run, as
[Writing a Version](Writing%20a%20Version.md) requires. §4-5 are written after.*

---

## 1. What it aims to do

[The 0.0.8d reconstruction](InfiniteAgent%200.0.8d.md) §5.1 failed with its root
agent livelocked for 31 consecutive steps, and
[Lossy Memory and the Loop](Lossy%20Memory%20and%20the%20Loop.md) is the
diagnosis: **the run's memory of itself sustained the loop rather than breaking
it.** One defect — `agent.py:98` calling `BashSession` with arguments it does not
take — was restated in 58 consecutive summaries with its truth value flipping
four times, including "fixed step 85" about a bug that was never fixed.

That is not a prompt failure. It is three properties of the shape of register 4:
a summary rewritten whole from (previous summary + one step) **cannot count**,
because no count is ever in its input; it **resamples rather than consolidates**,
so a repeated fact gets paraphrased into something new instead of becoming harder
to dislodge; and it **compresses history into state**, keeping line numbers and
byte counts while discarding how long the run has been where it is.

A human's memory of a task is more lossy than this and does not produce loops,
because it loses detail first and keeps the aggregate — *I have been going round
on this constructor* — and because it carries a signal about effort spent that is
separate from the content of the work.

**0.0.8e aims to give the scaffold that aggregate.** The scaffold already
computes it: `Progress` knows what moved and how long the run of nothing is, and
the check knows whether the verdict has changed. None of it reaches the run's
memory. So the version is one idea in two halves — **put duration where the agent
reads it, and stop the model asserting things the machine decides** — and one
removal.

What would count as solving it: **the root of a long run does not spend thirty
steps re-reading two files, and if it starts to, its own context says so in a
form it cannot restate away.** What would count as failing: a livelock of the
same shape, with the ledger present and read past — which would say the defect is
affordance rather than memory, and that
[0.0.8d §10.3](InfiniteAgent%200.0.8d.md)'s tool-withdrawal tier is the next
thing to try rather than this.

## 2. What it modifies

Five changes. Four are the mechanism; the fifth is a removal the operator asked
for and it is the one with a case against it (§2.5).

### 2.1 The summariser is told what the step changed — `summary.py`, `agent.py`

`Summariser.update` gains `moved: bool` and `stall_streak: int`, and
`build_input` renders them as a section. Its system message gains one rule:

> When the step changed nothing durable, do not restate the situation. Carry a
> line of the form *"no progress on X for N steps"* and increment N.

This is the smallest change that makes a count representable at all, because the
count now arrives in the input instead of having to survive forty rewrites.

### 2.2 A ledger the model does not write — `progress.py`, `registers.py`

Anything that must accumulate cannot be maintained by a rewrite, so the run's
memory splits by writer:

| | written by | shape | holds |
| --- | --- | --- | --- |
| register 4 | the summariser | rewritten whole | what is true now |
| **the ledger** | **the scaffold** | **counted, monotonic** | **how long things have been the way they are** |

`Ledger` accumulates, per agent, facts the machine knows exactly and the model
cannot argue with: the step of the last durable progress, how many steps the
check's verdict has been unchanged and what it is, how many steps since the
target was rewritten, and — for the paths the frame has read since it last made
progress — a count per path. It renders one line, above the registers:

```
[Ledger] no progress for 31 steps (last: step 85). check unchanged 31 steps. read since: agent.py x8, run2.log x9, bash_tool.py x3
```

It appears only when there is something to report, so a run that is moving never
pays for it. This is 0.0.8d §10.7's "specific, not generic" — the frame's own
trace rather than a scold — and unlike the `[Stall]` line it is not a sentence
that can become wallpaper, because its numbers change every step.

### 2.3 The summary may not claim a machine verdict — `summary.py`

One rule in the summariser's system message:

> Never assert that anything builds, imports, passes, or is fixed. Record what
> was attempted; the check reports what is true.

"Fixed step 85" is what cost the 0.0.8d root perhaps forty steps, and the
summariser had no way to check it. This is the same principle as `check` itself:
put what must be true under the machine, and leave the model the judgement.

### 2.4 The tracked paths — `progress.py`

`Progress` already scans the workspace; it does not know what was *read*. The
ledger's per-path counts come from the step's tool calls (`load` paths and the
paths appearing in `bash` commands), reset on progress. Cheap, and it is the
evidence half of §2.2.

### 2.5 `facts.md` is removed — `workspace.py`, `prompt.py`, `agent.py`

The memo table, its header, `Workspace.remember`, its path helper and the system
message sentence that names it all go.

**The case against doing this should be recorded, because it is real.** 0.0.8d
§7.3 named `facts.md` the best available explanation of its 3/3 on `width`, and
the 0.0.8d reconstruction *did* use it — 17 lines, unprompted, including a note
about a seam mismatch of exactly the kind that killed the run. So this removes
the one mechanism the previous version credited.

**The case for it** is that the reconstruction showed what the table can and
cannot do: it records facts *after* they are resolved, and a livelock is the
state in which nothing is resolved — so it is empty exactly where it is needed.
It is also a second opt-in memory competing with register 4 for the same job, and
0.0.8e's whole argument is that the failure is in the memory the scaffold
*maintains*, not in the one the agent may choose to keep. Removing it makes the
next result attributable: if the ledger works, it worked without a memo table.

That is the reasoning, and §4 should be read knowing that a 0.0.8e regression on
`width` is as likely to be this removal as anything else in §2.

## 3. What to evaluate

The offline suite first: it must stay green, and the `facts.md` tests are deleted
rather than skipped.

Then, named before the runs:

| measurement | geometry | how many | what would count as failure |
| --- | --- | ---: | --- |
| `width` — infinite complexity | `--profile frame --arm baseline` | 3 | fewer than 2 of 3 produce the module. 0.0.8d was 3/3, so 2/3 is within variance and 0-1/3 says §2.5 cost something |
| `volume` — infinite writing | `--profile frame`, N=120 and N=1,200 | 2 | either row wrong, or the largest request growing with the output |
| **the Reconstruction Test** | **bare, `--frame`, 500 steps** | **1** | **any of the three gates. This is the test 0.0.8e exists for** |

The reconstruction is the one that decides §1, and two things about it are fixed
in advance so that §4 cannot be written around them:

- **The staging is bare and unchanged** — the same spec file, the same
  `TASK.md`, the same workspace recipe as 0.0.8d. The only difference is the
  scaffold and 0.0.8d §10.1's correction to the check (below). If the staging
  moves, the comparison is gone.
- **The root gets a `--check` that constructs**, not one that imports. 0.0.8d
  §10.1 is unambiguous that its absence was a setup error rather than a scaffold
  property, and repeating a known setup error to keep a comparison clean would be
  measuring the wrong thing. This is stated here, before the run, because it
  makes a 0.0.8e pass *weaker* evidence for §2 than it looks: two things moved.

**The number that would change my mind about §2:** the root's longest stall
streak. 0.0.8d's was 31. If 0.0.8e livelocks at a comparable length with the
ledger in its dump, the memory hypothesis is wrong and
[0.0.8d §10.3](InfiniteAgent%200.0.8d.md) is next.

**What this version does not claim.** It does not address the seams that actually
killed 0.0.8d — ten modules by four agents, seven signature mismatches — beyond
the check correction, which is staging. If 0.0.8e fails on seams again while
never livelocking, §2 worked and the run still failed, and that is a result worth
having stated in advance.

## 4. Experiment results

*Written after the runs.*

## 5. Handoff to the next version

*Written after the runs.*
