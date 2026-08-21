Every version of InfiniteAgent gets one document, and this is its shape.

Recorded for versions from here on. The documents already in `docs/` were written
under looser conventions and are not being retrofitted — the reading order in
[Iterating to 0.0.8d](Iterating%20to%200.0.8d.md) §7 is how to find your way
around those.


## The file

One file per version, named for the version and nothing else:

    docs/InfiniteAgent 0.0.9.md
    docs/InfiniteAgent 0.0.9a.md      # a letter is a sub-version, not a chapter

A letter means a version that stands on its own: its own aim, its own changes,
its own experiment. It does not mean "part two of 0.0.9's write-up". If what you
have is one version with several sections, that is one file.


## The five sections

In this order, always, and with the numbers on them so that a reference from
another document lands somewhere exact.

1. **What it aims to do.** The problem, and what would count as solving it. One
   or two paragraphs, not a list of features.
2. **What it modifies.** Every change, with the file or knob it lands in. A
   reader should be able to diff the version from this section alone.
3. **What to evaluate.** The measurements that will decide whether §1 happened,
   named *before* they are taken: which probe, at what geometry, how many runs,
   and what result would count as a failure. State the number that would change
   your mind.
4. **Experiment results.** What the runs actually did. Every figure names the run
   that produced it.
5. **Handoff to the next version.** What is left, what is unattributed, and what
   the next person should not redo.


## The order is the point

**§1-3 are written before the implementation and before the experiment. §4-5 are
written after.** Two commits to the same file, and the git history is the
evidence: the first commit timestamps the plan, so nobody has to trust that it
was not shaped around the results.

This is not bookkeeping. A criterion written after the numbers are in is not a
criterion, and the failure it lets through is the one this project keeps
finding — a mechanism kept because the run it was fitted to passed. §3 written
first is what makes §4 able to say *no*.

Two rules that follow from it:

- **A refuted claim stays in the document,** with what replaced it and why. The
  old sentence is more useful than a clean page: it is the thing the next person
  would otherwise conclude for themselves.
- **A claim whose evidence is one run says so.** So does a result with more than
  one variable in it.


## What "everything else" is

[Standard Evaluations](Standard%20Evaluations.md) is the battery: the offline
suite, the `width` and `volume` probes, the three public benchmarks, and the
commands for each. Read it before writing §3 — it also records what each grade
does *not* check, which is what a §3 criterion has to be written around, and
which of them have no script yet.

## The last test a version takes

**If everything else a version set out to measure has passed, it attempts the
[Reconstruction Test](The%20Reconstruction%20Test.md)** — the agent rebuilds that
version of InfiniteAgent from a condensed specification of itself, in an empty
directory, under that version's own geometry, and then runs what it built. That
document is how to build the task for a new version and how to grade it; the
short of it is one or two files that condense everything normative about the
version, and a workspace with nothing else in it.

It goes last because it is the expensive one — hours rather than minutes; the
one pass took 2h43m and the longest failure 17.5 — and because it is not a
measurement. The probes in `eval/benchmarks/` are twenty minutes each and each
isolates one axis, so they are what a version is *tuned* against. This is the one that says whether the
version works, on the only task that is long enough, wide enough and deep enough
to be the claim in the [Design Tests](Design%20Tests%20(Top%20Down).md) rather
than a component of it. A version whose probes all pass and which has not
attempted it has not finished.

In the five sections that means: **§3 names it** among the measurements, with the
staging it will be given; **§4 reports the outcome** against the three gates, pass
or fail, with the measures the test document's §3.4 lists; and **§5 says plainly
that it was not attempted** if it was not, so the next version knows the claim is
open. A failed reconstruction is a result — every letter of the 0.0.7 series was
one — and the failure names the next change.

## Where results live

Live-run trajectories are in `runs/`, which is gitignored, so a figure in §4
needs a copy that survives a fresh clone. Distil each version's runs into
`eval/results/<probe>-<version>.json` and cite that file. `steploop-0.0.8.json`,
`volume-0.0.8d.json` and `width-0.0.8d.json` are the pattern.


## If a version needs a directory

A single file is the default and covers most versions. Use a directory when a
version's evaluation produces artefacts that do not belong in prose — several
probes, per-arm notes, a table too wide to read:

    docs/0.0.9/
      README.md        §1-5, the document; the only thing that must exist
      evaluation.md    §3 and §4 in detail, if they outgrow the document
      <artefacts>

The rule is unchanged: the five sections still exist, still in that order, still
split before and after. A directory is a place to put overflow, never a reason to
have no single document that can be read start to finish.
