"""The four tools of the 0.0.1-simple scaffold: bash, load, set, spawn.

Every tool takes a destination register that receives its return information.
The full, untruncated return information also goes into the trajectory, and for
bash and spawn into a json file whose path lands in register 0.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .config import Config
from .model import ToolCall

if TYPE_CHECKING:  # pragma: no cover
    from .agent import Agent


@dataclass
class ToolResult:
    name: str
    #: Destination register to fill, or None when the tool wrote it itself /
    #: when the call failed before doing anything.
    register_id: int | None
    #: Value for the destination register (truncated to fit when stored).
    payload: str = ""
    #: Value for register 0: a result-file path, or a status / error message.
    status: str = ""
    #: The `observation.results` entry for the trajectory.
    record: dict[str, Any] = field(default_factory=dict)


def tool_specs(config: Config, *, spawn: bool = True) -> list[dict[str, Any]]:
    """The tool schemas. `spawn=False` is how a summariser is kept from recursing.

    Sent in full every step, so the wording is priced per generation: 0.0.7g cut
    these from 1,547 tokens to a third of that, keeping every rule and dropping
    the sentence that explained it. `spawn` was 634 of the 1,547 on its own.
    """
    first = config.num_special_registers
    last = config.num_registers - 1
    destination = {
        "type": "integer",
        "minimum": first,
        "maximum": last,
        "description": (
            f"Register for the return information ({first}-{last}; {config.canvas_id} is "
            "the canvas). Longer is cut to fit."
        ),
    }
    specs = [
        {
            "name": "bash",
            "description": (
                "Run a command in a persistent shell in the workspace. Terminal output "
                "(stdout and stderr interleaved) goes to the register, and in full to a "
                "json file whose path lands in register 0. This is how you write files, "
                "your response file included."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "register_id": destination,
                },
                "required": ["command", "register_id"],
            },
        },
        {
            "name": "load",
            "description": (
                "Read a file into a register from character `start`. As much as the "
                "register holds is stored, and register 0 reports the file's total "
                "length, so you can page through it. Past the end gives an empty string."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative to the workspace, or absolute."},
                    "start": {"type": "integer", "minimum": 0, "description": "0-based character offset."},
                    "register_id": destination,
                },
                "required": ["path", "start", "register_id"],
            },
        },
        {
            "name": "set",
            "description": (
                "Store a value in a register; non-strings are stringified. If it does not "
                "fit, the register is unchanged and register 0 holds the error."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "value": {
                        "type": ["string", "number", "integer", "boolean", "object", "array", "null"],
                    },
                    "register_id": destination,
                },
                "required": ["value", "register_id"],
            },
        },
        {
            "name": "set_target",
            "description": (
                f"Write register {config.target_id}, the target: what you are trying to "
                "achieve and how. Nothing else touches it, so it survives every step — keep "
                "in it the plan you want to be following twenty steps from now. Replaces "
                "the register whole; if it does not fit, nothing changes and register 0 "
                "holds the error."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": f"At most {config.max_special_length} chars.",
                    }
                },
                "required": ["content"],
            },
        },
        {
            "name": "spawn",
            "description": (
                "Run a fresh sub-agent on `prompt`. It starts with empty registers and its "
                "own trajectory and budget, and shares this workspace's files. Its response "
                "(which must match `return_schema`) and its trajectory path go to the "
                "register; its response file path lands in register 0. Use it for work "
                "whose intermediate context you do not want to keep. Several `spawn` calls "
                "in one step run at the same time, so a fan-out costs the slowest child "
                "rather than the sum — ask for them in one step and give each child its own "
                "files to write."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": (
                            "The sub-agent's instruction. It reads the same files you can, "
                            "so name paths and line ranges instead of pasting contents. Ask "
                            "for the thing you want, never for a number of characters: a "
                            "child told to hit a length spends its budget measuring and "
                            "rewriting."
                        ),
                    },
                    "return_schema": {
                        "type": "object",
                        "description": "JSON Schema its response must satisfy.",
                    },
                    "max_steps": {
                        "type": "integer",
                        "minimum": 1,
                        "description": (
                            "Steps it may take before it gives up and returns an error. "
                            "Omit to give it your own budget. Set it to what you think the "
                            "job is worth — you are waiting for it."
                        ),
                    },
                    "resume": {
                        "type": "string",
                        "description": (
                            "Id of a child that ran out, to continue rather than start "
                            "again: it keeps its registers, files and step count, and "
                            "`prompt`/`return_schema` are ignored. Give it a `max_steps`."
                        ),
                    },
                    "register_id": destination,
                },
                "required": ["prompt", "return_schema", "register_id"],
            },
        },
    ]
    return specs if spawn else [s for s in specs if s["name"] != "spawn"]


class ToolBox:
    def __init__(self, agent: "Agent"):
        self.agent = agent

    @property
    def config(self) -> Config:
        return self.agent.config

    def specs(self) -> list[dict[str, Any]]:
        return tool_specs(self.config, spawn=self.agent.can_spawn)

    def execute(self, call: ToolCall) -> ToolResult:
        handlers = {
            "bash": self._bash,
            "load": self._load,
            "set": self._set,
            "set_target": self._set_target,
            "spawn": self._spawn,
        }
        if not self.agent.can_spawn:
            # Not offered, so this is a model calling a tool it was not given —
            # refused here too, because that is where recursion would start.
            handlers.pop("spawn")
        handler = handlers.get(call.name)
        if handler is None:
            if call.name == "spawn":
                # Say *why* it is gone rather than "unknown tool": an agent at
                # the floor that asks anyway should learn the reason once,
                # instead of concluding the tool list was wrong.
                return self._failed(
                    call,
                    f"error: no `spawn` tool at depth {self.agent.depth} "
                    f"(max_depth={self.config.max_depth}); do this work yourself",
                )
            return self._failed(call, f"error: unknown tool {call.name!r}")
        try:
            return handler(call)
        except Exception as exc:  # a tool failure must not end the run
            return self._failed(
                call, f"error: {call.name} failed: {type(exc).__name__}: {exc}"
            )

    # --- helpers -------------------------------------------------------
    def _failed(self, call: ToolCall, message: str) -> ToolResult:
        return ToolResult(
            name=call.name,
            register_id=None,
            status=message,
            record={"tool": call.name, "input": call.input, "error": message},
        )

    def _destination(self, call: ToolCall) -> tuple[int | None, str | None]:
        register_id = call.input.get("register_id")
        error = self.agent.registers.check_destination(register_id)
        if error:
            return None, error
        return register_id, None

    def _write_output_file(self, tool: str, content: dict[str, Any]):
        path = self.agent.workspace.output_path(self.agent.agent_id, self.agent.step, tool)
        path.write_text(
            json.dumps(content, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        return path

    # --- tools ---------------------------------------------------------
    def _bash(self, call: ToolCall) -> ToolResult:
        command = call.input.get("command")
        if not isinstance(command, str):
            return self._failed(call, "error: 'command' must be a string")
        register_id, error = self._destination(call)
        if error:  # reject before running, so the command has no side effects
            return self._failed(call, error)

        output = self.agent.bash.execute_command(command)
        path = self._write_output_file(
            "bash", {"tool": "bash", "command": command, "output": output}
        )
        display = self.agent.workspace.display(path)
        return ToolResult(
            name="bash",
            register_id=register_id,
            payload=output,
            status=display,
            record={
                "tool": "bash",
                "register_id": register_id,
                "command": command,
                "output": output,
                "file": display,
            },
        )

    def _load(self, call: ToolCall) -> ToolResult:
        raw_path = call.input.get("path")
        if not isinstance(raw_path, str):
            return self._failed(call, "error: 'path' must be a string")
        start = call.input.get("start", 0)
        if not isinstance(start, int) or isinstance(start, bool) or start < 0:
            return self._failed(call, f"error: 'start' must be an integer >= 0, got {start!r}")
        register_id, error = self._destination(call)
        if error:
            return self._failed(call, error)

        path = self.agent.workspace.resolve(raw_path)
        display = self.agent.workspace.display(path)
        # `load` reads from Python, so the OS sandbox around bash does not see
        # it; the same policy is applied here by hand.
        blocked = self.agent.firewall.check_read(path, display)
        if blocked:
            return self._failed(call, blocked)
        if not path.exists():
            return self._failed(call, f"error: {display} does not exist")
        if path.is_dir():
            return self._failed(call, f"error: {display} is a directory, not a file")
        size = path.stat().st_size
        if size > self.config.max_load_bytes:
            return self._failed(
                call,
                f"error: {display} is {size} bytes, over the {self.config.max_load_bytes} "
                "byte load limit; read part of it with bash instead",
            )

        text = path.read_text(encoding="utf-8", errors="replace")
        limit = self.agent.registers.limit(register_id)
        excerpt = text[start : start + limit]
        status = (
            f"OK load {display} (length={len(text)}, start={start}, "
            f"display_length={len(excerpt)})"
        )
        return ToolResult(
            name="load",
            register_id=register_id,
            payload=excerpt,
            status=status,
            record={
                "tool": "load",
                "register_id": register_id,
                "path": display,
                "start": start,
                "length": len(text),
                "display_length": len(excerpt),
                "content": excerpt,
            },
        )

    def _set(self, call: ToolCall) -> ToolResult:
        if "value" not in call.input:
            return self._failed(call, "error: 'value' is required")
        value = call.input["value"]
        register_id, error = self._destination(call)
        if error:
            return self._failed(call, error)

        # `set` is strict rather than truncating, so it writes the register
        # itself and reports register_id=None to the caller.
        error = self.agent.registers.assign(register_id, value)
        status = error or (
            f"OK set register {register_id} "
            f"({len(self.agent.registers.values[register_id])} chars)"
        )
        return ToolResult(
            name="set",
            register_id=None,
            status=status,
            record={
                "tool": "set",
                "register_id": register_id,
                "value": value,
                "status": status,
            },
        )

    def _set_target(self, call: ToolCall) -> ToolResult:
        content = call.input.get("content")
        if not isinstance(content, str):
            return self._failed(
                call, f"error: 'content' must be a string, got {type(content).__name__}"
            )

        target = self.config.target_id
        # Writes the register itself, the way `set` does: this is the only path
        # to a special register, so it does not go through check_destination.
        error = self.agent.registers.assign(target, content)
        status = error or (
            f"OK set_target ({len(self.agent.registers.values[target])} chars)"
        )
        return ToolResult(
            name="set_target",
            register_id=None,
            status=status,
            record={
                "tool": "set_target",
                "register_id": target,
                "content": content,
                "status": status,
            },
        )

    def _spawn(self, call: ToolCall) -> ToolResult:
        resume = call.input.get("resume")
        prompt = call.input.get("prompt")
        return_schema = call.input.get("return_schema")
        if resume is not None and not isinstance(resume, str):
            return self._failed(call, "error: 'resume' must be an agent id")
        if resume is None:
            if not isinstance(prompt, str):
                return self._failed(call, "error: 'prompt' must be a string")
            if not isinstance(return_schema, dict):
                return self._failed(
                    call, "error: 'return_schema' must be a JSON Schema object"
                )
        register_id, error = self._destination(call)
        if error:
            return self._failed(call, error)
        max_steps = call.input.get("max_steps")
        if max_steps is not None and (
            not isinstance(max_steps, int) or isinstance(max_steps, bool) or max_steps < 1
        ):
            return self._failed(
                call, f"error: 'max_steps' must be an integer >= 1, got {max_steps!r}"
            )
        if self.agent.depth + 1 > self.config.max_depth:
            return self._failed(
                call,
                f"error: spawn depth limit reached (max_depth={self.config.max_depth}); "
                "do this work yourself",
            )

        if resume is not None:
            if resume == self.agent.agent_id:
                return self._failed(call, "error: an agent cannot resume itself")
            if not self.agent.workspace.trajectory_path(resume).exists():
                return self._failed(
                    call, f"error: no agent {resume} in this workspace to resume"
                )
            result = self.agent.resume_child(resume, max_steps)
        else:
            result = self.agent.spawn_child(prompt, return_schema, max_steps)
        trajectory = self.agent.workspace.display(result.trajectory_path)
        response_file = self.agent.workspace.display(result.response_path)
        response: dict[str, Any] = {"file": response_file, "steps": result.steps}
        if result.ok:
            response["content"] = result.response
            status = response_file
        else:
            response["error"] = result.error
            # The path first, as everywhere else: at a small geometry this
            # status is all the parent reads, and the handoff file is what turns
            # a dead child into one it can continue.
            handoff = (
                self.agent.workspace.display(result.handoff_path)
                if result.handoff_path
                else None
            )
            response["handoff"] = handoff
            status = (
                f"{handoff}\nerror: sub-agent {result.agent_id} stopped after "
                f"{result.steps} steps without a response. That file says where it got "
                f'to; continue it with spawn(resume="{result.agent_id}", max_steps=N).'
            )
        content = {"trajectory": trajectory, "response": response}
        return ToolResult(
            name="spawn",
            register_id=register_id,
            payload=json.dumps(content, ensure_ascii=False, indent=2, default=str),
            status=status,
            record={
                "tool": "spawn",
                "register_id": register_id,
                "prompt": prompt,
                "return_schema": return_schema,
                "max_steps": max_steps,
                "resume": resume,
                "agent_id": result.agent_id,
                "content": content,
            },
        )
