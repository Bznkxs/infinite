# InfiniteAgent 0.0.7g — the context, compressed

0.0.7f-short reached 10,000 tokens a generation by shrinking the registers. It
then failed at the reconstruct task, and while it was failing it made the case
for this letter: **46% of everything the model was sent was the scaffold talking
about itself**, and none of that had ever been counted.

0.0.7g brings one whole generation under **8,000 tokens** — 7,802 measured with
the API's own tokeniser — by cutting the fixed half rather than the working
space. Every rule of every earlier letter is still stated. What is gone is the
second sentence that explained the first.

## What the series had done to the context

Every run stored its system message and tool schemas verbatim in its trajectory
header, so this is measured, not reconstructed:

| version | sys+tools | max dump | max in | out cap | max total |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0.0.6 | 4,228 | 16,927 | 21,155 | 8,192 | **29,347** |
| 0.0.7a | 4,358 | 16,927 | 21,285 | 16,384 | **37,669** |
| 0.0.7b | 4,424 | 25,283 | 29,707 | 16,384 | **46,091** |
| 0.0.7d | 4,568 | 25,283 | 29,851 | 16,384 | **46,235** |
| 0.0.7f | 5,017 | 25,283 | 30,300 | 16,384 | **46,684** |
| **0.0.7g** | **3,361** | 2,576 | 5,933 | 1,920 | **7,853** |

Two thirds of the growth was one letter's registers (0.0.7b) and one letter's
output cap (0.0.7a). The five paragraphs of hard-won advice cost 789 tokens of
the 17,337 the series added: **the arguments were cheap and the containers were
not.**

## The changes

### 1. A scaffold that knows what a step costs

`Config.dump_chars` is the largest dump a geometry can produce — every register
at its limit, plus the header line each one always emits. `Config.context_tokens`
adds the fixed half and the output cap, which is the number a generation is
actually bought by. Every agent computes it at construction, logs it, and records
it in its trajectory header:

```
agent 34eede3b: one generation is up to 7983 tokens (6063 in, 1920 out)
```

`max_context_tokens` (None by default, which is what every earlier version was)
makes it a ceiling, checked before the run starts rather than discovered in a
bill. It has already refused three configurations of mine, each over by a margin
I had miscounted — once because I forgot the firewall paragraph is part of every
request, once because 0.0.7h's new `spawn` parameter is too.

Estimating uses **2.6 chars a token**, measured over 580 steps of the 0.0.7f run
and again against this letter's denser prose. It errs high by about 1.5%: the
short configuration estimates 7,983 and counts 7,802.

### 2. The prose, halved

| | before | after |
| --- | ---: | ---: |
| system message | 2,448 | **1,742** |
| tool schemas (`spawn` alone was 634) | 1,547 | **1,291** |
| firewall paragraph | 590 chars | **423 chars** |

Nothing was dropped: the twenty-four rules the system message states are all
still in it, and each tool still carries the guidance its letter added — brief a
child with paths, never ask it for a length, several spawns run at once.

### 3. The target and the summary stop sharing a limit

`max_target_length` splits register 2 from register 4. They are the same tier and
different problems: the agent writes its own target and can be brief on purpose,
while the summariser writes what the material needs and *cannot* hit a length by
generating — 0.0.5's lesson, and the thing that decides how much room register 4
needs. At this scale the split is worth 768 characters, which is most of a canvas
page.

The summary register is 1,536 against a 600-char budget because the first short
run measured the overshoot: at 768 the summariser went over on **all sixteen**
attempts it made in two minutes (812–1,082 chars), and at 1,280 it still retried
one step in eight. This is 0.0.6's lesson at small scale — the budget in the
prompt does not set the length, the material does — and 0.0.7b's remedy: give the
register room for the overshoot instead of arguing with the model about it.

## The configuration

```
11 registers: 0-4 special, 5-9 the agent's, 10 the canvas
normal 208        target 704        summary 1,536      register 3 halves 240
canvas 1,536      output 1,920      summary budget 600, 512 tokens
```

46% of the budget is still the fixed half. **A small-context scaffold is mostly
its own system message**, and that is the finding this configuration exists to
expose: below about 6,000 tokens there would be no room left to work in without
saying less than the scaffold has learned to say.

## What it showed

On published long-context benchmarks, at this ceiling: **18 of 18**. BABILong
from 245KB to **39.4MB** — 15/15, including three-fact chaining, relational and
yes/no/maybe splits — and ∞Bench's whole-novel multiple choice 3/3. The step
count barely moves with length: six to seventeen steps whether the corpus is a
quarter of a megabyte or thirty-nine. One SWE-bench Verified instance
(`pallets__flask-5014`) fixed in 29 steps, graded by held-out tests.

Against that, **building** a large artifact at this size is where it struggles:
two reconstruct runs lost nine children to their step bounds without producing a
package. Reading an arbitrarily large corpus and writing an arbitrarily large one
are not the same problem, and 0.0.7h is about the second.
