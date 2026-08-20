"""The recursive agent loop.

Each step is a stateless model call whose only user message is the register
dump. Everything else — the past trajectory, earlier tool output — lives on
disk, reachable through the tools.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import shlex
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jsonschema

from . import summary as summary_module
from .bash_tool import BashSession
from .config import (
    REGISTER_LAYOUT,
    RESULT_REGISTER,
    STEP_ACTION_LABEL,
    STEP_LABEL_LENGTH,
    STEP_REGISTER,
    STEP_THINKING_LABEL,
    SUMMARY_REGISTER,
    TARGET_REGISTER,
    TRUNCATION_REGISTER,
    Config,
)
from .firewall import Firewall
from .model import Model
from .progress import Progress, stall_line
from .prompt import build_system_message
from .regfile import RegisterShell
from .registers import RegisterFile
from .tools import ToolBox, ToolResult
from .trajectory import FORMAT_VERSION, Trajectory
from .workspace import Workspace

logger = logging.getLogger(__name__)

#: A shell says 127 when the command does not exist and 126 when it exists and
#: cannot be run. A check that returns one of those did not decide anything: it
#: never ran. The child is told so in as many words, because the default
#: reading of a failed check — "my work is wrong" — is the wrong one here, and
#: the command is its parent's rather than its own.
CHECK_DID_NOT_RUN = (126, 127)

NO_TOOL_CALL_NOTICE = (
    "notice: the previous step made no tool call, so nothing changed. Use a tool to make "
    "progress, and write your response file when the work is done."
)
NO_ACTION = "(no tool call)"
CUT_OFF_ACTION = "(generation cut off before a tool call could run; nothing took effect)"
#: Register 0 is a normal register — 224 chars in the short geometry — so this
#: has to survive its own limit, the way 0.0.7b's truncation notice does.
CUT_OFF_NOTICE = (
    "notice: cut off at the token limit; the call you were writing did not run. "
    "Write less per step — one file, or part of one."
)
CUT_OFF_PARTIAL = " The {ran} call(s) before it did run."


def _thinking_text(blocks: list[dict[str, Any]]) -> str:
    """Everything the model generated that was not a tool call, in order.

    Thinking and prose are concatenated rather than chosen between, so the
    register carries the step's reasoning whether or not thinking is enabled.
    """
    parts = []
    for block in blocks:
        kind = block.get("type")
        if kind == "thinking":
            parts.append(block.get("thinking", ""))
        elif kind == "redacted_thinking":
            parts.append("[redacted thinking]")
        elif kind == "text":
            parts.append(block.get("text", ""))
    return "\n".join(part for part in parts if part)


def _action_text(calls: list[Any], *, dropped: int = 0) -> str:
    """The step's tool calls, as close to how the model wrote them as fits."""
    if not calls:
        return CUT_OFF_ACTION if dropped else NO_ACTION
    text = "\n".join(
        f"{call.name}({json.dumps(call.input, ensure_ascii=False, default=str)})"
        for call in calls
    )
    if dropped:
        text += "\n(one more call was cut off mid-way and did not run)"
    return text


#: The shortest register value counted as transit. Below this a match is as
#: likely to be a coincidence — "True", a two-letter flag — as a value the model
#: copied out of the dump.
MIN_TRANSIT_CHARS = 16


def _transit(before: list[str], calls: list[Any], *, shell: bool) -> dict[str, Any]:
    """What this step spent generating values it already had — 0.0.8a's §7.1.

    The letter's first open question is whether transit costs anything
    measurable: "output tokens spent on literals that already existed verbatim
    in a register". If the answer is "not much", registers-as-files is justified
    by the working set alone (§4) and not by the copying it saves.

    So the scaffold counts it. `retyped` is the characters of register values
    that turn up verbatim inside the step's tool-call arguments; `generated` is
    all the characters of those arguments; `references` is how many times the
    step reached a register through the shell instead, which is the same
    quantity going the other way.
    """
    arguments = "\n".join(
        json.dumps(call.input, ensure_ascii=False, default=str) for call in calls
    )
    if not arguments:
        return {"generated": 0, "retyped": 0, "registers": [], "references": 0}
    retyped, registers = 0, []
    for i, value in enumerate(before):
        if len(value) >= MIN_TRANSIT_CHARS and value in arguments:
            retyped += len(value)
            registers.append(i)
    references = 0
    if shell:
        for i in range(len(before)):
            references += arguments.count(f"$R{i}") + arguments.count(f"REGDIR/{i}")
    return {
        "generated": len(arguments),
        "retyped": retyped,
        "registers": registers,
        "references": references,
    }


def _complete_calls(response) -> tuple[list[Any], int]:
    """The calls of a cut-off generation that are certainly whole.

    A tool call block only exists because the one before it finished, so every
    call but the last is complete and safe to run. 0.0.1 dropped all of them,
    which was right when a step could generate 8192 tokens and truncation was
    rare; at 0.0.7g's 1920 a quarter of generations are cut off, and across
    three runs that rule discarded 56 finished calls.
    """
    calls = list(response.tool_calls)
    return (calls[:-1], 1) if calls else ([], 0)


def _step_text(thinking: str, action: str, half: int) -> tuple[str, bool]:
    """Register 3: the whole step, each half cut to its own budget.

    Cutting the halves separately rather than the joined text is the point: a
    long deliberation can no longer push the record of what was actually done
    out of the register, which is the half a next step cannot do without.
    """
    cut = len(thinking) > half or len(action) > half
    text = STEP_THINKING_LABEL + thinking[:half] + STEP_ACTION_LABEL + action[:half]
    return text, cut


CONFIG_FIELDS = {field.name for field in dataclasses.fields(Config)}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _timing(
    started_at: str,
    clock: float,
    generated: float,
    flushed: float,
    ran: float,
    done: float,
) -> dict[str, Any]:
    """Where a step's wall-clock went: the model, the tools, and the waiting.

    `summary_s` is not here. Since 0.0.7f the summariser of this step runs
    alongside the *next* step's generation, so what it costs is not part of this
    step's elapsed time; it is filled in when the thread is collected, and what
    the loop actually paid for it is `summary_wait_s` — the tail of the previous
    step's summariser that had not finished when this generation came back.
    """
    return {
        "started_at": started_at,
        "generation_s": round(generated - clock, 3),
        "summary_wait_s": round(flushed - generated, 3),
        "tools_s": round(ran - flushed, 3),
        "total_s": round(done - clock, 3),
    }


@dataclass
class AgentResult:
    agent_id: str
    ok: bool
    response: Any
    response_path: Path
    trajectory_path: Path
    steps: int
    error: str | None = None
    #: Written only when the run did not finish: what it was trying to do and
    #: what it had established, for whoever picks it up.
    handoff_path: Path | None = None
    #: The last check this agent ran, when it failed: the command, the exit
    #: code and where the output is. A parent whose brief carried an unrunnable
    #: check should be told that rather than that its child "produced nothing".
    check_failure: dict[str, Any] | None = None
    #: Steps this segment took, as against `steps`, which counts every segment
    #: on record.
    segment_steps: int = 0
    #: What the whole subtree cost: this segment's own steps plus everything its
    #: descendants spent. This is the number that comes out of a parent's
    #: budget, and the number 0.0.7j could only show.
    cost: int = 0


class Agent:
    def __init__(
        self,
        *,
        config: Config,
        workspace: Workspace,
        model: Model,
        instruction: str,
        agent_id: str | None = None,
        return_schema: dict[str, Any] | None = None,
        depth: int = 0,
        resume_from: int = 0,
        can_spawn: bool = True,
        seed: dict[int, str] | None = None,
        check: str | None = None,
        goal: str | None = None,
        write: str | None = None,
        depth_from_parent: bool = False,
    ):
        self.config = config
        self.workspace = workspace
        self.model = model
        self.agent_id = agent_id or workspace.new_agent_id()
        self.return_schema = return_schema
        self.depth = depth
        #: 0.0.8c §3: the command that decides whether this agent's work is
        #: done. The scaffold runs it when a response lands, and a response that
        #: fails it is not a return — so correctness rests on neither the
        #: parent's recollection nor the child's self-report, the two lossy
        #: parties, but on the machine.
        self.check = check
        #: The one sentence its caller asked for, and where the work goes. Both
        #: are names the caller already held, both are short, and both are in
        #: the system message rather than only in the instruction file: a child
        #: whose goal was a file spent 27 steps re-reading it.
        self.goal = goal
        self.write = write
        #: Whether the depth ceiling was allowed by a parent or set for the run.
        #: The refusal at the floor should name whose decision it was, because
        #: "the scaffold forbids it" is exactly the thing 0.0.8c removes.
        self.depth_from_parent = depth_from_parent
        #: Steps this agent's descendants have taken, which come out of its own
        #: budget (0.0.8c §5). Written from the spawn threads, so it is locked.
        self.charged = 0
        self._charge_lock = threading.Lock()
        #: What one failed check said, attached to the step that ran it and
        #: then cleared.
        self._last_check: dict[str, Any] | None = None
        #: The last check result of the whole segment, kept: a child that died
        #: against a check has nothing to show for it unless the parent — the
        #: only one who can change the check — is told which one.
        self._check_result: dict[str, Any] | None = None
        #: The verdict the next dump will carry, and the step it is from, so a
        #: response landing in the same step reuses it rather than paying twice.
        self._check_line: str | None = None
        self._check_step = -1
        #: Set when the check turned out to be too slow to be a heartbeat.
        self._check_is_slow = False
        #: 0.0.8d §4.1: what each step left behind, and how long the current run
        #: of steps that left nothing is. Built here rather than in `run` so the
        #: first step is measured against the workspace as it was handed over.
        self.progress = Progress(workspace.root)
        #: Budget charged for stalling, on the same footing as `charged`: steps
        #: this agent spent without leaving anything behind, priced so that a
        #: livelock is bounded by the resource rather than by a ceiling. 0.0.8c
        #: §6's rule applied to a frame instead of a subtree.
        self.stalled = 0
        #: Steps already on record; a fresh run starts at 0.
        self.step = resume_from
        #: Where this segment began, so a budget and an allowance can be worked
        #: out before `run` starts as well as during it.
        self._segment_start = resume_from
        self.resumed = resume_from > 0
        #: An agent at the depth floor cannot spawn, so it is not offered the
        #: tool: 0.0.6's run had one such agent try anyway, five times over
        #: thirty-four steps, because the refusal only lives in a register that
        #: gets rewritten. A tool that cannot succeed should not be in the list.
        #: `max_depth` is None by default since 0.0.8c — the scaffold has no
        #: opinion — and what bounds a tree instead is that its steps are
        #: charged: a chain that never bottoms out still runs out of budget.
        self.can_spawn = can_spawn and (
            config.max_depth is None or depth < config.max_depth
        )
        self.summarizes = config.summary
        #: Register 4's keeper: one tool-less call per step, not an agent.
        self.summariser = summary_module.Summariser(config, model)

        #: Why the last generation attempt failed, for the segment's `final`.
        self._last_error = ""
        #: The summariser runs on one thread of its own so that it overlaps the
        #: next generation instead of standing between two steps: across
        #: 0.0.7e's run it was 32% of the wall-clock of every agent in it.
        self._summary_pool: ThreadPoolExecutor | None = None
        #: The step whose record is written but whose summary has not landed
        #: yet: (record, future). At most one, because it is collected before
        #: the next one is started.
        self._pending: tuple[dict[str, Any], Future] | None = None

        self.registers = RegisterFile(config)
        #: Registers the agent starts its first step with already filled — for
        #: an agent whose whole input is data the caller already has, which can
        #: then answer on step one instead of paging a file in through a
        #: register.
        self.seed = dict(seed or {})
        for register_id, value in self.seed.items():
            self.registers.store(register_id, value)
        self.instruction = instruction
        self.instruction_path = workspace.instruction_path(self.agent_id)
        self.instruction_path.write_text(instruction, encoding="utf-8")
        self.response_path = workspace.response_path(self.agent_id)
        self.trajectory = Trajectory(
            workspace.trajectory_path(self.agent_id), resume=self.resumed
        )
        self.firewall = Firewall.build(
            workspace.root, config.readable_dirs, enabled=config.firewall
        )
        #: Somewhere inside the workspace for temporary files, with the shell's
        #: TMPDIR and caches pointed at it. Its own directory per agent, so a
        #: sub-agent's scratch does not appear in the parent's workspace.
        self.scratch = workspace.scratch_path(self.agent_id)
        #: The register file as the shell sees it (0.0.8a §3), synced around
        #: every `bash` call. None when the run is configured without it.
        self.regshell = (
            RegisterShell(
                self.registers, workspace.reg_path(self.agent_id), config
            )
            if config.registers_as_files
            else None
        )
        environment = workspace.environment(self.agent_id)
        if self.regshell is not None:
            environment.update(self.regshell.environment())
        self.bash = BashSession(
            cwd=str(workspace.root),
            timeout=config.bash_timeout,
            firewall=self.firewall,
            env=environment,
        )
        self.tools = ToolBox(self)
        #: What one generation of this run can cost, at its fullest. Recorded in
        #: the trajectory and refused here if the config set a ceiling: the
        #: scaffold had grown from 0.0.6's ~22k tokens a step to 0.0.7f's ~45k
        #: without anything ever adding the two halves up.
        self.context = self._context_budget()
        limit = config.max_context_tokens
        if limit is not None and self.context["total_tokens"] > limit:
            raise ValueError(
                f"one generation is up to {self.context['total_tokens']} tokens "
                f"({self.context['input_tokens']} in, {self.context['output_tokens']} out), "
                f"over the max_context_tokens of {limit}: "
                f"{self.context['fixed_chars']} chars of system message and tool schemas "
                f"(the return schema is part of it, and a shorter one is the usual fix) "
                f"and {self.context['dump_chars']} chars of registers"
            )

    def _context_budget(self) -> dict[str, int]:
        """The size of the largest request this agent can make.

        The two halves are measured as they will actually be sent: the rendered
        system message and the rendered tool schemas, which do not change, and
        the register dump at every register's limit, which is the ceiling rather
        than the average.
        """
        fixed = len(self.system_message()) + len(
            json.dumps(self.tools.specs(), ensure_ascii=False)
        )
        return self.config.context_tokens(fixed)

    # --- context -------------------------------------------------------
    def system_message(self) -> str:
        return build_system_message(
            config=self.config,
            workspace_root=str(self.workspace.root),
            instruction_file=self.workspace.display(self.instruction_path),
            response_file=self.workspace.display(self.response_path),
            trajectory_file=self.workspace.display(self.trajectory.path),
            return_schema=self.return_schema,
            firewall=self.firewall.describe(),
            summarizes=self.summarizes,
            can_spawn=self.can_spawn,
            instruction_register=self.instruction_register,
            scratch_dir=self.workspace.display(self.scratch),
            check=self.check if self.config.run_checks else None,
            goal=self.goal,
            write=self.write,
            facts_file=self.workspace.display(self.workspace.facts_path()),
            reg_dir=(
                f"${self.regshell.environment_variable}"
                if self.regshell is not None
                else None
            ),
        )

    @property
    def instruction_register(self) -> int | None:
        """The register holding a *complete* copy of the instruction, if any.

        A copy that did not fit is not one the agent can rely on, so it is not
        advertised: that agent is told to read the file like any other.
        """
        for register_id in self.seed:
            if self.registers.values[register_id] == self.instruction:
                return register_id
        return None

    # --- resuming ------------------------------------------------------
    @classmethod
    def resume(
        cls,
        *,
        workspace: Workspace,
        model: Model,
        agent_id: str,
        overrides: dict[str, Any] | None = None,
        upgrade_registers: bool = False,
    ) -> "Agent":
        """Rebuild an agent from its trajectory, ready for another segment.

        The stored config is authoritative — the register geometry has to match
        the values being restored — so `overrides` is for budgets and the model
        only. Register state comes from the run's last `final` record; if the
        process was killed before writing one, it falls back to the last step's
        `registers_before`, which costs one re-done step and never invents state.
        """
        path = workspace.trajectory_path(agent_id)
        records = Trajectory(path, resume=True).read()
        header = next((r for r in records if r.get("role") == "user"), None)
        if header is None:
            raise ValueError(f"{path} has no header record; nothing to resume")

        stored = {k: v for k, v in (header.get("config") or {}).items() if k in CONFIG_FIELDS}
        if isinstance(stored.get("readable_dirs"), list):
            stored["readable_dirs"] = tuple(stored["readable_dirs"])
        relayout = cls._check_layout(stored, upgrade_registers)
        config = dataclasses.replace(Config(**stored), **(overrides or {}))

        steps = [r for r in records if r.get("role") == "assistant"]
        if not steps:
            raise ValueError(f"{path} has no steps; start a fresh run instead")
        last_step = max(r.get("step", 0) for r in steps)
        # Continue past the closing `final` marker rather than reusing its
        # number, so no two steps in the file share one.
        next_step = max(r.get("step", 0) for r in records)

        finals = [r for r in records if r.get("role") == "final"]
        if finals and isinstance(finals[-1].get("registers"), list):
            values, source = finals[-1]["registers"], "final"
        else:
            values, source = steps[-1].get("registers_before", []), "last-step"

        agent = cls(
            config=config,
            workspace=workspace,
            model=model,
            instruction=header.get("content", ""),
            agent_id=agent_id,
            return_schema=header.get("return_schema"),
            depth=header.get("depth", 0),
            resume_from=next_step,
            check=header.get("check"),
            goal=header.get("goal"),
            write=header.get("write"),
            depth_from_parent=header.get("depth_from_parent", False),
        )
        for i, value in enumerate(values[: config.num_registers]):
            agent.registers.values[i] = value
        if relayout:
            # Under every earlier layout register 4 held something that is not a
            # summary. Carrying it across would present it as one; the next step
            # writes a real summary anyway.
            agent.registers.values[SUMMARY_REGISTER] = ""
        agent._resume_note = {
            "resumed_from_step": last_step,
            "registers_from": source,
            "previous_error": finals[-1].get("error") if finals else None,
            **({"registers_relayout": relayout} if relayout else {}),
        }
        return agent

    @staticmethod
    def _check_layout(stored: dict[str, Any], upgrade: bool) -> dict[str, Any] | None:
        """Refuse to resume a run whose registers meant something else.

        Register values are restored by index, so what each special register
        means has to be what it meant when the run was recorded. Every change to
        that meaning bumps REGISTER_LAYOUT — 0.0.3 turned registers 2-4 from
        scratch into the target and the automatic pair, 0.0.4 merged the pair
        into register 3 and gave register 4 to the summary. Continuing across
        one of those is a decision the operator makes, not one this code makes
        for them.
        """
        defaults = Config()
        # A trajectory recorded before layouts were numbered has no field to
        # read, and it is by definition not this one.
        was_layout = stored.get("register_layout", 0)
        was_special = stored.get("num_special_registers", defaults.num_special_registers)
        if was_layout == REGISTER_LAYOUT and was_special == defaults.num_special_registers:
            return None
        if not upgrade:
            raise ValueError(
                f"this run was recorded with register layout {was_layout or 'unnumbered'} "
                f"({was_special} special registers) and this scaffold uses layout "
                f"{REGISTER_LAYOUT} ({defaults.num_special_registers} special registers), "
                "in which the same register numbers mean something else. Pass "
                f"--upgrade-registers to continue anyway: register {TARGET_REGISTER}'s "
                f"contents become the target, register {STEP_REGISTER} is overwritten with "
                f"the next step, and register {SUMMARY_REGISTER} is cleared for the summary"
            )
        stored["num_special_registers"] = defaults.num_special_registers
        stored["register_layout"] = REGISTER_LAYOUT
        # This scaffold's wide tier, clamped into whatever geometry the run was
        # recorded with: a small canvas must still bound the special registers.
        normal = stored.get("max_register_length", defaults.max_register_length)
        canvas = stored.get("max_canvas_length", defaults.max_canvas_length)
        stored["max_special_length"] = max(
            normal, min(defaults.max_special_length, canvas)
        )
        stored["max_step_half_length"] = max(
            1, min(defaults.max_step_half_length, (canvas - STEP_LABEL_LENGTH) // 2)
        )
        return {
            "register_layout": [was_layout, REGISTER_LAYOUT],
            "num_special_registers": [was_special, defaults.num_special_registers],
            "max_special_length": stored["max_special_length"],
            "max_step_half_length": stored["max_step_half_length"],
            "summary_register": "cleared",
        }

    # --- the loop ------------------------------------------------------
    def run(self) -> AgentResult:
        system = self.system_message()
        tools = self.tools.specs()
        segment_start = self.step
        self._segment_start = segment_start
        self._segment_started = time.monotonic()
        if self.summarizes:
            self._summary_pool = ThreadPoolExecutor(
                max_workers=1, thread_name_prefix=f"summary-{self.agent_id}"
            )

        logger.info(
            "agent %s: one generation is up to %d tokens (%d in, %d out)",
            self.agent_id,
            self.context["total_tokens"],
            self.context["input_tokens"],
            self.context["output_tokens"],
        )

        if self.resumed:
            # A resumed run continues the same file, so the reader sees one
            # history with a seam in it rather than two disconnected runs.
            self.trajectory.append(
                {
                    "step": self.step,
                    "role": "resume",
                    "agent_id": self.agent_id,
                    "started_at": _now(),
                    "max_steps": self.config.max_steps,
                    "config": vars(self.config),
                    "context": self.context,
                    "context_template": {
                        "system": system,
                        "tools": tools,
                        "max_tokens": self.config.workspace_tokens,
                    },
                    "registers": self.registers.snapshot(),
                    **getattr(self, "_resume_note", {}),
                }
            )
        else:
            # The user message is the first step of the trajectory even though it
            # is not put in the context directly: the model reads it from a file.
            # The header also holds the half of the model input that never changes.
            self.trajectory.append(
                {
                    "format_version": FORMAT_VERSION,
                    "step": 0,
                    "role": "user",
                    "agent_id": self.agent_id,
                    "depth": self.depth,
                    "started_at": _now(),
                    "content": self.instruction,
                    "workspace_root": str(self.workspace.root),
                    "instruction_file": self.workspace.display(self.instruction_path),
                    "response_file": self.workspace.display(self.response_path),
                    "trajectory_file": self.workspace.display(self.trajectory.path),
                    "return_schema": self.return_schema,
                    "check": self.check,
                    "goal": self.goal,
                    "write": self.write,
                    "depth_from_parent": self.depth_from_parent,
                    "config": vars(self.config),
                    "context": self.context,
                    "seed_registers": sorted(self.seed),
                    "firewall": {
                        "enabled": self.firewall.enabled,
                        "writable": str(self.firewall.workspace),
                        "readable": [str(p) for p in self.firewall.readable],
                    },
                    "context_template": {
                        "system": system,
                        "tools": tools,
                        "max_tokens": self.config.workspace_tokens,
                    },
                }
            )
            self.registers.store(TRUNCATION_REGISTER, "False")

        try:
            while self._within_budget(segment_start):
                self.step += 1
                self.workspace.record_step(self.agent_id)
                registers_before = self.registers.snapshot()
                messages = [
                    {
                        "role": "user",
                        "content": self.registers.render(
                            step=self.step,
                            max_steps=self._budget_end(segment_start),
                            run=self.workspace.spent(),
                            charged=self.charged,
                            depth=self.depth,
                            check=self._check_line,
                            stalled=self.stalled,
                            stall=stall_line(
                                self.progress.streak, self.config.stall_notice
                            ),
                        ),
                    }
                ]

                started_at, clock = _now(), time.monotonic()
                response = self._generate(system, tools, messages)
                if response is None:
                    # Every attempt failed. The step never happened, so it is not
                    # recorded; the segment ends where it stood and `--resume`
                    # picks it up from the registers on disk — including the
                    # summary of the step before, which was being written while
                    # this generation was failing.
                    self._collect_summary()
                    self.step -= 1
                    return self._result(
                        ok=False,
                        response=None,
                        error=f"generation failed at step {self.step + 1}: {self._last_error}",
                    )
                generated = time.monotonic()
                # The previous step's summary was written during this
                # generation; take delivery of it now that the generation this
                # step needed it *after* is over.
                self._collect_summary()
                flushed = time.monotonic()

                record: dict[str, Any] = {
                    "step": self.step,
                    "role": "assistant",
                    "agent_id": self.agent_id,
                    "model_input": {
                        "messages": messages,
                        "max_tokens": self.config.workspace_tokens,
                    },
                    "registers_before": registers_before,
                    "content": response.blocks,
                    "stop_reason": response.stop_reason,
                    "usage": response.usage,
                }

                # The step's own reasoning and action are handed back to the next
                # step: without this the model has no memory of what it just did.
                thinking = _thinking_text(response.blocks)
                cut_off = response.stop_reason == "max_tokens"
                calls, dropped = (
                    _complete_calls(response) if cut_off else (response.tool_calls, 0)
                )
                action = _action_text(calls, dropped=dropped)
                record["transit"] = _transit(
                    registers_before, calls, shell=self.regshell is not None
                )
                text, clipped = _step_text(
                    thinking, action, self.config.max_step_half_length
                )
                self.registers.store(STEP_REGISTER, text, truncated=clipped)

                if cut_off:
                    # The call the generation was cut in the middle of may be
                    # half-written, so it is dropped; the ones it had already
                    # finished are run, and the model continues next step.
                    self.registers.store(TRUNCATION_REGISTER, "True")
                    results = self._run_tools(calls)
                    if results:
                        record["observation"] = {"results": [r.record for r in results]}
                    ran = time.monotonic()
                    notice = CUT_OFF_NOTICE.format(register=STEP_REGISTER)
                    if results:
                        notice += CUT_OFF_PARTIAL.format(ran=len(results))
                    self.registers.store(RESULT_REGISTER, notice)
                    self._observe_check()
                    if self._last_check is not None:
                        record["check"] = self._last_check
                        self._last_check = None
                    record["timing"] = _timing(
                        started_at, clock, generated, flushed, ran, time.monotonic()
                    )
                    self._close_step(record, thinking, action, results, cut_off=True)
                    logger.info(
                        "agent %s step %d: generation truncated (%d of %d calls ran)",
                        self.agent_id, self.step, len(results), len(calls) + dropped,
                    )
                    continue

                self.registers.store(TRUNCATION_REGISTER, "False")
                results = self._run_tools(calls)
                if results:
                    record["observation"] = {"results": [r.record for r in results]}
                # Before the response is read, so a response that lands in this
                # step is judged by this step's verdict rather than paying for
                # the same command twice.
                self._observe_check()
                ran = time.monotonic()

                # Read the response before summarising: a run that is over does
                # not need a summary handed to a step that will never happen.
                done, value, error = self.read_response()
                if self._last_check is not None:
                    record["check"] = self._last_check
                    self._last_check = None
                record["timing"] = _timing(
                    started_at, clock, generated, flushed, ran, time.monotonic()
                )
                self._close_step(
                    record, thinking, action, results, cut_off=False, last=done
                )

                if done:
                    logger.info(
                        "agent %s finished in %d steps", self.agent_id, self.step
                    )
                    return self._result(ok=True, response=value)
                if error:
                    self.registers.store(RESULT_REGISTER, error)
                elif response.stop_reason == "refusal":
                    self.registers.store(
                        RESULT_REGISTER, "notice: the previous generation was declined"
                    )
                elif not response.tool_calls:
                    self.registers.store(RESULT_REGISTER, NO_TOOL_CALL_NOTICE)

            # Kept short on purpose: this lands in a parent's register, which
            # truncates, and in the spawn payload.
            error = (
                f"no valid response in {self.step - segment_start} steps "
                f"(expected {self.workspace.display(self.response_path)})"
            )
            logger.warning("agent %s gave up: %s", self.agent_id, error)
            self._collect_summary()
            return self._result(ok=False, response=None, error=error)
        finally:
            # Nothing is left in flight: a summary still being written when the
            # segment ends is waited for and recorded, so the `final` a resume
            # reads holds the register file as it really stood.
            self._collect_summary()
            if self._summary_pool is not None:
                self._summary_pool.shutdown(wait=True)
                self._summary_pool = None
            self.bash.close()

    def _within_budget(self, segment_start: int) -> bool:
        """The budget is per segment, so a resumed run gets a fresh allowance.

        Since 0.0.8c a descendant's steps count against it too. Without that a
        parent's counter moved by one however many steps its child spent, so
        `max_steps` on a spawn was a wish rather than an allocation, and a
        hundred-step digest cost the same as one `grep`.
        """
        if self.config.max_steps is None:
            return True
        return (
            self.step - segment_start + self.charged + self.stalled
            < self.config.max_steps
        )

    def allowance(self) -> int | None:
        """Steps left for this agent's children, or None when it has no cap.

        Counted from where the segment began, so a resumed agent's fresh
        allowance is the one it can actually give away.
        """
        if self.config.max_steps is None:
            return None
        return (
            self.config.max_steps
            - (self.step - self._segment_start)
            - self.charged
            - self.stalled
        )

    def _stall_surcharge(self, streak: int) -> int:
        """What this step costs on top of itself for having left nothing behind.

        Nothing until the streak is long enough to be a livelock rather than a
        step spent reading, and then a flat surcharge for every further one — so
        a run that loops spends its budget at twice the rate and a run that is
        working never notices the mechanism exists.
        """
        threshold = self.config.stall_notice
        if threshold is None or streak < threshold:
            return 0
        return self.config.stall_surcharge

    def charge(self, steps: int) -> None:
        """Debit this agent for what a descendant spent."""
        if not self.config.charge_children or steps <= 0:
            return
        with self._charge_lock:
            self.charged += steps

    def depth_refusal(self) -> str:
        """Why there is no `spawn` here, and whose decision that was.

        0.0.8c §6: a ceiling is a property of the subtree, and the refusal
        should say *your parent allowed this depth* rather than *the scaffold
        forbids it* — the scaffold no longer has an opinion.
        """
        ceiling = self.config.max_depth
        if ceiling is None:  # then can_spawn was False for some other reason
            return f"no `spawn` in this run; do this work yourself (depth {self.depth})"
        whose = "your parent allowed" if self.depth_from_parent else "this run allows"
        return (
            f"no `spawn` at depth {self.depth}: {whose} depth {ceiling}. "
            "Do this work yourself."
        )

    # --- the shell -----------------------------------------------------
    def run_shell(self, command: str) -> tuple[str, list[str]]:
        """One command, with the registers reachable as files around it.

        0.0.8a §3. Out first, so `$R5` and `$REGDIR/5` are current at the moment
        the command runs; back afterwards, so a file the command wrote becomes
        the register it names. Both halves are the whole of copy, deref-copy and
        computed-into-a-register, and none of them passes through a generation.
        """
        if self.regshell is None:
            return self.bash.execute_command(command), []
        self.regshell.sync_out()
        output = self.bash.execute_command(self.regshell.preamble() + command)
        return output, self.regshell.sync_in()

    def run_check(self, command: str) -> tuple[int, str]:
        """The acceptance test, as a machine operation. Returns (exit code, output).

        In a subshell and pinned to the workspace root, so a check that `cd`s or
        exits cannot move the session it borrowed. The registers are not synced
        around it: a check decides whether the work is done and has no business
        writing the agent's memory.
        """
        marker = "__INFINITE_CHECK_EXIT__"
        root = shlex.quote(str(self.workspace.root))
        wrapped = f"( cd {root} && {command} ) 2>&1; echo {marker}$?"
        output = self.bash.execute_command(wrapped, timeout=self.config.check_timeout)
        head, sep, tail = output.rpartition(marker)
        if not sep:
            # A timeout restarts the session and never prints the marker.
            return -1, output
        try:
            code = int(tail.strip().splitlines()[0])
        except (ValueError, IndexError):
            return -1, output
        return code, head

    def _generate(self, system, tools, messages):
        """The step's own model call, retried rather than fatal.

        A run of a thousand steps meets a transient API error eventually, and a
        crash there costs everything not already on disk — 0.0.7b lost a run that
        was two thirds of the way through a reconstruction to one `Overloaded`.
        """
        delay = self.config.step_retry_backoff
        deadline = time.monotonic() + self.config.step_retry_seconds
        attempt = 0
        while True:
            attempt += 1
            try:
                return self.model.generate(
                    system=system,
                    tools=tools,
                    messages=messages,
                    max_tokens=self.config.workspace_tokens,
                )
            except Exception as exc:
                self._last_error = f"{type(exc).__name__}: {exc}"
                left = deadline - time.monotonic()
                if left <= 0:
                    self._last_error = (
                        f"{self._last_error} (gave up after {attempt} attempts over "
                        f"{self.config.step_retry_seconds / 60:.0f} min)"
                    )
                    logger.warning(
                        "agent %s step %d: generation attempt %d failed (%s)",
                        self.agent_id, self.step, attempt, self._last_error[:240],
                    )
                    return None
                logger.warning(
                    "agent %s step %d: generation attempt %d failed (%s); retrying in %.0fs"
                    " (%.0f min of patience left)",
                    self.agent_id, self.step, attempt, self._last_error[:200],
                    min(delay, left), left / 60,
                )
                time.sleep(min(delay, left))
                delay = min(delay * 2, self.config.step_retry_backoff_max)

    def _budget_end(self, segment_start: int) -> int | None:
        """The last step number this segment may reach, or None for no cap."""
        if self.config.max_steps is None:
            return None
        return segment_start + self.config.max_steps

    def _run_tools(self, calls: list[Any]) -> list[ToolResult]:
        """Every call of the step, in the model's order — spawns side by side.

        A step is one generation however many calls it holds (0.0.7e), and the
        scaffold asks the agent to batch on exactly that argument. For `spawn`
        the argument was false: 0.0.7e's root asked for five children in one
        step and the scaffold ran them one after another, so a step that should
        have cost the slowest child cost the sum of all five — 16.3 hours of a
        17.5-hour run, and the children were writing different files.

        Only a run of two or more consecutive `spawn` calls goes concurrent.
        Anything else keeps the order the model wrote, because a `bash` before a
        `spawn` may well be what the child is meant to find on disk, and the
        shell is one session that cannot run two commands at once anyway.
        """
        results: list[ToolResult] = []
        index, total = 0, len(calls)
        while index < total:
            end = index
            while end < total and calls[end].name == "spawn":
                end += 1
            if end - index > 1:
                results.extend(self._run_spawn_group(calls[index:end]))
                index = end
            else:
                results.append(self._run_tool(calls[index]))
                index += 1
        return results

    def _run_spawn_group(self, calls: list[Any]) -> list[ToolResult]:
        """Children of one step, started together and applied in order.

        `spawn_workers` is the ceiling: a fan-out of five puts five agents and
        five summarisers on the API at once, and an overloaded API is what
        0.0.7c had to teach the scaffold to survive.
        """
        workers = min(len(calls), self.config.spawn_workers)
        logger.info(
            "agent %s step %d: %d spawns in one step, %d at a time",
            self.agent_id,
            self.step,
            len(calls),
            workers,
        )
        with ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix=f"spawn-{self.agent_id}"
        ) as pool:
            results = list(pool.map(self._execute_tool, calls))
        # Registers are written afterwards, in the order the model asked, so a
        # concurrent step leaves the register file exactly where a serial one
        # would — register 0 holds the last call of the step, not the first
        # child to finish.
        for result in results:
            self._store_result(result)
        return results

    def _execute_tool(self, call) -> ToolResult:
        """Run one call and time it, touching no register."""
        clock = time.monotonic()
        result = self.tools.execute(call)
        result.record["duration_s"] = round(time.monotonic() - clock, 4)
        return result

    def _run_tool(self, call) -> ToolResult:
        result = self._execute_tool(call)
        self._store_result(result)
        return result

    def _store_result(self, result: ToolResult) -> None:
        status = result.status
        if result.register_id is not None:
            cut = self.registers.store(result.register_id, result.payload)
            if cut:
                # 0.0.7a's run read 190 lines of a file into a 512-char register,
                # saw the first 512, decided it had not seen enough, and read a
                # different range — for 435 steps. The dump tagged the register
                # `truncated` and that was not enough: register 0 now says what
                # was lost and where the rest is, in the one place the agent
                # always reads.
                status = self._truncation_notice(result, status)
        self.registers.store(RESULT_REGISTER, status)
        logger.info(
            "agent %s step %d: %s -> %s",
            self.agent_id,
            self.step,
            result.name,
            status.splitlines()[0] if status else "",
        )

    def _truncation_notice(self, result: ToolResult, status: str) -> str:
        """What register 0 says when a result did not fit its destination.

        The numbers, and then the two ways out: the canvas is the register sized
        for content, and the result file holds the whole thing either way.
        """
        register_id = result.register_id
        kept = self.registers.limit(register_id)
        whole = len(result.payload)
        canvas = self.config.canvas_id
        # Short, because register 0 is a normal register and this has to survive
        # its own limit. The path stays first: it is the thing to act on.
        remedy = (
            f"canvas (register {canvas}, {self.config.max_canvas_length})"
            if register_id != canvas
            else "`load(start=N)` in pieces"
        )
        return (
            f"{status}\nCUT: {whole} chars, register {register_id} kept {kept}. "
            f"You are not seeing all of it — for the rest use the {remedy}, "
            f"or load the file above. Re-running the command shows no more."
        )

    def _result(self, *, ok: bool, response: Any, error: str | None = None) -> AgentResult:
        handoff = None if ok else self._write_handoff(error)
        segment_steps = self.step - self._segment_start
        self.trajectory.append(
            {
                "step": self.step + 1,
                "role": "final",
                "agent_id": self.agent_id,
                "ok": ok,
                "response_file": self.workspace.display(self.response_path),
                "response": response,
                "error": error,
                "ended_at": _now(),
                "segment_duration_s": round(
                    time.monotonic() - getattr(self, "_segment_started", time.monotonic()), 3
                ),
                "segment_steps": segment_steps,
                "charged": self.charged,
                "cost": segment_steps + self.charged,
                "stalled": self.stalled,
                "progress": self.progress.summary(),
                "registers": self.registers.snapshot(),
            }
        )
        return AgentResult(
            agent_id=self.agent_id,
            ok=ok,
            response=response,
            response_path=self.response_path,
            trajectory_path=self.trajectory.path,
            steps=self.step,
            error=error,
            handoff_path=handoff,
            check_failure=(
                self._check_result
                if not ok and (self._check_result or {}).get("exit_code")
                else None
            ),
            segment_steps=segment_steps,
            # Not `+ self.stalled`. The surcharge is a rate inside this frame's
            # own allowance — it makes a livelocked frame run out sooner — and
            # billing a parent for it as well would let a child cost more than
            # the allocation the parent made, which is the one thing 0.0.8c §5
            # exists to prevent. The parent learns about the livelock from the
            # handoff instead, where it can act on it by changing the brief.
            cost=segment_steps + self.charged,
        )

    def _write_handoff(self, error: str | None) -> Path:
        """The account an unfinished agent leaves behind.

        Three children in a row at a small geometry ran out of steps, and each
        parent was told only that — so it re-dispatched the whole job, and the
        seventy steps of reading the child had done were spent again. What the
        child knew is in its registers: the target it set itself, the summary of
        what it established, and the step it was on.
        """
        path = self.workspace.handoff_path(self.agent_id)
        path.write_text(
            json.dumps(
                {
                    "agent_id": self.agent_id,
                    "steps": self.step,
                    "error": error,
                    "target": self.registers.values[TARGET_REGISTER],
                    "summary": self.registers.values[SUMMARY_REGISTER],
                    "last_step": self.registers.values[STEP_REGISTER],
                    "check": self.check,
                    # 0.0.8d §4.1: a parent deciding whether to resume this child
                    # or re-brief it wants to know whether it was moving. A child
                    # that ran out of steps having stalled nine in a row is not a
                    # child to hand more steps to unchanged.
                    "progress": self.progress.summary(),
                    # A child that died against a check its parent wrote wrongly
                    # has nothing to show for it unless the parent can see the
                    # check. The parent is the only one who can change it.
                    "last_check": self._check_result,
                    "instruction_file": self.workspace.display(self.instruction_path),
                    "trajectory_file": self.workspace.display(self.trajectory.path),
                    "resume_with": f'resume(agent_id="{self.agent_id}", max_steps=N)',
                },
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
        return path

    # --- response ------------------------------------------------------
    def read_response(self) -> tuple[bool, Any, str | None]:
        """(finished, value, error) — the error goes to register 0 as feedback."""
        name = self.workspace.display(self.response_path)
        if not self.response_path.exists():
            return False, None, None
        try:
            raw = self.response_path.read_text(encoding="utf-8")
        except OSError as exc:
            return False, None, f"error: could not read {name}: {exc}"
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            return False, None, (
                f"error: {name} is not valid JSON ({exc}); rewrite the whole file"
            )
        if self.return_schema is not None:
            try:
                jsonschema.validate(value, self.return_schema)
            except jsonschema.exceptions.SchemaError as exc:
                return False, None, f"error: the required schema is itself invalid: {exc.message}"
            except jsonschema.ValidationError as exc:
                location = "/".join(str(part) for part in exc.absolute_path) or "(root)"
                return False, None, (
                    f"error: {name} does not match the required schema at {location}: "
                    f"{exc.message}; rewrite the whole file"
                )
        # 0.0.8c §3: a return that fails its check is not a return. This is the
        # last thing that happens, because a response which does not parse has
        # nothing for a check to be about.
        if self.check and self.config.run_checks:
            failure = self._check_failed()
            if failure:
                return False, None, failure
        return True, value, None

    def _observe_check(self) -> None:
        """Run the acceptance test after a step and keep its verdict for the dump.

        7.3 asks for write-then-verify to replace acquiring an interface, and
        0.0.8b §1 says why it is affordable: a check is a machine operation, so
        it is unbounded and costs no width. What it needed to become a habit
        rather than advice was to be *there* — one line at the top of every
        dump, saying whether the work currently passes.

        A check that takes longer than `check_live_seconds` stops being run this
        way. A test suite is a fine acceptance test and a poor heartbeat, and
        the scaffold can tell which one it was given by running it once.
        """
        if not (self.check and self.config.run_checks and self.config.check_every_step):
            return
        if self._check_is_slow:
            return
        result = self._run_check_now()
        if result["duration_s"] > self.config.check_live_seconds:
            self._check_is_slow = True
            self._check_line = (
                f"{self._check_line} — too slow ({result['duration_s']:.0f}s) to run "
                "every step, so this is the last time; run it yourself."
            )

    def _run_check_now(self) -> dict[str, Any]:
        """One run of the check, recorded and turned into a line for the dump."""
        clock = time.monotonic()
        code, output = self.run_check(self.check)
        path = self.workspace.output_path(self.agent_id, self.step, "check")
        path.write_text(
            json.dumps(
                {
                    "tool": "check",
                    "command": self.check,
                    "exit_code": code,
                    "output": output,
                    "passed": code == 0,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        display = self.workspace.display(path)
        first = next((line for line in output.strip().splitlines()[::-1] if line.strip()), "")
        self._last_check = self._check_result = {
            "command": self.check,
            "exit_code": code,
            "file": display,
            "duration_s": round(time.monotonic() - clock, 3),
        }
        self._check_step = self.step
        # One line, because it is paid for on every step that follows.
        self._check_line = (
            "passes."
            if code == 0
            else f"FAILS (exit {code}): {first[:160]} — {display}"
        )
        logger.info(
            "agent %s step %d: check %s",
            self.agent_id, self.step, "passed" if code == 0 else f"failed (exit {code})",
        )
        return self._last_check

    def _check_failed(self) -> str | None:
        """Whether a landed response is refused, and what register 0 should say.

        Reuses this step's verdict when there is one: the check runs after the
        tools and a response written by those tools is read afterwards, so the
        two would otherwise pay for the same command twice.
        """
        result = (
            self._last_check
            if self._check_step == self.step and self._last_check is not None
            else self._run_check_now()
        )
        code, display = result["exit_code"], result["file"]
        if code == 0:
            return None
        first = self._check_line.split(": ", 1)[-1].split(" — ")[0] if self._check_line else ""
        # Both of these have to survive register 0, which is 208 chars at the
        # 0.0.8 geometry, so the path comes first and the prose is short. The
        # check itself is already in the system message and is not repeated.
        if code in CHECK_DID_NOT_RUN:
            return (
                f"{display}\nerror: check exit {code} — that command does not exist here, "
                "so it says nothing about your work. Your parent wrote it."
            )
        return (
            f"{display}\nerror: check exit {code}, response refused; fix the work and it "
            f"is taken as it stands. {first[:100]}"
        )

    # --- the summary ---------------------------------------------------
    def _close_step(
        self,
        record: dict[str, Any],
        thinking: str,
        action: str,
        results: list[ToolResult],
        *,
        cut_off: bool,
        last: bool = False,
    ) -> None:
        """End a step: hand it to the summariser, and hold its record until then.

        The summary of step N is written *while step N+1 is being generated*,
        and lands in register 4 in time for the dump of step N+2. Nothing is
        lost by that: register 3 always holds the step immediately before, so
        the pair the agent reads — the summary through N, register 3 = step N+1
        — still covers every step of the run, with the overlap the two used to
        have taken out of it rather than a gap put in.

        What it buys is the wall-clock. Across 0.0.7e's 1,368 steps the
        summariser was 5.3 of the 16.3 hours the agents spent, all of it with
        the run standing still; run alongside a generation that takes twice as
        long, it costs nothing at all.

        The record waits for its summary so the trajectory keeps saying what it
        always said — one line per step, carrying the summary that followed it.

        It is also where the step's progress is measured (0.0.8d §4.1) — after
        the tools have run, after the check, and after the response was read, so
        that everything the step could have left behind has landed.
        """
        progress = record["progress"] = self.progress.record(
            target=self.registers.values[TARGET_REGISTER],
            check=self._check_line,
        )
        surcharge = self._stall_surcharge(progress["stall_streak"])
        if surcharge:
            self.stalled += surcharge
            progress["surcharge"] = surcharge
        if not self.summarizes or last:
            # A run that is over does not need a summary handed to a step that
            # will never happen.
            self.trajectory.append(record)
            return

        limit = self.registers.limit(SUMMARY_REGISTER)
        arguments = dict(
            agent_id=self.agent_id,
            step=self.step,
            instruction=self.instruction,
            target=self.registers.values[TARGET_REGISTER],
            previous_summary=self.registers.values[SUMMARY_REGISTER],
            thinking=thinking,
            action=action,
            observations=summary_module.describe_observations(
                results, self.config.max_step_half_length
            ),
            cut_off=cut_off,
            limit=limit,
        )
        assert self._summary_pool is not None
        self._pending = (record, self._summary_pool.submit(self._summarise, arguments))

    def _summarise(self, arguments: dict[str, Any]) -> tuple[Any, float]:
        """The summariser call itself, on its own thread. Touches no register.

        One tool-less generation, retried whole if what comes back does not fit
        and truncated after the last attempt — the rules live in `Summariser`.
        What is given is one summary and one step, never the history, so the
        cost per step is flat however long the run gets.
        """
        clock = time.monotonic()
        update = self.summariser.update(**arguments)
        return update, time.monotonic() - clock

    def _collect_summary(self) -> None:
        """Take delivery of the pending summary, write register 4, file the step.

        A summariser that fails leaves the old summary standing. Losing the
        run's memory over one bad call would be a far worse outcome than a
        summary that is one step out of date, and the step it missed is still in
        register 3 and in the trajectory.
        """
        if self._pending is None:
            return
        record, future = self._pending
        self._pending = None
        step = record.get("step", self.step)
        try:
            update, seconds = future.result()
        except Exception as exc:  # nothing about the summary may end a run
            logger.warning(
                "agent %s step %d: summariser thread failed (%s: %s)",
                self.agent_id, step, type(exc).__name__, exc,
            )
            record.setdefault("timing", {})["summary_s"] = 0.0
            record["summary"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            self.trajectory.append(record)
            return

        if update.ok:
            # The truncation flag comes from the summariser: a cut that happened
            # before the value got here is one the length alone cannot report.
            self.registers.store(
                SUMMARY_REGISTER, update.summary, truncated=update.truncated
            )
            if update.truncated:
                logger.warning(
                    "agent %s step %d: summary truncated to %d chars after %d attempts",
                    self.agent_id,
                    step,
                    update.limit,
                    len(update.attempts),
                )
        else:
            logger.warning(
                "agent %s step %d: summary not updated (%s)",
                self.agent_id,
                step,
                update.error,
            )
        record.setdefault("timing", {})["summary_s"] = round(seconds, 3)
        record["summary"] = update.record()
        self.trajectory.append(record)

    # --- recursion -----------------------------------------------------
    def resume_child(self, agent_id: str, max_steps: int | None = None) -> AgentResult:
        """Give an unfinished child more steps, with its registers as they were.

        The plumbing is `--resume`, which has existed since 0.0.2 for a human at
        a terminal; what 0.0.7h adds is that a parent can reach it. A child that
        ran out is a process to continue, not work to redo — and at a small
        geometry, where a step buys less, running out is ordinary.
        """
        overrides = {} if max_steps is None else {"max_steps": max_steps}
        child = Agent.resume(
            workspace=self.workspace,
            model=self.model,
            agent_id=agent_id,
            overrides=overrides,
        )
        logger.info(
            "agent %s step %d: resuming %s from step %d (%s)",
            self.agent_id, self.step, agent_id, child.step,
            "no step cap" if child.config.max_steps is None
            else f"{child.config.max_steps} more steps",
        )
        result = child.run()
        self.charge(result.cost)
        return result

    def spawn_child(
        self,
        brief: str,
        return_schema: dict[str, Any],
        max_steps: int | None = None,
        *,
        check: str | None = None,
        goal: str | None = None,
        write: str | None = None,
        depth_allowance: int | None = None,
    ) -> AgentResult:
        """A fresh agent in this workspace, with a budget out of its parent's.

        Until 0.0.7f a child inherited the whole of its parent's `max_steps`,
        and there was no way to say otherwise: 0.0.7e's root asked for a digest
        of one part of a document and got a child that spent 278 steps and six
        and a half hours on it, invisibly. 0.0.7f let a parent bound it; 0.0.8c
        makes the bound come out of the parent's own budget, so it is an
        allocation rather than a wish.

        `depth_allowance` is the other half of 0.0.8c §6: the scaffold picks no
        ceiling, and a parent that wants one for its subtree passes it down the
        way it passes steps. None means the child inherits whatever the parent
        was allowed.
        """
        config = self.config
        if max_steps is not None:
            config = dataclasses.replace(config, max_steps=max_steps)
        depth = self.depth + 1
        from_parent = self.depth_from_parent
        if depth_allowance is not None:
            config = dataclasses.replace(config, max_depth=depth + depth_allowance)
            from_parent = True
        child = Agent(
            config=config,
            workspace=self.workspace,
            model=self.model,
            instruction=brief,
            return_schema=return_schema,
            depth=depth,
            check=check,
            goal=goal,
            write=write,
            depth_from_parent=from_parent,
        )
        logger.info(
            "agent %s step %d: spawning %s at depth %d (%s)",
            self.agent_id,
            self.step,
            child.agent_id,
            child.depth,
            "no step cap" if config.max_steps is None else f"{config.max_steps} steps",
        )
        result = child.run()
        self.charge(result.cost)
        return result
