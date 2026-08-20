"""Whether a step left anything behind — 0.0.8d §4.1.

The first Design Test asks for *infinite complexity*: complete a task however
complicated it is, while the context stays the same size. That is a claim about
steps buying progress. A run that loops fails at eighty steps and would fail at
eight hundred, and then the claim is false for a reason that has nothing to do
with the size of the context.

Nothing in 0.0.8 could tell the two apart. `charge_children` prices delegation
and the budget line is watched, but a step that runs one `grep` and a step that
writes a module cost exactly the same and the dump says nothing about what
either one left behind.

Three terms, and only the third is a defect:

* **Progress** — the step changed durable state: a file in the workspace, the
  target register, the memo table, or the check's verdict. Everything else a
  step makes, the next step or the one after overwrites: register 3 holds one
  step, register 4 is rewritten every step, and register 0 is the last result
  only.
* **Stall** — a step that changed none of it. Not a defect. Reading four files
  in one step to decide is a stall, and the system message asks for exactly
  that.
* **Livelock** — stalls in a row. This is the one worth acting on, and on the
  five 0.0.8 arms it is the only measure that separated the frames that shipped
  a module from the frames that did not: every passing frame stalled at most
  four steps in a row, at most twice; the failing frames ran to six, eight and
  nine.

What is *not* measured here is repetition. Reading one file twice is progress if
something happened in between and a loop if nothing did, so the second read is
not the observable — the nothing in between is.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

#: Directories under the workspace root that the scaffold writes on every step,
#: whatever the agent did. Counting these would make every step look like
#: progress, which is the one failure mode this file exists to avoid.
IGNORED_DIRS = ("tool_output",)

#: Names inside an agent's scratch directory that are the scaffold's or the
#: toolchain's rather than the agent's work: the registers-as-files mirror
#: (rewritten around every shell command), and the caches `Workspace.environment`
#: points here so that the sandbox is invisible to `python3`.
IGNORED_SCRATCH = ("reg", "tmp", "cache", "pycache")

#: The scaffold's own writing about an agent, rather than an agent's work. A
#: child's trajectory grows while its parent waits, so a parent that counted
#: these would never see itself stall; and the instruction file is written for an
#: agent before its first step, which would have made every run's opening step
#: look like progress.
#:
#: A `spawn` therefore does not count as progress by itself, which is right: the
#: cascade of 4.4 was four frames forwarding a goal and writing nothing, and a
#: parent whose child is working sees that child's files, its handoff and its
#: response soon enough.
IGNORED_FILES = re.compile(r"^(trajectory-[0-9a-f]+\.jsonl|instruction-[0-9a-f]+\.md)$")

#: How many changed paths a step's record names. The count is the measure; the
#: names are for reading a trajectory afterwards.
NAMED_PATHS = 5


def _ignored(relative: Path) -> bool:
    parts = relative.parts
    if not parts:
        return True
    if parts[0] in IGNORED_DIRS:
        return True
    if IGNORED_FILES.match(parts[-1]):
        return True
    # .scratch/<agent>/<what>/…
    if parts[0] == ".scratch" and len(parts) > 2 and parts[2] in IGNORED_SCRATCH:
        return True
    return False


def scan(root: Path) -> dict[str, tuple[int, int]]:
    """Every file the agent could have written, as path -> (mtime_ns, size).

    Cheap by design: one `stat` per file and no reads, so it costs the same on a
    ten-megabyte corpus as on a stub. A file that was rewritten with identical
    contents still counts as a change — the agent did something, and deciding
    otherwise would mean hashing the workspace every step.
    """
    state: dict[str, tuple[int, int]] = {}
    root = Path(root)
    for path in root.rglob("*"):
        try:
            if not path.is_file():
                continue
            relative = path.relative_to(root)
            if _ignored(relative):
                continue
            info = path.stat()
        except OSError:
            # A file that vanished mid-scan is a change either way, and the next
            # scan will see it gone.
            continue
        state[str(relative)] = (info.st_mtime_ns, info.st_size)
    return state


class Progress:
    """Per-step progress for one agent, and the stall streak it accumulates."""

    def __init__(self, root: str | Path, *, target: str = "", check: str | None = None):
        self.root = Path(root)
        self._files = scan(self.root)
        self._target = target
        self._check = check
        #: Consecutive stalled steps ending at the last one recorded.
        self.streak = 0
        #: The longest streak this agent has run, for the handoff and the record.
        self.longest = 0
        self.stalls = 0
        self.steps = 0

    def record(self, *, target: str, check: str | None) -> dict[str, Any]:
        """Close a step: what changed, and how long the run of nothing is now."""
        files = scan(self.root)
        created = sorted(set(files) - set(self._files))
        removed = sorted(set(self._files) - set(files))
        modified = sorted(
            path
            for path in files.keys() & self._files.keys()
            if files[path] != self._files[path]
        )
        target_moved = target != self._target
        check_moved = check != self._check
        self._files, self._target, self._check = files, target, check

        moved = bool(created or removed or modified or target_moved or check_moved)
        self.steps += 1
        if moved:
            self.streak = 0
        else:
            self.streak += 1
            self.stalls += 1
            self.longest = max(self.longest, self.streak)
        touched = created + modified + removed
        return {
            "moved": moved,
            "created": len(created),
            "modified": len(modified),
            "removed": len(removed),
            "target": target_moved,
            "check": check_moved,
            "stall_streak": self.streak,
            "paths": touched[:NAMED_PATHS],
        }

    def summary(self) -> dict[str, int]:
        return {
            "steps": self.steps,
            "stalls": self.stalls,
            "longest_stall_streak": self.longest,
        }


#: What the dump says once a run of nothing gets long enough to be a livelock
#: rather than a step spent reading. The reason is in it because the reason is
#: the argument: steps that leave nothing behind do not finish the task at any
#: budget, so this is not advice about tidiness.
STALL_NOTICE = (
    "{streak} steps in a row have changed no file, no target and no fact. Steps "
    "that leave nothing behind will not finish this at any budget — make this "
    "one leave something: write the file, record what you resolved, or hand a "
    "brief to a frame that will."
)


def stall_line(streak: int, threshold: int | None) -> str | None:
    """The `[Stall]` line, or None while the run is moving."""
    if threshold is None or streak < threshold:
        return None
    return STALL_NOTICE.format(streak=streak)
