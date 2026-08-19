# InfiniteAgent 0.0.8b — precise at the frame, lossy above it

*The second of two design letters. [0.0.8a](InfiniteAgent%200.0.8a.md) is about
moving values without a generation; this one is about the quantity that
[Depth, Volume and Width](Depth,%20Volume%20and%20Width.md) says a fixed context
is actually defeated by — the number of facts that must be true at once — and
about the only thing that reduces it, which is not a bigger register.*

---

## 1. Two kinds of operation

The machine metaphor has been carrying an ambiguity, and it is worth settling
before anything else.

| | input and output | bounded by |
| --- | --- | --- |
| **machine operation** | a `grep` over 39MB; a test run; a file rewritten | need, and nothing else |
| **model operation** | one generation | what can be true at once |

The scaffold should put **no** restriction on the first. Depth and volume are
already answered — paging reads any corpus, steps write any file — and a limit
on what bash may pass or produce would be a limit invented by the scaffold
rather than found in the work.

The second is the whole subject. The ALU comparison is about model operations
only: at any generation the model should be holding a small, bounded set of
precise facts, and the way to make that true of a large task is not to compress
the task but to arrange that only a small part of it is ever live.

## 2. The invariant

At any model call the context should hold:

- **one active goal**, stated precisely, with somewhere to put its result;
- **accurate references** for that goal — how to name the things it touches, not
  what they contain;
- **a lossy compression of everything above it** — why we are here, what the run
  is for;
- **nothing at all about what is below it or beside it**.

Ten questions about one text is the clean case: keep the path to the question
file and one question — *what is the name of Amy's dog* — find it, write the
answer, take the next. Nine questions are on disk and none of them is in the
context.

The entangled case has the same shape and is only less obvious. "Write this line
of code; it calls into six modules" is the lossy statement of the goal, and it
is enough to act on. The precise part is the six *names*, and even those are not
needed together: they are resolved one at a time, and each resolution is a small
question with a small answer.

### Why the lossiness runs upward and not downward

This is the part that makes the invariant safe rather than merely economical.

A lossy memory of the global goal produces a **wrong subgoal** — visible on
return, catchable by the frame that asked for it, cheap to redo. A lossy memory
of a signature produces **code that parses and is wrong**, and nothing catches
it until much later, if at all.

So precision belongs where the decision is, and compression belongs where the
context is. Push lossiness up, push precision down.

## 3. A stack, not a plan

An earlier draft of this proposed a *work list*: decompose the task into N
operations up front, keep the list on disk, keep `(path, index)` in a register.
That is wrong, and it is wrong in exactly the way the letter is about —
enumerating two hundred operations requires holding the shape of the whole task,
so **the decomposition would itself be the widest operation in the run**.

A queue needs global knowledge. A stack needs only the current frame and how to
return. So the decomposition is not planned; it is *discovered by descent*, and
the only thing that has to persist is the path back.

Worked, on the line that six modules made impossible:

```python
dump = registers.render(step=n, max_steps=m, run=workspace.spent())
```

| frame | goal | what is precise here |
| ---: | --- | --- |
| 0 | implement `run_step` | the file to write; the loop's job, lossily |
| 1 | emit the line that produces the dump | which module renders a dump — a search |
| 2 | `RegisterFile.render` — parameters? | one signature line |
| 3 | what does `run=` want | one signature line, `workspace.spent` |

Pop, pop, pop; the line is written; the file on disk holds it and the context
does not. Forty facts are still used over the course of the file. Three are ever
live.

This is the stack mode of [Design Tests (Top
Down)](Design%20Tests%20(Top%20Down).md), and the depth of the stack is
unbounded while the width of the context is constant. It is also the honest form
of the Turing-machine argument in §6 of the width letter: the tape is the frames,
and what grows with complexity is steps.

## 4. A stack does not remember what descent already resolved

The 150-step child made **345 tool calls, almost all reads**, and wrote nothing.
That is descent without memory of its own descent: a stack says where you are,
not what you already know, and a fact resolved at frame 3 and popped is gone.

So the stack needs a companion — a store of resolved facts, addressed by name,
appended when a lookup resolves and consulted before descending. One line in,
one line out, and `grep` is the whole of the query.

This is the artefact five runs kept reaching for. Every one of them opened by
writing a digest of the specification, against the scaffold's advice, and it has
been read here as avoidance and then as the model's answer to width. It is
neither: it is a **memo table in the wrong form** — prose, written once, read
whole — when what the work wants is a table written incrementally and read by
key.

It sits next to 7.1 rather than replacing it. `lookup` is the same table
maintained by the scaffold from an AST walk; the agent's own store holds what an
AST cannot know — that a return is `None` on cut-off, that a parameter is
keyword-only by convention, which of two plausible functions is the one this
project uses.

## 5. Depth costs reliability, so every pop needs a check

Descent converts width into depth, and depth compounds. N operations at
per-operation failure probability p all succeed with (1−p)^N: two hundred
operations at one percent is thirteen percent.

So a frame cannot resolve as *(goal → result)*. It has to resolve as *(goal →
result → check)*, and the check has to be a **machine** operation — an import, a
type checker, one test — because a check performed by the model against its own
lossy recollection is the failure it is meant to catch. §1 is what makes this
affordable: checks are unbounded and free of width.

This is 7.3 arriving from the other direction. Acquiring forty facts up front is
one way to be right; being corrected on the two that were wrong is the other,
and only the second one fits.

## 6. What the caller should write, and when

There is a good consequence hiding in the frame discipline.

0.0.5's complaint about the summariser is that it is "a model that cannot be told
what to keep": it rewrites register 4 after every step from material it has no
stake in, and the run's memory of itself is therefore second-hand and
undirected. At a stack frame the problem disappears, because **the return
context is written by the caller at push time**, not reconstructed by a
summariser at pop time. The frame that descends is the one thing in the run that
knows exactly what it will need when it comes back — it is about to stop knowing
everything else.

That is a better mechanism than a summariser for anything that is a descent, and
it costs one write on the way down.

## 7. What the scaffold would have to provide

Small, and mostly already present:

1. **Somewhere for the stack** — a file, and a register holding its path and the
   current depth. Push and pop are determined actions with fixed argument
   shapes, so by 0.0.8a's rule they are tools rather than conventions.
2. **The resolved-facts store**, plus 7.1's `lookup` beside it.
3. **The invariant, as a sentence in the system message** — a recommendation
   about how to work, so not a tool.
4. **A check at every pop**, which is bash and needs nothing built.

Note what already exists: `spawn` is a frame. It gives the callee a fresh
context, its own budget and a schema-shaped return, and the parent's registers
survive the call. What it does not give is *cheapness* — a whole agent, its own
summariser, a JSON contract — and a return that lands anywhere but the parent's
next step.

## 8. Open questions

1. **Is `spawn` the primitive, made cheap, or is an in-agent frame needed?**
   Answered in [0.0.8c](InfiniteAgent%200.0.8c.md): `spawn` is the frame, and
   what it lacked was a brief a lossy caller could write, a check it could be
   judged by, and a price its caller could see. No in-agent frame.
2. **When to descend and when to commit?** Also answered there — descend at a
   *working-set boundary*, when the subgoal needs facts you do not have and you
   will not need its facts once it returns. The observed failure was
   over-descent, and a stack makes descent cheaper; the counter-force is that a
   child's steps debit its parent's budget.
3. **Who states the top frame?** A task arrives as prose. Turning it into a goal
   with somewhere to put the result is itself a model operation, and possibly a
   wide one.
4. **Does the memo store want to be the target register?** It is the one place
   that survives untouched today, and 0.0.8a's optional destination would give
   it siblings. Or it is a file and only its path is held — which is the whole
   argument of 0.0.8a applied to this letter's artefact.
