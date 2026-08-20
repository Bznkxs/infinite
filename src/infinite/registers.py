"""The register file: the whole of the model's active context."""

from __future__ import annotations

import json
from typing import Any

from .config import Config

#: How near the end of a budget the dump starts saying so.
LAST_STEPS_WARNING = 3


def to_text(value: Any) -> str:
    """Convert a register value to the string that is actually stored."""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


class RegisterFile:
    def __init__(self, config: Config):
        self.config = config
        self.values: list[str] = [""] * config.num_registers
        self.truncated: list[bool] = [False] * config.num_registers

    # --- introspection -------------------------------------------------
    def limit(self, register_id: int) -> int:
        return self.config.register_limit(register_id)

    def is_special(self, register_id: int) -> bool:
        return self.config.is_special(register_id)

    def exists(self, register_id: Any) -> bool:
        return (
            isinstance(register_id, int)
            and not isinstance(register_id, bool)
            and 0 <= register_id < self.config.num_registers
        )

    def check_destination(self, register_id: Any) -> str | None:
        """Validate a tool's destination register. Returns an error message or None."""
        if not self.exists(register_id):
            return (
                f"error: register_id must be an integer in 0..{self.config.num_registers - 1}, "
                f"got {register_id!r}"
            )
        if self.is_special(register_id):
            return (
                f"error: register {register_id} is a special register written by the system "
                f"and cannot be a tool destination; pick a register in "
                f"{self.config.num_special_registers}..{self.config.num_registers - 1}"
            )
        return None

    # --- writing -------------------------------------------------------
    def assign(self, register_id: int, value: Any) -> str | None:
        """Strict write used by `set`: reject oversized values and change nothing."""
        text = to_text(value)
        limit = self.limit(register_id)
        if len(text) > limit:
            return (
                f"error: value is {len(text)} chars but register {register_id} holds at most "
                f"{limit}; register {register_id} is unchanged"
            )
        self.values[register_id] = text
        self.truncated[register_id] = False
        return None

    def store(self, register_id: int, value: Any, *, truncated: bool | None = None) -> bool:
        """Truncating write used for tool return information. Returns True if truncated.

        `truncated` overrides the flag for a value that was cut before it got
        here: register 3 is assembled from two halves that are each cut to
        their own budget, so the assembled value always fits and the length
        alone would say nothing was lost.
        """
        text = to_text(value)
        limit = self.limit(register_id)
        was_truncated = len(text) > limit
        self.values[register_id] = text[:limit]
        self.truncated[register_id] = was_truncated if truncated is None else truncated
        return was_truncated or bool(truncated)

    # --- reading -------------------------------------------------------
    def snapshot(self) -> list[str]:
        return list(self.values)

    def render(
        self,
        *,
        step: int | None = None,
        max_steps: int | None = None,
        run: tuple[int, int] | None = None,
        charged: int = 0,
        depth: int | None = None,
        check: str | None = None,
        stall: str | None = None,
    ) -> str:
        """The register dump that makes up the model's context each step.

        `step` and `max_steps` are the one thing the dump said nothing about
        until 0.0.7d: which step this is and how many are left. A run that
        cannot see its budget cannot pace itself against it — 0.0.7c spent a
        fifth of one on a document it never used and had no way to notice.

        `run` is the same argument one level up (0.0.7j): a parent's own counter
        moves by one however many steps the child it is waiting for spends, so
        the cost of delegating is invisible to the agent deciding to delegate.

        `charged` is 0.0.8c §5, which is that clause made real rather than
        merely visible: the steps this agent's children have taken come out of
        its own remaining budget, so `max_steps` on a `spawn` stops being a wish
        and becomes an allocation.

        `depth` is 0.0.8c §6. The scaffold no longer has an opinion about how
        deep a tree should go, and an agent that is to have one needs to be able
        to see where it is standing.

        `check` is the acceptance test's current verdict, run by the scaffold
        after every step. It is one line, it is the machine rather than the
        agent's recollection, and it is the thing 7.3 says should replace
        acquiring an interface: a run that is told every step whether its work
        imports does not have to read six modules to find out.

        `stall` is 0.0.8d §4.1, and it is here rather than in the system message
        for the same reason the step counter is: it is *state*, and the one kind
        of state five runs show the agent acts on. It appears only while the run
        of steps that changed nothing is long enough to be a livelock, so a run
        that is working never pays for it.
        """
        lines = []
        if step is not None or depth is not None:
            spent = "" if depth is None else f"depth {depth}"
            if step is not None:
                spent += (", " if spent else "") + f"step {step}"
            if step is not None and max_steps:
                left = max_steps - step + 1 - charged
                spent += f" of {max_steps} ({left} left, including this one"
                spent += f"; {charged} of your budget went to children)" if charged else ")"
                # Four children have now finished their work and died without
                # writing the one file that ends a run, each of them on a step
                # that began "with only two steps remaining". The count was
                # already here; what it never said was what to do about it.
                if left <= LAST_STEPS_WARNING:
                    spent += " — write your response file NOW, or this work is reported unfinished"
            if run and run[1] > 1:
                spent += f"; this run has spent {run[0]} steps across {run[1]} agents"
            lines.append(f"[Step] {spent}")
        if check:
            lines.append(f"[Check] {check}")
        if stall:
            lines.append(f"[Stall] {stall}")
        lines.append("[Registers]")
        for i, value in enumerate(self.values):
            # The name comes first: with five special registers, "register 3"
            # alone is not enough to act on without re-reading the system message.
            tags = []
            name = self.config.register_name(i)
            if name:
                tags.append(name)
            if self.is_special(i):
                tags.append("special")
            if self.truncated[i]:
                tags.append("truncated")
            suffix = ("; " + ", ".join(tags)) if tags else ""
            lines.append(f"--- register {i} ({len(value)}/{self.limit(i)} chars{suffix}) ---")
            if value:
                lines.append(value)
        return "\n".join(lines)
