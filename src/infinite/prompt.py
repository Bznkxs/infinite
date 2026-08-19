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


#: The brief a lossy caller can write — 0.0.8c §2. Everything a parent can state
#: precisely from a lossy context is a *name*: a goal, some paths, an output
#: location, and the command that decides whether the work is done. Everything
#: it cannot state is method, and the child is the frame that has the facts for
#: it. So the scaffold renders names into a brief rather than asking a parent
#: for prose it is constitutionally unable to supply.
def build_brief(
    *,
    goal: str,
    check: str,
    read: list[str] | None = None,
    write: str | None = None,
    goal_file: str | None = None,
) -> str:
    parts = [f"[Goal]\n{goal.strip()}"]
    if goal_file:
        parts.append(f"[Goal, in full]\nRead {goal_file} before anything else.")
    if write:
        parts.append(f"[Write]\n{write}")
    parts.append(
        "[Check]\nThe scaffold runs this when you write your response. A response that "
        "fails it is refused, the reason lands in register 0, and you keep working.\n\n"
        f"    {check.strip()}"
    )
    if read:
        listed = "\n".join(f"- {item}" for item in read)
        parts.append(
            "[Start here]\nPointers, not limits — read anything you need, and expect "
            f"this list to be incomplete.\n{listed}"
        )
    return "\n\n".join(parts) + "\n"


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
    check: str | None = None,
    goal: str | None = None,
    write: str | None = None,
    facts_file: str | None = None,
    reg_dir: str | None = None,
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
    # 0.0.8b §2 says the one thing that must be true at every model call is the
    # active goal, stated precisely. The first live 0.0.8 run said what happens
    # when it is not: a child whose goal was a file spent 27 steps re-reading
    # that file, its own instruction and the stub, and wrote nothing. The goal
    # is one sentence and the frame is what the run is; both belong here, where
    # they cost nothing to remember.
    frame_lines = []
    if goal:
        frame_lines.append(f"\n[Goal]\n{goal.strip()}")
    if write:
        frame_lines.append(f"\nPut the work in {write}.")
    if check:
        frame_lines.append(
            "\nYour response is refused unless this command succeeds; the reason lands "
            f"in register {RESULT_REGISTER} and you keep working:\n\n    {check}"
        )
    check_section = ("\n".join(frame_lines) + "\n") if frame_lines else ""
    # 0.0.8a §3 is stated in `bash`'s own schema and not repeated here: both
    # halves of the request are sent every step, so a second copy is a second
    # bill. What belongs here is only the consequence for the register file.
    shell_registers = (
        "\nA value that already exists somewhere should move through the shell "
        f"(`bash`, `$R5`, `{reg_dir}/6`) rather than through a generation of yours; "
        "`set` is for a value you are the author of.\n"
        if reg_dir
        else ""
    )
    memo_line = (
        f"\n`lookup` costs a line, not a page. <{facts_file}> is this run's memo table: "
        "`grep` it before you go looking, append a line for what an index cannot know.\n"
        if facts_file
        else ""
    )
    # 0.0.8b's invariant and 0.0.8c's rule for when to descend. Both are
    # recommendations about how to work rather than determined actions, so by
    # 0.0.8a's rule they are sentences here and not tools.
    frames_section = (
        "\n[Frames]\n\n"
        "One goal at a time: precise about the goal you are on — the names it touches, "
        "where its result goes — lossy about why you are here, and holding nothing about "
        "what is beside it. A vague memory of the wider goal gives a wrong subgoal, "
        "caught on return; a vague memory of a signature gives code that parses and is "
        "wrong, caught by nothing. Precision down, lossiness up.\n\n"
        "Descend at a working-set boundary: spawn when the subgoal needs facts you do "
        "not have and you will not need its facts once it returns. Share most of your "
        "facts with it and inline is cheaper. Do not decompose the task up front — that "
        "is the widest thing you could do; find the parts by descending into them.\n\n"
        "End work with a machine check — an import, a test, a diff. A check against your "
        "own recollection is the mistake it is meant to catch, and a command costs you "
        "no context.\n"
        + memo_line
    )
    # The two wide registers share a limit unless `max_target_length` splits
    # them, and when it does, saying the shared one is simply wrong: `set_target`
    # rejects rather than truncates, so an agent told 1,536 against a real 704
    # loses the whole write and does it again.
    target_limit = config.register_limit(TARGET_REGISTER)
    if not summarizes:
        wide = f"{TARGET_REGISTER} holds {target_limit}"
    elif target_limit == config.max_special_length:
        wide = f"{TARGET_REGISTER} and {SUMMARY_REGISTER} hold {config.max_special_length}"
    else:
        wide = (
            f"{TARGET_REGISTER} holds {target_limit}, {SUMMARY_REGISTER} holds "
            f"{config.max_special_length}"
        )

    return f"""You are an agent running inside InfiniteAgent, a scaffold that keeps your active context to a fixed set of registers. Your working directory is {workspace_root}; paths below are relative to it.

Read your instructions from <{instruction_file}>.{instruction_line} Write your final response to <{response_file}> as JSON. The run ends the moment that file exists and parses, so write it once, when the work is done.
{schema_section}{check_section}{firewall_section}{scratch_section}{spawn_line}
[Registers]

Each step you see this message, the tool schemas, and the registers — no conversation history. Anything you want to keep, put in a register with `set` or in a file whose path you keep in a register.

Registers 0-{last}. {first_free}-{last} are yours; 0-{first_free - 1} are written by the system and no tool may target them. A tool's `register_id` is optional: omit it and the payload is discarded while the status still lands in register {RESULT_REGISTER}, so a register you never name keeps what it holds through a step that reads four files.

- {RESULT_REGISTER} last result: the return information of the single most recent tool call — a result-file path, or a short status or error. Only the most recent; earlier result files are still on disk.
- {TRUNCATION_REGISTER} cut off?: "True" if your last generation was cut off, else "False". When True, register {STEP_REGISTER}'s `[thinking]` holds what you had produced; continue from there.
- {TARGET_REGISTER} target: what you are trying to achieve and how. Only `set_target` writes it and nothing clears it — the one register that survives untouched. Set it early; rewrite it when the plan changes.
- {STEP_REGISTER} last step: the step before this one and nothing earlier, as `[thinking]` (everything you generated but the calls) and `[action]` (the calls). Read it before deciding, and do not redo what it shows.
{summary_line}

{shell_registers}
Lengths: registers {first_free}-{config.canvas_id - 1} hold {config.max_register_length} chars, {wide}, {STEP_REGISTER} holds {config.max_step_half_length} of each half, and {config.canvas_id} is the canvas at {config.max_canvas_length} — the register for long excerpts. Anything longer than its register is cut to fit and tagged `truncated` in the dump; the whole of it is in the result file and the trajectory.

[Working]

You may generate {config.workspace_tokens} tokens a step. Over that the generation is cut off, saved to the trajectory, register {TRUNCATION_REGISTER} goes True, and no tool call in it takes effect. The past trajectory is in <{trajectory_file}>, which you can read but not write. A run can be stopped and resumed with registers and workspace intact, and the step counter carries on.

The dump opens with `[Step]`: how deep you are, which step this is, and what budget is left. A child's steps come out of that budget, so a delegation you cannot afford is one you can see. Pace against it.

Every step should make at least one tool call. **One step is one generation, however many calls it holds**: four reads in one step cost one generation, in four steps they cost four steps of your budget. When you already know what you need — several ranges of a file, several files, a read and the command that follows it — ask for all of it in one step, each result in its own register; you have {spare} to land them in ({first_free}-{config.canvas_id - 1}, plus the canvas). Keep one-call steps for when the next thing genuinely depends on this answer.

A file does not have to fit in a register. `load(path, start)` reads any file of any size from any offset — nothing is too big to read, only too big to read at once, and paging costs one call. Never rewrite a file to hit a character count, whether to fit a register or to meet a length someone asked you for: that is a length you cannot hit by generating, and measuring and rewriting until it fits is a loop with no end.

{frames_section}
Spend your steps on the thing you were asked for. A file you can read is not context you have to save, so copying source material into a file of your own buys nothing. Write plans and notes only where they change what you do next, and keep them short: a step that produces the deliverable is worth more than a step that describes it."""
