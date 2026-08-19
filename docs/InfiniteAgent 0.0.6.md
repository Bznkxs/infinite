# InfiniteAgent 0.0.6-simple

0.0.5 took the summariser away from a sub-agent and gave it to one model call.
That removed the loop — no summariser has failed to converge since — but not the
cost. On the first long run of 0.0.5, summarising was still **69–78% of every
agent's wall-clock** and **3408 output tokens per step**, against the ~250 the
0.0.5 doc measured. Two things were wrong, and both were in the configuration
rather than the machinery.

0.0.6 changes what the call costs and what the model is told. Same register, same
one call, same loop, same termination.

## What the run showed

Twenty-one summarised steps, three agents, `summary_target_chars` at 3000 and
register 4's limit at 4096:

```
first attempt:  min 1663   median 4291   max 4773
steps that needed a retry:      13/21 (62%)
steps truncated after 3 tries:   5/21 (24%)
wall-clock in the summariser:   12.6 of 16.1 min (79%)
```

The median first attempt is not near the 3000 it was asked for. It is near
**4096** — the number in the next sentence of its own system message:

> Aim for about 3000 characters. That is a target, not a limit; the register
> holds 4096, so a little over is fine and there is no reason to pad up to it.

Telling a model the ceiling and asking it not to use the ceiling does not work.
It wrote to 4096, the scaffold rejected it at 4096, and the retry rule then
bought two more whole generations on most steps — the retry path, described in
0.0.5 as headroom for the rare overshoot, was load-bearing on two steps in
three. And every one of those generations was the run's own frontier model,
thinking off but effort on, spending Opus tokens to rewrite a paragraph.

## 1. The budget is the only length it is told

The soft-target-plus-hard-limit pair was right. Naming both of them to the model
was the mistake. Now it is told one number — `summary_target_chars` (3000),
presented as the limit it has:

> Your summary must fit in {budget} characters, so that is the space you have.
> Use it — a summary well under it has thrown away room it could have kept a
> fact in — and do not exceed it.

Register 4's real limit is the scaffold's business and appears nowhere in the
prompt. The retry message measures against the budget too, so a regeneration
does not leak the number the first call was denied.

**Nothing about enforcement changed.** `Summariser.update()` still checks the
real limit, still regenerates whole up to `summary_max_attempts` (3) times, still
truncates the last over-long draft rather than losing the summary. What changed
is that the gap between the two numbers is now genuinely headroom: a model aiming
at 3000 and overshooting by 20% lands at 3600 and fits, and the retry rule goes
back to being the rare case it was described as.

The obvious alternative — enforce at 3000 and drop the second number — is the
same mistake in reverse. Then every ordinary overshoot is a retry, which is
exactly the cost this version is removing.

The instruction is also *not* "be brief". A summary that comes in at 900
characters has thrown away room, and the oldest facts are the ones nothing else
in the register file still holds; the register is a fixed size and the point is
to fill it.

## 2. It runs on a cheap model, with no effort at all

Rewriting a paragraph is not the work the run's model is there for.

| | 0.0.5 | 0.0.6 |
| --- | --- | --- |
| `summary_model` | `None` — the run's model | `"claude-haiku-4-5"` |
| `summary_effort` | `"low"` | `"none"` — no effort parameter at all |

`summary_effort = "none"` is not an API effort level. The API's levels stop at
`low`; below that there is only the *absence* of the parameter, so `NO_EFFORT`
means the request carries no `output_config` at all. That is also not optional
for the cheap tier: a small model **rejects** an effort rather than ignoring one,
so the seam has to be able to omit it. `AnthropicModel.generate` does, and a
run's own steps are unaffected — the override applies to the summary call only.

Measured on the same shape of step that produced the loop, against the same
material:

```
0.0.4  sub-agent:   6 steps, ~150s,  ~15,000 output tokens
0.0.5  one call:    1-3 generations, 35-60s, ~3,400 output tokens
0.0.6  cheap call:  1 generation,    ~3s,       ~80 output tokens
```

Output tokens are also 5× cheaper each ($5/MTok against $25), so the summary
stops being a material line in the run's cost rather than being most of it.

**What this trades.** Deciding what to drop from a full summary is a judgement,
and this is a smaller model making it. The rules it is given have not changed —
keep findings, decisions and dead ends; leave out narration and anything one
register away in 0 or 3; prefer the older fact when both do not fit — and the
work is a rewrite of material it is handed rather than anything it has to find.
`--summary-model` takes the run's model back if a run needs it, and
`--summary-model none` is not a thing: `None` in config means "the run's model",
which is what 0.0.5 defaulted to.

## Config

| Field | Default | Meaning |
| --- | --- | --- |
| `summary` | `True` | Keep register 4. |
| `summary_target_chars` | `3000` | The budget, and the only length the summariser is told. |
| `summary_max_attempts` | `3` | Whole generations spent getting under the register's real limit. |
| `summary_model` | `"claude-haiku-4-5"` | `None` means the run's model. |
| `summary_effort` | `"none"` | `NO_EFFORT`: send no `output_config` at all. |
| `summary_thinking` | `False` | |
| `summary_max_tokens` | `2048` | |

`NO_EFFORT` is honoured for the agent's own effort too (`--effort none`), because
it is a property of the seam rather than of the summariser.

## Trajectory

**Unchanged, still v3.** No field is added, removed or re-typed. Two that already
existed change meaning slightly, and are now the whole story of the mechanism:

- `summary.target_chars` is what the model was *told*, and `summary.limit` is
  what the scaffold *enforced*. In 0.0.5 the model knew both numbers; now it
  knows only the first, and the distance between them is the design.
- `summary.attempts` is how you tell whether that is working. A run whose
  `attempts` arrays are all single-element is a run where the budget is holding;
  a run of `[4548, 4212, 4183]` is what 0.0.5 looked like.

`summary.model` already recorded which model wrote the summary — "not necessarily
the run's" is now the default rather than the exception.

## Resuming across the change

`register_layout` stays **4**. 0.0.6 changed what the summariser costs and what
it is told, not what register 4 holds, so a 0.0.4 or 0.0.5 run resumes into this
scaffold with no `--upgrade-registers` and no cleared register. Budgets and the
model may be overridden across the seam as always, which now includes the
summary settings.

## Not in this version

- **Nothing reads the summary but the model.** Unchanged since 0.0.4: the
  scaffold does not check it, score it, or compare it against the trajectory —
  and that goes for a summary written by a smaller model too.
- **No comparison of summary quality across models.** What is measured here is
  cost and convergence. Whether Haiku's judgement about what to drop is as good
  as Opus's over forty steps is not something this version establishes; the
  register's rules and `--summary-model` are what it offers instead.
- **The budget is fixed.** It does not adapt to how much the step actually
  contained, or shrink as the run gets longer.
- **The overrun path is still barely exercised against a real model.** It is
  covered offline, and the whole point of the change is that live runs should
  stop reaching it. A run whose `attempts` arrays grow is the signal that
  something about this reasoning was wrong.
