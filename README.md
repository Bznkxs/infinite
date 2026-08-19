# InfiniteAgent

A recursive agent that keeps a fixed-size active context, storing everything
else in reliable storage while keeping a reference to it.

This repository implements **0.0.8**: the 0.0.1 scaffold
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
already was. `--frame` is the configuration that carries all of it.

## The scaffold

Every step is a *stateless* model call. The only user message is `[Step] step N of
M` and a dump of the registers — there is no conversation history. Everything else lives on disk and
is reachable through the tools.

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
- **Tools** — `bash(command, register_id)`, `load(path, start, register_id)`,
  `set(value, register_id)`, `set_target(content)`,
  `spawn(prompt, return_schema, register_id)`. All but `set_target` write their
  return information to a destination register, truncated to fit; the full
  version is in the trajectory (and, for `bash` and `spawn`, in a json result
  file). No tool may target a special register.
- **Workspace** — at most `workspace_tokens` generated per step. Over that, the
  generation is cut off, saved to the trajectory, no tool calls run, and
  register 1 flips to `True`.
- **Context budget** — every agent works out what one generation of it can cost
  — the system message, the tool schemas, the fullest possible register dump,
  and the output cap — logs it, and records it in its trajectory header. Setting
  `max_context_tokens` turns that into a ceiling the run refuses to start over.
  0.0.7f's own geometry comes to 46,684 tokens; **`--short` is the same scaffold
  under 8,000** ([`0.0.7g`](docs/InfiniteAgent%200.0.7g.md)), reached by
  compressing the fixed half of every request rather than the working space —
  and that is where the accounting for the whole series lives.
- **Two budgets** — the input geometry and the output cap are separate
  resources. Reading is bounded by paging and is indifferent to the cap; writing
  tracks it almost exactly (9.5 lines of code a step at 16,384 tokens, 1.3 at
  1,920). `--wide-output` keeps `--short`'s 6,063-token input and gives the
  generation 8,192 ([`0.0.7i`](docs/InfiniteAgent%200.0.7i.md)).
- **What the run has spent** — once a run has more than one agent, the `[Step]`
  line adds `this run has spent N steps across M agents`, because a parent's own
  counter moves by one however many steps its child spends
  ([`0.0.7j`](docs/InfiniteAgent%200.0.7j.md)).
- **Unfinished children** — an agent that stops without a response writes
  `handoff-<id>.json` saying what it had established, and a parent can continue
  it with `spawn(resume="<id>", max_steps=N)` instead of starting again. A
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
intermediate context out of the parent's registers. It reaches `max_depth` (1)
levels: an agent at the floor is not offered the tool at all, since a tool that
cannot succeed should not be in the list. Several `spawn` calls in one step run
**at the same time**, `spawn_workers` (4) at once, so a fan-out costs the slowest
child rather than the sum of them; their registers are written afterwards in the
order the model asked, so a concurrent step leaves the register file where a
serial one would. A child takes the parent's step budget unless the call gives it
a `max_steps` of its own, and what it spent comes back with its answer.

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
uv run pytest test/infinite_0_0_1_simple    # offline: the model is scripted
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

```bash
uv run python -m eval.run babilong --config 10M --split qa2 -n 1 --profile short
uv run python -m eval.run --report
```

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
