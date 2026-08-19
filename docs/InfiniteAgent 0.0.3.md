# InfiniteAgent 0.0.3-simple

0.0.1 made every dynamic part of the context a register and left two ideas from
the bottom-up notes unbuilt: a place for the agent to keep a strategy it can
"stick to", and the "last part of history" — what it just said and did. 0.0.3
builds both, as registers, because in this scaffold everything in context is a
register.

Two special registers become five, and the length limits split into three
tiers. Nothing else changes: same tools plus one, same loop, same termination.

## The register file

| Register | Written by | Limit | Holds |
| --- | --- | --- | --- |
| 0 | system | 512 | Return information of the last **one** tool call. |
| 1 | system | 512 | `"True"` if the last generation was cut off. |
| 2 | `set_target` only | 4096 | The target: what the agent is trying to do. |
| 3 | system, every step | 4096 | What the agent generated last step, minus the tool call. |
| 4 | system, every step | 4096 | The tool calls the agent made last step. |
| 5–31 | the agent | 512 | Scratch. |
| 32 | the agent | 20000 | Canvas, for long excerpts. |

Registers 0–4 are special: no tool may name them as a destination. Register 2
is reachable only through `set_target`; 3 and 4 are reachable by nothing at
all.

### Why three length tiers

Normal registers drop from 2000 chars to **512**. They are addresses and short
notes — a path, a count, a line of plan — and 2000 chars each across 27 of them
was most of the context spent on registers that are usually near-empty.

Registers 2–4 hold prose the agent has to read back and act on, so they get
**4096**: enough for a real plan and for a step's reasoning, and still a fifth
of the canvas. Registers 0 and 1 stay at the normal limit; a file path and a
boolean do not need more.

The canvas stays at **20000** — it is the one place sized for content rather
than for notes about content, and 0.0.3 does not change what it is for.

`Config` enforces the ordering: `max_register_length ≤ max_special_length ≤
max_canvas_length`. A geometry that violates it is refused at construction.

## Register 2 — the target

```
set_target(content: str)
```

Sets register 2, whole. `content` must be a string. Oversized values are
**rejected**, not truncated, and the register is left as it was — the same
strictness as `set`, for the same reason: a plan silently cut in half is worse
than a plan that failed to save.

This is the bottom-up doc's "strategy" zone, which 0.0.1 deliberately skipped:

> We can also indicate a zone for "strategy", where models can design their own
> strategy. This part will keep unchanged until the model sets a new one. […]
> we need something for the model to "bootstrap", i.e. it should be able to
> generate a strategy from scratch, and then stick to that strategy.

What makes it useful is not its size but what *cannot* touch it. Registers 0,
1, 3 and 4 are overwritten by the system on a schedule the agent does not
control; registers 5–32 are the agent's, and an agent under context pressure
recycles them. Register 2 is the only address in the file that changes when the
agent decides it should and at no other time. That is what lets a plan survive
forty steps of work that has nothing to do with it.

## Registers 3 and 4 — the automatic pair

After every step the system writes:

- **register 3** — every non-tool-call block the model generated, in order:
  thinking, and any prose alongside it. Concatenated rather than chosen
  between, so the register is meaningful with thinking on or off.
- **register 4** — the step's tool calls, rendered as `name({...input})`, one
  per line, in call order.

Both are **truncated** to fit, unlike `set_target`. Truncating is right here:
these are a record of something that already happened and is already in the
trajectory in full. A too-long generation should arrive clipped, not vanish.

This is the other deferred idea:

> last part of history: If it is not the first model response, contain the last
> two parts: the last model response and the last tool use result.

Register 0 was already the second half of that. Registers 3 and 4 are the
first, split in two because they answer different questions — *why did I do
that* and *what exactly did I do* — and a model rereading its own step usually
wants one or the other.

They describe the step immediately before and nothing earlier. There is no
accumulation and no history: step N sees step N−1, full stop. Anything the
agent wants to keep for longer it must copy somewhere it controls, which is
precisely the discipline the scaffold exists to impose.

### Interactions

- **Cut-off generation.** Register 3 gets whatever was produced before the cut,
  which is exactly what the agent needs to continue; register 4 says the
  generation was cut off and nothing ran, so a half-written call is never
  mistaken for a call that happened. Register 1 still flips to `"True"`.
- **No tool call.** Register 4 reads `(no tool call)`.
- **Resume.** Both are ordinary register values, so they cross the seam with
  everything else: a run continued a day later opens with the same last-step
  memory it had when it stopped.
- **Sub-agents.** A spawned agent has its own register file and starts with all
  five empty. It inherits no target — it gets a prompt instead.

## Naming in the dump

With five special registers, `--- register 3 ---` is not enough to act on. The
dump now names each one:

```
--- register 2 (32/4096 chars; target, special) ---
--- register 3 (118/4096 chars; thinking, special, truncated) ---
```

The name is in the same place as the existing `canvas` / `special` /
`truncated` tags, so it costs one word per register and removes a reason to
re-read the system message.

## Resuming a run recorded before this change

Resume restores registers **by index**, so a run recorded when registers 2–4
were ordinary scratch cannot simply continue now that they mean something else:
the same numbers would silently change meaning under an agent that has notes
referring to them.

So `--resume` refuses, and says why. `--upgrade-registers` accepts the
consequences explicitly:

```bash
infinite -w runs/x --resume 0ac207e0 --max-steps 40 --upgrade-registers
```

- register 2's contents are kept and become the target — the agent can no
  longer `set` it, only `set_target` it;
- registers 3 and 4 keep their contents for exactly one step, then the
  automatic writes take over;
- the wide tier is clamped into the run's own geometry, so a run recorded with
  a small canvas does not end up with special registers larger than it;
- the `resume` record carries `registers_relayout` so the seam says what was
  reinterpreted.

This is the same rule 0.0.2 stated for register geometry — it may not change
across a seam — with an explicit override rather than a silent reinterpretation.

## Trajectory

No structural change: the format stays **v2**. `registers_before` is a longer
list of shorter strings, and readers get the layout from the header's `config`
(`num_special_registers`, `max_special_length`) rather than assuming it.
`set_target` adds one observation shape — `{tool, register_id, content,
status}` — the way any new tool would.

## Not in this version

- **Register 2 is not consulted by the scaffold.** Nothing reads the target or
  checks progress against it. It is a place to put a plan, not a mechanism that
  enforces one.
- **No history beyond one step.** Registers 3 and 4 hold the last step only.
  Making them a window of the last *k* steps would reintroduce the growing
  context this scaffold exists to avoid.
