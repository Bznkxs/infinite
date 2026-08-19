# InfiniteAgent 0.0.7b-simple

0.0.7a's run found the thing that stops a reconstruction, and it is not the
summariser and not the step budget. It is **containers that are too small and a
scaffold that does not say so.**

## What the 0.0.7a run showed

The root wrote nine parts of the spec into its scratch (still: see 7b's spawn
change below), spawned one child at step 8, and the child ran for its whole
500-step budget without ever writing a response.

```
steps 1-65     8 modules written        112 tool calls, 12 of them file writes
steps 66-250   1 module written         341 tool calls, 7 of them file writes
steps 251-500  0 modules written        483 tool calls, 5 of them file writes
                                        464 of those 483 were reads
```

Nine of fifteen modules, 2,115 lines, and then 435 steps that produced nothing.
Zero tool errors in the whole run: it was not stuck on a failure, it was stuck on
a **read**. Steps 401, 402 and 403 each open with the same sentence —

> *I need to add CANVAS_ID to config.py, then move through agent.py, summary.py,
> and main.py* —

and each spends its calls re-reading `config.py` instead of editing it. Across
the last 250 steps it re-read its own modules 124 times (`trajectory.py`), 103
(`tools.py`), 92 (`registers.py`).

**The mechanism.** `sed -n 60,190p config.py` returns about 5,000 characters. The
destination register held **512**. So the agent asked for 130 lines, got the first
tenth of them, concluded it had not seen enough, asked for a different range, got
a tenth again — and the dump's `truncated` tag was not enough to tell it that the
*register*, not the command, was the limit. The full output was in a result file
it never loaded. The canvas — the register sized for exactly this — it had stopped
using: the productive first 65 steps read with `load` into register 32, and the
barren 435 read with `bash sed` into 512-char registers.

## The changes

| | 0.0.7a | 0.0.7b | Why |
| --- | --- | --- | --- |
| register 0 on a truncated result | the dump tags the register | **says what was cut and where the rest is** | The loop above, in the one register the agent always reads. |
| `max_register_length` | 512 | **1024** | A `sed` of a source file is thousands of chars; 512 showed a tenth. |
| `max_special_length` | 4096 | **6144** | The summariser writes what the material needs — 4,100-5,000 chars whatever budget it is told — so 4096 bought a second generation on 274 of 500 steps. |
| `spawn` prompt / description | "shares this workspace's files" | **"brief it with paths and line ranges rather than copying material into the prompt"** | 0.0.7a's root still transcribed 108KB of spec to brief its child, because nothing said the child could read the file itself. |

### What register 0 now says

```
tool_output/01a1caa5-step402-0817-bash.json
CUT: 5231 chars, register 7 kept 1024. You are not seeing all of it — for the
rest use the canvas (register 32, 20000), or load the file above. Re-running the
command shows no more.
```

Short on purpose: register 0 is a normal register and the notice has to survive
its own limit, so the result-file path stays first and the sentence that follows
is the shortest true statement of what happened and what to do. On the canvas
itself — already the largest register — the remedy is `load(start=N)` instead.

The budget-versus-length lesson from 0.0.6 also finished arriving here. 0.0.7a
lowered `summary_target_chars` to 2400 and the retry rate went **up** (55% of
steps, against 26% at 3000): the number in the prompt does not control the length
of the summary, the material does. So 0.0.7b stops arguing with the model and
gives the register the room the summaries actually need.

## Not in 0.0.7b

- **Nothing that detects the loop itself.** The scaffold still cannot see that
  three consecutive steps had the same intention; it only tells the truth about
  truncation and leaves the noticing to the agent. If 0.0.7b's run loops again
  with the notice in front of it, that is the next letter's problem.
- **`spawn` is still synchronous**, `max_depth` is still 1, and the summariser is
  unchanged apart from the register it writes into.
