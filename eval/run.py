"""Run InfiniteAgent over benchmark instances and record what happened.

    python -m eval.run babilong --config 64k --split qa2 -n 3 --profile short
    python -m eval.run swebench -n 1 --profile full
    python -m eval.run --report

One instance is one workspace under `runs/eval/<benchmark>/<id>/`, one
subprocess, and one line in `runs/eval/<benchmark>/results.jsonl`. Nothing here
touches the scaffold: it is the CLI a person would type, typed by a script, so
what is measured is the shipped thing.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .benchmarks import REGISTRY
from .workspace import Instance

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs" / "eval"
PROFILES = {"full": [], "short": ["--short"]}


def run_one(instance: Instance, *, profile: str, fresh: bool) -> dict[str, Any]:
    module = REGISTRY[instance.benchmark]
    workspace = instance.write(RUNS, fresh=fresh)
    if hasattr(module, "materialise"):
        module.materialise(instance, workspace)

    command = [
        sys.executable, "-m", "infinite.main",
        "-f", str(workspace / "TASK.md"),
        "-w", str(workspace),
        "-s", str(workspace / "schema.json"),
        "--max-steps", str(instance.max_steps),
        *PROFILES[profile],
    ]
    log = workspace.parent / f"{instance.instance_id}.{profile}.log"
    clock = time.monotonic()
    with log.open("w", encoding="utf-8") as handle:
        completed = subprocess.run(command, cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT)
    elapsed = time.monotonic() - clock

    response, agent_id = None, None
    for path in sorted(workspace.glob("response-*.json")):
        agent_id = path.stem.split("-", 1)[1]
        try:
            response = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            response = None
    grade = (
        module.grade(response, instance.truth, workspace=workspace)
        if "workspace" in module.grade.__code__.co_varnames
        else module.grade(response, instance.truth)
    )
    # A pass proves the environment works. A failure does not distinguish "the
    # agent did not fix it" from "this instance cannot be built here", so the
    # official fix is applied and graded, and only an instance whose gold patch
    # passes counts against the agent.
    verified = True
    if not grade.get("correct") and hasattr(module, "materialise"):
        from .goldcheck import check

        verified = bool(check(instance.instance_id).get("gold_passes"))

    record = {
        "environment_ok": verified,
        "benchmark": instance.benchmark,
        "instance_id": instance.instance_id,
        "profile": profile,
        "exit_code": completed.returncode,
        "seconds": round(elapsed, 1),
        "agent_id": agent_id,
        "response": response,
        **grade,
        **measure(workspace),
        "truth": {k: v for k, v in instance.truth.items() if k not in ("test_patch", "gold_patch")},
    }
    results = workspace.parent / "results.jsonl"
    with results.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    return record


def measure(workspace: Path) -> dict[str, Any]:
    """What the run cost, from the trajectories it wrote."""
    steps = agents = 0
    tokens_in = tokens_out = 0
    context = None
    for path in workspace.glob("trajectory-*.jsonl"):
        agents += 1
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("role") == "user":
                context = record.get("context") or context
            if record.get("role") != "assistant":
                continue
            steps += 1
            usage = record.get("usage", {})
            tokens_in += (
                usage.get("input_tokens", 0)
                + usage.get("cache_read_input_tokens", 0)
                + usage.get("cache_creation_input_tokens", 0)
            )
            tokens_out += usage.get("output_tokens", 0)
    return {
        "steps": steps,
        "agents": agents,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "context_ceiling": (context or {}).get("total_tokens"),
    }


def report() -> None:
    rows: list[dict[str, Any]] = []
    for path in RUNS.glob("*/results.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            rows.append(json.loads(line))
    if not rows:
        print("no results yet")
        return
    print(f"{'benchmark':14s} {'profile':7s} {'n':>3s} {'correct':>7s} {'steps':>6s} {'ceiling':>8s} {'minutes':>8s}")
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault((row["benchmark"], row["profile"]), []).append(row)
    for (benchmark, profile), group in sorted(groups.items()):
        # Instances whose environment could not be rebuilt are not scored: a
        # harness that cannot run the official fix has measured nothing.
        gradable = [r for r in group if r.get("environment_ok", True)]
        excluded = len(group) - len(gradable)
        correct = sum(1 for r in gradable if r.get("correct"))
        steps = sum(r.get("steps", 0) for r in group) / len(group)
        ceiling = next((r.get("context_ceiling") for r in group if r.get("context_ceiling")), None)
        minutes = sum(r.get("seconds", 0) for r in group) / 60
        note = f"  ({excluded} unreproducible)" if excluded else ""
        print(f"{benchmark:14s} {profile:7s} {len(gradable):3d} {correct:3d}/{len(gradable):<3d} "
              f"{steps:6.1f} {str(ceiling or '-'):>8s} {minutes:8.1f}{note}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eval.run", description=__doc__)
    parser.add_argument("benchmark", nargs="?", choices=sorted(REGISTRY))
    parser.add_argument("--config", default=None, help="dataset config: a length for babilong, a task for the others")
    parser.add_argument("--split", default=None, help="babilong: qa1..qa10")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("-n", "--count", type=int, default=1)
    parser.add_argument("--profile", default="short", choices=sorted(PROFILES))
    parser.add_argument("--max-steps", type=int, default=None, help="override the benchmark's own budget")
    parser.add_argument("--fresh", action="store_true", help="delete an existing workspace first")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="build the workspaces and stop")
    args = parser.parse_args(argv)

    if args.report or not args.benchmark:
        report()
        return 0

    module = REGISTRY[args.benchmark]
    kwargs: dict[str, Any] = {"offset": args.offset, "count": args.count}
    if args.config:
        kwargs["config"] = args.config
    if args.split:
        kwargs["split"] = args.split
    instances = module.load(**kwargs)
    if not instances:
        print("no instances matched", file=sys.stderr)
        return 1

    for instance in instances:
        if args.max_steps:
            instance.max_steps = args.max_steps
        if args.dry_run:
            path = instance.write(RUNS, fresh=args.fresh)
            print(f"prepared {path} ({sum(len(v) for v in instance.files.values()):,} chars, "
                  f"{instance.max_steps} steps)")
            continue
        record = run_one(instance, profile=args.profile, fresh=args.fresh)
        mark = "PASS" if record.get("correct") else "fail"
        print(f"{mark} {record['instance_id']} — {record.get('answer')!r} vs {record.get('target')!r} "
              f"({record['steps']} steps, {record['seconds']:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
