# Evaluating InfiniteAgent on public benchmarks

The reconstruct task measures one job in depth. This measures the claim itself,
on benchmarks whose ground truth someone else established: **can a fixed, small
active context do work whose material is arbitrarily larger than it?**

Everything here runs the shipped CLI as a subprocess — the harness has no way to
reach inside the scaffold, so what is measured is the thing that ships.

```bash
uv run python -m eval.run babilong --config 1M --split qa2 -n 1 --profile short
uv run python -m eval.run infinitebench --config longbook_choice_eng -n 3
uv run python -m eval.run swebench -n 5 --profile short
uv run python -m eval.run --report
```

`--profile short` is 0.0.7g's geometry: **7,802 tokens for a whole generation**,
input and output together. `--profile full` is 0.0.7f's 46,684.

## The benchmarks

| | source | material | graded by |
| --- | --- | --- | --- |
| **BABILong** | `RMT-team/babilong` | bAbI facts hidden in a PG-19 novel, 0k to **10M tokens** | the gold string appears in the answer (the benchmark's own metric) |
| **∞Bench** | `xinrongzhang2022/InfiniteBench` | whole novels, ~1MB each | the chosen option, or overlap with the reference |
| **SWE-bench Verified** | `princeton-nlp/SWE-bench_Verified` | a real repository at a real commit | the held-out `FAIL_TO_PASS` and `PASS_TO_PASS` tests |

Nothing needs credentials: the rows API serves what fits, the giant
configurations come from a range request over the raw file (one 10M-token
BABILong record is 37MB inside a 4GB file), and ∞Bench's hundreds of megabytes
are read as a prefix.

## Results at 7,802 tokens a generation

| benchmark | n | correct | avg steps |
| --- | ---: | ---: | ---: |
| BABILong (64k → 10M) | 15 | **15/15** | 11.3 |
| ∞Bench, whole-novel multiple choice | 3 | **3/3** | 10.3 |

```
64k  qa1  245 KB   8 steps      512k qa1  2.1 MB  11 steps
128k qa2  494 KB  17 steps      1M   qa3  3.7 MB  13 steps   (three chained facts)
1M   qa5  3.7 MB  16 steps      1M   qa10 3.7 MB   9 steps   (indefinite knowledge)
10M  qa2  39.4 MB 17 steps      ← 5,000× the context, in 172 seconds
```

The step count barely moves with the corpus. That is the whole claim, stated as
a measurement: **the context does not have to grow with the material.**

## The same instances at both ceilings

The obvious objection to any of this is that the large configuration succeeds
because it is large. So the same instances were run at 46,684 tokens and at
7,802:

| instance | 46,684 tokens | 7,802 tokens |
| --- | --- | --- |
| BABILong 1M qa2 (3.7MB) | ✅ bedroom, 6 steps | ✅ bedroom, 19 steps |
| ∞Bench free-form QA #0 | ✅ Peyton, 5 steps | ✅ Peyton, 10 steps |
| ∞Bench free-form QA #1 | ❌ "Cael" | ❌ "Cael" — the same wrong answer |

Same outcomes, **including the same mistake**, at a fifth of the context and two
to four times the steps. Where the small configuration fails, the large one
fails identically, which locates that failure in the model's reading rather than
in the size of its context.

One number that surprises: the small profile spends *more* total tokens (83k of
input against 34k for the same BABILong instance), because it pays the fixed
half of the request again on every one of its extra steps. A small context is
not a cheap context; it is a context that does not grow.

## Reading is not writing

The benchmarks above all read a great deal and answer briefly. The reconstruct
task is the other shape — read a 114KB specification, write a 5,500-line package
— and there the two configurations are not equivalent at all:

| | input | output | lines of code per step |
| --- | ---: | ---: | ---: |
| 0.0.7f | 30,300 | 16,384 | **9.5** |
| 0.0.7g/h | 6,063 | 1,920 | **1.3** |

Writing throughput tracks the output cap almost exactly, and no amount of paging
substitutes for it: 5,500 lines is about 70,000 output tokens however it is
sliced. Reading throughput does not — more steps absorb a longer corpus
gracefully.

They are separate resources, and it is the *input* that carries the attention
cost a long context is criticised for. `--wide-output` is the configuration that
follows — the same 6,063-token input, an 8,192-token generation — and it writes
at **10.3 lines a step**, which is 0.0.7f's rate at a fifth of 0.0.7f's input.
The active context was never what bounded writing.

## The SWE harness, and why it is restricted

`pallets__flask-5014` passed at the short profile: a real bug, 29 steps, graded
by tests the agent never saw. Getting there meant fixing the harness six times,
each fault found by applying the **gold patch** and checking the grader called it
a pass — the only evidence that a grader measures the agent rather than itself.

| symptom | cause |
| --- | --- |
| no tests collected | pytest resolved rootdir to the *outer* project |
| `monkeypatch.notset` missing | pytest 8 against a 2023 conftest |
| `ast.Str` deprecated | Python 3.13 against a 2023 pytest |
| `werkzeug.__version__` missing | an undeclared transitive pin |
| setuptools unsatisfiable | the date bound had pinned the build backend too |
| "no module named pytest" | an install can succeed and leave no test runner |

What works without Docker: the interpreter chosen from the commit's year,
dependencies resolved with `uv --exclude-newer <commit date>`, build tooling
exempt from that bound, and the files the test patch touches reset to the base
commit before it is applied — so an agent that edits tests gains nothing, and
grading is idempotent.

Instances created before **2022** are refused with the reason stated. A 2013
environment cannot be rebuilt from PyPI at any interpreter this harness can
install; that is what the official per-instance images are for, and pretending
otherwise would produce failures that say nothing about the agent.

## What this does not measure

- **Long dialogues.** LoCoMo and LongMemEval are the obvious targets and the
  scaffold does not take turns yet.
- **Writing something large.** Every task here reads a lot and answers briefly.
  The reconstruct task is the other shape, and at 8,000 tokens it is where the
  scaffold struggles — see [0.0.7h](InfiniteAgent%200.0.7h.md).
