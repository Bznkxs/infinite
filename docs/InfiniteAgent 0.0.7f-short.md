# InfiniteAgent 0.0.7f-short

> **Superseded by [0.0.7g](InfiniteAgent%200.0.7g.md)**, which reaches 8,000
> tokens by compressing the fixed half of every request instead of the
> registers. This letter's own run failed the reconstruct task: five children
> ran out of steps writing and re-reading a 115KB blueprint, and 936 lines of
> the package existed after four hours. What it established — the accounting
> below, and that the summariser's register has to hold its overshoot — is what
> 0.0.7g was built from.

The premise of this project is a **fixed-size active context**: everything else
goes to disk and the agent keeps a reference to it. Seven letters of 0.0.7 made
the runs better, and nobody ever added up what they had done to that context.

This letter adds it up, and then builds the configuration that honours the
premise: **one whole generation — everything sent plus everything generated —
under 10,000 tokens.**

## What the series did to the context

Every run in the series stored its system message and tool schemas verbatim in
its trajectory header, so this is measured rather than reconstructed. "Max in" is
the fixed half plus the fullest register dump the geometry can produce, counted
with the API's own tokeniser; "max total" adds the output cap.

| version | sys+tools | max dump | max in | out cap | max total |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0.0.6 | 4,228 | 16,927 | 21,155 | 8,192 | **29,347** |
| 0.0.7a | 4,358 | 16,927 | 21,285 | 16,384 | **37,669** |
| 0.0.7b | 4,424 | 25,283 | 29,707 | 16,384 | **46,091** |
| 0.0.7d | 4,568 | 25,283 | 29,851 | 16,384 | **46,235** |
| 0.0.7e | 4,732 | 25,283 | 30,015 | 16,384 | **46,399** |
| 0.0.7f | 5,017 | 25,283 | 30,300 | 16,384 | **46,684** |
| **0.0.7f-short** | 4,479 | 2,766 | 7,245 | 2,560 | **9,805** |

Where it went, letter by letter — input and output only:

| letter | the model's input | the model's output |
| --- | --- | --- |
| 0.0.7a | +481 chars of system message; `spawn`'s schema no longer sent at the depth floor (−700 chars for a leaf) | **8,192 → 16,384**, the only output change in the series |
| 0.0.7b | registers 512 → 1,024 and the wide pair 4,096 → 6,144: the dump ceiling 49,085 → 68,029 chars, **+8,356 tokens**; the truncation notice when it fires; +223 chars of `spawn` description | — |
| 0.0.7c | nothing — retries and backoff never enter the context | — |
| 0.0.7d | `[Step] N of M`, the first line of every dump (~50 chars); +478 chars of system message | — |
| 0.0.7e | +531 chars of system message: the batching paragraph | — |
| 0.0.7f | +193 chars of system message, +809 of tool schemas (`spawn`'s description and `max_steps`) | — |

Two thirds of the growth is one letter's registers and one letter's output cap.
The prose — five paragraphs of hard-won advice across five letters — is 789
tokens of the 17,337 the series added, which is worth knowing: **the arguments
were cheap and the containers were not.**

## The change: a scaffold that knows what a step costs

`Config.dump_chars` is the largest dump a geometry can produce — every register
at its limit, plus the header line each one always emits. `Config.context_tokens`
adds the fixed half and the output cap and gives the number a generation is
actually bought by. Every agent computes it at construction, logs it, and records
it in its trajectory header:

```
agent 3024a05a: one generation is up to 9887 tokens (7327 in, 2560 out)
```

`max_context_tokens` (None by default, which is what every earlier version was)
turns that number into a ceiling, checked before the run starts rather than
discovered in a bill. It earned itself immediately: the first 0.0.7f-short
workspace was refused at 10,039 tokens, because the fixed half of a request is
13KB of prose and JSON whatever the geometry says, and the arithmetic that
missed it was mine.

Estimating uses **2.8 chars a token**, measured over the 580 steps of the 0.0.7f
run — prose runs about 3.1, tool JSON about 2.6, and a dump of source and paths
2.53. It errs high by about 1%: the short configuration estimates 9,887 and
counts 9,805.

## The configuration

```
11 registers: 0-4 special, 5-9 the agent's, 10 the canvas
normal 224          target and summary 1,280      register 3 halves 256
canvas 2,048        output 2,560                  summary budget 600, 512 tokens
```

Nothing about the mechanism changes — five tools, five special registers, the
summariser alongside the next generation, children of one step run at once and
bounded, the firewall, resume, trajectory v3. Only the room.

Two of these numbers were set by the run rather than by arithmetic:

- **The summary register is 1,280 against a 600-char budget.** At 768 the
  summariser went over on all sixteen attempts it made in the first two minutes
  (812–1,082 chars). That is 0.0.6's lesson at small scale — *the budget in the
  prompt does not set the length, the material does* — and the fix is the one
  0.0.7b made: give the register room for the overshoot rather than argue with
  the model about it.
- **The output cap is 2,560 and the canvas 2,048**, because the fixed half is
  4,479 tokens: 46% of the whole budget is spent before a single register. A
  small-context scaffold is mostly its own system message, and that is the
  finding this configuration exists to expose.

## What it is for

The 0.0.7f run reconstructed this scaffold in 2h43m with 46,684 tokens a
generation available to it. The question 0.0.7f-short asks is whether the
scaffold was doing that, or whether the context was: at 9,805 tokens a step must
write about fifty lines instead of four hundred, the canvas shows fifty lines of
a file instead of five hundred, and the run's whole memory of itself is 1,280
characters.
