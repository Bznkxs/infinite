# InfiniteAgent 0.0.7j — a child's steps are the run's steps

Five reconstruct runs, at four different context sizes, have all opened the same
way: the root commissions a document about the specification before writing any
code. 0.0.7a told it that copying source material buys nothing. 0.0.7d showed it
its step budget. 0.0.7f made children cheap to bound and quick to run in
parallel. It has never once changed the opening move.

This letter is about why the advice cannot land, and it is not about the advice.

## What the agent could see

The 0.0.7i root, at its seventeenth step, had spawned two children who had spent
**124 steps between them** on a spec digest and a checklist of the root's own
instruction. What its context said was:

```
[Step] step 17 of 500 (484 left, including this one)
```

**A parent's counter moves by one however many steps its child spends.** From
where the root sits, delegating a hundred-step digest and running one `grep` are
the same price. The scaffold has been asking an agent to economise on a resource
it shows it only a twentieth of.

## The change

One clause on the line 0.0.7d added, and only when there is more than one agent
in the run:

```
[Step] step 17 of 500 (484 left, including this one); this run has spent 141 steps across 3 agents
```

The workspace already exists to be shared by an agent and everyone it spawns, so
it is what counts: every step of every agent, and how many agents have taken
one. Concurrent children make it a number that moves under the parent's feet,
which is honest — that is what a fan-out does.

Forty characters a step, and the parent can finally see the bill it is signing.

## The other end of the same line

A child of the 0.0.7i run ran out of steps twice. The second time, its own
summary said:

> *WP3: `infinite_agent/tools.py` fully implemented. Public API: ToolResult,
> tool_schemas(config), ToolDispatcher. DONE: all imports; JSON schemas
> (bash/load/set/set_target/spawn)…*

417 lines, finished, and no response file — so the scaffold reported it as
having produced nothing. That is the fourth child today to spend its last step
working and die with the deliverable on disk and the ceremony undone, each of
them on a step that opened *"with only two steps remaining"*.

The count was already in the dump. What it never said was what the count meant:

```
[Step] step 38 of 40 (3 left, including this one) — write your response file NOW, or this work is reported unfinished
```

Three steps from the end, and only when there is an end. It is the same argument
as the clause above — the agent could see the number and not the consequence —
and it costs nothing on any step that is not nearly the last.

## Not in 0.0.7j

- **Nothing refuses a delegation.** The parent can still spend the run on
  digests; it now knows that it is.
- **The child cannot see it either** — it gets the same line, and for a child
  the number is mostly its parent's history. Whether a child should see what its
  siblings are spending is a question this letter does not answer.
- **Nothing says what the steps bought.** The scaffold counts steps, not lines
  of code or files written, and a run that spends 124 steps well looks exactly
  like one that spends them on a checklist.
