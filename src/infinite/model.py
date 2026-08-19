"""The seam between the scaffold and the Claude API.

The scaffold never keeps a conversation: every step is a fresh single-turn
request whose only user message is the register dump.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from .config import NO_EFFORT, Config


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class ModelResponse:
    #: Raw content blocks, JSON-serializable, stored verbatim in the trajectory.
    blocks: list[dict[str, Any]]
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)

    @property
    def text(self) -> str:
        """Everything the model said, for a call whose answer is prose.

        A step's answer is its tool calls, so nothing reads this; the
        summariser's answer *is* the text, and it has no tools at all.
        """
        return "\n".join(
            block.get("text", "")
            for block in self.blocks
            if block.get("type") == "text" and block.get("text")
        )


class Model(Protocol):
    def generate(
        self,
        *,
        system: str,
        tools: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        max_tokens: int,
        model: str | None = None,
        effort: str | None = None,
        thinking: bool | None = None,
    ) -> ModelResponse:
        """One stateless request.

        The four required arguments are a step. The three overrides are for the
        summariser, which is the same seam used differently: a cheaper model, no
        effort and no thinking, because it rewrites a paragraph rather than
        deciding what to do next. `None` means "whatever the run uses"; an
        `effort` of `NO_EFFORT` means send none at all.
        """
        ...


class AnthropicModel:
    """Claude, called one stateless step at a time."""

    def __init__(self, config: Config, client: Any = None):
        self.config = config
        if client is None:
            import anthropic

            # The SDK retries 429/5xx/529 with backoff; its default of 2 tries is
            # sized for a request, not for a run that makes thousands of them.
            # 0.0.7b died on an `overloaded_error` that outlasted two attempts.
            client = anthropic.Anthropic(max_retries=config.api_max_retries)
        self.client = client

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
        thinking = self.config.thinking if thinking is None else thinking
        effort = self.config.effort if effort is None else effort
        kwargs: dict[str, Any] = {
            "model": model or self.config.model,
            "max_tokens": max_tokens,
            # The system message and tool list are identical every step, so a
            # breakpoint here caches tools + system; the registers land in the
            # user message after it.
            "system": [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "tools": tools,
            "messages": messages,
        }
        # The effort floor is `low`; below it there is only the absence of the
        # parameter, which is also what a small model requires — it rejects an
        # effort rather than ignoring one.
        if effort != NO_EFFORT:
            kwargs["output_config"] = {"effort": effort}
        if thinking:
            kwargs["thinking"] = {"type": "adaptive", "display": "summarized"}

        # Stream so a large workspace budget cannot hit the request timeout.
        with self.client.messages.stream(**kwargs) as stream:
            message = stream.get_final_message()

        blocks = [block.model_dump(mode="json") for block in message.content]
        tool_calls = [
            ToolCall(
                id=block.id,
                name=block.name,
                input=dict(block.input) if isinstance(block.input, dict) else {},
            )
            for block in message.content
            if block.type == "tool_use"
        ]
        usage = message.usage.model_dump(mode="json") if message.usage else {}
        return ModelResponse(
            blocks=blocks,
            tool_calls=tool_calls,
            stop_reason=message.stop_reason,
            usage=usage,
        )
