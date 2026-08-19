# Trajectory Format

Design doc for `trajectory-<agent_id>.jsonl`, version **3**.

> **v2 (0.0.2)** adds three things: per-step `timing`, a `firewall` record of
> what the run was allowed to touch, and *segments* — a run that stopped can be
> resumed into the same file, so `final` is no longer necessarily the last
> record. That last one is why this is a version bump and not just new fields.
>
> **0.0.4** adds two fields inside v2, which is not a bump: `summary` on an
> assistant step, and `timing.summary_s`. Both describe the summariser sub-agent
> that rewrites register 4 after every step.
>
> **v3 (0.0.5)** is a bump because it *removes*: the summariser stopped being a
> sub-agent and became one tool-less model call, so a step's `summary` no longer
> points at an agent — `agent_id`, `trajectory` and `steps` are gone from it —
> and the header's `summarizer` flag is gone with them. `timing.summary_s` is
> unchanged.
>
> **0.0.7f** adds one field inside v3, which is not a bump: `timing.summary_wait_s`.
> The summariser now runs alongside the *next* step's generation, so `summary_s`
> is what it cost and `summary_wait_s` is what the loop paid for it — usually
> nothing. `summary` still describes the step it is on, and is still written to
> that step's line; the line is simply appended once the summary lands, which is
> during the step after it.

The trajectory is the only complete record of a run. Registers are lossy by
construction — every tool result is truncated to fit — so the trajectory has to
carry the untruncated version of everything: what the model saw, what it
generated, and what came back. It is also read *by the agent itself* (the
system message tells it where the file is), so the format has to stay readable
by a model that only gets to see a few thousand characters at a time.

Two properties follow from that:

* **Append-only and untruncated.** One JSON object per line, written after the
  step completes. Nothing is ever rewritten, and no field is elided for size.
  The file is left mode `0444` between appends so the agent can `cat` it but
  cannot corrupt its own history through `bash`.
* **Replayable.** Every line carries enough to reconstruct the exact request
  that produced it. A reader must never need the scaffold's source code, the
  config file, or a second run to know what the model was looking at.

## Layout

```
runs/<workspace>/
  instruction-<id>.md        the agent's instruction
  response-<id>.json         its final response (its existence ends the run)
  trajectory-<id>.jsonl      this format
  tool_output/<id>-step<NNN>-<NNNN>-<tool>.json
```

One *workspace* is a directory shared by an agent and every agent it spawns, so
a workspace holds one trajectory file per agent. There is no manifest: the set
of agents in a workspace is exactly the set of `trajectory-*.jsonl` files, and
the parent/child edges are recoverable from the `spawn` records inside them.

## Records

Every line is an object with `step` (int), `role` (string), and `agent_id`.
`role` discriminates the four record kinds; `step` is monotonically
non-decreasing.

A trajectory is a sequence of one or more **segments**. A fresh run opens the
file with a `header` and closes it with a `final`; resuming appends a `resume`
record and continues, so the shape is:

```
header  assistant…  final   resume  assistant…  final   …
```

Step numbers continue across the seam — they identify a step within the whole
run, not within a segment — and no two records share one, so a segment's
closing `final` consumes a number and the next segment's first step follows it.
The assistant steps of a resumed run therefore skip a number at each seam.
Readers must take the **last** `final` as the outcome and treat earlier ones as
segment boundaries.

### `header` — `role: "user"`, `step: 0`

Written once, before the first model call. Holds everything constant for the
run: the instruction, the file layout, the config, and the static half of the
model input.

| Field | Type | Meaning |
| --- | --- | --- |
| `format_version` | int | This document's version. Absent means pre-v1 (see *Compatibility*). |
| `step` | int | Always `0`. |
| `role` | `"user"` | The instruction is the user's turn, even though it never enters the context directly — the model reads it from a file. |
| `agent_id` | str | 8 hex chars; names every file belonging to this agent. |
| `depth` | int | `0` for the root agent, `parent + 1` for a spawned one. |
| `content` | str | The instruction text, verbatim. |
| `workspace_root` | str | Absolute path; also the agent's cwd. |
| `instruction_file` `response_file` `trajectory_file` | str | Workspace-relative paths. |
| `return_schema` | object \| null | JSON Schema the response must satisfy. |
| `config` | object | The full `Config` dataclass as a dict. |
| `summarizer` | bool | **Pre-v3 only.** True for the sub-agent that kept another agent's register 4. Absent since v3, where no agent is one; a reader must treat absent as false. |
| `seed_registers` | array of int | Registers filled before the first step. Those values are part of the first step's input and are not derivable from anything else. |
| `started_at` | str | UTC ISO-8601, when the run began. |
| `firewall` | object | `{enabled, writable, readable[]}` — the path policy in force. |
| `context_template` | object | See below. |

`firewall` is what the run was *allowed* to touch, which is not derivable from
anything else in the file: two identical trajectories can differ only in
whether some directory was readable. `writable` is always the workspace.

`context_template` is the part of the model input that does not change between
steps — it is stored once rather than on every line:

```json
{
  "system": "You are a helpful assistant running inside InfiniteAgent…",
  "tools": [ { "name": "bash", "description": "…", "input_schema": {…} }, … ],
  "max_tokens": 8192
}
```

The `system` string is the *rendered* system message, not a template with
holes. The template lives in `prompt.py`; what a reader wants is the text the
model actually received, with the register counts and file names already
substituted. Since the scaffold sends it identically every step (and marks it
with a cache breakpoint), storing one copy is exact, not an approximation.

### `assistant` — `role: "assistant"`, `step: 1…max_steps`

One per model call, written after the call's tool results are in.

| Field | Type | Meaning |
| --- | --- | --- |
| `model_input` | object | `{"messages": [...], "max_tokens": int}` — the *dynamic* half of the request, verbatim. Concatenated with the header's `context_template`, this is the entire request. |
| `registers_before` | array of str | The register values as of the start of the step. Redundant with `model_input.messages` but cheap, and it lets a reader diff registers across steps without re-parsing the dump. |

Which registers are special, what they mean, and how long each may be come from
the header's `config` — `register_layout`, `num_special_registers`,
`max_register_length`, `max_special_length`, `max_step_half_length`,
`max_canvas_length`. A reader must not hard-code the layout: it has changed
between scaffold versions, `register_layout` is the version of that meaning, and
the config is the record of what was in force. Note that some special registers
are written by the system *after* a step, so a step's `registers_before` shows
the previous step's record and the summary as it stood then, not its own.
| `content` | array | Raw content blocks from the API, unmodified: `thinking`, `text`, `tool_use`. Includes thinking signatures. |
| `stop_reason` | str | `end_turn`, `tool_use`, `max_tokens`, `refusal`. |
| `usage` | object | Token counts from the API, including cache reads. |
| `observation` | object | `{"results": [...]}`, one entry per tool call, **in the same order as the `tool_use` blocks**. Absent when no tool ran. |
| `summary` | object | The call that rewrote register 4 after this step. Absent when summaries are off, and on the step that ends the run. See below. |
| `timing` | object | `{started_at, generation_s, summary_wait_s, tools_s, summary_s, total_s}`. |

The `summary` object, since v3:

| Field | Type | Meaning |
| --- | --- | --- |
| `ok` | bool | Whether register 4 was replaced. False leaves the previous summary standing. |
| `attempts` | array of int | The character length of every generation, in order. More than one means the first came back over `limit`. |
| `target_chars` | int | The soft target the model was asked for. |
| `limit` | int | Register 4's hard limit, checked by the scaffold. |
| `model` | str | Which model wrote it — not necessarily the run's. |
| `usage` | object | Token counts summed across attempts, so a retry is not free in the record. |
| `summary` `chars` `truncated` | str, int, bool | Present when `ok`. `truncated` means no attempt fit and the scaffold cut the last one. |
| `error` | str | Why it did not fit or did not finish. Usually with `ok: false`, but it appears alongside a summary when a call broke and an over-long earlier attempt was kept and cut instead. |

`attempts` is the field that makes the retry rule auditable: a run whose
summaries keep overshooting shows it here rather than only in the clock.

Before v3 the same field described a sub-agent instead — `{agent_id, ok,
trajectory, steps}` plus `summary`/`chars` or `error` — and its `trajectory`
was an edge to another file in the workspace. Since v3 `spawn` is the only such
edge.

`timing` splits the step's wall-clock into the things that can actually be
traded against each other: `generation_s` is time waiting on the model,
`tools_s` is time running what it asked for, and `summary_s` is the summary
call, retries included. Since 0.0.7f the summary of a step is written while the
*next* step is generated, so `summary_s` is not part of this step's elapsed time
— what the loop actually paid is `summary_wait_s`, the tail of the previous
step's summariser that had not finished when this generation came back, and
`total_s` is `generation_s + summary_wait_s + tools_s` plus the bookkeeping
between them. A run whose summariser is slower than its generations shows it as
a `summary_wait_s` that stops being zero. Each observation entry also carries its own
`duration_s`, so a slow step can be attributed to a specific command rather
than to "tools". Durations are monotonic-clock seconds; `started_at` is a UTC
wall-clock stamp, and the two must not be mixed — only `started_at` is
comparable across machines.

`model_input.messages` is a single-element list — the register dump — because
the scaffold keeps no conversation history. It is stored as a list anyway so
the record shape survives a scaffold that later sends more than one message.

The invariant a reader can rely on: **the request for step *N* is exactly**

```
system   = header.context_template.system
tools    = header.context_template.tools
messages = step[N].model_input.messages
```

Nothing else is sent. No history, no prior tool results, no instruction text.

Observation entries are per-tool records, always carrying `tool` and either the
call's inputs and outputs or an `error`:

| Tool | Fields |
| --- | --- |
| `bash` | `register_id`, `command`, `output` (full, stdout+stderr interleaved), `file` (path to the tool-output json) |
| `load` | `register_id`, `path`, `start`, `length` (of the whole file), `display_length`, `content` (the excerpt stored) |
| `set` | `register_id`, `value`, `status` |
| `set_target` | `register_id` (always the target register), `content`, `status` |
| `spawn` | `register_id`, `prompt`, `return_schema`, `max_steps` (the budget the parent gave, or null), `agent_id` (the child's), `content: {trajectory, response}` |
| any | `error` — the call was rejected or raised; nothing was stored |
| any | `duration_s` — how long the call took |

`content.response` carries `{file, steps}` and then either `content` (the
child's response) or `error`, so what a child cost is on record beside what it
returned. When a step holds several `spawn` calls they run concurrently (0.0.7f),
so their `duration_s` values overlap and may each be longer than the step's
`timing.tools_s`; the order of the entries is still the order the model asked in.

A `spawn` entry's `content.trajectory` is the workspace-relative path of the
child's trajectory file. Since v3 it is the **only** link between trajectories
and the only thing a reader follows to build the call tree. Before v3 a step's
`summary.trajectory` was a second one, pointing at the summariser sub-agent that
kept register 4 — a child like any other, distinguishable by having no summary
and no `spawn` tool of its own.

When `stop_reason` is `max_tokens` the record has **no** `observation`: a
cut-off generation may hold a half-written tool call, so nothing is executed.
The next step's registers will show register 1 flipped to `"True"`. It still
carries a `summary`, because the step happened and the summary is the record of
what happened.

### `final` — `role: "final"`

Closes a segment, at `step = last_assistant_step + 1`.

| Field | Type | Meaning |
| --- | --- | --- |
| `ok` | bool | Whether a valid response was produced. |
| `response` | any | The parsed response, or `null`. |
| `response_file` | str | Workspace-relative path. |
| `error` | str \| null | Why the segment ended — step budget exhausted, or a crash. |
| `ended_at` | str | UTC ISO-8601. |
| `segment_duration_s` | float | Wall-clock for this segment. |
| `registers` | array of str | Register values at the end. |

`registers` is what makes resuming exact rather than a guess — see below.

A trajectory whose last segment has no `final` line is a run still in progress
or killed. Readers must handle that: the file is flushed per step, so a live
trajectory is always valid jsonl up to its last complete line.

### `resume` — `role: "resume"`

Opens a new segment on an existing file, at `step = the last step on record`
(the previous `final`'s number).

| Field | Type | Meaning |
| --- | --- | --- |
| `resumed_from_step` | int | The last *assistant* step the previous segment reached. |
| `max_steps` | int \| null | The new budget — steps *added*, not a new total. `null` means no cap. |
| `registers_from` | str | `"final"` or `"last-step"`; see below. |
| `registers_relayout` | object | Present only when the operator accepted a change in what the registers mean; records the old and new layout. |
| `previous_error` | str \| null | Why the previous segment stopped. |
| `started_at` | str | UTC ISO-8601. |
| `config` | object | The config for this segment. |
| `context_template` | object | Re-recorded, because config changes can alter the system message. |
| `registers` | array of str | The state restored into the new segment. |

**What resuming restores.** The scaffold is stateless per step: everything that
carries over between steps is the register file plus the workspace on disk. The
workspace is already there, so a resume only has to restore registers, and the
previous segment's `final.registers` is exactly that state — `registers_from:
"final"`.

If the process was killed before writing a `final`, that record does not exist.
Rather than reconstruct the state by replaying the last step's observations —
which would duplicate the loop's logic and quietly diverge from it — the resume
falls back to the last step's `registers_before` (`registers_from:
"last-step"`). The cost is that one step is re-done; the benefit is that no
state is ever invented. A reader should show which of the two happened, because
a re-done step appears twice in the file with different step numbers.

What resume does *not* restore: the per-register `truncated` flags, which are
display-only, and the config's register geometry, which is deliberately taken
from the header — restoring 2000-char values into 256-char registers would be
incoherent. Budgets and the model may be overridden across a seam; register
geometry may not.

## Compatibility

**v1 → v2.** Every v1 field is still present and unchanged, so a v1 reader
reads a v2 file correctly *except* for one assumption: that `final` is the last
record and appears once. A reader that takes the first `final` as the outcome
will report a resumed run as failed. Take the last one.

**v2 → v3.** Nothing changed shape except a step's `summary`, and every field it
lost was optional to begin with. A v3 reader reads a v2 file correctly if it
treats the header's `summarizer` as absent-means-false and does not require
`summary.attempts`; a v2 reader reads a v3 file correctly except that the
summariser link it looks for is not there, because there is no longer a
summariser to link to. Both are one-line accommodations, which is why the two
versions render side by side in the same viewer.

`format_version` is absent on trajectories written before this doc. A reader
that wants to display them can reconstruct the missing pieces, because the
pre-v1 header already carried `config`, `instruction_file`, `response_file`,
and `return_schema`:

* `context_template.system` — re-render `build_system_message` from `config`
  plus the header's file names, with `workspace_root` taken from the file's own
  location and `trajectory_file` from the agent id.
* `context_template.tools` — re-derive from `tool_specs(config)`.
* `model_input.messages` — re-render the register dump from `registers_before`.

The reconstruction is faithful except for per-register *truncated* flags, which
pre-v1 records do not store. Anything reconstructed this way must be labelled
as such in a UI rather than presented as what the model actually saw.

Version bumps: adding a field is not a bump; removing or re-typing one is.
Readers ignore unknown fields.

## Why not one line per message

The obvious alternative is an OpenAI-style message log — one record per
user/assistant/tool message, replayed by concatenation. It does not fit here,
because in this scaffold the context is *not* the concatenation of past
messages. It is a fixed-size register file that the agent rewrites. A message
log would imply a history that the model never sees, and would have nowhere to
put the thing a reader most wants: the register state at each step.

So the unit is the *step* — one model call and its consequences — and the
context is stored as a value, not derived from a fold over history.
