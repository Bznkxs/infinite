"""Building a run workspace for one benchmark instance.

Everything the agent may read has to be inside the workspace — that is the
firewall's rule — so an instance is a directory holding the corpus, the task,
and the response schema, and nothing else.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: Kept deliberately small: the schema is rendered into the system message, and
#: at 0.0.7g's budget every 100 tokens of it is 1.3% of the whole generation.
ANSWER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "evidence": {"type": "string"},
    },
    "required": ["answer", "evidence"],
}


@dataclass
class Instance:
    """One benchmark item, ready to be run."""

    benchmark: str
    instance_id: str
    task: str
    #: Files to write into the workspace: relative path -> contents.
    files: dict[str, str] = field(default_factory=dict)
    schema: dict[str, Any] = field(default_factory=lambda: dict(ANSWER_SCHEMA))
    #: Whatever the grader needs, carried through the run untouched.
    truth: dict[str, Any] = field(default_factory=dict)
    #: How many steps this kind of instance is worth.
    max_steps: int = 40

    def write(self, root: Path, *, fresh: bool = False) -> Path:
        workspace = root / self.benchmark / self.instance_id
        if fresh and workspace.exists():
            shutil.rmtree(workspace)
        workspace.mkdir(parents=True, exist_ok=True)
        for name, content in self.files.items():
            path = workspace / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        (workspace / "TASK.md").write_text(self.task, encoding="utf-8")
        (workspace / "schema.json").write_text(
            json.dumps(self.schema, ensure_ascii=False), encoding="utf-8"
        )
        # The truth lives beside the workspace, not inside it: the agent must
        # not be able to read the answer it is being asked for.
        (workspace.parent / f"{self.instance_id}.truth.json").write_text(
            json.dumps({"instance_id": self.instance_id, **self.truth}, ensure_ascii=False),
            encoding="utf-8",
        )
        return workspace
