"""Shared fixtures for the 0.0.8 tests."""

import json

import pytest

from infinite.agent import Agent
from infinite.config import Config
from infinite.model import ToolCall
from infinite.workspace import Workspace

from test.infinite_0_0_1_simple.fake_model import FakeModel


def build_agent(tmp_path, **overrides):
    config = Config(
        **{
            "max_register_length": 120,
            "max_special_length": 240,
            "max_step_half_length": 60,
            "max_canvas_length": 400,
            "summary": False,
            "bash_timeout": 10.0,
            "max_steps": 40,
            **overrides,
        }
    )
    return Agent(
        config=config,
        workspace=Workspace(tmp_path / "run"),
        model=FakeModel([]),
        instruction="do the thing",
    )


@pytest.fixture
def agent(tmp_path):
    built = build_agent(tmp_path)
    built.step = 1
    yield built
    built.bash.close()


def call(name, **params):
    return ToolCall(id="toolu_test", name=name, input=params)


def run(agent, name, **params):
    """Execute one tool the way the loop does, registers and all."""
    result = agent.tools.execute(call(name, **params))
    if result.register_id is not None:
        agent.registers.store(result.register_id, result.payload)
    agent.registers.store(0, result.status)
    return result


def json_payload(result):
    return json.loads(result.payload)
