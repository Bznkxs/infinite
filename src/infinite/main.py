"""CLI entry point: run one InfiniteAgent on an instruction, or resume one."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .agent import Agent  # importing the package also loads .env
from .config import FRAME, SHORT, WIDE_OUTPUT, Config
from .firewall import FirewallUnavailable
from .model import AnthropicModel
from .workspace import Workspace


def steps_arg(value: str) -> int | None:
    """`--max-steps 40` or `--max-steps none` for no cap."""
    if value.strip().lower() in ("none", "unlimited", "inf"):
        return None
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("max-steps must be at least 1, or 'none'")
    return number


def depth_arg(value: str) -> int | None:
    """`--max-depth 2` or `--max-depth none`, which is the default since 0.0.8c.

    A user is a parent and should get any control a parent has, so the ceiling
    stays available; what changed is that the scaffold no longer picks one.
    """
    if value.strip().lower() in ("none", "unlimited", "inf"):
        return None
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("max-depth must not be negative, or 'none'")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="infinite", description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("instruction", nargs="?", help="The instruction text.")
    source.add_argument(
        "-f", "--instruction-file", help="Read the instruction from this file instead."
    )
    source.add_argument(
        "-r",
        "--resume",
        metavar="AGENT_ID",
        help=(
            "Continue the run with this agent id in --workspace, from its last "
            "recorded step. Its instruction, schema and register geometry come "
            "from the trajectory; --max-steps sets the new budget."
        ),
    )
    parser.add_argument(
        "-w",
        "--workspace",
        default="runs/latest",
        help="Workspace directory for instructions, responses and trajectories.",
    )
    parser.add_argument(
        "-s",
        "--schema",
        help="Path to a JSON Schema the final response must satisfy.",
    )
    parser.add_argument(
        "--allow-read",
        action="append",
        default=[],
        metavar="DIR",
        help=(
            "Let the agent read this directory as well as the workspace. Repeatable. "
            "Writing stays confined to the workspace no matter what."
        ),
    )
    parser.add_argument(
        "--upgrade-registers",
        action="store_true",
        help=(
            "On resume, continue a run that was recorded with a different special-register "
            "layout. Its register 2 becomes the target, register 3 is overwritten with the "
            "next step, and register 4 is cleared for the summary."
        ),
    )
    parser.add_argument(
        "--no-summary",
        action="store_true",
        help=(
            "Leave register 4 empty instead of rewriting the run's summary after every "
            "step. Cheaper, and the agent then remembers only the step immediately "
            "before."
        ),
    )
    parser.add_argument(
        "--summary-target-chars",
        type=int,
        help=(
            "The budget the summariser is given, and the only length it is told "
            "(default 3000). Register 4's real limit is larger and is what a "
            "regeneration is actually triggered by."
        ),
    )
    parser.add_argument(
        "--summary-max-attempts",
        type=int,
        help=(
            "Generations to spend getting the summary under register 4's limit "
            "(default 3). The last one is truncated rather than discarded."
        ),
    )
    parser.add_argument(
        "--summary-model",
        help="Model for the summariser call (default 'claude-haiku-4-5').",
    )
    parser.add_argument(
        "--summary-effort",
        help=(
            "Effort for the summariser call (default 'none' — send no effort at "
            "all, which the small models require)."
        ),
    )
    parser.add_argument(
        "--no-firewall",
        action="store_true",
        help="Run without a sandbox. The agent can then read and write anywhere.",
    )
    # Defaults stay None so a resumed run can tell "not given" from "given"; a
    # fresh run falls back to Config's own defaults.
    parser.add_argument(
        "--short",
        action="store_true",
        help=(
            "0.0.7f-short: the same scaffold with one whole generation — everything "
            "sent plus everything generated — held under 10,000 tokens. 11 registers, "
            "a 2560-char canvas, 2816 output tokens."
        ),
    )
    parser.add_argument(
        "--frame",
        action="store_true",
        help=(
            "0.0.8: 0.0.7i's input with a 4096-char canvas, a structured brief for "
            "`spawn` whose `check` the scaffold runs at the pop, a child's steps charged "
            "to its parent, no depth ceiling, optional destination registers, and the "
            "registers reachable from the shell."
        ),
    )
    parser.add_argument(
        "--check",
        help=(
            "A command that decides whether this run's work is done. The response is "
            "refused until it succeeds. This is what a parent gives a child; a user is "
            "a parent."
        ),
    )
    parser.add_argument(
        "--goal",
        help=(
            "One sentence naming what must be true when the run ends. It goes in the "
            "system message, so it is the one thing the agent never has to re-read. "
            "The instruction file is still where the detail lives."
        ),
    )
    parser.add_argument(
        "--write",
        metavar="PATH",
        help="Where the work goes. Also carried in the system message.",
    )
    parser.add_argument(
        "--no-shell-registers",
        action="store_true",
        help="Do not put the registers in the shell as $R0.. and $REGDIR (0.0.8a §3).",
    )
    parser.add_argument(
        "--no-charge",
        action="store_true",
        help=(
            "Do not debit a parent for its children's steps (0.0.8c §5), which is "
            "0.0.7j's accounting: visible, not charged."
        ),
    )
    parser.add_argument(
        "--no-checks",
        action="store_true",
        help="Do not run a child's `check` at the pop; it becomes advice (0.0.8c §3).",
    )
    parser.add_argument(
        "--no-live-check",
        action="store_true",
        help=(
            "Run the check only when a response lands, not after every step. The "
            "verdict then leaves the dump, and write-then-verify goes back to being "
            "advice (7.3)."
        ),
    )
    parser.add_argument(
        "--wide-output",
        action="store_true",
        help=(
            "0.0.7g's small input with a 8192-token generation instead of 1920 "
            "(16,000 for the whole request). Reading is bounded by paging and does "
            "not need it; writing is bounded by the output cap and does."
        ),
    )
    parser.add_argument(
        "--max-context-tokens",
        type=int,
        help=(
            "Refuse to start if one generation could exceed this many tokens, "
            "counting the system message, the tool schemas, the fullest possible "
            "register dump and the output cap."
        ),
    )
    parser.add_argument("--model")
    parser.add_argument("--effort")
    parser.add_argument("--no-thinking", action="store_true")
    parser.add_argument("--workspace-tokens", type=int)
    parser.add_argument("--max-register-length", type=int)
    parser.add_argument("--max-canvas-length", type=int)
    parser.add_argument(
        "--max-steps",
        type=steps_arg,
        help="Step budget for this run; on resume, how many more steps to allow. "
        "'none' for no cap.",
    )
    parser.add_argument(
        "--max-depth",
        type=depth_arg,
        help=(
            "The deepest `spawn` may go. 'none' (the default) means the scaffold has no "
            "opinion and depth is bounded by the budget instead."
        ),
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="Only print the result.")
    return parser


def collect_overrides(args) -> dict:
    """Only the settings the user actually named, so resume keeps the rest."""
    named = {
        "model": args.model,
        "effort": args.effort,
        "workspace_tokens": args.workspace_tokens,
        "max_register_length": args.max_register_length,
        "max_canvas_length": args.max_canvas_length,

        "summary_target_chars": args.summary_target_chars,
        "summary_max_attempts": args.summary_max_attempts,
        "summary_model": args.summary_model,
        "summary_effort": args.summary_effort,
        "max_context_tokens": args.max_context_tokens,
    }
    overrides = {k: v for k, v in named.items() if v is not None}
    # The preset first, so anything named on the command line still wins.
    if args.short or args.wide_output or args.frame:
        preset = FRAME if args.frame else WIDE_OUTPUT if args.wide_output else SHORT
        overrides = {**preset, **overrides}
    # max_depth is like max_steps: None is a meaningful value, so key off the flag.
    if "--max-depth" in sys.argv:
        overrides["max_depth"] = args.max_depth
    # max_steps is special: None is a meaningful value, so key off the raw flag.
    if "--max-steps" in sys.argv:
        overrides["max_steps"] = args.max_steps
    if args.no_thinking:
        overrides["thinking"] = False
    if args.no_summary:
        overrides["summary"] = False
    if args.no_firewall:
        overrides["firewall"] = False
    if args.no_shell_registers:
        overrides["registers_as_files"] = False
    if args.no_charge:
        overrides["charge_children"] = False
    if args.no_checks:
        overrides["run_checks"] = False
    if args.no_live_check:
        overrides["check_every_step"] = False
    if args.allow_read:
        overrides["readable_dirs"] = tuple(args.allow_read)
    return overrides


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not (args.instruction or args.instruction_file or args.resume):
        print("give an instruction, -f FILE, or --resume AGENT_ID", file=sys.stderr)
        return 2

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(message)s",
        stream=sys.stderr,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    overrides = collect_overrides(args)
    workspace = Workspace(args.workspace)

    try:
        if args.resume:
            config = Config(**overrides)  # only for the model client
            agent = Agent.resume(
                workspace=workspace,
                model=AnthropicModel(config),
                agent_id=args.resume,
                overrides=overrides,
                upgrade_registers=args.upgrade_registers,
            )
            budget = agent.config.max_steps
            print(
                f"resuming {args.resume} from step {agent.step} "
                f"({'no step cap' if budget is None else f'{budget} more steps'})",
                file=sys.stderr,
            )
        else:
            instruction = (
                Path(args.instruction_file).read_text(encoding="utf-8")
                if args.instruction_file
                else args.instruction
            )
            config = Config(**overrides)
            agent = Agent(
                config=config,
                workspace=workspace,
                model=AnthropicModel(config),
                instruction=instruction,
                check=args.check,
                goal=args.goal,
                write=args.write,
                return_schema=(
                    json.loads(Path(args.schema).read_text(encoding="utf-8"))
                    if args.schema
                    else None
                ),
            )
    except FirewallUnavailable as exc:
        print(f"firewall: {exc}", file=sys.stderr)
        return 2
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    result = agent.run()

    print(f"\ntrajectory: {result.trajectory_path}")
    print(f"response:   {result.response_path}")
    if result.ok:
        print(json.dumps(result.response, indent=2, ensure_ascii=False))
        return 0
    print(f"failed at step {result.steps}: {result.error}", file=sys.stderr)
    print(
        f"continue it with: infinite --workspace {args.workspace} "
        f"--resume {result.agent_id} --max-steps N",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
