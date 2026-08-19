"""0.0.8a §3 — the registers are files, so a value moves without a generation.

Until 0.0.8 there was one route out of a register: the model read the value off
the dump and typed it again. Register to command, register to register,
register to a child's brief — all three were re-generation, in a scaffold whose
writing rate is its bottleneck. These tests are about the four things the shell
can now do instead, and about the one thing it still may not.
"""

import pytest

from infinite.config import Config
from infinite.regfile import REGDIR_VAR

from .conftest import agent, build_agent, run  # noqa: F401


def test_a_register_value_reaches_a_command_without_being_retyped(agent):
    agent.registers.store(6, "needle in the haystack")
    result = run(agent, "bash", command='printf "%s" "$R6"', register_id=7)

    assert agent.registers.values[7] == "needle in the haystack"
    # And the command that ran is the one the model wrote: the substitution is
    # the shell's, and what the trajectory records is `$R6` (0.0.8a §6).
    assert result.record["command"] == 'printf "%s" "$R6"'


def test_a_command_writes_a_register_by_writing_its_file(agent):
    agent.registers.store(6, "one\ntwo\nthree\n")
    run(agent, "bash", command=f'grep -c . "${REGDIR_VAR}/6" > "${REGDIR_VAR}/7"')

    assert agent.registers.values[7].strip() == "3"


def test_register_to_register_is_cp(agent):
    """The copy 0.0.8a would otherwise have needed a tool schema for."""
    agent.registers.store(6, "a value that already exists somewhere")
    run(agent, "bash", command=f'cp "${REGDIR_VAR}/6" "${REGDIR_VAR}/8"')

    assert agent.registers.values[8] == "a value that already exists somewhere"


def test_a_register_holding_a_path_is_dereferenced_by_the_shell(agent):
    (agent.workspace.root / "src.txt").write_text("line1\nline2\nline3\n")
    agent.registers.store(6, "src.txt")
    run(agent, "bash", command=f'sed -n 1,2p "$R6" > "${REGDIR_VAR}/9"')

    assert agent.registers.values[9] == "line1\nline2\n"


def test_the_shell_reports_what_it_wrote_in_register_0(agent):
    result = run(agent, "bash", command=f'echo hello > "${REGDIR_VAR}/6"')

    assert "shell wrote r6=6c" in result.status
    assert result.record["registers_written"] == ["r6=6c"]


def test_a_value_too_long_for_its_register_is_cut_and_said_to_be(agent):
    limit = agent.registers.limit(6)
    run(agent, "bash", command=f'printf "x%.0s" $(seq 1 500) > "${REGDIR_VAR}/6"')

    assert len(agent.registers.values[6]) == limit
    assert agent.registers.truncated[6] is True
    assert f"r6={limit}c (cut from 500)" in agent.registers.values[0]


def test_the_canvas_is_writable_from_the_shell_like_any_other_register(agent):
    canvas = agent.config.canvas_id
    run(agent, "bash", command=f'seq 1 50 > "${REGDIR_VAR}/{canvas}"')

    assert agent.registers.values[canvas].startswith("1\n2\n")
    assert len(agent.registers.values[canvas]) <= agent.config.max_canvas_length


def test_a_write_to_a_system_register_is_refused_and_put_back(agent):
    """Registers 0-4 are the system's, the way `check_destination` says."""
    agent.registers.store(2, "the target as it stands")
    result = run(agent, "bash", command=f'echo hijacked > "${REGDIR_VAR}/2"')

    assert agent.registers.values[2] == "the target as it stands"
    assert "r2 refused (system-written)" in result.status
    # And the file agrees with the register again, so the next command does not
    # read a value the dump does not show.
    assert agent.regshell.path(2).read_text() == "the target as it stands"


def test_reading_a_system_register_is_allowed(agent):
    agent.registers.store(2, "read the corpus, then answer")
    run(agent, "bash", command=f'cat "${REGDIR_VAR}/2" > "${REGDIR_VAR}/6"')

    assert agent.registers.values[6] == "read the corpus, then answer"


def test_deleting_a_register_file_does_not_clear_the_register(agent):
    agent.registers.store(6, "still here")
    run(agent, "bash", command=f'rm -f "${REGDIR_VAR}/6"')

    assert agent.registers.values[6] == "still here"


def test_values_with_quotes_and_newlines_survive_the_round_trip(agent):
    nasty = "it's \"quoted\"\nand $HOME and `backticks`\n"
    agent.registers.store(6, nasty)
    run(agent, "bash", command=f'cat "${REGDIR_VAR}/6" > "${REGDIR_VAR}/7"')

    assert agent.registers.values[7] == nasty
    # And the exported variable is the same string, not the shell's idea of it.
    run(agent, "bash", command=f'printf "%s" "$R6" > "${REGDIR_VAR}/8"')
    assert agent.registers.values[8] == nasty


def test_the_registers_live_outside_the_work(agent):
    """0.0.8a's second open question: the scratch directory, not the workspace."""
    listing = run(agent, "bash", command="ls -a", register_id=6)

    assert "reg" not in listing.record["output"].split()
    assert agent.regshell.directory.is_relative_to(agent.scratch)


def test_the_scaffold_can_be_run_without_any_of_this(tmp_path):
    """A knob, because 0.0.8a's first open question is whether transit costs."""
    built = build_agent(tmp_path, registers_as_files=False)
    built.step = 1
    try:
        assert built.regshell is None
        built.registers.store(6, "value")
        result = run(built, "bash", command='printf "%s" "$R6"', register_id=7)
        assert built.registers.values[7] == ""
        assert result.record["registers_written"] == []
        assert "$REGDIR" not in built.system_message()
    finally:
        built.bash.close()
