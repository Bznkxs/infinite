# InfiniteAgent 0.0.4-simple

0.0.3 gave the agent five special registers: the last result, the cut-off flag,
the target, and one register each for the last step's thinking and its tool
calls. That last pair is the whole of the agent's memory, and it reaches exactly
one step back. At step 40, everything between step 1 and step 39 is gone unless
the agent copied it somewhere itself.

0.0.4 spends one register on fixing that, and pays for it by merging two:

- **register 3** becomes the whole of the last step — thinking *and* action, in
  one register, each half cut to 2048 chars.
- **register 4** becomes a running **summary of the run**, rewritten after every
  step by a sub-agent whose only job is that rewrite.

Nothing else changes: same tools, same loop, same termination.

## The register file

| Register | Written by | Limit | Holds |
| --- | --- | --- | --- |
| 0 | system | 512 | Return information of the last **one** tool call. |
| 1 | system | 512 | `"True"` if the last generation was cut off. |
| 2 | `set_target` only | 4096 | The target: what the agent is trying to do. |
| 3 | system, every step | 2×2048 + labels | The last step: `[thinking]`, then `[action]`. |
| 4 | a summariser sub-agent, every step | 4096 | The run so far, everything before the last step. |
| 5–31 | the agent | 512 | Scratch. |
| 32 | the agent | 20000 | Canvas, for long excerpts. |

Registers 0–4 are still special: no tool may name them as a destination.
Register 2 is reachable only through `set_target`; 3 and 4 are reachable by
nothing at all.

## 1. Register 3 — one register for one step

0.0.3 split the last step across two registers because thinking and action
answer different questions — *why did I do that* and *what exactly did I do* —
and a model rereading its own step usually wants one or the other.

That was true and not worth a register. They are always written together, always
about the same step, and always read together; splitting them cost a second
4096-char slot to hold the smaller half. Merged, one register carries the step:

```
--- register 3 (2114/4117 chars; last step, special) ---
[thinking]
The count from wc is lines, not occurrences. grep -o is what I want.
[action]
bash({"command": "grep -o gamma corpus.txt | wc -l", "register_id": 7})
```

**Each half is cut to its own 2048 chars, not the pair to 4096.** This is the
part that matters. Under a shared budget a long deliberation would push the
action out of the register, and the action is the half a next step cannot do
without: it is the difference between "I planned to grep" and "I grepped". A
step whose thinking runs to 5000 chars still arrives with its tool calls intact.

Because the halves are cut before they are joined, the assembled value always
fits and its length can no longer report that anything was lost. So the register
file takes the truncation flag explicitly, and the dump keeps saying
`truncated` when either half was cut:

```
--- register 3 (2114/4117 chars; last step, special, truncated) ---
```

The limit is `2 × max_step_half_length + 21`, the 21 being the two labels. It is
stated that way rather than rounded to 4096 so that neither half can ever be
squeezed by the labels that separate them.

Cut-off generations behave as they did: the `[thinking]` half holds whatever was
produced before the cut, and the `[action]` half says the generation was cut off
and nothing ran, so a half-written call is never mistaken for a call that
happened.

## 2. Register 4 — a summary kept by a sub-agent

Register 4 holds prose describing the run so far. Nothing the agent can call
writes it. After every step, the scaffold spawns a sub-agent, hands it the
previous summary and that one step, and puts what it returns in register 4.

### Why a sub-agent and not code

Deciding what to keep is a judgement, not a transformation. A summary register
is full almost immediately in a long run, and from then on every update is the
question *what, out of what I already have, is worth less than this new step?*
Truncation answers that question with "whatever is at the end", which throws away
the oldest facts first — precisely the ones nothing else in the register file
still holds. Appending answers it with "nothing", and overflows. A model answers
it by reading both and choosing, which is what this register needs and what a
rule cannot do.

Doing it in a sub-agent rather than in the agent's own step is what keeps the
cost flat. The summariser sees one step and one summary, never the history, so
what it costs per step does not grow with the run — the same reason the scaffold
exists at all. And the parent's context is untouched: it gets the result, not
the work.

### Why it cannot recurse

A sub-agent is an ordinary agent, and an ordinary agent has a register 4 and a
`spawn` tool — so an agent that summarises would summarise its summariser, and
that summariser would summarise its own, forever. The summariser is therefore
built without either mechanism:

- **no summary of its own.** Its config carries `summary=False`, so nothing is
  spawned after its steps and its register 4 stays empty. Its system message
  says so, rather than describing a register it will never see.
- **no `spawn` tool.** It is not offered one, and `ToolBox` refuses the call
  even if it is asked for by name — the same refusal in both places, because a
  tool that is merely undocumented is not a tool that is unavailable.

Those are the only two differences in kind; it also starts with its canvas seeded
(below). Everything else — the register file, the tools, the firewall, the
trajectory — is the standard agent, so a summariser can be read in the viewer
like any other sub-agent.

### What it is given

Its instruction is the whole of its input, so its job is a rewrite and not a
search:

- the agent's task, cut to 2000 chars, and its target — so it can tell a fact
  that matters from one that does not;
- **the summary so far**, which it is replacing;
- **the one new step**: what was thought, what was called, and what came back —
  each tool result named, with its payload bounded, so a step that read a
  100KB file does not become the summariser's whole context.

It is told to keep findings, decisions, dead ends and where the work stands
against the target; to leave out narration, and anything already one register
away in 0 or 3; and, when it cannot fit everything, to prefer the older fact —
the newest step is still in register 3, while the oldest exists only in the
summary.

Its response schema caps the summary at register 4's length, so an over-long
summary is *rejected* and rewritten rather than silently cut in half.

### It is handed its input, not sent to find it

The instruction goes in the usual place — `instruction-<id>.md`, so the run has a
record of exactly what was asked — but it is *also* seeded into the summariser's
canvas before its first step, and its system message says so.

That is not a convenience. A summariser that has to read its own instruction
first is a summariser whose first step is a `load`, and the first live run of
this mechanism failed exactly there: the sub-agent `cat`-ed its instruction into
a 512-char register, saw only the opening paragraph, decided it had not read
enough, and did it again — three times, until its budget ran out and the summary
went unwritten. The instruction is data the parent already has; making a
sub-agent page it in through a register is work with nothing to show for it.

Seeded, the summariser answers on step one. `summary_max_steps` (6) is then
headroom for a schema rejection or a bad tool call, not the budget for a paging
loop.

Seeding is general — `Agent(seed={register: value})` — and the register is only
advertised in the system message when the whole instruction fits in it, since a
copy that was truncated is not one the agent can rely on.

### When a summariser fails

The old summary stays. A run whose memory is erased because one sub-agent ran out
of steps would be far worse off than one whose memory is a step out of date, and
the step it missed is still in register 3 and in the trajectory. The failure is
recorded on the step (`summary.ok: false`, with the error) and logged, so a run
that quietly stops summarising is visible rather than merely poorer.

### When it runs, and when it does not

After the step's tools, and only if the run is not over: the step that writes the
response file gets no summary, because there is no next step to hand it to. A
cut-off step *is* summarised — it happened, and the summary is the record of what
happened.

`--no-summary` turns the mechanism off for a whole run. Register 4 then stays
empty and the agent remembers exactly one step, as in 0.0.3. It is the cheap
mode, and it is what the summariser itself runs in.

### What the summary is not

It is second-hand and lossy by construction: prose about the run, written by a
model that saw one step of it. It is not a substitute for the trajectory, which
holds everything untruncated, and not a place to keep a value that has to be
exact. The system message says as much — anything that must survive precisely
belongs in a file or in a register the agent controls.

## Cost

Every step now runs a sub-agent, so a step costs its own generation plus one
extra call — the summariser answers in a single step. On a small live run that
was around 5-6s of the step's 8-10s, and roughly one extra generation's worth of
tokens per step. That is the price of memory older than one step, and it is
bounded per step rather than growing with the run. `summary_s` in each step's
`timing` is how much of the step went on it, so the trade is measurable rather
than assumed.

## Resuming across the change

Register values are restored **by index**, so the meaning of each special
register has to be the one it had when the run was recorded. 0.0.3 stated that
rule for register *geometry*; the meanings are now versioned explicitly:
`register_layout` in the config, `4` in this scaffold.

A run recorded under any earlier layout — 0.0.2's two specials, or 0.0.3's five
with a different 3 and 4 — refuses to resume, and says which layout it was. The
count alone cannot tell 0.0.3 from 0.0.4: both have five. `--upgrade-registers`
accepts the reinterpretation explicitly:

```bash
infinite -w runs/x --resume 0ac207e0 --max-steps 40 --upgrade-registers
```

- register 2's contents are kept and become the target;
- register 3 keeps its contents for one step, then the automatic write takes
  over;
- **register 4 is cleared.** Under every earlier layout it held something that is
  not a summary, and presenting an old action as a summary of the run would be a
  lie the agent has no way to detect;
- the wide tier and the register-3 halves are clamped into the run's own
  geometry, so a run recorded with a small canvas does not end up with special
  registers larger than it;
- the `resume` record carries `registers_relayout`, including the layout numbers
  and that register 4 was cleared.

## Trajectory

The format stays **v2** — two added fields, no changed ones:

- `summary` on an assistant step: `{agent_id, ok, trajectory, steps}`, plus
  `summary` and `chars` when it worked or `error` when it did not. It is the
  second kind of edge between two trajectories, after `spawn`.
- `timing.summary_s`, alongside `generation_s` and `tools_s`.

The viewer shows each step's summary update as a fold under the step, with a link
into the summariser's own trajectory.

## Not in this version

- **Nothing reads the summary but the model.** The scaffold does not check it,
  score it, or compare it against the trajectory. As with the target, it is a
  place to keep something, not a mechanism that enforces anything.
- **One summariser per step, synchronously.** It runs between the step's tools
  and the next generation, so the step waits for it. Running it in parallel with
  the next generation would mean a step whose summary describes a step it cannot
  yet see.
- **No summary of the summary.** The summariser is a leaf. Whatever it drops is
  gone, save for the trajectory.
