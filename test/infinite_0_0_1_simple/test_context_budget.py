"""What one generation costs, measured before it is made (0.0.7f-short).

Every version through 0.0.7f grew one half of the request or the other — the
registers from 47KB to 66KB, the output cap from 8192 to 16384 — and nothing
anywhere added the two together. This is that sum, recorded in the trajectory
and, when a ceiling is set, enforced before the run starts.
"""

import json

import pytest

from infinite.agent import Agent
from infinite.config import CHARS_PER_TOKEN, SHORT, Config, short_config
from infinite.workspace import Workspace

from .fake_model import FakeModel, step, text, tool_use


def make(tmp_path, **overrides):
    return Agent(
        config=Config(**overrides),
        workspace=Workspace(tmp_path / "run"),
        model=FakeModel([]),
        instruction="do the thing",
    )


def test_the_dump_ceiling_is_every_register_at_its_limit(tmp_path):
    config = Config(
        num_registers=8, max_register_length=100, max_special_length=200,
        max_step_half_length=50, max_canvas_length=400, num_special_registers=5,
    )
    content = sum(config.register_limit(i) for i in range(config.num_registers))
    assert content == 100 + 100 + 200 + 121 + 200 + 100 + 100 + 400
    # Plus the header line every register emits, whether or not it holds
    # anything, and the `[Step]` line at its very longest.
    assert config.dump_chars > content
    assert config.dump_chars < content + 60 * config.num_registers + 300


def test_the_budget_counts_both_halves_of_a_generation(tmp_path):
    agent = make(tmp_path)
    budget = agent.context

    assert budget["dump_chars"] == agent.config.dump_chars
    assert budget["output_tokens"] == agent.config.workspace_tokens
    assert budget["input_tokens"] == int(
        (budget["fixed_chars"] + budget["dump_chars"]) / CHARS_PER_TOKEN
    )
    assert budget["total_tokens"] == budget["input_tokens"] + budget["output_tokens"]
    # The fixed half is the system message and the tool schemas as sent.
    assert budget["fixed_chars"] == len(agent.system_message()) + len(
        json.dumps(agent.tools.specs(), ensure_ascii=False)
    )


def test_a_run_records_what_one_generation_can_cost(tmp_path):
    agent = make(tmp_path)
    agent.model.script = [
        step(tool_use("bash", command=f"printf '{{}}' > {agent.response_path.name}", register_id=5))
    ]
    agent.run()

    header = agent.trajectory.read()[0]
    assert header["context"] == agent.context
    assert header["context"]["total_tokens"] > 0


def test_a_ceiling_the_registers_alone_break_is_refused_by_the_config():
    with pytest.raises(ValueError, match="over the max_context_tokens"):
        Config(max_context_tokens=1000)


def test_a_ceiling_the_prose_breaks_is_refused_by_the_agent(tmp_path):
    """The registers fit; the system message and tool schemas do not."""
    fits = short_config()
    assert fits.context_tokens(0)["total_tokens"] < 10000  # geometry alone is fine
    with pytest.raises(ValueError, match="over the max_context_tokens"):
        Agent(
            config=short_config(max_context_tokens=4000),
            workspace=Workspace(tmp_path / "run"),
            model=FakeModel([]),
            instruction="do the thing",
        )


def test_no_ceiling_by_default(tmp_path):
    assert Config().max_context_tokens is None
    agent = make(tmp_path)  # 0.0.7f's own geometry is far over any short budget
    assert agent.context["total_tokens"] > 10000


def test_the_target_can_be_smaller_than_the_summary(tmp_path):
    """Two registers of the same tier, written by writers with different problems."""
    assert Config().max_target_length is None  # they share, as they always did
    shared = Config()
    assert shared.register_limit(2) == shared.register_limit(4)

    split = short_config()
    assert split.register_limit(2) < split.register_limit(4)
    # And nothing else moved: register 3 keeps its own rule, normal ones theirs.
    assert split.register_limit(3) == 2 * split.max_step_half_length + 21
    assert split.register_limit(5) == split.max_register_length


def test_the_short_configuration_fits_under_its_ceiling(tmp_path):
    """0.0.7g bought 8,000; 0.0.8's own prose costs about 1,200 tokens more.

    The register geometry is 0.0.7g's to the character — this preset is still
    that *input* — and what moved is the fixed half: the frame discipline, the
    optional destination, `lookup`, `resume`, and the sentence that makes the
    registers reachable from the shell. 7.4 asks for that trade to be made
    explicitly, which is what the number in the config is.
    """
    agent = Agent(
        config=short_config(),
        workspace=Workspace(tmp_path / "run"),
        model=FakeModel([]),
        instruction="do the thing",
        return_schema={"type": "object", "properties": {"answer": {"type": "string"}}},
    )

    assert agent.config.max_context_tokens == 9000
    assert agent.context["total_tokens"] <= 9000
    # And the agent's own share of it is reported beside the total, because a
    # scaffold that grows its prose to buy the agent room should show both.
    assert agent.context["working_set_chars"] == 5 * 208 + 1536 + 704
    # And it is a real scaffold, not a stub: seven tools, five special
    # registers, a canvas, and room to land a call in every free register.
    assert [t["name"] for t in agent.tools.specs()] == [
        "bash", "load", "set", "set_target", "lookup", "spawn", "resume",
    ]
    assert agent.config.canvas_id == 10
    canvas = agent.registers.limit(agent.config.canvas_id)
    assert canvas == max(agent.registers.limit(i) for i in range(agent.config.num_registers))
    assert canvas >= 1536  # still an excerpt of a file, not a line of one
    # And the summariser is told a budget its register can hold the overshoot of:
    # at 768 it went over on every attempt it made, at 812-1082 chars.
    assert agent.registers.limit(4) >= 2 * agent.config.summary_target_chars


def test_the_short_preset_is_only_a_geometry():
    """Nothing about the mechanism changes — only how much room each part gets."""
    short, full = short_config(), Config()
    for field in (
        "model", "effort", "thinking", "num_special_registers", "register_layout",
        "summary", "summary_model", "summary_effort", "max_depth", "spawn_workers",
        "charge_children", "registers_as_files", "lookup", "run_checks",
        "step_retry_seconds", "api_max_retries", "firewall",
    ):
        assert getattr(short, field) == getattr(full, field), field
    assert set(SHORT) == {
        "num_registers", "max_register_length", "max_special_length",
        "max_target_length", "max_step_half_length", "max_canvas_length",
        "workspace_tokens", "summary_target_chars", "summary_max_tokens",
        "max_context_tokens",
    }
