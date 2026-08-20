# InfiniteAgent

A recursive agent that keeps a fixed-size active context, storing everything
else in reliable storage while keeping a reference to it.

This repository implements **0.0.8d**: the 0.0.1 scaffold
([`docs/InfiniteAgent 0.0.1.md`](docs/InfiniteAgent%200.0.1.md)), plus a
filesystem firewall, resumable runs and per-step timing
([`0.0.2`](docs/InfiniteAgent%200.0.2.md)), plus a target register and an
automatic record of the last step ([`0.0.3`](docs/InfiniteAgent%200.0.3.md)),
plus a running summary of the trajectory
([`0.0.4`](docs/InfiniteAgent%200.0.4.md)) which
[`0.0.5`](docs/InfiniteAgent%200.0.5.md) moved out of a sub-agent and into a
single model call, adding a scratch directory along the way, and which
[`0.0.6`](docs/InfiniteAgent%200.0.6.md) made cheap: a small model, no effort at
all, and one length told to it instead of two. **0.0.7a** starts an iteration
series ([`0.0.7a`](docs/InfiniteAgent%200.0.7a.md),
[`0.0.7b`](docs/InfiniteAgent%200.0.7b.md),
[`0.0.7c`](docs/InfiniteAgent%200.0.7c.md),
[`0.0.7d`](docs/InfiniteAgent%200.0.7d.md),
[`0.0.7e`](docs/InfiniteAgent%200.0.7e.md),
[`0.0.7f`](docs/InfiniteAgent%200.0.7f.md)) aimed at one goal — the agent
reconstructing this scaffold from its own spec. 0.0.7a spent its changes on where
the steps go; 0.0.7b on registers big enough to hold what was read, and on saying
out loud when one was not; 0.0.7c on surviving a transient API failure instead of
dying of one; 0.0.7d on showing the agent its step budget, which nothing in its
context had ever done; 0.0.7e on telling it what a step costs, after four runs
spent 1.8 tool calls in each of them; and 0.0.7f on the clock — the summariser
now runs alongside the next generation instead of between two steps, and the
children of one step run alongside each other. **0.0.7f's run is where that
series ends**: in 2h43m the agent rebuilt all thirteen modules of this scaffold
from the spec (5,529 lines, a 677-test suite), then ran the rebuild on a 367KB
Wikipedia article and answered a three-part question about it correctly, in five
steps. 0.0.7e's run took 17.5 hours to write eleven modules and never reached
the test.

**0.0.8** is a different diagnosis. [Depth, Volume and
Width](docs/Depth,%20Volume%20and%20Width.md) closed 0.0.7 by naming the axis a
fixed context is actually defeated by — not the size of the corpus but the
number of facts that must be true at once — and three design letters answer it:
[`0.0.8a`](docs/InfiniteAgent%200.0.8a.md) stops a value having to pass through
a generation in order to move, [`0.0.8b`](docs/InfiniteAgent%200.0.8b.md) says a
model operation should be precise at one frame and lossy above it, and
[`0.0.8c`](docs/InfiniteAgent%200.0.8c.md) makes `spawn` behave like the frame it
already was. `--frame` is the configuration that carries all of it. **What it
did** ([`0.0.8`](docs/InfiniteAgent%200.0.8.md)): the module with six-way fan-out
that defeated 0.0.7 four times was implemented and imported in 56 steps with a
largest request of 8,233 tokens, where the 0.0.7 attempt that managed it at all
peaked at 23,251; the reading results did not move (six of six, four of them
faster); and three of five attempts at that module wrote a complete
implementation against 0.0.7's none-of-four.

**0.0.8d** ([`the build note`](docs/InfiniteAgent%200.0.8d.md), and
[`Iterating to 0.0.8d`](docs/Iterating%20to%200.0.8d.md) for the working list) is
the iteration with no design letter: a diagnosis read off the trajectories 0.0.8
had already produced. 0.0.8's own verdict was that the task turns on *when a run
starts writing* — which the trajectories refute, since both frames that produced
a working module wrote in the last fifth of their budget. What they turn on is
whether a step leaves anything behind at all, so the scaffold now measures that,
says so when a run has stopped, and charges for it. On the far side of it the hard
task passes **three times out of three**, the writing clause has its first live
evidence, and every clause of the Infinite Context Test has a number against it
rather than an argument — with the caveat that four things changed at once and the
mechanism 0.0.8d is named for collected two budget units across those three runs,
so it is the least likely cause of its own success.

## The scaffold

Every step is a *stateless* model call. The only user message is
`[Step] depth D, step N of M` and a dump of the registers — there is no
conversation history. Everything else lives on disk and is reachable through
the tools.

- **33 registers** (0–32), in three length tiers. Registers 0–4 are special and
  written by the system, and
  no tool may name them as a destination; registers 5–31 are the agent's and
  hold `max_register_length` (1024) chars each; register 32 is the canvas at
  `max_canvas_length` (20000).
  - register 0 — return information of the single most recent tool call: the
    path to its result file, or a status / error message.
  - register 1 — `"True"` if the previous generation was cut off before
    finishing, `"False"` otherwise.
  - register 2 — the **target**, written only by `set_target` and by nothing
    else, ever. The one address in the file that changes when the agent decides
    it should, so a plan can outlive the work it directs.
  - register 3 — the **last step**, written automatically after every step:
    `[thinking]`, everything the agent generated other than its tool calls, then
    `[action]`, the calls themselves. Each half is cut to
    `max_step_half_length` (2048) chars on its own, so a long deliberation
    cannot crowd out the record of what was actually done.
  - register 4 — a running **summary** of the run so far. After every step one
    cheap tool-less model call is handed the previous summary and that one step
    and returns the summary that replaces it; nothing else writes it. It is the
    agent's only memory of anything before the last step. That call runs
    *alongside the next generation* rather than between two steps, so the
    register is one step behind — the summary through step N lands in time for
    step N+2, and register 3's copy of step N+1 is the other half of a pair that
    still covers the whole run. `--no-summary` turns it off.
  - registers 2 and 4 hold `max_special_length` (6144) chars — larger than a
    normal register, smaller than the canvas. 3 and 4 truncate; `set_target`
    rejects.
- **Tools** — `bash(command)`, `load(path, start)`, `set(value, register_id)`,
  `set_target(content)`, `spawn(goal, check, return_schema, …)`
  and `resume(agent_id, max_steps)`. All but `set` and `set_target` take an
  **optional** `register_id` for their return information, truncated to fit; the
  full version is in the trajectory (and, for `bash` and the two recursion
  tools, in a json result file). No tool may target a special register.
  Omitting `register_id` discards the payload, which is how a working set
  survives a step that reads four files — before 0.0.8 the write was
  unconditional, so a five-call step overwrote all five free registers and the
  scaffold charged the agent its whole memory for taking its own batching advice.
- **The registers are files** — around every `bash` call the register file is
  written to `$REGDIR/0 … $REGDIR/N` and exported as `$R0 … $RN`, and read back
  afterwards: a file the command wrote becomes that register, truncated and
  tagged exactly as a tool result is. So `cp $REGDIR/5 $REGDIR/6`,
  `grep -n "$R5" src/*.py > $REGDIR/6` and `sed -n 1,40p "$R5" > $REGDIR/6` are
  copy, register-to-register and deref-copy, and none of them passes through a
  generation. Registers 0-4 are read-only and a write to one is refused on the
  way back. It lives in the agent's own scratch directory, so neither an `ls` of
  the work nor the agent's own `rm` reaches it
  ([`0.0.8a`](docs/InfiniteAgent%200.0.8a.md)).
- **The memo table** — `facts.md`, one resolved fact a line, shared by every
  agent in the workspace, written with `>>` and queried with `grep`: the
  artefact five runs kept reaching for as a prose digest, in the form the work
  wants. It exists from the moment the workspace does, header and all, because
  the system message names it every step. 0.0.8 filled it from a `lookup(symbol)`
  tool backed by an AST index; **0.0.8d removed that tool** — the index only
  parsed Python, which made the one primitive meant to turn width into depth a
  special case for one language, and `grep` is language-agnostic and already in
  the agent's hands. Ten calls across five runs, none of them in the two runs
  that passed.
- **Workspace** — at most `workspace_tokens` generated per step. Over that, the
  generation is cut off, saved to the trajectory, no tool calls run, and
  register 1 flips to `True`.
- **Context budget** — every agent works out what one generation of it can cost
  — the system message, the tool schemas, the fullest possible register dump,
  and the output cap — logs it, and records it in its trajectory header. Setting
  `max_context_tokens` turns that into a ceiling the run refuses to start over.
  0.0.7f's own geometry comes to 46,684 tokens; **`--short` is 0.0.7g's input**
  ([`0.0.7g`](docs/InfiniteAgent%200.0.7g.md)), reached by compressing the fixed
  half of every request rather than the working space — and that is where the
  accounting for the whole series lives. Since 0.0.8 the budget also reports
  `working_set_chars`: the free registers, the canvas and the target — what the
  *agent* controls, as against what the request costs. At 0.0.7g that was 3,280
  characters of a 7,453-token request; `--frame` makes it 5,840. (`--frame`'s
  surrounding total is ~16,700 tokens at 2.6 chars/token, or 16,639 as
  `Config.context_tokens` reports it at four; compare the character counts.)
- **Two budgets** — the input geometry and the output cap are separate
  resources. Reading is bounded by paging and is indifferent to the cap; writing
  tracks it almost exactly (9.5 lines of code a step at 16,384 tokens, 1.3 at
  1,920). `--wide-output` keeps `--short`'s input geometry and gives the
  generation 8,192 ([`0.0.7i`](docs/InfiniteAgent%200.0.7i.md)); in practice its
  agents' largest requests came to about 5,400 tokens.
- **What the run has spent** — the `[Step]` line opens with the agent's depth,
  says how much of its budget went to children, and once a run has more than one
  agent adds `this run has spent N steps across M agents`
  ([`0.0.7j`](docs/InfiniteAgent%200.0.7j.md) made the price visible;
  [`0.0.8c`](docs/InfiniteAgent%200.0.8c.md) made it charged).
- **Progress, and the price of not making any** — every step records what
  durable state it changed: a file in the workspace, the target register, the
  memo table, the check's verdict. Everything else a step makes, the next step
  overwrites. A step that changed none of it is a *stall*, which is not a defect
  — reading four files in one step to decide is a stall and the scaffold asks for
  it — but stalls in a row are a livelock, and a run that loops fails at eighty
  steps and would fail at eight hundred. So from the third in a row the `[Step]`
  line says where the budget went, a `[Stall]` line says what has not happened,
  and each further one costs a step of budget on top of itself. A price and not a
  ceiling, for the reason `max_depth` is gone: the scaffold has an opinion about
  the resource, not about the shape of the work. On the five runs of the hard
  task this was the only measure that separated the frames that shipped a module
  from the frames that did not — every one that passed stalled at most four steps
  in a row, every one that failed ran to six, eight, nine
  ([`0.0.8d`](docs/Iterating%20to%200.0.8d.md) §4.1).
- **The invariant** — four sentences of system message, because a recommendation
  about how to work is a sentence and not a tool: hold one goal at a time and be
  precise about it, lossy about why you are here, and hold nothing about what is
  beside it; descend at a working-set boundary and not otherwise; end work with a
  machine check ([`0.0.8b`](docs/InfiniteAgent%200.0.8b.md)).
- **Unfinished children** — an agent that stops without a response writes
  `handoff-<id>.json` saying what it had established — including the check it
  was failing, which is the parent's and only the parent can change — and a
  parent can continue it with `resume(agent_id="<id>", max_steps=N)` instead of
  starting again. A
  generation cut off at the token cap now runs the calls it had finished
  ([`0.0.7h`](docs/InfiniteAgent%200.0.7h.md)).
- **Firewall** — the bash session runs inside an OS sandbox (seatbelt on macOS,
  bubblewrap on Linux) and `load` is checked against the same policy: the agent
  writes only inside the workspace, and reads only the workspace plus whatever
  `--allow-read` grants. The run's own record — trajectories and `tool_output/`
  — is denied even though it lives in the workspace. Network is not restricted.
  With no backend available the run refuses to start rather than run unconfined.
- **Scratch** — each agent gets `.scratch/<agent_id>/` inside the workspace, and
  its shell runs with `TMPDIR`, `PYTHONPYCACHEPREFIX` and the other cache
  variables pointed there, so the toolchain never trips over the sandbox and no
  agent's temporary files land where another agent's `ls` will find them.
- **Failure** — a tool that raises becomes an error in register 0, a summariser
  that fails leaves the previous summary standing, and a step's own generation is
  retried for up to `step_retry_seconds` (900) with a backoff that doubles to a
  one-minute ceiling, before the segment ends with a `final` that `--resume` can
  continue from. Nothing about a
  transient API error should cost a run its work.
- **Termination** — the run ends when the agent writes valid JSON to its
  `response-<id>.json` (matching the return schema, if one was given).
  A rejected response comes back as an error in register 0. A run that instead
  exhausts `max_steps` can be continued with `--resume`.
- **Timing** — each step records where its wall-clock went: `generation_s`,
  `tools_s`, the `summary_s` its summariser spent alongside the *next*
  generation, and `summary_wait_s`, the part of that the loop actually had to
  wait for. On a real run the wait is a millisecond a step against seconds of
  summarising.
- **Trajectory** — `trajectory-<id>.jsonl`, one JSON object per step, nothing
  truncated. Left read-only between appends, so the agent can read it but not
  write it. The header line holds the instruction, the config, and the static
  half of the model input (system message + tool schemas); each assistant step
  holds the messages it was sent, the register snapshot, the raw content
  blocks, an `observation.results` entry per tool call, and the `summary` update
  that followed — enough to replay any request exactly. Specified in
  [`docs/Trajectory Format.md`](docs/Trajectory%20Format.md).

`spawn` creates a fresh agent in the same workspace with its own registers,
workspace budget, and trajectory — the recursion that keeps a sub-task's
intermediate context out of the parent's registers.
[`0.0.8c`](docs/InfiniteAgent%200.0.8c.md) makes it behave like the frame it
already was:

- **The brief is names, not prose.** `goal` (one sentence), `read` (where to
  start, a pointer set and not a permission set), `write`, `check`, and
  `goal_file` for anything longer — the scaffold renders them into the child's
  instruction. A parent is the lossy frame by construction, so the field that
  asked it for a precise instruction asked for something it could not supply,
  and briefs came out either as 0.0.6's 42KB contract document or as one vague
  paragraph.
- **The goal, the destination and the check are in the child's system message**,
  not only in its instruction file. They are the one thing 0.0.8b's invariant
  says must be true at every model call, and a 0.0.8 child whose goal was only a
  file spent 27 of its 30 steps re-reading it.
- **`check` is required, with `true` as an explicit opt-out.** The scaffold runs
  it when the child writes its response; a response that fails it is refused,
  the reason lands in register 0, and the child keeps working. A shell's 126 or
  127 — the command does not exist — reads differently from a check that ran and
  said no, because that check is the parent's and the child cannot change it.
- **And it runs after every step, not only at the pop.** The verdict is one line
  at the top of the dump, between the budget and the registers:
  `[Check] FAILS (exit 1): ModuleNotFoundError… — tool_output/…`. That is 7.3's
  "verify instead of read" made structural: a check is a machine operation, so
  it is unbounded and costs no width, and being told every step whether the work
  imports is cheaper than reading six modules to find out. A check slower than
  `check_live_seconds` (15s) stops being run that way and says so —
  `--no-live-check` turns it off.
- **A child's steps come out of its parent's budget**, transitively, so
  `max_steps` is an allocation rather than a wish and the `[Step]` line says how
  much of the budget went to children. An allocation larger than what is left is
  cut to it.
- **The scaffold has no opinion about depth.** `max_depth` is None: the agent
  sees its own depth on the `[Step]` line, a parent may pass its children an
  allowance, and the refusal at a floor names whose allowance ran out. What
  bounds a runaway chain is that its steps are charged. `--max-depth` is still
  there, because a user is a parent and should get any control a parent has.
- **`resume(agent_id, max_steps)`** continues a child that ran out, keeping its
  registers, its files, its check and its step count.

Several `spawn` calls in one step run **at the same time**, `spawn_workers` (4)
at once, so a fan-out costs the slowest child rather than the sum of them; their
registers are written afterwards in the order the model asked, so a concurrent
step leaves the register file where a serial one would.

The summariser behind register 4 is *not* one of those. It is a single
tool-less generation: previous summary and one step in, new summary out, with no
registers, no trajectory and no second step. It is given
`summary_target_chars` (2400) as the space it has, and that is the **only** length
it is told: register 4's real limit is checked here and never named to the model,
because a model told the ceiling writes to the ceiling. A summary over the real
limit is regenerated whole — `summary_max_attempts` (3) times, each retry shown
the attempt that was too long — and truncated if the last one still does not fit.
It runs on `summary_model` (`claude-haiku-4-5`) with thinking off and
`summary_effort` (`none` — no effort parameter at all, which the small models
require), because it rewrites a paragraph rather than deciding what to do next.

## Running it

```bash
cp .env.example .env   # then fill in ANTHROPIC_API_KEY

uv run infinite "Count how many times 'gamma' appears in corpus.txt" \
    --workspace runs/count-gamma \
    --schema schema.json          # optional: JSON Schema for the final response
```

`--workspace` is the directory the agent works in and where its instruction,
response, trajectory, and tool output files land — and, under the firewall, the
only place it can write. `uv run infinite --help` lists the register,
workspace, and recursion limits.

```bash
# let it read a corpus it must not modify
uv run infinite -f task.md -w runs/x --allow-read ~/corpus

# it ran out of steps: give it 40 more, or no cap at all
uv run infinite -w runs/x --resume 0ac207e0 --max-steps 40
uv run infinite -w runs/x --resume 0ac207e0 --max-steps none
```

A run recorded under an earlier register layout refuses to resume, because the
same register numbers meant something else — 0.0.2's registers 2–4 were the
agent's own notes, and 0.0.3's 3 and 4 were the last step's thinking and action.
Pass `--upgrade-registers` to accept the reinterpretation: register 2 becomes the
target, register 3 is overwritten with the next step, and register 4 is cleared
for the summary. A 0.0.4 or 0.0.5 run needs none of that — 0.0.5 changed who
writes register 4 and 0.0.6 changed what that writer costs, neither of them what
the register holds — so both resume into this scaffold as it stands.

On resume, `--max-steps` is how many *more* steps to allow. The continuation
appends to the same trajectory after a `resume` record; registers come from
where the previous segment stopped, and the workspace is already on disk.
Register geometry is inherited from the original run — only budgets and the
model can be changed across the seam.

```bash
uv run pytest test    # offline: the model is scripted
```

## What a fixed context can and cannot do

[`docs/Depth, Volume and Width.md`](docs/Depth,%20Volume%20and%20Width.md) is
the findings document for the 0.0.7f–0.0.7j experiments: a job costs *depth*
(how much material), *volume* (how much output) and *width* (how many facts must
be true at once), and only the third one touches the context. Reading 39MB and
writing a module both work at 8,000 tokens; implementing a module that calls into
six others does not, and the reason is that the agent controls 1,261 tokens of
that 8,000 and needs about forty interface facts. It also argues that no
functionality *requires* a growing context — width is bounded by coupling and by
retrieval granularity, both of which the scaffold can attack — and says what to
build next.

## Evaluation

`eval/` runs the shipped CLI over public long-context benchmarks — BABILong,
∞Bench and SWE-bench Verified — and grades it against their own ground truth.
At **7,802 tokens for a whole generation** it answers 18 of 18 reading questions
over corpora from 245KB to **39.4MB**, and fixes a real flask bug graded by
held-out tests. See [`docs/Evaluation.md`](docs/Evaluation.md).

Two probes in `eval/benchmarks/` are the project's own rather than a public
dataset, because the Infinite Context Test asks for two things no benchmark
measures. `width` is the task the whole series turns on — implement one module
that calls into nine siblings. `volume` is *infinite writing*: turn a corpus of
records into a card each, run it twice at ten times the size, and the claim is
not that either run succeeds but that the largest request does not move between
the two rows while the output does. It generates its corpus from a seed, so it
needs no network and works on a fresh clone.

Both have been run, and both clauses hold.

`volume`: 120 records then 1,200, every field of every card correct in both,
**ten times the output and the largest request 5.1% smaller** — 106,274 bytes
produced from 8,594 generated tokens against a 6,446-token request
([`eval/results/volume-0.0.8d.json`](eval/results/volume-0.0.8d.json)).

`width`: **three of three**, modules of 550, 350 and 377 lines that all import
with no stub left, graded by running the interpreter rather than by reading the
response. The largest request across the three spans **232 tokens** — 7,867 to
8,099 — which is the fixed-context property on the task this whole series was
shaped by. It is one task and three runs, and four things changed at once against
the 0.0.8 arms' 2 of 5, so it is a result rather than an explanation
([`eval/results/width-0.0.8d.json`](eval/results/width-0.0.8d.json)).

```bash
uv run python -m eval.run babilong --config 10M --split qa2 -n 1 --profile short
uv run python -m eval.run volume --config 120  --profile frame
uv run python -m eval.run volume --config 1200 --profile frame   # ten times as much
uv run python -m eval.run width -n 3 --profile frame             # the hard task
uv run python -m eval.run width -n 3 --profile frame --arm no-stall-charge
uv run python -m eval.run --report
```

`--arm` is one named variable off the baseline, because the one thing that has
repeatedly cost a comparison here is an arm that changed two things at once.

## Reading a run

```bash
uv run infinite-viewer runs        # http://127.0.0.1:8765
```

Scans every workspace under `runs/`, lists the agents it finds, and shows a
trajectory as a dialogue: instruction, then one turn per step with its
thinking, tool calls, full tool output, the summary that replaced register 4
afterwards, and where the step's time went (generation vs tools vs summary).
A resumed run shows the seam where it was picked up. Two panels are collapsed until
clicked — the *input context template* (the system message and tool schemas,
identical every step) and, per step, the *model input* that was actually sent:
system, tools, and the register dump verbatim. Sub-agents link through from the
`spawn` call that created them. Trajectories written under earlier formats still
render — including runs from 0.0.4 and before, whose summariser sub-agents keep
their own trajectories and their links from the step they summarised — with a
pre-v1 context re-derived and labelled as such.

## Layout

| File | Contents |
| --- | --- |
| `config.py` | Register counts, length limits, budgets |
| `registers.py` | The register file and its rendering |
| `prompt.py` | The system message |
| `progress.py` | What a step left behind, the stall streak, and the `[Stall]` line |
| `summary.py` | The summariser: its prompts, its length rules, its one call (register 4) |
| `tools.py` | Tool schemas and handlers |
| `bash_tool.py` | Persistent bash session (stdout+stderr on one pipe, with a timeout) |
| `firewall.py` | The path policy and the sandbox backends |
| `agent.py` | The step loop, response validation, recursion, resume |
| `model.py` | The Claude API seam (`Model` protocol + `AnthropicModel`) |
| `trajectory.py` | Append-only read-only jsonl |
| `workspace.py` | Path layout for a run |
| `main.py` | CLI |
| `viewer/reader.py` | Trajectory scanning and normalization |
| `viewer/server.py` | Local http server (`infinite-viewer`) |
| `viewer/index.html` | The dialogue page |

## Documents

`docs/` is the record: what each version set out to do, what it changed, and what
the runs said about it. [`Writing a
Version`](docs/Writing%20a%20Version.md) is the convention for new ones — one
file per version, five numbered sections (aim, modifies, evaluate, results,
handoff), with the first three written *before* the implementation and the
experiment and the last two after, as two commits to the same file. The point of
the split is that a criterion written after the numbers are in is not a
criterion.

| | |
| --- | --- |
| [`Design Tests (Top Down)`](docs/Design%20Tests%20(Top%20Down).md) | The only statement of what "done" means. One page. Start here. |
| [`Depth, Volume and Width`](docs/Depth,%20Volume%20and%20Width.md) | The diagnosis the 0.0.8 series answers, and the axis a fixed context is actually defeated by. |
| [`InfiniteAgent 0.0.X.md`](docs/InfiniteAgent%200.0.8d.md) | One per version. A letter (`0.0.8a`) is a version that stands on its own, not a chapter of another. |
| [`Iterating to 0.0.8d`](docs/Iterating%20to%200.0.8d.md) | The working handoff: problems ranked, what to do next, and the pitfalls that have already cost time. §7 is the reading order for everything above. |
| [`Trajectory Format`](docs/Trajectory%20Format.md) | What a run writes to disk, field by field. |
| [`Evaluation`](docs/Evaluation.md) | How the benchmarks are fetched, posed and graded, and what they have scored. |
| `eval/results/*.json` | Live-run figures, distilled — `runs/` is gitignored, so a number quoted in a document is backed here. |

The documents written before 2026-08-20 predate that convention and are
deliberately not retrofitted.
