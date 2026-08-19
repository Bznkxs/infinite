"""A scripted stand-in for the Claude API, so the loop can be tested offline."""

from __future__ import annotations

import itertools
from typing import Any

from infinite.model import ModelResponse, ToolCall

_ids = itertools.count()


def tool_use(name: str, **params) -> dict[str, Any]:
    return {
        "type": "tool_use",
        "id": f"toolu_{next(_ids):04d}",
        "name": name,
        "input": params,
    }


def text(value: str) -> dict[str, Any]:
    return {"type": "text", "text": value}


def step(*blocks: dict[str, Any], stop_reason: str | None = None) -> ModelResponse:
    calls = [
        ToolCall(id=b["id"], name=b["name"], input=b["input"])
        for b in blocks
        if b["type"] == "tool_use"
    ]
    if stop_reason is None:
        stop_reason = "tool_use" if calls else "end_turn"
    return ModelResponse(
        blocks=list(blocks),
        tool_calls=calls,
        stop_reason=stop_reason,
        usage={"input_tokens": 1, "output_tokens": 1},
    )


class FakeModel:
    """Replays a script. Entries are ModelResponses or callables taking the request."""

    def __init__(self, script):
        self.script = list(script)
        self.requests: list[dict[str, Any]] = []

    def generate(
        self,
        *,
        system,
        tools,
        messages,
        max_tokens,
        model=None,
        effort=None,
        thinking=None,
    ) -> ModelResponse:
        request = {
            "system": system,
            "tools": tools,
            "messages": messages,
            "max_tokens": max_tokens,
            # The summariser is the same seam called with overrides, so a test
            # can tell one kind of call from the other by what was asked for.
            "model": model,
            "effort": effort,
            "thinking": thinking,
        }
        self.requests.append(request)
        if not self.script:
            return step(text("script exhausted"))
        entry = self.script.pop(0)
        return entry(request) if callable(entry) else entry
