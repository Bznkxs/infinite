# InfiniteAgent 0.0.8a — the registers are write-only

*A design letter rather than a result, and the first of two. [Depth, Volume and
Width](Depth,%20Volume%20and%20Width.md) closed the 0.0.7 series with a
diagnosis — a fixed context is defeated by width, not by size — and named five
things to build. This letter is about the register file and the tools that
reach it. The other half, how a model operation is kept narrow in the first
place, is [0.0.8b](InfiniteAgent%200.0.8b.md).*

---

## 1. The defect

There is a path from the world into a register. `bash` puts a command's output
in one and the model generates not a character of it; `load` does the same for a
slice of a file. Going the other way — *using* what a register holds — there is
exactly one route: the model reads the value out of the dump and types it again
into its next generation. Register to shell command, register to register,
register to a child's brief: all three are re-generation.

So a register is a place values arrive and are read **by the model**, and never
by anything else. It is a display, not a memory. That is the whole of the
problem, because a display is held by the context, and the agent-controlled
context is 1,261 tokens.

The machine the name is borrowed from does the opposite. `ADD R1, R2, R3` names
three locations; the values never enter the instruction. Here every instruction
carries its operands as literals, which is why forty facts cost forty places in
the context rather than forty *names*.

## 2. What indirection can buy, and what it cannot

Three things consume a register's value, and only two of them can be served by
naming instead of copying.

| consumer | can indirection serve it | mechanism |
| --- | --- | --- |
| the shell | yes | `$R5`, `reg/5` |
| another tool's argument | yes | argument-by-path |
| **the model's own reasoning** | **no** | — |

`step_loop.py` failed in the third row. The model had to *reason with* forty
signatures while generating code, and a fact you think with is a fact you see.
Nothing in this letter touches that; it is 0.0.8b's subject.

What indirection does buy is two other things, both real:

- **transit** — every value that moves currently costs output tokens and a
  chance of corruption, in a scaffold whose writing rate is its bottleneck;
- **the working set** — §4, which is where the surprise is.

This letter should not be read as a fix for width. It is a fix for a scaffold
that is *spending* width on clerical work.

## 3. One mechanism instead of six: registers are files

The obvious shape is a family of tools — `get_register`, `set_register`,
`copy`, `deref`, `pass-register-as-argument`. The cheaper shape is a directory.
Sync the register file to `reg/0 … reg/N` around every `bash` call and export
`$R0 … $RN` into the persistent shell; read them back afterwards and apply the
length limits, tagging `truncated` exactly as `store` does today.

```sh
grep -n "$R5" src/*.py             # register → command
cp reg/5 reg/6                      # register → register
sed -n '1,40p' "$R5" > reg/6        # r5 holds a path: its content into r6
rg -o '^def \w+' src/*.py > reg/6   # computed → register, nothing generated
```

Copy, deref-copy, discarding a result, writing a register from a computation:
all of it is the shell, and it costs one sentence of system message rather than
four tool schemas. Registers 0–4 stay the system's — the files are read-only and
a write to one is refused on sync-back, the way `check_destination` refuses it
now.

`set` survives this, and the distinction is worth keeping: a shell redirect
moves a value that already exists somewhere, while `set` writes a value the
model is the author of — a plan, a note, a decision. The first is transit and
should never pass through a generation; the second is not transit at all.

### An alternative that was considered and dropped

If bash is the way registers are addressed, a new capability could ship as an
executable on `PATH` rather than as a tool schema — 7.1's `lookup` becomes an
`idx` command, and costs nothing on a step that does not call it. That is
attractive against 7.4, where the fixed prose is already 43% of the request and
every tool added to answer width makes width worse.

It is dropped on a rule that is worth stating generally: **a determined action
with a fixed argument shape is a tool; a recommendation about how to work is a
sentence in the system message.** A model given a schema uses it and is
validated against it; a model given a command has to discover it and gets its
errors back as shell noise. `lookup` is a determined action, so it is a tool.

The honest accounting, then: registers-as-files adds a sentence and removes no
schema, and `lookup` adds a schema. The fixed constant grows. That is a
deliberate trade — width is what is binding — and 7.4's instruction to make the
trade *explicitly* is satisfied by saying so here.

## 4. The destination register is eating the working set

Every tool call must name a destination, and the write is unconditional. There
are five free registers at 0.0.7g's geometry. A five-call step — precisely what
0.0.7e's batching advice asks for — overwrites all five.

**The scaffold tells the agent to batch and charges it its entire memory for
complying.** A step that reads four files and runs one command has, by the time
it is over, nothing left holding anything it knew before.

So 7.2, "pinned registers", needs nothing added. It needs something removed:

> `register_id` becomes optional. Omitted means the payload is discarded — the
> status still lands in register 0, the full text is still in the result file
> and the trajectory.

Any register the agent then declines to name is pinned by construction, and the
agent decides which. The mechanism 7.2 asks for is the *absence* of a forced
write.

## 5. The gap is smaller than the measurement suggested

The agent-controlled space at 0.0.7g:

| | chars |
| --- | ---: |
| canvas | 1,536 |
| five free registers | 1,040 |
| target | 704 |
| **total** | **3,280** |

Forty signature lines at ~60 characters is **~2,400** — it fits, given
line-granular retrieval and a scaffold that stops clobbering registers. But the
canvas alone holds twenty-five of them, so a working set cannot land in one
place, and one split across six registers that tool calls overwrite is not one
an agent will commit against.

The distance to close is therefore a factor of about 1.5, not the factor of 16
that the raw comparison with 0.0.7f implies. It argues for a canvas nearer 2,560
or 4,096 in this series, and it says the changes above are worth more than any
amount of extra context.

Two caveats on that number. It is the width of *one* decision, not of a run —
0.0.8b's whole argument is that forty is already too many to want live at once.
And it assumes the forty are one line each, which is 7.1's job and not this
letter's.

## 6. What 0.0.8a does not propose

- **Sequential tool calls with result-passing.** Pipes and `$()` already do
  this, better and with no schema. The one case the shell cannot cover is
  `spawn`, whose prompt no command can build — that is answered by argument
  **by reference** (`prompt_file`), which also removes the length limit on a
  brief, and not by a templating ABI over every argument.
- **Anything that hides what ran.** If register 3 shows `grep "$R5" …` and the
  dump does not show what `$R5` held, the agent has lost the plot. Substitution
  must stay visible in the action half.
- **A fix for width.** §2.

## 7. Open questions

1. **Does transit actually cost anything measurable?** The scaffold can count
   it: output tokens spent on literals that already existed verbatim in a
   register. If the answer is "not much", §3 is justified by §4 alone.
2. **Where does `reg/` live?** Inside the workspace it is discoverable and
   deletable by the agent's own `rm`; in the per-agent scratch directory it is
   safe and has to be named by an environment variable. The second is probably
   right and costs one more sentence.
3. **Does the canvas want to grow?** §5 says a working set has to land in one
   register to be committed against. 7.6's bisection should be run on the canvas
   specifically, not on the whole geometry.
