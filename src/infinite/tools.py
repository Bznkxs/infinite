"""The tools: bash, load, set, set_target, lookup, spawn, resume.

Every tool *may* take a destination register for its return information; since
0.0.8a §4 it is optional, and omitting it discards the payload rather than
spending one of five registers on a value the agent did not want. The status
still lands in register 0, and the full, untruncated return information still
goes into the trajectory — and for bash and spawn into a json file.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .config import Config
from .model import ToolCall
from .prompt import build_brief

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
    the sentence that explained it. `spawn` was 634 of the 1,547 on its own, and
    0.0.8c adds fields to it on the argument that the prose it stops a parent
    generating is worth more than the schema it costs — a trade 7.4 asks to be
    made explicitly, so it is stated here and measured in the run.
    """
    first = config.num_special_registers
    last = config.num_registers - 1
    destination = {
        "type": "integer",
        "minimum": first,
        "maximum": last,
        # Repeated once per tool in every request, so it is priced seven times.
        "description": (
            f"Optional register for the return information ({first}-{last}; "
            f"{config.canvas_id} is the canvas), cut to fit. Omit to discard it."
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
                # 0.0.8a §3, and said here only: the system message would be a
                # second copy of it, and both are in every request.
                + (
                    f" The registers are files: $R0-$R{last} are their values and "
                    f"$REGDIR/0-$REGDIR/{last} the files, and a file you write becomes "
                    "that register when the command ends — `cp $REGDIR/5 $REGDIR/6`, "
                    f"`grep -c . \"$R5\" > $REGDIR/6`. 0-{first - 1} are read-only."
                    if config.registers_as_files
                    else ""
                )
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "register_id": destination,
                },
                "required": ["command"],
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
                "required": ["path", "start"],
            },
        },
        {
            "name": "set",
            "description": (
                "Store a value in a register; non-strings are stringified. If it does not "
                "fit, the register is unchanged and register 0 holds the error. For a "
                "value you are the author of — a plan, a note, a decision."
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
                        # The target's own limit, which is not the wide-register
                        # limit when `max_target_length` splits them: at the
                        # 0.0.8 geometry it is 704 against 1,536, and a model
                        # told the wrong number writes to the wrong number and
                        # has its write rejected whole.
                        "description": (
                            f"At most {config.register_limit(config.target_id)} chars."
                        ),
                    }
                },
                "required": ["content"],
            },
        },
    ]
    if config.lookup:
        specs.append(
            {
                "name": "lookup",
                "description": (
                    "One line per definition — where it is and what it takes. Give it a "
                    "symbol for one fact, or a file for the whole surface of a module, "
                    "which is how you learn to call into one without reading it. A "
                    "working set is then lines rather than pages."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": (
                                "A name, `Class.method`, a fragment — or a path "
                                "(`src/registers.py`, `pkg.registers`) for every "
                                "definition in that file."
                            ),
                        },
                        "register_id": destination,
                    },
                    "required": ["symbol"],
                },
            }
        )
    specs.append(
        {
            "name": "spawn",
            "description": (
                "Descend one frame: a child with a fresh context, its own trajectory, "
                "this workspace, and steps out of your budget. Name things; it works out "
                "method — you do not have its facts and are not meant to. Spawns in one "
                "step run at the same time."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "goal": {
                        "type": "string",
                        "description": (
                            "One sentence: what must be true when it returns. Longer "
                            "belongs in `goal_file`."
                        ),
                    },
                    "check": {
                        "type": "string",
                        "description": (
                            "Command that decides whether the work is done — an import, a "
                            "test, a diff. Run when the child writes its response; a "
                            "response that fails it is refused and it keeps going. `true` "
                            "opts out, deliberately."
                        ),
                    },
                    "return_schema": {
                        "type": "object",
                        "description": "JSON Schema its response must satisfy.",
                    },
                    "read": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Where to start reading. Pointers, not permission: it may "
                            "read anything."
                        ),
                    },
                    "write": {"type": "string", "description": "Where the work goes."},
                    "goal_file": {
                        "type": "string",
                        "description": (
                            "A file holding the goal in full; the child gets the path, so "
                            "nothing passes through your generation."
                        ),
                    },
                    "max_steps": {
                        "type": "integer",
                        "minimum": 1,
                        "description": (
                            "Steps it may take, out of what is left of yours. Omit to "
                            "give it all of them."
                        ),
                    },
                    "depth": {
                        "type": "integer",
                        "minimum": 0,
                        "description": (
                            "Levels it may descend below itself. Omit to pass on your "
                            "allowance; 0 stops it spawning."
                        ),
                    },
                    "register_id": destination,
                },
                "required": ["goal", "check", "return_schema"],
            },
        }
    )
    specs.append(
        {
            "name": "resume",
            "description": (
                "Give a child that ran out more steps. It keeps its registers, files, "
                "check and step count — a child that ran out is a process to continue, "
                "not work to redo."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "agent_id": {"type": "string", "description": "The id in its handoff file."},
                    "max_steps": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "More, out of what is left of yours.",
                    },
                    "register_id": destination,
                },
                "required": ["agent_id", "max_steps"],
            },
        }
    )
    return specs if spawn else [s for s in specs if s["name"] not in ("spawn", "resume")]


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
            "resume": self._resume,
        }
        if not self.config.lookup:
            handlers.pop("lookup", None)
        else:
            handlers["lookup"] = self._lookup
        if not self.agent.can_spawn:
            # Not offered, so this is a model calling a tool it was not given —
            # refused here too, because that is where recursion would start.
            handlers.pop("spawn")
            handlers.pop("resume")
        handler = handlers.get(call.name)
        if handler is None:
            if call.name in ("spawn", "resume"):
                # Say *why* it is gone rather than "unknown tool": an agent at
                # the floor that asks anyway should learn the reason once,
                # instead of concluding the tool list was wrong. 0.0.8c §6: the
                # number is somebody's allowance, not a constant the scaffold
                # picked, and the refusal says whose.
                return self._failed(call, f"error: {self.agent.depth_refusal()}")
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
        """The register to land in, or None for "discard the payload".

        0.0.8a §4: the write used to be unconditional, and with five free
        registers a five-call step — precisely what 0.0.7e's batching advice
        asks for — overwrote every one of them. The scaffold told the agent to
        batch and charged it its whole memory for complying. Any register it now
        declines to name is pinned by construction, and it decides which.
        """
        if call.input.get("register_id") is None:
            return None, None
        register_id = call.input["register_id"]
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

        output, notes = self.agent.run_shell(command)
        path = self._write_output_file(
            "bash",
            {
                "tool": "bash",
                "command": command,
                "output": output,
                "registers_written": notes,
            },
        )
        display = self.agent.workspace.display(path)
        # The registers the command wrote are named in register 0, because the
        # dump shows a changed register and not what changed it.
        status = display if not notes else f"{display}\nshell wrote {', '.join(notes)}"
        return ToolResult(
            name="bash",
            register_id=register_id,
            payload=output,
            status=status,
            record={
                "tool": "bash",
                "register_id": register_id,
                "command": command,
                "output": output,
                "registers_written": notes,
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
        # With no destination the payload is discarded, so what is kept is only
        # what the trajectory records; the canvas is the widest a register gets.
        limit = (
            self.agent.registers.limit(register_id)
            if register_id is not None
            else self.config.max_canvas_length
        )
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
        if call.input.get("register_id") is None:
            return self._failed(call, "error: 'register_id' is required by `set`")
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

    def _lookup(self, call: ToolCall) -> ToolResult:
        """7.1: turn width into depth — a signature costs a line, not a page."""
        symbol = call.input.get("symbol")
        if not isinstance(symbol, str):
            return self._failed(call, "error: 'symbol' must be a string")
        register_id, error = self._destination(call)
        if error:
            return self._failed(call, error)

        index = self.agent.index
        path = index._as_path(symbol)
        if path is not None:
            hits, total = index.outline(path, self.config.lookup_max_outline)
            # A dotted name that names nothing is more likely a symbol with a
            # dot in it than a module, so fall back rather than report a miss.
            if not hits:
                hits, total = index.lookup(symbol, self.config.lookup_max_matches)
        else:
            hits, total = index.lookup(symbol, self.config.lookup_max_matches)
        if not hits:
            payload = ""
            status = (
                f"no definition of {symbol!r} in the workspace's Python. "
                "It may be in another language, imported from elsewhere, or spelled "
                "differently — `grep` for it."
            )
        else:
            payload = "\n".join(hit.render() for hit in hits)
            status = f"OK lookup {symbol!r}: {len(hits)} of {total}"
            if total > len(hits):
                status += " (narrow it, or grep)"
            # The memo table of 0.0.8b §4, kept by the scaffold for the half an
            # AST can know. What it cannot know — that a return is None on
            # cut-off, which of two plausible functions this project uses — the
            # agent appends itself, and `grep` is the whole of the query.
            self.agent.workspace.remember(hit.render() for hit in hits)
        return ToolResult(
            name="lookup",
            register_id=register_id,
            payload=payload,
            status=status,
            record={
                "tool": "lookup",
                "register_id": register_id,
                "symbol": symbol,
                "matches": total,
                "content": payload,
            },
        )

    def _allowance(self, call: ToolCall, max_steps: Any) -> tuple[int | None, str | None]:
        """The steps a child may have, out of what is left of its parent's.

        0.0.8c §5. Until now a parent's counter moved by one however many steps
        its child spent, so commissioning a hundred-step digest and running one
        `grep` cost the same — and a run has already spent 124 steps on a digest
        and a checklist under exactly those incentives. Charged, `max_steps`
        stops being a wish and becomes an allocation.
        """
        if max_steps is not None and (
            not isinstance(max_steps, int) or isinstance(max_steps, bool) or max_steps < 1
        ):
            return None, f"error: 'max_steps' must be an integer >= 1, got {max_steps!r}"
        if not self.config.charge_children:
            return max_steps, None
        left = self.agent.allowance()
        if left is None:  # no cap on the parent, so none to pass down
            return max_steps, None
        if left < 1:
            return None, (
                "error: no steps left to give a child — your budget is spent on this "
                "step. Finish what you can and write your response file."
            )
        if max_steps is None or max_steps > left:
            return left, None
        return max_steps, None

    def _child_result(self, call: ToolCall, result, register_id, record) -> ToolResult:
        """The common return shape of `spawn` and `resume`."""
        trajectory = self.agent.workspace.display(result.trajectory_path)
        response_file = self.agent.workspace.display(result.response_path)
        response: dict[str, Any] = {
            "file": response_file,
            "steps": result.steps,
            "cost": result.cost,
        }
        if result.ok:
            response["content"] = result.response
            status = f"{response_file} ({result.cost} steps of yours)"
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
                f"{result.steps} steps ({result.cost} of yours) without a response. That "
                f"file says where it got to; continue it with "
                f'resume(agent_id="{result.agent_id}", max_steps=N).'
            )
            if result.check_failure:
                # The check is the parent's, and the parent is the only one who
                # can change it. A child that spent its budget failing one it
                # could not have passed should say so here.
                failure = result.check_failure
                response["check_failure"] = failure
                status += (
                    f" Its last check exited {failure['exit_code']}: "
                    f"`{failure['command']}` — see {failure['file']}."
                )
        content = {"trajectory": trajectory, "response": response}
        record = {
            **record,
            "register_id": register_id,
            "agent_id": result.agent_id,
            "cost": result.cost,
            "content": content,
        }
        return ToolResult(
            name=call.name,
            register_id=register_id,
            payload=json.dumps(content, ensure_ascii=False, indent=2, default=str),
            status=status,
            record=record,
        )

    def _spawn(self, call: ToolCall) -> ToolResult:
        """Descend one frame. 0.0.8c: the brief names, and does not describe.

        The parent is the lossy frame by construction, so the field that asked
        it for prose asked for something it could not supply — and briefs came
        out either as 0.0.6's 42KB contract document or as one vague paragraph.
        Everything a lossy caller *can* state precisely is a name: a goal, some
        paths, an output location, and the command that decides whether the work
        is done.
        """
        goal = call.input.get("goal")
        check = call.input.get("check")
        return_schema = call.input.get("return_schema")
        if not isinstance(goal, str) or not goal.strip():
            return self._failed(call, "error: 'goal' must be a non-empty sentence")
        if not isinstance(check, str) or not check.strip():
            return self._failed(
                call,
                "error: 'check' must be a command that decides whether the work is done; "
                'use "true" to say deliberately that there is none',
            )
        if not isinstance(return_schema, dict):
            return self._failed(call, "error: 'return_schema' must be a JSON Schema object")
        read = call.input.get("read")
        if read is not None and (
            not isinstance(read, list) or not all(isinstance(r, str) for r in read)
        ):
            return self._failed(call, "error: 'read' must be a list of paths")
        write = call.input.get("write")
        if write is not None and not isinstance(write, str):
            return self._failed(call, "error: 'write' must be a path")
        goal_file = call.input.get("goal_file")
        if goal_file is not None and not isinstance(goal_file, str):
            return self._failed(call, "error: 'goal_file' must be a path")
        depth = call.input.get("depth")
        if depth is not None and (
            not isinstance(depth, int) or isinstance(depth, bool) or depth < 0
        ):
            return self._failed(call, f"error: 'depth' must be an integer >= 0, got {depth!r}")
        register_id, error = self._destination(call)
        if error:
            return self._failed(call, error)
        max_steps, error = self._allowance(call, call.input.get("max_steps"))
        if error:
            return self._failed(call, error)

        brief = build_brief(
            goal=goal,
            check=check,
            read=read,
            write=write,
            goal_file=goal_file,
        )
        result = self.agent.spawn_child(
            brief,
            return_schema,
            max_steps=max_steps,
            check=check,
            goal=goal,
            write=write,
            depth_allowance=depth,
        )
        return self._child_result(
            call,
            result,
            register_id,
            {
                "tool": "spawn",
                "goal": goal,
                "check": check,
                "read": read,
                "write": write,
                "goal_file": goal_file,
                "brief": brief,
                "return_schema": return_schema,
                "max_steps": max_steps,
                "depth": depth,
            },
        )

    def _resume(self, call: ToolCall) -> ToolResult:
        agent_id = call.input.get("agent_id")
        if not isinstance(agent_id, str):
            return self._failed(call, "error: 'agent_id' must be an agent id")
        if agent_id == self.agent.agent_id:
            return self._failed(call, "error: an agent cannot resume itself")
        if not self.agent.workspace.trajectory_path(agent_id).exists():
            return self._failed(call, f"error: no agent {agent_id} in this workspace to resume")
        register_id, error = self._destination(call)
        if error:
            return self._failed(call, error)
        max_steps, error = self._allowance(call, call.input.get("max_steps"))
        if error:
            return self._failed(call, error)

        result = self.agent.resume_child(agent_id, max_steps)
        return self._child_result(
            call,
            result,
            register_id,
            {"tool": "resume", "resume": agent_id, "max_steps": max_steps},
        )
