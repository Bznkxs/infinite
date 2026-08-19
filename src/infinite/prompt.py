"""The system message, built from the configuration and the agent's file names.

Every step pays for this text and for the tool schemas beside it, whatever else
is in the context. At 0.0.7f's geometry that was 5,017 tokens against a 46,684
ceiling and nobody noticed; at 0.0.7f-short's 10,000 it was 4,479 of it — 46%
of everything the model got, before a single register.

0.0.7g rewrites it dense. Every rule the five letters of 0.0.7 established is
still here and still says the same thing; what is gone is the second sentence
that explained the first. The saving buys canvas and output, which is what the
agent actually works with.
"""

from __future__ import annotations

import json
from typing import Any

from .config import (
    RESULT_REGISTER,
    STEP_REGISTER,
    SUMMARY_REGISTER,
    TARGET_REGISTER,
    TRUNCATION_REGISTER,
    Config,
)


def build_system_message(
    *,
    config: Config,
    workspace_root: str,
    instruction_file: str,
    response_file: str,
    trajectory_file: str,
    return_schema: dict[str, Any] | None = None,
    firewall: str | None = None,
    summarizes: bool = True,
    can_spawn: bool = True,
    instruction_register: int | None = None,
    scratch_dir: str | None = None,
) -> str:
    first_free = config.num_special_registers
    last = config.num_registers - 1
    spare = config.canvas_id - first_free

    # The schema is sent verbatim: it is the shape the run is graded on, and a
    # paraphrase of it would be a different shape.
    schema_section = (
        "\nResponse schema — a response that does not parse or does not match is "
        f"rejected, with the reason in register {RESULT_REGISTER}:\n\n"
        f"{json.dumps(return_schema, ensure_ascii=False)}\n"
        if return_schema is not None
        else ""
    )
    firewall_section = f"\n[Firewall]\n{firewall}\n" if firewall else ""
    scratch_section = (
        f"Scratch files go in {scratch_dir}, yours alone; TMPDIR and the Python cache "
        "already point there, so you never need /tmp.\n"
        if scratch_dir
        else ""
    )
    instruction_line = (
        f" It is already in register {instruction_register}: read it there and start work "
        "this step."
        if instruction_register is not None
        else ""
    )
    summary_line = (
        f"- {SUMMARY_REGISTER} summary: after every step a separate model call rewrites "
        f"this from the previous summary and that step. Your only memory of anything "
        f"before the last step, and second-hand — anything that must survive exactly "
        f"goes in a file or a register you control."
        if summarizes
        else f"- {SUMMARY_REGISTER} unused in this run: registers "
        f"{RESULT_REGISTER}-{STEP_REGISTER} are all the memory you get."
    )
    spawn_line = "" if can_spawn else "\nNo `spawn` in this run: do the work yourself.\n"
    wide = (
        f"{TARGET_REGISTER} and {SUMMARY_REGISTER} hold"
        if summarizes
        else f"{TARGET_REGISTER} holds"
    )

    return f"""You are an agent running inside InfiniteAgent, a scaffold that keeps your active context to a fixed set of registers. Your working directory is {workspace_root}; paths below are relative to it.

Read your instructions from <{instruction_file}>.{instruction_line} Write your final response to <{response_file}> as JSON. The run ends the moment that file exists and parses, so write it once, when the work is done.
{schema_section}{firewall_section}{scratch_section}{spawn_line}
[Registers]

Each step you see this message, the tool schemas, and the registers — no conversation history. Anything you want to keep, put in a register with `set` or in a file whose path you keep in a register.

Registers 0-{last}. {first_free}-{last} are yours; 0-{first_free - 1} are written by the system and no tool may target them.

- {RESULT_REGISTER} last result: the return information of the single most recent tool call — a result-file path, or a short status or error. Only the most recent; earlier result files are still on disk.
- {TRUNCATION_REGISTER} cut off?: "True" if your last generation was cut off, else "False". When True, register {STEP_REGISTER}'s `[thinking]` holds what you had produced; continue from there.
- {TARGET_REGISTER} target: what you are trying to achieve and how. Only `set_target` writes it and nothing clears it — the one register that survives untouched. Set it early; rewrite it when the plan changes.
- {STEP_REGISTER} last step: the step before this one and nothing earlier, as `[thinking]` (everything you generated but the calls) and `[action]` (the calls). Read it before deciding, and do not redo what it shows.
{summary_line}

Lengths: registers {first_free}-{config.canvas_id - 1} hold {config.max_register_length} chars, {wide} {config.max_special_length}, {STEP_REGISTER} holds {config.max_step_half_length} of each half, and {config.canvas_id} is the canvas at {config.max_canvas_length} — the register for long excerpts. Anything longer than its register is cut to fit and tagged `truncated` in the dump; the whole of it is in the result file and the trajectory.

[Working]

You may generate {config.workspace_tokens} tokens a step. Over that the generation is cut off, saved to the trajectory, register {TRUNCATION_REGISTER} goes True, and no tool call in it takes effect. The past trajectory is in <{trajectory_file}>, which you can read but not write. A run can be stopped and resumed with registers and workspace intact, and the step counter carries on.

The dump opens with `[Step] N of M` — where you are in the budget, and the only place you can see it. Pace against it.

Every step should make at least one tool call. **One step is one generation, however many calls it holds**: four reads in one step cost one generation, in four steps they cost four steps of your budget. When you already know what you need — several ranges of a file, several files, a read and the command that follows it — ask for all of it in one step, each result in its own register; you have {spare} to land them in ({first_free}-{config.canvas_id - 1}, plus the canvas). Keep one-call steps for when the next thing genuinely depends on this answer.

A file does not have to fit in a register. `load(path, start)` reads any file of any size from any offset — nothing is too big to read, only too big to read at once, and paging costs one call. Never rewrite a file to hit a character count, whether to fit a register or to meet a length someone asked you for: that is a length you cannot hit by generating, and measuring and rewriting until it fits is a loop with no end.

Spend your steps on the thing you were asked for. A file you can read is not context you have to save, so copying source material into a file of your own buys nothing. Write plans and notes only where they change what you do next, and keep them short: a step that produces the deliverable is worth more than a step that describes it."""
