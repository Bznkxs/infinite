import pytest

from infinite.config import (
    STEP_LABEL_LENGTH,
    STEP_REGISTER,
    SUMMARY_REGISTER,
    TARGET_REGISTER,
    Config,
)
from infinite.registers import RegisterFile, to_text

FIRST_FREE = 5


def small() -> Config:
    return Config(
        max_register_length=10,
        max_special_length=20,
        max_step_half_length=10,
        max_canvas_length=60,
    )


def test_layout():
    registers = RegisterFile(small())
    assert len(registers.values) == 33
    # Three length tiers: normal, the wide special registers, the canvas.
    assert registers.limit(FIRST_FREE) == 10
    assert registers.limit(TARGET_REGISTER) == 20
    assert registers.limit(SUMMARY_REGISTER) == 20
    # Register 3 holds both halves of the last step at once, plus their labels.
    assert registers.limit(STEP_REGISTER) == 10 + 10 + STEP_LABEL_LENGTH
    assert registers.limit(32) == 60  # the canvas is the last register
    # Registers 0-1 hold a path and a flag, so they stay at the normal length.
    assert registers.limit(0) == 10 and registers.limit(1) == 10


def test_the_five_system_written_registers_are_special():
    registers = RegisterFile(small())
    assert all(registers.is_special(i) for i in range(5))
    assert not registers.is_special(FIRST_FREE)


def test_special_and_out_of_range_destinations_are_rejected():
    registers = RegisterFile(small())
    for register_id in range(5):
        assert "special register" in registers.check_destination(register_id)
    assert "must be an integer" in registers.check_destination(33)
    assert "must be an integer" in registers.check_destination(-1)
    assert "must be an integer" in registers.check_destination("2")
    assert "must be an integer" in registers.check_destination(True)
    assert registers.check_destination(FIRST_FREE) is None
    assert registers.check_destination(32) is None


def test_set_rejects_oversized_values_and_changes_nothing():
    registers = RegisterFile(small())
    assert registers.assign(FIRST_FREE, "fits") is None
    error = registers.assign(FIRST_FREE, "x" * 11)
    assert error is not None and "unchanged" in error
    assert registers.values[FIRST_FREE] == "fits"


def test_the_wide_registers_accept_what_a_normal_one_rejects():
    registers = RegisterFile(small())
    value = "x" * 15

    assert registers.assign(FIRST_FREE, value) is not None  # over the normal limit
    assert registers.assign(TARGET_REGISTER, value) is None
    assert registers.values[TARGET_REGISTER] == value


def test_store_truncates_and_flags():
    registers = RegisterFile(small())
    assert registers.store(FIRST_FREE, "x" * 25) is True
    assert registers.values[FIRST_FREE] == "x" * 10
    assert registers.truncated[FIRST_FREE] is True
    assert registers.store(FIRST_FREE, "short") is False
    assert registers.truncated[FIRST_FREE] is False


def test_store_takes_an_explicit_truncation_flag():
    """Register 3 arrives already cut to size, so its length cannot report it."""
    registers = RegisterFile(small())

    assert registers.store(STEP_REGISTER, "fits", truncated=True) is True
    assert registers.values[STEP_REGISTER] == "fits"
    assert registers.truncated[STEP_REGISTER] is True
    assert registers.store(STEP_REGISTER, "fits", truncated=False) is False
    assert registers.truncated[STEP_REGISTER] is False


def test_non_string_values_are_converted():
    assert to_text("a") == "a"
    assert to_text(12) == "12"
    assert to_text({"a": 1}) == '{"a": 1}'
    assert to_text(None) == "null"


def test_render_lists_every_register_and_marks_state():
    registers = RegisterFile(small())
    registers.store(0, "status")
    registers.store(32, "y" * 70)
    rendered = registers.render()

    for i in range(33):
        assert f"--- register {i} (" in rendered
    assert "--- register 0 (6/10 chars; last result, special) ---\nstatus" in rendered
    assert "canvas, truncated" in rendered
    # empty registers are a header only
    assert "--- register 5 (0/10 chars) ---\n--- register 6" in rendered


def test_render_names_the_special_registers():
    """With five of them, the number alone is not enough to act on."""
    rendered = RegisterFile(small()).render()

    assert "--- register 2 (0/20 chars; target, special) ---" in rendered
    assert "--- register 3 (0/41 chars; last step, special) ---" in rendered
    assert "--- register 4 (0/20 chars; summary, special) ---" in rendered


def test_the_geometry_must_be_coherent():
    with pytest.raises(ValueError, match="smaller than the canvas"):
        Config(max_register_length=10, max_special_length=100, max_canvas_length=40)
    with pytest.raises(ValueError, match="not be smaller than a normal one"):
        Config(max_register_length=100, max_special_length=10, max_canvas_length=400)
    with pytest.raises(ValueError, match="system-written"):
        Config(num_special_registers=2)
    with pytest.raises(ValueError, match="smaller than the canvas"):
        # both halves of register 3 have to fit inside the canvas as well
        Config(max_step_half_length=200, max_canvas_length=300)


def test_the_dump_opens_with_the_step_and_the_budget():
    """0.0.7c spent a fifth of a run on a document it never used, with no way to
    see that it was spending it."""
    registers = RegisterFile(Config(max_register_length=50))

    dump = registers.render(step=48, max_steps=500)
    assert dump.splitlines()[0] == "[Step] step 48 of 500 (453 left, including this one)"
    assert dump.splitlines()[1] == "[Registers]"


def test_an_uncapped_run_is_told_the_step_but_no_total():
    registers = RegisterFile(Config(max_register_length=50))

    assert registers.render(step=7, max_steps=None).splitlines()[0] == "[Step] step 7"
    # And a dump asked for without a step is the bare register dump, as before.
    assert registers.render().splitlines()[0] == "[Registers]"


def test_the_last_steps_of_a_budget_say_what_to_spend_them_on():
    """A child that runs out with its work done and no response file has wasted
    all of it — the count was visible, the consequence was not."""
    registers = RegisterFile(Config(max_steps=40))

    assert "write your response file NOW" not in registers.render(step=36, max_steps=40)
    assert "write your response file NOW" in registers.render(step=38, max_steps=40)
    assert "write your response file NOW" in registers.render(step=40, max_steps=40)
    # An uncapped run has no end to warn about.
    assert "write your response file NOW" not in registers.render(step=999)
