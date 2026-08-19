"""Read trajectories off disk and normalize them for display.

The wire shape is documented in `docs/Trajectory Format.md`. Pre-v1
trajectories are missing the recorded context, so it is re-derived here from
the header's config and flagged `reconstructed` — the page labels it rather
than passing it off as what the model saw.
"""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path
from typing import Any

from ..config import Config
from ..prompt import build_system_message
from ..registers import RegisterFile
from ..tools import tool_specs

TRAJECTORY_RE = re.compile(r"^trajectory-(?P<agent_id>[^/]+)\.jsonl$")

CONFIG_FIELDS = {field.name for field in dataclasses.fields(Config)}


# --- scanning ----------------------------------------------------------
def _read_records(path: Path) -> list[dict[str, Any]]:
    """Parse a trajectory. A live run's last line may be partial; drop it."""
    records = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                break
    return records


def _summarize(path: Path, agent_id: str) -> dict[str, Any]:
    records = _read_records(path)
    header = next((r for r in records if r.get("role") == "user"), {})
    # Since v2 a trajectory can hold several segments, so the *last* final is
    # the outcome; an earlier one is just where a previous segment stopped.
    finals = [r for r in records if r.get("role") == "final"]
    steps = [r for r in records if r.get("role") == "assistant"]
    return {
        "agent_id": agent_id,
        "depth": header.get("depth", 0),
        # Pre-v3 only: the summariser used to be a sub-agent with a trajectory
        # of its own. Absent on anything written since, which is what False means.
        "summarizer": bool(header.get("summarizer")),
        "instruction": header.get("content", ""),
        "steps": len(steps),
        "ok": bool(finals[-1].get("ok")) if finals else None,
        "running": not finals or _has_open_segment(records),
        "segments": 1 + sum(1 for r in records if r.get("role") == "resume"),
        "model": (header.get("config") or {}).get("model"),
        "mtime": path.stat().st_mtime,
        "size": path.stat().st_size,
    }


def _has_open_segment(records: list[dict[str, Any]]) -> bool:
    """True when the file ends mid-segment: a resume with no final after it."""
    for record in reversed(records):
        if record.get("role") == "final":
            return False
        if record.get("role") in ("resume", "user"):
            return True
    return True


def list_workspaces(root: str | Path) -> list[dict[str, Any]]:
    """Every workspace under `root`, each with its agents, newest first.

    A workspace is any directory holding at least one trajectory file; agents
    within one are ordered by depth then start time, so the root agent leads.
    """
    root = Path(root)
    if not root.is_dir():
        return []

    workspaces = []
    for directory in sorted(p for p in root.rglob("*") if p.is_dir()) + [root]:
        agents = []
        for path in sorted(directory.glob("trajectory-*.jsonl")):
            match = TRAJECTORY_RE.match(path.name)
            if match:
                agents.append(_summarize(path, match.group("agent_id")))
        if not agents:
            continue
        agents.sort(key=lambda a: (a["depth"], a["mtime"]))
        name = str(directory.relative_to(root)) if directory != root else "."
        workspaces.append(
            {
                "workspace": name,
                "agents": agents,
                "mtime": max(a["mtime"] for a in agents),
            }
        )
    workspaces.sort(key=lambda w: w["mtime"], reverse=True)
    return workspaces


def trajectory_path(root: str | Path, workspace: str, agent_id: str) -> Path:
    """Resolve a workspace/agent pair, refusing anything outside `root`."""
    root = Path(root).resolve()
    if not TRAJECTORY_RE.match(f"trajectory-{agent_id}.jsonl"):
        raise ValueError(f"bad agent id: {agent_id!r}")
    path = (root / workspace / f"trajectory-{agent_id}.jsonl").resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"path escapes the runs directory: {workspace!r}")
    if not path.is_file():
        raise FileNotFoundError(str(path))
    return path


# --- reconstruction for pre-v1 trajectories ----------------------------
def _config_from(header: dict[str, Any]) -> Config:
    raw = header.get("config") or {}
    return Config(**{k: v for k, v in raw.items() if k in CONFIG_FIELDS})


def _rebuild_template(header: dict[str, Any], path: Path) -> dict[str, Any]:
    config = _config_from(header)
    agent_id = header.get("agent_id", "")
    system = build_system_message(
        config=config,
        workspace_root=header.get("workspace_root") or str(path.parent),
        instruction_file=header.get("instruction_file", f"instruction-{agent_id}.md"),
        response_file=header.get("response_file", f"response-{agent_id}.json"),
        trajectory_file=header.get("trajectory_file", path.name),
        return_schema=header.get("return_schema"),
    )
    return {
        "system": system,
        "tools": tool_specs(config),
        "max_tokens": config.workspace_tokens,
        "reconstructed": True,
    }


def _rebuild_messages(values: list[str], config: Config) -> list[dict[str, str]]:
    registers = RegisterFile(config)
    for i, value in enumerate(values[: config.num_registers]):
        registers.values[i] = value
    return [{"role": "user", "content": registers.render()}]


# --- normalization -----------------------------------------------------
def _split_blocks(blocks: list[dict[str, Any]]) -> dict[str, list]:
    thinking, text, calls = [], [], []
    for block in blocks or []:
        kind = block.get("type")
        if kind == "thinking":
            thinking.append(block.get("thinking", ""))
        elif kind == "redacted_thinking":
            thinking.append("[redacted thinking]")
        elif kind == "text":
            text.append(block.get("text", ""))
        elif kind == "tool_use":
            calls.append(
                {
                    "id": block.get("id"),
                    "name": block.get("name"),
                    "input": block.get("input", {}),
                }
            )
    return {"thinking": thinking, "text": text, "tool_calls": calls}


def _child_trajectory(result: dict[str, Any]) -> str | None:
    if result.get("tool") not in ("spawn", "resume"):
        return None
    return (result.get("content") or {}).get("trajectory")


def _normalize_step(
    record: dict[str, Any], config: Config, has_context: bool
) -> dict[str, Any]:
    parts = _split_blocks(record.get("content", []))
    results = (record.get("observation") or {}).get("results", [])
    registers_before = record.get("registers_before", [])

    # Results come back in tool-call order, so index matching is exact.
    for i, call in enumerate(parts["tool_calls"]):
        result = results[i] if i < len(results) else None
        call["result"] = result
        call["child_trajectory"] = _child_trajectory(result) if result else None

    model_input = record.get("model_input")
    if model_input is None:
        model_input = {
            "messages": _rebuild_messages(registers_before, config),
            "max_tokens": config.workspace_tokens,
            "reconstructed": True,
        }
    else:
        model_input = dict(model_input)
        model_input["reconstructed"] = not has_context

    return {
        "step": record.get("step"),
        "role": "assistant",
        "thinking": parts["thinking"],
        "text": parts["text"],
        "tool_calls": parts["tool_calls"],
        # Extra results with no matching call would otherwise vanish.
        "orphan_results": results[len(parts["tool_calls"]) :],
        "stop_reason": record.get("stop_reason"),
        "truncated": record.get("stop_reason") == "max_tokens",
        "usage": record.get("usage") or {},
        "timing": record.get("timing") or {},
        "registers_before": registers_before,
        "model_input": model_input,
        # The summariser that rewrote register 4 after this step, if one ran.
        "summary": record.get("summary"),
        "raw": record,
    }


def load_trajectory(path: str | Path, workspace: str = "") -> dict[str, Any]:
    """One trajectory file, normalized into the shape the page renders."""
    path = Path(path)
    records = _read_records(path)
    header = next((r for r in records if r.get("role") == "user"), {})
    finals = [r for r in records if r.get("role") == "final"]
    config = _config_from(header)

    template = header.get("context_template")
    has_context = template is not None
    if not has_context:
        template = _rebuild_template(header, path)

    # Steps and seams are interleaved in file order so the page can draw the
    # resume boundary where it actually happened.
    steps: list[dict[str, Any]] = []
    for record in records:
        role = record.get("role")
        if role == "assistant":
            steps.append(_normalize_step(record, config, has_context))
        elif role == "resume":
            steps.append(
                {
                    "role": "resume",
                    "step": record.get("step"),
                    "resumed_from_step": record.get("resumed_from_step"),
                    "started_at": record.get("started_at"),
                    "max_steps": record.get("max_steps"),
                    "registers_from": record.get("registers_from"),
                    "previous_error": record.get("previous_error"),
                }
            )
        elif role == "final" and record is not finals[-1]:
            steps.append({"role": "segment_end", "step": record.get("step"), "final": record})

    usage_total: dict[str, int] = {}
    duration_total = 0.0
    for step in steps:
        for key in ("input_tokens", "output_tokens", "cache_read_input_tokens"):
            value = (step.get("usage") or {}).get(key)
            if isinstance(value, int):
                usage_total[key] = usage_total.get(key, 0) + value
        duration_total += (step.get("timing") or {}).get("total_s") or 0.0

    return {
        "workspace": workspace,
        "agent_id": header.get("agent_id") or path.stem.removeprefix("trajectory-"),
        "trajectory_file": path.name,
        "format_version": header.get("format_version"),
        "reconstructed": not has_context,
        "depth": header.get("depth", 0),
        # Pre-v3 only: the summariser used to be a sub-agent with a trajectory
        # of its own. Absent on anything written since, which is what False means.
        "summarizer": bool(header.get("summarizer")),
        "seed_registers": header.get("seed_registers") or [],
        "instruction": header.get("content", ""),
        "instruction_file": header.get("instruction_file"),
        "response_file": header.get("response_file"),
        "workspace_root": header.get("workspace_root") or str(path.parent),
        "return_schema": header.get("return_schema"),
        "config": header.get("config") or {},
        "registers": {
            "count": config.num_registers,
            "num_special": config.num_special_registers,
            "canvas_id": config.canvas_id,
            "max_register_length": config.max_register_length,
            "max_special_length": config.max_special_length,
            "max_step_half_length": config.max_step_half_length,
            "max_canvas_length": config.max_canvas_length,
            "names": {
                str(i): config.register_name(i)
                for i in range(config.num_registers)
                if config.register_name(i)
            },
        },
        "firewall": header.get("firewall"),
        "context_template": template,
        "steps": steps,
        "final": finals[-1] if finals else None,
        "running": not finals or _has_open_segment(records),
        "segments": 1 + sum(1 for r in records if r.get("role") == "resume"),
        "usage_total": usage_total,
        "duration_total_s": round(duration_total, 2),
    }
