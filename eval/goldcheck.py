"""Does the harness call the gold patch a pass?

A grader that fails the official fix is measuring itself. This applies the
dataset's own patch to an instance's repository and grades it: `correct` must be
true, and it must have been false before. Run it whenever an instance fails, so
a failure can be attributed to the agent rather than to the environment.

    python -m eval.goldcheck pylint-dev__pylint-6528
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .benchmarks import swebench
from .run import RUNS


def check(instance_id: str) -> dict:
    workspace = (RUNS / "swebench" / instance_id).resolve()
    repo = workspace / "repo"
    if not repo.exists():
        return {"instance_id": instance_id, "error": "no workspace; run the instance first"}
    instance = next(
        (i for i in swebench.load(count=60) if i.instance_id == instance_id), None
    )
    if instance is None:
        return {"instance_id": instance_id, "error": "not in the fetched slice"}

    # Discard whatever is in the tree and apply the official fix instead.
    subprocess.run(["git", "-C", str(repo), "checkout", "--", "."], check=False)
    subprocess.run(
        ["git", "-C", str(repo), "checkout", instance.truth["base_commit"], "--", "."],
        check=False,
    )
    patch = workspace / "gold.patch"
    patch.write_text(instance.truth["gold_patch"], encoding="utf-8")
    applied = subprocess.run(
        ["git", "-C", str(repo), "apply", str(patch)], capture_output=True, text=True
    )
    if applied.returncode != 0:
        return {"instance_id": instance_id, "gold_applies": False, "error": applied.stderr[-300:]}
    graded = swebench.grade({"answer": "gold"}, instance.truth, workspace=workspace)
    return {
        "instance_id": instance_id,
        "gold_applies": True,
        "gold_passes": graded.get("correct"),
        "fail_to_pass_ok": graded.get("fail_to_pass_ok"),
        "pass_to_pass_ok": graded.get("pass_to_pass_ok"),
        "error": graded.get("error"),
        "tail": (graded.get("fail_to_pass_tail") or "")[-200:],
    }


if __name__ == "__main__":
    for name in sys.argv[1:]:
        result = check(name)
        verdict = (
            "harness is sound for this instance"
            if result.get("gold_passes")
            else "HARNESS PROBLEM — the official fix does not pass here"
        )
        print(f"{name}: {verdict}")
        for key, value in result.items():
            if key != "instance_id" and value:
                print(f"  {key}: {str(value)[:220]}")
