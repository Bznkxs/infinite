"""Append-only trajectory: one JSON object per step, nothing truncated.

The file is left read-only between appends so the model cannot write to it
through bash. The record shapes are specified in `docs/Trajectory Format.md`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

#: Bumped when a field is removed or re-typed, or when the file's structure
#: changes. v2: a trajectory may hold several segments, so `final` is no longer
#: necessarily the last record. v3: the summariser stopped being a sub-agent, so
#: a step's `summary` no longer points at one — `agent_id`, `trajectory` and
#: `steps` are gone from it, and the header's `summarizer` flag with them.
FORMAT_VERSION = 3

READ_ONLY = 0o444
WRITABLE = 0o644


class Trajectory:
    def __init__(self, path: str | Path, *, resume: bool = False):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if resume:
            if not self.path.exists():
                raise FileNotFoundError(f"nothing to resume: {self.path}")
            return  # keep every existing record; the next append continues it
        if self.path.exists():
            os.chmod(self.path, WRITABLE)
        self.path.write_text("", encoding="utf-8")
        os.chmod(self.path, READ_ONLY)

    def append(self, record: dict[str, Any]) -> None:
        line = json.dumps(record, ensure_ascii=False, default=str)
        os.chmod(self.path, WRITABLE)
        try:
            with open(self.path, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        finally:
            os.chmod(self.path, READ_ONLY)

    def read(self) -> list[dict[str, Any]]:
        text = self.path.read_text(encoding="utf-8")
        return [json.loads(line) for line in text.splitlines() if line.strip()]
