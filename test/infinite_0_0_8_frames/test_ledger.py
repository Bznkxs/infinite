"""The ledger: duration the summariser cannot keep — 0.0.8e §2.2.

The 0.0.8d reconstruction's root restated one defect in 58 consecutive summaries
and flipped its truth value four times, because a register rewritten whole from
(previous summary + one step) has no channel through which anything can
accumulate. These are the properties that make the ledger a different kind of
object: it counts, it is written by the scaffold, and it says nothing a step did
not actually do.
"""

from __future__ import annotations

import json

from infinite.config import Config, FRAME
from infinite.progress import LEDGER_PATHS, Ledger, read_paths
from infinite.registers import RegisterFile


class FakeResult:
    """Enough of a ToolResult for `read_paths`."""

    def __init__(self, record):
        self.record = record


def stall(ledger: Ledger, steps, *, check="FAILS (exit 1): boom", paths=()):
    for step in steps:
        ledger.record(step=step, moved=False, check=check, paths=list(paths))


# --- it counts, which is the whole point ------------------------------------
def test_a_stalled_run_accumulates_and_a_moving_one_does_not():
    ledger = Ledger()
    stall(ledger, range(1, 32))
    assert ledger.stalled_for == 31
    assert "no progress for 31 steps" in ledger.line(3)

    ledger.record(step=32, moved=True, check="passes.", paths=[])
    assert ledger.stalled_for == 0
    assert ledger.line(3) is None


def test_nothing_is_said_below_the_threshold():
    ledger = Ledger()
    stall(ledger, range(1, 3))
    assert ledger.line(3) is None
    stall(ledger, [3])
    assert ledger.line(3) is not None


def test_a_none_threshold_silences_it_entirely():
    ledger = Ledger()
    stall(ledger, range(1, 40))
    assert ledger.line(None) is None


def test_it_names_the_step_progress_last_happened():
    ledger = Ledger()
    ledger.record(step=1, moved=True, check=None, paths=[])
    stall(ledger, range(2, 10), check=None)
    assert "(last: step 1)" in ledger.line(3)


# --- the check half ---------------------------------------------------------
def test_a_verdict_that_does_not_move_is_reported_with_its_age():
    ledger = Ledger()
    stall(ledger, range(1, 12), check="FAILS (exit 1): ImportError")
    assert "check unchanged 11 steps" in ledger.line(3)


def test_a_verdict_that_changes_resets_its_age_but_not_the_stall():
    ledger = Ledger()
    stall(ledger, range(1, 12), check="FAILS (exit 1): ImportError")
    # A different failure is progress for `Progress`; here it only resets the
    # verdict's age, because the caller decides what counts as movement.
    ledger.record(step=12, moved=False, check="FAILS (exit 1): TypeError", paths=[])
    line = ledger.line(3)
    assert "no progress for 12 steps" in line
    assert "check unchanged" not in line


def test_an_unchecked_run_says_nothing_about_a_check():
    ledger = Ledger()
    stall(ledger, range(1, 12), check=None)
    line = ledger.line(3)
    assert "no progress for 11 steps" in line
    assert "check" not in line


# --- the evidence half ------------------------------------------------------
def test_it_counts_what_the_frame_keeps_reading():
    ledger = Ledger()
    stall(ledger, range(1, 9), paths=["agent.py", "bash_tool.py"])
    line = ledger.line(3)
    assert "read since: " in line
    assert "agent.py x8" in line
    assert "bash_tool.py x8" in line


def test_a_path_read_once_is_not_evidence_of_anything():
    ledger = Ledger()
    stall(ledger, [1, 2, 3], paths=["config.py"])
    ledger.record(step=4, moved=False, check=None, paths=["read_once.py"])
    line = ledger.line(3)
    assert "config.py x3" in line
    assert "read_once.py" not in line


def test_the_read_window_starts_over_when_the_run_moves():
    ledger = Ledger()
    stall(ledger, range(1, 9), paths=["agent.py"])
    ledger.record(step=9, moved=True, check=None, paths=["agent.py"])
    stall(ledger, range(10, 14), paths=["agent.py"])
    # One from the moving step, four since: not the twelve it has read in total.
    assert "agent.py x5" in ledger.line(3)


def test_it_names_at_most_a_handful_of_paths():
    ledger = Ledger()
    many = [f"m{i}.py" for i in range(LEDGER_PATHS + 4)]
    stall(ledger, range(1, 6), paths=many)
    assert ledger.line(3).count(" x") == LEDGER_PATHS


# --- what counts as a read --------------------------------------------------
def test_load_states_its_path_and_bash_is_matched_against_the_workspace():
    known = {"infinite_agent/agent.py", "notes/plan.md"}
    results = [
        FakeResult({"tool": "load", "path": "notes/plan.md", "start": 0}),
        FakeResult({"tool": "bash", "command": "sed -n '85,115p' infinite_agent/agent.py"}),
    ]
    assert read_paths(results, known) == ["notes/plan.md", "infinite_agent/agent.py"]


def test_a_bare_basename_resolves_to_the_file_that_has_it():
    known = {"infinite_agent/bash_tool.py"}
    results = [FakeResult({"tool": "bash", "command": "grep -n 'def __init__' bash_tool.py"})]
    assert read_paths(results, known) == ["infinite_agent/bash_tool.py"]


def test_flags_patterns_and_words_are_not_paths():
    known = {"infinite_agent/agent.py"}
    results = [
        FakeResult({"tool": "bash", "command": "python -m infinite_agent --no-firewall --max-steps 40"}),
        FakeResult({"tool": "bash", "command": "grep -rn 'BashSession(' ."}),
    ]
    assert read_paths(results, known) == []


def test_a_write_is_still_a_read_here_and_that_is_deliberate():
    # The ledger's window closes on *progress*, so a step that wrote is a step
    # that moved and the window resets anyway. Trying to tell a read command
    # from a write one is the shell-parsing this deliberately avoids.
    known = {"infinite_agent/agent.py"}
    results = [FakeResult({"tool": "bash", "command": "cat > infinite_agent/agent.py <<'EOF'"})]
    assert read_paths(results, known) == ["infinite_agent/agent.py"]


# --- where it lands ---------------------------------------------------------
def test_the_dump_carries_it_below_the_stall_line():
    registers = RegisterFile(Config(**FRAME))
    dump = registers.render(
        step=40, max_steps=80, depth=0, stall="looping.", ledger="no progress for 31 steps."
    )
    lines = dump.splitlines()
    assert lines[0].startswith("[Step]")
    assert lines[1].startswith("[Stall]")
    assert lines[2] == "[Ledger] no progress for 31 steps."
    assert lines[3] == "[Registers]"


def test_a_moving_run_pays_nothing_for_it():
    registers = RegisterFile(Config(**FRAME))
    dump = registers.render(step=1, max_steps=80, depth=0)
    assert "[Ledger]" not in dump
    assert "[Stall]" not in dump


def test_the_dump_ceiling_covers_the_extra_line():
    config = Config(**FRAME)
    registers = RegisterFile(config)
    for i in range(config.num_registers):
        registers.store(i, "x" * config.register_limit(i))
    dump = registers.render(
        step=999, max_steps=999, depth=9, charged=99, stalled=99, run=(9999, 99),
        check="FAILS (exit 1): " + "e" * 200,
        stall="s" * 250,
        ledger="l" * 250,
    )
    assert len(dump) <= config.dump_chars


# --- the summary is fed the same signal -------------------------------------
def test_the_summariser_is_told_the_step_left_nothing_behind():
    from infinite.summary import build_input

    body = build_input(
        step=7, instruction="i", target="t", previous_summary="p",
        thinking="th", action="a", observations="o", cut_off=False, budget=600,
        moved=False, stall_streak=5,
    )
    assert "changed nothing durable" in body
    assert "5 step(s) in a row" in body
    assert "Age the line you already have" in body


def test_a_moving_step_is_told_so_without_a_count():
    from infinite.summary import build_input

    body = build_input(
        step=7, instruction="i", target="t", previous_summary="p",
        thinking="th", action="a", observations="o", cut_off=False, budget=600,
        moved=True, stall_streak=0,
    )
    assert "It changed durable state." in body
    assert "step(s) in a row" not in body


def test_without_the_signal_the_section_is_absent_entirely():
    from infinite.summary import build_input

    body = build_input(
        step=7, instruction="i", target="t", previous_summary="p",
        thinking="th", action="a", observations="o", cut_off=False, budget=600,
    )
    assert "Step's effect" not in body


def test_the_summariser_is_forbidden_from_claiming_a_verdict():
    from infinite.summary import system_message

    rules = system_message(agent_id="abcd1234", budget=600)
    assert "Never assert that anything builds, imports, passes, is fixed" in rules
    assert "you report what was tried" in rules


# --- and it is recorded ------------------------------------------------------
def test_the_summary_is_json_serialisable_for_the_trajectory():
    ledger = Ledger()
    stall(ledger, range(1, 6), paths=["agent.py"])
    record = ledger.summary()
    assert json.loads(json.dumps(record))["stalled_for"] == 5
    assert record["most_read_since_progress"]["agent.py"] == 5
