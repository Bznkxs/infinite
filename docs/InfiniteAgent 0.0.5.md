# InfiniteAgent 0.0.5-simple

0.0.4 gave register 4 to a running summary and gave the summary to a sub-agent.
The register was right. The sub-agent was not: on the first long run of it, four
of five summarisers spent their entire step budget failing to write one
paragraph, two never finished at all, and summarising cost 94% of the run's
wall-clock and 96% of its output tokens — to keep a register the agent it was
serving had generated in ten seconds.

0.0.5 keeps the register and replaces the machine behind it with **one model
call**. Nothing else changes: same registers, same tools, same loop, same
termination. Two smaller fixes ride along, both of them things the same run
made obvious.

## 1. The summariser is a generation, not an agent

```
previous summary + one step  ->  one tool-less call  ->  the new summary
```

No registers, no trajectory, no instruction file, no response file, no tools,
no second step. `Summariser.update()` is a plain object over the model seam;
`summary.py` no longer imports the agent, and the agent no longer spawns.

### What went wrong with the sub-agent

The argument for a sub-agent in 0.0.4 was that deciding what to drop from a
summary that is already full is a judgement, and judgement needs a model.
That part was right and is unchanged. What was wrong was concluding that it
needed an *agent*.

An agent has tools, and its answer had to fit register 4. So it measured. The
recorded loop, from one summariser that never converged:

```
step 2: 4610 chars   step 3: 4620   step 4: 4566   step 5: 4430   step 6: 4561
```

Five whole generations, each ~35s with thinking, writing the summary to a file,
running `wc -c` on it, finding it over 4096 and writing it again — the last
attempt longer than the one before. Another wrote `assert len(s) <= 4096` into a
scratch script and crashed on it four times before squeaking under at 4085 on
its final step. A model cannot hit a character budget by generating, and giving
it the means to check turns that into an iteration it has no way to win.

0.0.4 had already fixed one loop here. Seeding the instruction into the canvas
(§4.3) stopped summarisers spending their budget paging in their own prompt.
The lesson generalises further than that fix took it: **every capability the
summariser had, it used on something other than summarising.** Removing the
capabilities is the fix, not tuning the budget.

### Where the length rule lives now

With no tools there is nothing to measure with and nothing to iterate against,
so the rule moves to the scaffold, in three parts:

- a **soft target**, `summary_target_chars` (3000), which is what the model is
  asked for. It is deliberately below the register's 4096, so the ordinary
  overshoot of a model aiming at a length still fits and costs nothing.
- the **hard limit**, register 4's own, checked in `Summariser.update()`. The
  model is told what it is and is never asked to enforce it.
- on an overrun, a **whole new generation** — not an edit. It is given the same
  material as the first call *plus* the attempt that was too long, and asked to
  write a new summary rather than shorten that one. Asking a model to trim its
  own text to a count is the loop again; asking it to say the same things in
  fewer words, with the long version in front of it as material, is a fresh
  generation with better information. `summary_max_attempts` (3) is how many.
  Only the last failed attempt is shown, not all of them.
- and after the last attempt, **truncation**. A summary that loses its tail is
  worth more than no summary: the oldest facts in it are the ones nothing else
  in the register file still holds. The register file takes the truncation flag
  explicitly, the way register 3 does, because a value cut before it arrived
  fits — and so its length cannot report that anything was lost.

That last rule is about having something to cut, not about how the attempts
ended. A retry that *fails* — the call raises, or comes back empty — with an
over-long draft already in hand truncates that draft rather than throwing it
away, and the step records the error next to the summary it kept. Only a
summariser that produced nothing at all leaves the previous summary standing.

A configuration whose soft target is not actually under the hard limit is not a
soft target at all, so `Config.summary_target()` pulls one back to three
quarters of the register.

### Cheap on purpose

The summariser rewrites a paragraph; it does not decide what to do next. So it
runs with its own settings, and the defaults are the cheap ones:

| | |
| --- | --- |
| `summary_model` | `None` — the run's model, or name a smaller one |
| `summary_effort` | `low` |
| `summary_thinking` | `False` |
| `summary_max_tokens` | `2048` |

Its system message is identical every step, so it caches like the agent's does.

Measured on the same kind of step that produced the loop: **one attempt, ~4s,
~250 output tokens**, against 6 steps, ~150s and ~15,000 output tokens for the
sub-agent it replaces. The 0.0.4 doc predicted "5-6s of the step's 8-10s" and
got 150s of 160s; 0.0.5 actually is what 0.0.4 claimed to be.

### What is unchanged

Everything the register is for. The summariser still sees one step and one
summary and never the history, so its cost per step is flat however long the run
gets — the reason the scaffold exists. It is still told to keep findings,
decisions and dead ends, to leave out narration and anything already one register
away in 0 or 3, and to prefer the older fact when both do not fit. A failed
summary still leaves the old one standing, still records `summary.ok: false` on
the step, and still never costs the agent its memory. The last step of a run is
still not summarised, and a cut-off step still is. `--no-summary` still turns the
whole thing off.

### Its answer is text

There is no response schema any more, because there is no response file: the
reply *is* the register's new value. Only wrapping is stripped — a code fence
around the whole thing — because a model that ignores the instruction and
introduces its summary has said something, and silently deleting its first line
would be guessing which sentence was not meant to count. An empty reply is a
failure and leaves the previous summary alone.

## 2. A scratch directory

Every agent in the failing run reached for `/tmp`, got `Operation not
permitted`, and spent a step finding somewhere else — and then wrote that
somewhere else into the workspace root, where the parent saw `sum_tmp.py` and
`.sumtmp/` in its next `ls` as if they were part of the work.

Each agent now gets `.scratch/<agent_id>/`, made before its first step and named
in its system message. Per agent, because a workspace is shared with everything
spawned into it and scratch in the root is indistinguishable from output.

## 3. Caches inside the workspace

The shell's environment now points the usual cache locations into that scratch
directory — `TMPDIR`, `TMP`, `TEMP`, `PYTHONPYCACHEPREFIX`, `XDG_CACHE_HOME`.

Every one of them defaults to somewhere the firewall denies. The point is not
that the writes would otherwise fail — it is that they fail *loudly*, once per
invocation, into the agent's registers and from there into its summary. Pointing
them at a writable directory makes the sandbox invisible to the toolchain rather
than merely survivable, which is the same argument `SYSTEM_READ` already makes
for reads.

`TMPDIR` is also what makes `/tmp` unnecessary rather than merely denied:
anything that asks the platform for a temporary directory now gets a writable
one.

> **Known gap.** macOS's `xcrun` shim — which `/usr/bin/python3` is — ignores
> `TMPDIR` and uses the Darwin per-user temp directory from `confstr`, so it
> still prints `couldn't create cache file '…/xcrun_db-…'` on every invocation
> under the sandbox. It is cosmetic: the command runs and its output is correct.
> Silencing it would mean allowing a write outside the workspace, which is not a
> trade this version makes. A real interpreter — anything in a venv — is
> unaffected.

## Config

| Field | Default | Meaning |
| --- | --- | --- |
| `summary` | `True` | Keep register 4. |
| `summary_target_chars` | `3000` | Soft target, asked for, under the hard limit. |
| `summary_max_attempts` | `3` | Whole generations spent getting under the limit. |
| `summary_model` | `None` | The run's model unless named. |
| `summary_effort` | `"low"` | |
| `summary_thinking` | `False` | |
| `summary_max_tokens` | `2048` | |

`summary_max_steps` is gone: there are no steps.

## Trajectory

The format goes to **v3**. Two removals, which is what makes it a bump rather
than added fields:

- a step's `summary` no longer describes a sub-agent, so `agent_id`,
  `trajectory` and `steps` are gone from it. What replaces them says what the
  new mechanism actually did: `{ok, summary, chars, truncated, attempts,
  target_chars, limit, model, usage}`, where `attempts` is the character length
  of every generation in order — so a run that keeps overshooting is visible in
  the record rather than only in the clock.
- the header's `summarizer` flag is gone, because no agent is one. A reader
  that treats it as absent-means-false renders v2 and v3 alike, which is what
  the viewer does; old trajectories with real summariser sub-agents in them
  still show their chips and their links.

`timing.summary_s` is unchanged in name and meaning.

## Resuming across the change

`register_layout` stays **4**. 0.0.5 changed *who writes* register 4, not what
it holds, and resume restores values by index — so a 0.0.4 run continues into
this scaffold with no `--upgrade-registers` and no cleared register. A stored
`summary_max_steps` is dropped on the way in, like any config key this scaffold
does not have.

## Not in this version

- **Nothing reads the summary but the model.** Unchanged from 0.0.4: the
  scaffold does not check it, score it, or compare it against the trajectory.
- **The summariser is still synchronous.** It runs between the step's tools and
  the next generation. It is now cheap enough that this costs a few seconds
  rather than minutes, which is why it stays the simple thing.
- **No summary of the summary.** Whatever it drops is gone, save for the
  trajectory.
- **The overrun path is untested against a real model.** The retry and
  truncation rules are covered offline; no live run has yet produced a summary
  over 4096 characters, because the soft target keeps them well under it.
