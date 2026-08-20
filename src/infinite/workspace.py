"""The shared on-disk workspace: instructions, responses, trajectories, tool output."""

from __future__ import annotations

import os
import threading
import uuid
from pathlib import Path

#: Where an agent's temporary files go. Per agent, because a workspace is
#: shared with every agent spawned into it and scratch that lands in the root
#: shows up in the parent's next `ls` as if it were part of the work.
SCRATCH_DIR = ".scratch"

#: The run's memo table — 0.0.8b §4. Five runs opened by writing a digest of
#: the specification, against the scaffold's advice, and it was read here first
#: as avoidance and then as the model's answer to width. It is neither: it is a
#: memo table in the wrong form — prose, written once, read whole — when what
#: the work wants is a table written incrementally and read by key. One line in,
#: one line out, and `grep` is the whole of the query. Shared by every agent in
#: the workspace, because a fact one of them resolved is a fact the next one
#: would otherwise resolve again.
FACTS_FILE = "facts.md"

FACTS_HEADER = (
    "# facts\n"
    "# One resolved fact per line, appended as it is resolved. `grep` before you go\n"
    "# looking; a fact another agent paid for is one you should not pay for twice.\n"
)

#: Where the registers appear as files, inside the agent's own scratch directory
#: so that neither an `ls` of the work nor the agent's own `rm` reaches them.
REG_DIR = "reg"


class Workspace:
    """One directory shared by an agent and every agent it spawns.

    Files are named after the agent id, so a parent can read a child's
    trajectory and response by path.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.output_dir = self.root / "tool_output"
        self.output_dir.mkdir(exist_ok=True)
        self._output_counter = 0
        #: One workspace is shared by every agent in a run, and since 0.0.7f a
        #: step's children run at the same time — so the counter that keeps two
        #: result files from sharing a name is now written from several threads.
        self._output_lock = threading.Lock()
        #: Steps taken by every agent in this run, and how many agents have
        #: taken one. A parent sees its own step counter and nothing else, so a
        #: child costs it exactly one step however many the child spends —
        #: which is why five runs in a row opened by delegating a digest.
        self._spent = 0
        self._agents: set[str] = set()
        self._facts_lock = threading.Lock()
        #: Created empty-but-for-its-header, because the system message names it
        #: every step. Until 0.0.8d nothing but `lookup` ever wrote it, so in
        #: every run that did not call `lookup` the file did not exist while the
        #: agent was being told it was the run's memo table — and three runs
        #: opened by `cat`ing it and getting nothing. A header is the difference
        #: between an empty table and a missing one.
        facts = self.facts_path()
        if not facts.exists():
            facts.write_text(FACTS_HEADER, encoding="utf-8")

    def record_step(self, agent_id: str) -> None:
        with self._output_lock:
            self._spent += 1
            self._agents.add(agent_id)

    def spent(self) -> tuple[int, int]:
        """(steps taken in this run, agents that have taken one)."""
        with self._output_lock:
            return self._spent, len(self._agents)

    def new_agent_id(self) -> str:
        return uuid.uuid4().hex[:8]

    def instruction_path(self, agent_id: str) -> Path:
        return self.root / f"instruction-{agent_id}.md"

    def response_path(self, agent_id: str) -> Path:
        return self.root / f"response-{agent_id}.json"

    def trajectory_path(self, agent_id: str) -> Path:
        return self.root / f"trajectory-{agent_id}.jsonl"

    def output_path(self, agent_id: str, step: int, tool: str) -> Path:
        with self._output_lock:
            self._output_counter += 1
            counter = self._output_counter
        name = f"{agent_id}-step{step:03d}-{counter:04d}-{tool}.json"
        return self.output_dir / name

    def handoff_path(self, agent_id: str) -> Path:
        """Where an agent that did not finish says how far it got.

        A child that runs out of steps has usually done most of the work and
        written most of the files; what its parent lacks is any account of it.
        This is that account, and it is a file rather than a register because at
        a small geometry a register holds two hundred characters.
        """
        return self.root / f"handoff-{agent_id}.json"

    def facts_path(self) -> Path:
        return self.root / FACTS_FILE

    def remember(self, lines) -> int:
        """Append facts that are not already on record. Returns how many landed.

        Every agent in the run shares it and a step's children run at the same
        time, so the append is locked and the file is opened for append rather
        than rewritten.
        """
        path = self.facts_path()
        with self._facts_lock:
            existing = (
                set(path.read_text(encoding="utf-8").splitlines())
                if path.exists()
                else set()
            )
            fresh = []
            for line in lines:
                line = line.strip()
                if line and line not in existing:
                    existing.add(line)
                    fresh.append(line)
            if not fresh:
                return 0
            with path.open("a", encoding="utf-8") as handle:
                if handle.tell() == 0:
                    handle.write(FACTS_HEADER)
                handle.write("\n".join(fresh) + "\n")
            return len(fresh)

    def reg_path(self, agent_id: str) -> Path:
        """Where this agent's registers appear as files."""
        return self.scratch_path(agent_id) / REG_DIR

    def scratch_path(self, agent_id: str) -> Path:
        """This agent's scratch directory, created on demand."""
        path = self.root / SCRATCH_DIR / agent_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def environment(self, agent_id: str) -> dict[str, str]:
        """The environment a bash session runs in: caches pointed inside the workspace.

        Every one of these defaults to somewhere the firewall denies, and a tool
        that cannot write its cache does not fail quietly — `python3` prints an
        `Operation not permitted` line on every single invocation, which then
        lands in a register and in the agent's summary. Pointing them at the
        scratch directory makes the sandbox invisible to the toolchain instead
        of merely survivable.

        `TMPDIR` is also what makes `/tmp` unnecessary rather than just denied:
        anything that asks the platform for a temporary directory gets a
        writable one.
        """
        scratch = self.scratch_path(agent_id)
        temp = scratch / "tmp"
        cache = scratch / "cache"
        for path in (temp, cache):
            path.mkdir(exist_ok=True)
        env = dict(os.environ)
        env.update(
            {
                "TMPDIR": str(temp),
                "TMP": str(temp),
                "TEMP": str(temp),
                "PYTHONPYCACHEPREFIX": str(scratch / "pycache"),
                "XDG_CACHE_HOME": str(cache),
            }
        )
        return env

    def resolve(self, path: str | Path) -> Path:
        """Resolve a model-supplied path against the workspace root."""
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = self.root / candidate
        return candidate

    def display(self, path: str | Path) -> str:
        """Paths shown to the model: relative to the root, which is its cwd."""
        resolved = Path(path)
        try:
            return str(resolved.relative_to(self.root))
        except ValueError:
            return str(resolved)
