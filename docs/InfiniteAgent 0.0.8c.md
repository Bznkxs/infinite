# InfiniteAgent 0.0.8c — the brief is the frame

*The third design letter of the series. [0.0.8a](InfiniteAgent%200.0.8a.md)
moves values without a generation; [0.0.8b](InfiniteAgent%200.0.8b.md) says a
model operation should be precise at one frame and lossy above it. This letter
is about the mechanism that already implements a frame and does not yet behave
like one — `spawn` — and it settles 0.0.8b's first two open questions.*

---

## 1. `spawn` is already a frame

It gives the callee a fresh context, its own step budget and its own trajectory;
it gives the caller a schema-shaped return and leaves the caller's registers
standing. That is a call. Nothing else in the scaffold is.

What it does not do is behave like one, and the reason is a single structural
mistake:

> **The parent is asked to author a precise instruction out of a lossy context.**

Knowing what a child will need is knowledge of the child's subtree. The parent
does not have it, and by 0.0.8b's invariant it should not — it is the frame
above, and the frame above is the lossy one. So the `prompt` field asks for
something the caller is constitutionally unable to supply, and briefs come out at
one of the two extremes that produces:

| | what it looks like | what it costs |
| --- | --- | --- |
| over-specified | 0.0.6's 42KB contract document | the parent does the child's work, in prose |
| under-specified | one vague paragraph | the child re-derives everything, from nothing |

Five runs of spontaneous digest-writing are the same reflex at the root: an
agent trying to manufacture the precision its brief did not carry.

## 2. A brief should name, not describe

Everything a parent *can* state precisely from a lossy context is a **name**: a
goal, some paths, an output location, a command that decides whether the work is
done. Everything it cannot state is method. So the field that asks for prose
should be replaced by fields that ask for names:

```
spawn(goal:   "implement run_step",
      read:   ["src/registers.py", "notes/api.md#run_step"],
      write:  "src/step_loop.py",
      check:  "python -c 'import step_loop'",
      return_schema: {...},
      max_steps: 40)
```

That brief *is* the frame of 0.0.8b §3 — goal, references, somewhere to put the
result, and how the pop is judged — and every precise thing in it is a name the
parent already holds.

Two things this must not become:

- **`read` is a pointer set, not a permission set.** The child may read anything;
  the list is where to start. If the parent's lossiness became the child's wall,
  the invariant would be inverted — the frame above would be deciding what the
  frame below is allowed to know.
- **`goal` is not a specification.** It is one sentence. Anything longer wants to
  be a file, and 0.0.8a's argument-by-reference (`goal_file`) is how it gets
  there without passing through the parent's generation.

The cost is not free and should be stated: `spawn` was already 634 of 0.0.7g's
1,547 schema tokens, the single most expensive thing in the fixed constant, and
this adds fields to it. It is paid for by the prose it stops the parent
generating, and that trade should be measured rather than assumed.

## 3. The check is what makes a lossy caller safe

The reason a parent can be vague about method is that it is exact about
**acceptance**. `check` is a command; the scaffold runs it at pop; a return that
fails it is not a return. Correctness then rests on neither the parent's
recollection nor the child's self-report — the two lossy parties — but on the
machine, which is a machine operation and therefore free of width (0.0.8b §1).

This is 7.3 made structural instead of advisory, and it is also what stops a
frame written at push from silently rotting by the time it pops: the workspace
may have moved underneath it, and the check is what notices.

`check` is therefore **required, with an explicit opt-out**: `check: "true"`
passes trivially and is a decision the parent has to type. A field that may be
omitted is a field that is omitted; a field whose null value is a visible lie is
one the parent has to mean.

### Where the guarantee stops

| acceptance | pop is judged by | sound? |
| --- | --- | --- |
| compiles, imports, tests pass | the machine | yes |
| answer matches a schema | the machine | yes |
| "is this design good" | a model judge | no — lossy again |

Work of the third kind is real and this architecture does not cover it. It is
worth knowing that the reconstruct task is entirely of the first kind, which is
part of why it is such a good probe — and part of why a good result on it should
not be read as a general one.

## 4. Separating policy from execution is what `spawn` already is

The proposal to split the run into a phase that produces an accurate policy and
a phase that executes it is right, and it does not need a new mechanism. It needs
an answer to *who executes*:

| executor | what it means | verdict |
| --- | --- | --- |
| the same agent, later steps | the policy sits in a register; enforcement is advice | five runs say advice does not land |
| **a child** | **the policy is the brief; parent = policy, child = execution** | **this letter** |
| a program | policy is code and model calls are its subroutines | later — see below |

So the two ideas are one idea: separating the phases *is* what a frame does, and
the reason the current scaffold does not feel like it separates them is that its
policy phase emits prose instead of a frame.

There is a width argument for the split that stands on its own, independent of
delegation. *Deciding what to do* and *doing it* have different working sets, and
one generation currently holds their union. Splitting them compresses nothing —
it stops the two sets being live at the same time, which is the only thing
0.0.8b ever asks for.

The third row is the endpoint, and it is the "strategy code" of [DesignDoc -
Ideas (Bottom Up)](DesignDoc%20-%20Ideas%20(Bottom%20Up).md): control flow
becomes deterministic, loops and conditions cost nothing, and the model is called
only where judgment is needed, with each call's context constructed by the
program. It is out of scope here because that document's own open question —
*how to come back* — is unanswered, and because a declarative frame buys most of
it for a tenth of the build.

## 5. Steps must be charged, not merely shown

This is the precondition for everything above, and it should land before any
encouragement to delegate.

0.0.7j made the price of a child **visible**: the dump now says how many steps
the run has spent across how many agents. It did not make it **charged**. A
parent's own counter still moves by one however many steps its child burns, so
from where the parent sits, commissioning a hundred-step digest and running one
`grep` cost the same. A run has already spent 124 steps on a digest and a
checklist under exactly those incentives.

> **A child's steps debit the parent's remaining budget.**

Then `max_steps` stops being a wish and becomes an allocation; a parent that fans
out five ways can see that it has spent its run; and "prefer delegating" becomes
self-limiting rather than a licence. Encouraging delegation on top of *free*
delegation would make spawn-storms the equilibrium, and the storm is a failure
this project has already observed rather than a hypothetical one.

## 6. Depth: the scaffold should stop having an opinion

`max_depth` is currently 1, and hard: the root fans out to leaves and no
further, `spawn` vanishes from the schema at the floor, and the refusal names a
number the scaffold chose. 0.0.7a set it there for two reasons — deep trees
serialise, because `spawn` is synchronous and every ancestor sits blocked, and
every level paid to brief the next.

The second reason is what §2 is for. The first is real and unfixed. But neither
is a reason for the *scaffold* to pick the number, and the goal is unbounded
recursion:

- **The agent should know its own depth.** It currently cannot see it at all.
  One field on the `[Step]` line, beside the two counters already there.
- **The scaffold should not say how deep to go.** A ceiling is a property of the
  subtree, and only the agent standing in it knows anything about the subtree.
- **A parent may set one for its children**, the way it already sets `max_steps`
  — a voluntary allowance, passed down, and refused at the floor with a message
  that says *your parent allowed this depth*, not *the scaffold forbids it*.
- **Discouragement should be economic, not declarative.** §5 supplies it for
  free: once a child's steps debit its parent, a deep chain drains one budget,
  and depth is bounded by what the work is worth rather than by a constant.

That last point is the reason unbounded depth is safe to allow. Charged steps
make non-termination impossible — a chain that never bottoms out still runs out
of budget — so what is left to fear is waste, and waste is what a visible price
is for. What does not go away is serialisation: depth D means D agents blocked
on one descendant, D bash sessions, D summarisers, and wall-clock linear in D.
That is a resource cost, not a correctness one, and it should be measured before
the ceiling is lifted far.

N.B. We should allow having a max_depth when running the scaffold for experiment 
purposes and more delicate control, since user works like a parent and should 
naturally get any control a parent normally has.

## 7. When to descend — 0.0.8b's second question, answered

Not "prefer small tasks". One agent, one summariser and one JSON contract per
line of code is absurd, and a rule that implies it will be ignored for good
reasons. The unit is not small; it is **disjoint**:

> **Descend at a working-set boundary: when the subgoal needs facts you do not
> have, and you will not need its facts once it returns. When you and the
> subgoal share most of your facts, doing it inline is strictly cheaper.**

`run_step` and `config.py` share almost nothing, so they are frames. Two adjacent
lines of `run_step` share everything, so they are not. This is the same quantity
7.5 proposes to measure — fan-out in the call graph — used as a decision rule
rather than as a diagnosis, and it is a sentence in the system message rather
than a tool, by 0.0.8a's rule.

It also answers 0.0.8b's first question, in the negative: no in-agent frame is
needed. `spawn` is the frame; what it needed was a brief it could be given, a
check it could be judged by, and a price its caller could see.

## 8. Not in 0.0.8c

- **A judge for un-checkable work.** §3 stops where the machine does.
- **Asynchronous descent.** Concurrent *siblings* exist (0.0.7f); a parent that
  continues while a child runs does not, and every frame therefore blocks.
- **Any scaffold-chosen depth.** §6. The constant is removed, not retuned.
- **Strategy code.** §4, third row.

## 9. Open questions

1. **Does the structured brief actually pay for its schema?** It should be
   measured the way 0.0.7g measured prose: fixed tokens before and after, against
   briefing tokens generated before and after.
2. **What does a failed `check` do to the child?** Returning the failure and
   letting it continue is the useful behaviour and needs steps to be left for it
   — which interacts with §5, because those steps are the parent's.
3. **How does a parent allocate steps it cannot estimate?** Charging makes the
   allocation matter and does not make it easier. A frame that returns "I needed
   more" is already implemented as the handoff of 0.0.7h; whether that is enough
   is unknown.
4. **Does depth want to be free at all, or merely unlegislated?** §6 removes the
   constant on the argument that only the agent knows its subtree. That is an
   argument, not evidence, and the evidence that produced `max_depth = 1` was a
   real run.
