"""What a run actually did, out of its trajectories.

    python -m eval.analyse runs/steploop_0.0.8

[Depth, Volume and Width](../docs/Depth,%20Volume%20and%20Width.md) §8 says how
to tell whether 0.0.8 worked, and none of it is a benchmark score: a coding
child's reads-to-writes ratio, the share of its steps spent establishing
interfaces, whether the digest habit survives, and — the property the whole
thing is for — whether the largest request moves when the task gets harder.
This reads those off the trajectories rather than off an impression of them.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from infinite.config import CHARS_PER_TOKEN

#: Tools that acquire and tools that produce. `spawn` is neither: it is a frame.
READS = {"load"}
WRITES = {"set", "set_target"}

#: A bash command reads if it only looks. Crude, and stated so: the ratio is a
#: trend to watch across versions rather than a measurement of anything exact.
READING_COMMANDS = (
    "cat ", "sed -n", "grep", "rg ", "head ", "tail ", "ls ", "wc ", "find ",
    "awk ", "python3 -c \"import", "nl ", "diff ",
)


def classify(command: str) -> str:
    stripped = command.strip()
    if any(stripped.startswith(prefix) for prefix in READING_COMMANDS):
        return "read"
    if ">" in stripped or "cp " in stripped or "mv " in stripped or "<<" in stripped:
        return "write"
    return "other"


def read_trajectory(path: Path) -> list[dict[str, Any]]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # a live file can end mid-line
    return records


def request_chars(record: dict[str, Any], header: dict[str, Any]) -> int:
    template = header.get("context_template") or {}
    fixed = len(template.get("system", "")) + len(
        json.dumps(template.get("tools", []), ensure_ascii=False)
    )
    messages = (record.get("model_input") or {}).get("messages") or []
    return fixed + sum(len(m.get("content", "")) for m in messages)


#: A stall streak this long is what separated the five 0.0.8 arms: every frame
#: that shipped a working module stalled at most four steps in a row, every frame
#: that shipped nothing ran to six, eight or nine. It is also `Config.stall_notice`,
#: which is where the number came from.
LIVELOCK = 3


def stall_measures(moved: list[bool] | None) -> dict[str, Any]:
    """Stalls, the longest run of them, and how many runs reached `LIVELOCK`."""
    if moved is None:
        return {"stalls": None, "longest_stall_streak": None, "livelocks": None}
    streaks, run = [], 0
    for did in moved:
        if did:
            if run:
                streaks.append(run)
            run = 0
        else:
            run += 1
    if run:
        streaks.append(run)
    return {
        "stalls": sum(streaks),
        "longest_stall_streak": max(streaks, default=0),
        "livelocks": sum(1 for streak in streaks if streak >= LIVELOCK),
    }


def summarise(path: Path) -> dict[str, Any] | None:
    records = read_trajectory(path)
    header = next((r for r in records if r.get("role") == "user"), None)
    if header is None:
        return None
    steps = [r for r in records if r.get("role") == "assistant"]
    finals = [r for r in records if r.get("role") == "final"]

    tools: Counter[str] = Counter()
    kinds: Counter[str] = Counter()
    generated = retyped = references = 0
    truncations = checks = failed_checks = 0
    #: 0.0.8d §4.1. `moved` is one bool a step: did it change a file, the target,
    #: the memo table or the check's verdict. A run that stalls forever fails at
    #: any budget, so this is the measure that says whether steps were a
    #: resource. `None` for a trajectory recorded before the measure existed —
    #: reporting 0 stalls for those would be a lie in the flattering direction.
    moved: list[bool] | None = None
    request_tokens = 0
    for record in steps:
        for result in (record.get("observation") or {}).get("results", []):
            name = result.get("tool", "?")
            tools[name] += 1
            if name in READS:
                kinds["read"] += 1
            elif name in WRITES:
                kinds["write"] += 1
            elif name == "bash":
                kinds[classify(result.get("command", ""))] += 1
        transit = record.get("transit") or {}
        generated += transit.get("generated", 0)
        retyped += transit.get("retyped", 0)
        references += transit.get("references", 0)
        if record.get("stop_reason") == "max_tokens":
            truncations += 1
        if "check" in record:
            checks += 1
            failed_checks += bool(record["check"].get("exit_code"))
        if (progress := record.get("progress")) is not None:
            if moved is None:
                moved = []
            moved.append(bool(progress.get("moved")))
        # §6: every "token" figure in the write-ups until 0.0.8d was
        # `max_request_chars / 2.6`, which ran about 2% low. The `usage` records
        # are what the API actually charged for.
        usage = record.get("usage") or {}
        request_tokens = max(
            request_tokens,
            (usage.get("input_tokens") or 0)
            + (usage.get("cache_read_input_tokens") or 0)
            + (usage.get("cache_creation_input_tokens") or 0),
        )

    sizes = [request_chars(r, header) for r in steps] or [0]
    final = finals[-1] if finals else {}
    return {
        **stall_measures(moved),
        "agent": header.get("agent_id"),
        "depth": header.get("depth", 0),
        "steps": len(steps),
        "charged": final.get("charged", 0),
        "cost": final.get("cost", len(steps)),
        "ok": final.get("ok"),
        "max_request_chars": max(sizes),
        "max_request_tokens": request_tokens or None,
        "median_request_chars": sorted(sizes)[len(sizes) // 2],
        "tools": dict(tools),
        "reads": kinds["read"],
        "writes": kinds["write"],
        "truncated_generations": truncations,
        "checks_run": checks,
        "checks_failed": failed_checks,
        "generated_chars": generated,
        "retyped_chars": retyped,
        "shell_register_refs": references,
        "check": header.get("check"),
        "goal": (header.get("content") or "").splitlines()[:2],
    }


def report(workspace: Path) -> None:
    rows = [
        summary
        for path in sorted(workspace.glob("trajectory-*.jsonl"))
        if (summary := summarise(path))
    ]
    if not rows:
        print(f"no trajectories in {workspace}")
        return
    rows.sort(key=lambda r: (r["depth"], r["agent"]))

    print(f"{workspace}  —  {len(rows)} agents, {sum(r['steps'] for r in rows)} steps\n")
    header = f"{'agent':10s} {'d':>2s} {'steps':>6s} {'cost':>5s} {'ok':>5s} " \
             f"{'reads':>6s} {'writes':>7s} {'r:w':>6s} {'cut':>4s} {'chk':>7s} " \
             f"{'stall':>7s} {'worst':>5s} {'lock':>4s} {'max in':>7s}"
    print(header)
    print("-" * len(header))
    for row in rows:
        ratio = f"{row['reads'] / row['writes']:.1f}" if row["writes"] else "—"
        checks = f"{row['checks_failed']}/{row['checks_run']}"
        stalls = (
            "—" if row["stalls"] is None
            else f"{row['stalls']}/{row['steps']}"
        )
        worst = "—" if row["longest_stall_streak"] is None else str(row["longest_stall_streak"])
        locks = "—" if row["livelocks"] is None else str(row["livelocks"])
        tokens = row["max_request_tokens"] or int(row["max_request_chars"] / CHARS_PER_TOKEN)
        print(
            f"{row['agent']:10s} {row['depth']:2d} {row['steps']:6d} {row['cost']:5d} "
            f"{str(row['ok']):>5s} {row['reads']:6d} {row['writes']:7d} {ratio:>6s} "
            f"{row['truncated_generations']:4d} {checks:>7s} "
            f"{stalls:>7s} {worst:>5s} {locks:>4s} {tokens:7d}"
        )

    print()
    generated = sum(r["generated_chars"] for r in rows)
    retyped = sum(r["retyped_chars"] for r in rows)
    share = f"{100 * retyped / generated:.1f}%" if generated else "—"
    # 0.0.8a's first open question, answered by the run rather than assumed.
    print(f"transit: {retyped} of {generated} generated argument chars were already "
          f"in a register ({share}); {sum(r['shell_register_refs'] for r in rows)} "
          "shell references instead")
    # 0.0.8d §4.1: the number that says whether steps were a resource at all.
    if any(r["stalls"] is not None for r in rows):
        worst = max((r["longest_stall_streak"] or 0) for r in rows)
        locks = sum((r["livelocks"] or 0) for r in rows)
        stalled = sum((r["stalls"] or 0) for r in rows)
        counted = sum(r["steps"] for r in rows if r["stalls"] is not None)
        print(
            f"progress: {stalled} of {counted} steps changed nothing durable; "
            f"longest run of them {worst}; {locks} runs reached {LIVELOCK}"
        )
    biggest = max(r["max_request_chars"] for r in rows)
    smallest = min(r["max_request_chars"] for r in rows)
    # The property the whole thing is for: this number should not move when the
    # task gets harder, only when the geometry does.
    print(f"input: largest {int(biggest / CHARS_PER_TOKEN)} tokens "
          f"({biggest} chars), smallest agent's largest "
          f"{int(smallest / CHARS_PER_TOKEN)} — spread "
          f"{int((biggest - smallest) / CHARS_PER_TOKEN)} tokens")
    tools: Counter[str] = Counter()
    for row in rows:
        tools.update(row["tools"])
    print("tools:  " + ", ".join(f"{k} {v}" for k, v in tools.most_common()))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eval.analyse", description=__doc__)
    parser.add_argument("workspace", nargs="+", type=Path)
    parser.add_argument("--json", action="store_true", help="Machine-readable instead.")
    args = parser.parse_args(argv)
    for workspace in args.workspace:
        if args.json:
            rows = [
                summary
                for path in sorted(workspace.glob("trajectory-*.jsonl"))
                if (summary := summarise(path))
            ]
            print(json.dumps({"workspace": str(workspace), "agents": rows}, indent=1))
        else:
            report(workspace)
            print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
