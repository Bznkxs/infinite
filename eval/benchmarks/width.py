"""The width probe: implement one module that calls into nine siblings.

This is the task the whole series turns on. 0.0.7 failed it four times, 0.0.8
passed it twice in five arms, and it is the only test the project has of the
third clause of the [Infinite Context
Test](../../docs/Design%20Tests%20(Top%20Down).md) — *infinite complexity:
complete tasks however complicated they are, while context stays the same size*.
Reading has six results and a test; writing has a test; complexity has five live
runs, one per arm, on a task with enormous variance.

Until now it was a recipe in prose — rebuild the workspace from
`runs/reconstruct_infinite_0.0.7i`, copy nine modules and a 99-line stub, strip
`__pycache__`, do not reuse a workspace across arms — and every one of those
steps is a way to spoil a three-hour run. Three arms of the same thing is the
first item on 0.0.8d's list, so the recipe is code:

    python -m eval.run width -n 3 --profile frame
    python -m eval.run width -n 2 --profile frame --arm no-stall-charge

The corpus is not in the repository. `runs/` is gitignored — those workspaces
are hundreds of megabytes of trajectory — so `SOURCE` points at the 0.0.7i
reconstruction on the machine that produced it, and `INFINITE_WIDTH_SOURCE`
overrides it. An absent corpus is a loud failure with the recipe in it rather
than a run that grades zero for the wrong reason.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from ..workspace import Instance

NAME = "width"

ROOT = Path(__file__).resolve().parent.parent.parent

#: The reconstruction the stub comes out of: nine modules an earlier run wrote,
#: the specification they were written from, and the API they share.
SOURCE = Path(
    os.environ.get(
        "INFINITE_WIDTH_SOURCE", ROOT / "runs" / "reconstruct_infinite_0.0.7i"
    )
)

#: What the agent gets. `infinite_agent/step_loop.py` is inside it and is the
#: stub — the corpus is already in the state the probe wants, which is why this
#: is a copy and not a checkout.
COPY = ("API.md", "docs", "infinite_agent")

#: The module to implement, and the six siblings it has to call into. The count
#: is the whole point: this is width, not volume.
TARGET = "infinite_agent/step_loop.py"

TASK_TEMPLATE = """# Task: implement `{target}`

You are working in this directory, which holds a Python package
`infinite_agent/` that an earlier run built from
`docs/InfiniteAgent 0.0.7f-simple (condensed spec).md`. Nine of its modules are
written. One is a stub: `{target}`, {lines} lines of docstrings, signatures and
`raise NotImplementedError`.

Implement it. The signatures and the public names in the stub are the contract —
keep them. `API.md` states the interfaces of the modules it calls into, and the
specification's Part 7 is normative for behaviour, later letters winning over
earlier ones.

The module calls into its siblings — config, registers, prompt, tools,
trajectory, summariser — so most of the work is knowing what they expect. They
are on disk and they are not yours to change.

## Done

    {check}

Write your response when that command succeeds: `answer` is the file and its
line count, `evidence` is the command's output.
"""

CHECK = "python3 -c 'import infinite_agent.step_loop'"

#: 80, because that is what all five 0.0.8 arms were given and a replication that
#: changes the budget replicates nothing.
MAX_STEPS = 80


def _missing() -> str:
    return (
        f"the width corpus is not at {SOURCE}.\n"
        "It is the 0.0.7i reconstruction — nine written modules, the 99-line "
        f"`{TARGET}` stub, `API.md` and `docs/` — and `runs/` is gitignored, so a "
        "fresh clone does not have it. Point INFINITE_WIDTH_SOURCE at a copy, or "
        "produce one by running the reconstruct task in "
        "`runs/reconstruct_infinite_0.0.7i/TASK.md`."
    )


def load(*, config: str | None = None, offset: int = 0, count: int = 1) -> list[Instance]:
    """`count` copies of one task, because the point is the variance.

    Every number in §2 of the 0.0.8 handoff is n=1 per arm. Two runs of the same
    thing is the cheapest finding available and nobody has taken it.
    """
    if not SOURCE.is_dir():
        raise SystemExit(_missing())
    stub = SOURCE / TARGET
    if not stub.is_file():
        raise SystemExit(_missing())
    lines = len(stub.read_text(encoding="utf-8").splitlines())
    task = TASK_TEMPLATE.format(target=TARGET, lines=lines, check=CHECK)
    return [
        Instance(
            benchmark=NAME,
            instance_id=f"steploop-{offset + i}",
            task=task,
            truth={"target": TARGET, "stub_lines": lines, "check": CHECK},
            max_steps=MAX_STEPS,
        )
        for i in range(count)
    ]


def materialise(instance: Instance, workspace: Path) -> None:
    """Copy the corpus in, freshly, and leave the stub as the stub.

    `__pycache__` is stripped because a compiled `step_loop` from an earlier arm
    is a fact the next arm did not pay for — and because the firewall points
    `PYTHONPYCACHEPREFIX` into the agent's scratch, so anything here is stale by
    construction.
    """
    if not SOURCE.is_dir():
        raise SystemExit(_missing())
    for name in COPY:
        source = SOURCE / name
        if not source.exists():
            raise SystemExit(f"{_missing()}\n(missing {name})")
        destination = workspace / name
        if destination.exists():
            shutil.rmtree(destination) if destination.is_dir() else destination.unlink()
        if source.is_dir():
            shutil.copytree(
                source, destination, ignore=shutil.ignore_patterns("__pycache__")
            )
        else:
            shutil.copy2(source, destination)
    for cache in workspace.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)


def _stubs_left(path: Path) -> int:
    try:
        return path.read_text(encoding="utf-8").count("NotImplementedError")
    except OSError:
        return -1


def grade(
    response: dict[str, Any] | None,
    truth: dict[str, Any],
    workspace: Path | None = None,
) -> dict[str, Any]:
    """The machine decides, not the response.

    Two arms of 0.0.8 reported a module they had not written — one returned
    `ok=True` while its own response said the stub was untouched — so what the
    agent claims is recorded and what the interpreter says is graded.
    """
    if workspace is None:
        return {"correct": False, "answer": None, "target": truth.get("target")}
    module = workspace / truth["target"]
    lines = len(module.read_text(encoding="utf-8").splitlines()) if module.is_file() else 0
    stubs = _stubs_left(module)
    completed = subprocess.run(
        [sys.executable, "-c", "import infinite_agent.step_loop"],
        cwd=workspace,
        capture_output=True,
        text=True,
    )
    imports = completed.returncode == 0
    # Untouched is its own outcome, not a kind of failure: three of five arms
    # ended here, and a run that wrote 457 lines that do not import is a
    # different problem from one that wrote nothing in eighty steps.
    return {
        "correct": bool(imports and stubs == 0),
        "imports": imports,
        "stubs_left": stubs,
        "lines": lines,
        "untouched": lines == truth.get("stub_lines"),
        "import_error": (completed.stderr or "").strip().splitlines()[-1:] or None,
        "answer": (response or {}).get("answer"),
        "target": truth.get("target"),
    }
