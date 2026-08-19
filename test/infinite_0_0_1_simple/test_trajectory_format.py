"""The trajectory must record enough to replay every request. See
`docs/Trajectory Format.md`."""

import json

from infinite.agent import Agent
from infinite.config import Config
from infinite.trajectory import FORMAT_VERSION
from infinite.workspace import Workspace

from .fake_model import FakeModel, step, text, tool_use


def make_agent(tmp_path, script, *, instruction="summarize input.txt", **overrides):
    config = Config(max_register_length=200, max_special_length=400, max_step_half_length=200, max_canvas_length=800, summary=False, bash_timeout=5.0, **overrides)
    model = FakeModel(script)
    agent = Agent(
        config=config,
        workspace=Workspace(tmp_path / "run"),
        model=model,
        instruction=instruction,
    )
    return agent, model


def write_response(agent, payload):
    escaped = json.dumps(payload).replace("'", "'\\''")
    return tool_use(
        "bash", command=f"printf '%s' '{escaped}' > {agent.response_path.name}", register_id=5
    )


def run(tmp_path, extra_steps=(), **kwargs):
    agent, model = make_agent(tmp_path, [], **kwargs)
    model.script = [*extra_steps, step(write_response(agent, {"ok": True}))]
    agent.run()
    return agent, model, agent.trajectory.read()


def test_header_carries_the_static_half_of_the_request(tmp_path):
    agent, model, records = run(tmp_path)
    header = records[0]

    assert header["format_version"] == FORMAT_VERSION
    assert header["step"] == 0 and header["role"] == "user"
    assert header["workspace_root"] == str(agent.workspace.root)
    assert header["trajectory_file"] == agent.trajectory.path.name
    template = header["context_template"]
    assert template["system"] == model.requests[0]["system"]
    assert template["tools"] == model.requests[0]["tools"]
    assert template["max_tokens"] == model.requests[0]["max_tokens"]


def test_every_step_records_the_messages_it_was_sent(tmp_path):
    agent, model, records = run(
        tmp_path, [step(tool_use("set", value="a note", register_id=8))]
    )
    steps = [r for r in records if r["role"] == "assistant"]

    assert len(steps) == len(model.requests)
    for record, request in zip(steps, model.requests, strict=True):
        assert record["model_input"]["messages"] == request["messages"]
        assert record["model_input"]["max_tokens"] == request["max_tokens"]


def test_the_recorded_request_is_the_whole_request(tmp_path):
    """header.context_template + step.model_input reconstructs the call exactly."""
    _, model, records = run(tmp_path)
    template = records[0]["context_template"]
    first = [r for r in records if r["role"] == "assistant"][0]

    replayed = {
        "system": template["system"],
        "tools": template["tools"],
        "messages": first["model_input"]["messages"],
        "max_tokens": first["model_input"]["max_tokens"],
    }
    sent = model.requests[0]
    assert replayed == {key: sent[key] for key in replayed}
    # A step never overrides the model, effort or thinking — only the summariser
    # does — so the run's config plus these four fields is the whole request.
    assert {sent["model"], sent["effort"], sent["thinking"]} == {None}


def test_a_truncated_step_records_no_observation(tmp_path):
    cut_off = step(text("half a thou"), stop_reason="max_tokens")
    _, _, records = run(tmp_path, [cut_off])
    truncated = [r for r in records if r["role"] == "assistant"][0]

    assert truncated["stop_reason"] == "max_tokens"
    assert "observation" not in truncated


def test_results_are_in_tool_call_order(tmp_path):
    calls = step(
        tool_use("set", value="first", register_id=7),
        tool_use("set", value="second", register_id=8),
    )
    _, _, records = run(tmp_path, [calls])
    results = [r for r in records if r["role"] == "assistant"][0]["observation"]["results"]

    assert [r["register_id"] for r in results] == [7, 8]
    assert [r["value"] for r in results] == ["first", "second"]


def test_every_step_records_where_its_time_went(tmp_path):
    _, _, records = run(tmp_path, [step(tool_use("bash", command="sleep 0.2", register_id=5))])
    first = [r for r in records if r["role"] == "assistant"][0]
    timing = first["timing"]

    assert timing["started_at"].endswith("+00:00")
    assert timing["tools_s"] >= 0.2  # the sleep is in the tool half, not generation
    assert timing["total_s"] >= timing["tools_s"] + timing["generation_s"] - 0.01
    assert first["observation"]["results"][0]["duration_s"] >= 0.2


def test_the_run_is_stamped_end_to_end(tmp_path):
    _, _, records = run(tmp_path)

    assert records[0]["started_at"] <= records[-1]["ended_at"]
    assert records[-1]["segment_duration_s"] >= 0


def test_the_header_records_the_firewall_in_force(tmp_path, monkeypatch):
    readable = tmp_path / "shared"
    readable.mkdir()
    _, _, records = run(tmp_path, readable_dirs=(str(readable),))
    firewall = records[0]["firewall"]

    assert firewall["enabled"] is True
    assert firewall["readable"] == [str(readable)]
    assert "firewall" in records[0]["context_template"]["system"].lower()


def test_the_final_record_closes_the_file(tmp_path):
    _, _, records = run(tmp_path)
    final = records[-1]

    assert final["role"] == "final" and final["ok"] is True
    assert final["step"] == records[-2]["step"] + 1
    assert final["response"] == {"ok": True}
