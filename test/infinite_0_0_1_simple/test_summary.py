"""Register 4: the running summary, and the one generation that keeps it."""

import json

from infinite import summary as summary_module
from infinite.agent import Agent
from infinite.config import NO_EFFORT, SUMMARY_REGISTER, Config
from infinite.summary import Summariser
from infinite.workspace import Workspace

from .fake_model import step, text, tool_use

FIRST_FREE = 5
CANVAS = 32

#: The summariser's system message opens with this and nothing else does.
SUMMARIZER_MARK = "You keep the running summary"


def make_config(**overrides) -> Config:
    return Config(
        max_register_length=200,
        max_special_length=400,
        max_step_half_length=200,
        max_canvas_length=20000,
        bash_timeout=5.0,
        step_retry_seconds=0.0,
        **overrides,
    )


def write_response(name, payload):
    escaped = json.dumps(payload).replace("'", "'\\''")
    return tool_use(
        "bash", command=f"printf '%s' '{escaped}' > {name}", register_id=FIRST_FREE
    )


def is_summary_call(request) -> bool:
    return SUMMARIZER_MARK in request["system"]


class SummaryModel:
    """Parent steps come from a script; summary calls come from `summaries`.

    A `summaries` entry is what one *generation* returns, so a step that has to
    retry consumes more than one. An entry may be a string, None (the model
    answers with nothing) or an Exception (the call itself fails).
    """

    def __init__(self, script, summaries=()):
        self.script = list(script)
        self.summaries = list(summaries)
        self.requests: list[dict] = []
        #: The user message of each summary call, in order.
        self.prompts: list[str] = []

    def generate(
        self, *, system, tools, messages, max_tokens, model=None, effort=None, thinking=None
    ):
        request = {
            "system": system,
            "tools": tools,
            "messages": messages,
            "max_tokens": max_tokens,
            "model": model,
            "effort": effort,
            "thinking": thinking,
        }
        self.requests.append(request)
        if not is_summary_call(request):
            entry = self.script.pop(0) if self.script else step(text("script exhausted"))
            return entry(request) if callable(entry) else entry

        self.prompts.append(messages[0]["content"])
        value = self.summaries.pop(0) if self.summaries else "a summary"
        if isinstance(value, Exception):
            raise value
        return step(text(value)) if value is not None else step()


def make_agent(tmp_path, script, summaries=(), **overrides):
    model = SummaryModel(script, summaries)
    agent = Agent(
        config=make_config(**overrides),
        workspace=Workspace(tmp_path / "run"),
        model=model,
        instruction="count the gammas in corpus.txt",
    )
    return agent, model


def parent_requests(model):
    return [r for r in model.requests if not is_summary_call(r)]


def summary_requests(model):
    return [r for r in model.requests if is_summary_call(r)]


def three_step_run(tmp_path, **kwargs):
    agent, model = make_agent(tmp_path, [], **kwargs)
    model.script = [
        step(
            {"type": "thinking", "thinking": "start by counting lines", "signature": "s"},
            tool_use("bash", command="printf 'a\\nb\\n' > corpus.txt", register_id=FIRST_FREE),
        ),
        step(tool_use("bash", command="wc -l < corpus.txt", register_id=FIRST_FREE + 1)),
        step(write_response(agent.response_path.name, {"gammas": 0})),
    ]
    return agent, model, agent.run()


def four_step_run(tmp_path, **kwargs):
    """Three working steps and the response, so a dump can show step 1's summary.

    Since 0.0.7f a summary is written alongside the next generation, so the
    first dump that can hold the summary of step 1 is the one for step 3.
    """
    agent, model = make_agent(tmp_path, [], **kwargs)
    model.script = [
        step(tool_use("bash", command="printf 'a\\nb\\n' > corpus.txt", register_id=FIRST_FREE)),
        step(tool_use("bash", command="wc -l < corpus.txt", register_id=FIRST_FREE + 1)),
        step(tool_use("bash", command="echo again", register_id=FIRST_FREE + 2)),
        step(write_response(agent.response_path.name, {"gammas": 0})),
    ]
    return agent, model, agent.run()


def notes(agent):
    return [r["summary"] for r in agent.trajectory.read() if r.get("summary")]


# --- the register -------------------------------------------------------
def test_the_summary_register_is_rewritten_after_every_step(tmp_path):
    agent, model, result = three_step_run(
        tmp_path, summaries=["after step 1", "after step 2"]
    )

    assert result.ok
    assert agent.registers.values[SUMMARY_REGISTER] == "after step 2"
    # Every step is summarised, in order, and each summary replaces the last.
    assert [n["summary"] for n in notes(agent)] == ["after step 1", "after step 2"]


def test_the_summary_of_a_step_arrives_one_step_later(tmp_path):
    """It is written while the next generation runs, so it lands after that one.

    Nothing is lost by the delay: register 3 always holds the step immediately
    before, so what the agent reads — the summary through step N and step N+1 in
    full — still covers the whole run.
    """
    _, model, _ = four_step_run(tmp_path, summaries=["after step 1", "after 2", "after 3"])

    dumps = [r["messages"][0]["content"] for r in parent_requests(model)]
    assert "after step 1" not in dumps[0]
    assert "after step 1" not in dumps[1]  # still being written during this one
    assert "after step 1" in dumps[2]
    assert "after 2" in dumps[3] and "after step 1" not in dumps[3]


def test_the_summary_is_named_in_the_dump(tmp_path):
    _, model, _ = four_step_run(tmp_path, summaries=["what happened"])

    dump = parent_requests(model)[2]["messages"][0]["content"]
    assert "--- register 4 (13/400 chars; summary, special) ---\nwhat happened" in dump


def test_no_summary_call_is_made_when_the_summary_is_off(tmp_path):
    agent, model, result = three_step_run(tmp_path, summary=False)

    assert result.ok
    assert agent.registers.values[SUMMARY_REGISTER] == ""
    assert len(parent_requests(model)) == len(model.requests) == 3


def test_the_last_step_is_not_summarised(tmp_path):
    """The run is over; a summary would be handed to a step that never happens."""
    _, model, _ = three_step_run(tmp_path, summaries=["one", "two", "three"])

    assert model.summaries == ["three"]  # only two steps were summarised
    assert len(model.prompts) == 2


# --- it is a generation, not an agent -----------------------------------
def test_the_summariser_is_one_tool_less_call_per_step(tmp_path):
    agent, model, _ = three_step_run(tmp_path, summaries=["one", "two"])

    calls = summary_requests(model)
    assert len(calls) == 2  # two summarised steps, one generation each
    for call in calls:
        assert call["tools"] == []
        assert len(call["messages"]) == 1
    # No sub-agent: the workspace holds exactly one trajectory, and no second
    # instruction or response file was written for a summariser.
    assert [p.name for p in agent.workspace.root.glob("trajectory-*.jsonl")] == [
        agent.trajectory.path.name
    ]
    assert len(list(agent.workspace.root.glob("instruction-*.md"))) == 1


def test_the_summary_call_uses_its_own_cheaper_settings(tmp_path):
    """A small model and no effort at all, by default and not by configuration."""
    _, model, _ = three_step_run(tmp_path, summaries=["s"])

    call = summary_requests(model)[0]
    assert call["model"] == Config.summary_model == "claude-haiku-4-5"
    assert call["effort"] == NO_EFFORT
    assert call["thinking"] is False
    assert call["max_tokens"] == Config.summary_max_tokens
    # The agent's own steps are untouched by any of that.
    assert parent_requests(model)[0]["model"] is None
    assert parent_requests(model)[0]["effort"] is None


def test_the_summary_model_can_be_the_runs_own(tmp_path):
    _, model, _ = three_step_run(
        tmp_path, summaries=["s"], summary_model=None, summary_effort="low"
    )

    call = summary_requests(model)[0]
    assert call["model"] is None  # None means "whatever the run uses"
    assert call["effort"] == "low"


# --- what the summariser is given ---------------------------------------
def test_the_summariser_gets_the_previous_summary_and_the_one_new_step(tmp_path):
    _, model, _ = three_step_run(tmp_path, summaries=["step 1 made corpus.txt"])

    first, second = model.prompts
    assert "(nothing yet — this is the first step)" in first
    assert "start by counting lines" in first
    assert "> corpus.txt" in first  # the action it took, not just its reasoning

    # The second one is handed the first one's answer, and only step 2.
    assert "step 1 made corpus.txt" in second
    assert "wc -l < corpus.txt" in second
    assert "start by counting lines" not in second
    # and the agent's task, so it knows what matters
    assert "count the gammas in corpus.txt" in second


def test_the_summariser_gets_what_the_tools_returned(tmp_path):
    _, model, _ = three_step_run(tmp_path)

    assert "result 1: bash -> tool_output/" in model.prompts[1]
    assert "2\n" in model.prompts[1]  # wc -l printed 2 lines


def test_the_summariser_is_told_its_budget_and_not_the_real_limit(tmp_path):
    """Told the ceiling, a model writes to the ceiling. So it is not told."""
    _, model, _ = three_step_run(tmp_path, summaries=["s"], summary_target_chars=250)

    system = summary_requests(model)[0]["system"]
    assert "must fit in 250 characters" in system
    assert "400" not in system  # register 4's real limit stays with the scaffold


def test_a_regeneration_is_measured_against_the_budget_it_was_given(tmp_path):
    """The retry prompt cannot name the real limit either."""
    agent, model = make_agent(
        tmp_path, [], summaries=[over(400), "shorter"], summary_target_chars=250
    )
    model.script = [
        step(tool_use("bash", command="echo one", register_id=FIRST_FREE)),
        step(write_response(agent.response_path.name, {"ok": True})),
    ]

    agent.run()

    retry = model.prompts[1]
    assert "over the 250 you have" in retry
    assert "400" not in retry


def test_a_budget_at_or_over_the_limit_is_pulled_back_under_it():
    """A budget that is not under the real limit leaves no headroom."""
    config = make_config(summary_target_chars=100000)

    assert config.summary_target(400) == 300
    assert make_config(summary_target_chars=120).summary_target(400) == 120


# --- too long: a new generation, then truncation ------------------------
def over(limit, tag="x"):
    return tag * (limit + 50)


def test_an_over_long_summary_is_regenerated_from_scratch(tmp_path):
    agent, model = make_agent(tmp_path, [], summaries=[over(400), "second try, shorter"])
    model.script = [
        step(tool_use("bash", command="echo one", register_id=FIRST_FREE)),
        step(write_response(agent.response_path.name, {"ok": True})),
    ]
    agent.run()

    assert agent.registers.values[SUMMARY_REGISTER] == "second try, shorter"
    assert agent.registers.truncated[SUMMARY_REGISTER] is False
    first, retry = model.prompts
    # The retry is a fresh summary of the same material, not an edit request:
    # everything the first call got is there, plus what came back too long.
    assert "count the gammas in corpus.txt" in retry and "echo one" in retry
    assert "Your last attempt did not fit" not in first
    assert "Your last attempt did not fit" in retry
    assert f"It came back at {400 + 50} characters" in retry
    assert "over the 300 you have" in retry  # the budget, never the register
    assert over(400) in retry  # the attempt itself, so it need not be rebuilt


def test_only_the_last_failed_attempt_is_shown_to_the_next_one(tmp_path):
    agent, model = make_agent(
        tmp_path, [], summaries=[over(400, "a"), over(400, "b"), "third time lucky"]
    )
    model.script = [
        step(tool_use("bash", command="echo one", register_id=FIRST_FREE)),
        step(write_response(agent.response_path.name, {"ok": True})),
    ]
    agent.run()

    assert agent.registers.values[SUMMARY_REGISTER] == "third time lucky"
    third = model.prompts[2]
    assert over(400, "b") in third
    assert over(400, "a") not in third
    assert notes(agent)[0]["attempts"] == [450, 450, 16]


def test_after_the_last_attempt_the_summary_is_truncated_not_lost(tmp_path):
    """A summary missing its tail beats no summary: the oldest facts are only here."""
    agent, model = make_agent(
        tmp_path,
        [],
        summaries=[over(400, "a"), over(400, "b"), "step 2"],
        summary_max_attempts=2,
    )
    model.script = [
        step(tool_use("bash", command="echo one", register_id=FIRST_FREE)),
        step(tool_use("bash", command="echo two", register_id=FIRST_FREE)),
        step(write_response(agent.response_path.name, {"ok": True})),
    ]
    agent.run()

    # Step 1's summary is what step 3 reads: 400 chars of "b", cut from 450.
    # The value fits, so its length cannot report the loss; the flag does.
    dump = parent_requests(model)[2]["messages"][0]["content"]
    assert "--- register 4 (400/400 chars; summary, special, truncated) ---" in dump
    assert "b" * 400 in dump

    note = notes(agent)[0]
    assert note["ok"] is True and note["truncated"] is True
    assert note["attempts"] == [450, 450] and note["chars"] == 400


def test_one_attempt_means_no_retry_at_all(tmp_path):
    agent, model = make_agent(
        tmp_path, [], summaries=[over(400)], summary_max_attempts=1
    )
    model.script = [
        step(tool_use("bash", command="echo one", register_id=FIRST_FREE)),
        step(write_response(agent.response_path.name, {"ok": True})),
    ]
    agent.run()

    assert len(model.prompts) == 1
    assert agent.registers.values[SUMMARY_REGISTER] == "x" * 400


# --- failure ------------------------------------------------------------
def test_a_failed_summary_call_leaves_the_old_summary_standing(tmp_path):
    """One step out of date beats losing the run's memory to a bad call."""
    agent, model, result = three_step_run(
        tmp_path, summaries=["worth keeping", RuntimeError("upstream is down")]
    )

    assert result.ok  # the agent's own run is unaffected
    assert agent.registers.values[SUMMARY_REGISTER] == "worth keeping"
    assert [n["ok"] for n in notes(agent)] == [True, False]
    assert notes(agent)[1]["error"] == "RuntimeError: upstream is down"


def test_a_summary_call_that_says_nothing_changes_nothing(tmp_path):
    agent, _, result = three_step_run(tmp_path, summaries=["worth keeping", None])

    assert result.ok
    assert agent.registers.values[SUMMARY_REGISTER] == "worth keeping"
    assert notes(agent)[1]["error"] == "the summariser returned no text"


def test_the_summary_stays_empty_if_no_call_ever_answers(tmp_path):
    agent, _, result = three_step_run(tmp_path, summaries=[None, None])

    assert result.ok
    assert agent.registers.values[SUMMARY_REGISTER] == ""


def test_a_retry_that_breaks_still_keeps_the_draft_it_was_replacing(tmp_path):
    """An over-long summary is in hand; cutting it beats losing it to a bad call."""
    agent, model = make_agent(
        tmp_path, [], summaries=[over(400, "a"), RuntimeError("upstream is down")]
    )
    model.script = [
        step(tool_use("bash", command="echo one", register_id=FIRST_FREE)),
        step(write_response(agent.response_path.name, {"ok": True})),
    ]
    agent.run()

    assert agent.registers.values[SUMMARY_REGISTER] == "a" * 400
    assert agent.registers.truncated[SUMMARY_REGISTER] is True
    note = notes(agent)[0]
    # It worked *and* something went wrong; the record says both.
    assert note["ok"] is True and note["truncated"] is True
    assert note["error"] == "RuntimeError: upstream is down"
    assert note["attempts"] == [450]


# --- the record ---------------------------------------------------------
def test_the_summary_update_is_recorded_on_the_step(tmp_path):
    agent, _, _ = three_step_run(tmp_path, summaries=["what step 1 established"])

    steps = [r for r in agent.trajectory.read() if r.get("role") == "assistant"]
    note = steps[0]["summary"]
    assert note["ok"] is True
    assert note["summary"] == "what step 1 established"
    assert note["chars"] == len("what step 1 established")
    assert note["attempts"] == [note["chars"]]
    assert note["truncated"] is False
    assert note["target_chars"] == 300 and note["limit"] == 400
    assert note["model"] == Config.summary_model == "claude-haiku-4-5"
    # No sub-agent, so nothing to link to and no steps to count.
    assert "trajectory" not in note and "agent_id" not in note and "steps" not in note
    # Its time is its own, charged to neither generation nor tools.
    assert steps[0]["timing"]["summary_s"] >= 0
    assert "summary" not in steps[-1]  # the finishing step


def test_a_cut_off_step_is_summarised_too(tmp_path):
    agent, model = make_agent(tmp_path, [], summaries=["it was cut off mid-thought"])
    model.script = [
        step(
            {"type": "thinking", "thinking": "I had got this far", "signature": "s"},
            tool_use("bash", command="touch never-ran", register_id=FIRST_FREE),
            stop_reason="max_tokens",
        ),
        step(write_response(agent.response_path.name, {"ok": True})),
    ]
    agent.run()

    assert agent.registers.values[SUMMARY_REGISTER] == "it was cut off mid-thought"
    assert "generation cut off" in model.prompts[0]
    assert "This step's generation was cut off" in model.prompts[0]
    assert "(no tool call ran)" in model.prompts[0]
    assert not (agent.workspace.root / "never-ran").exists()


def test_the_summary_crosses_a_resume(tmp_path):
    agent, model = make_agent(tmp_path, [], summaries=["one step in"], max_steps=1)
    model.script = [step(tool_use("set", value="x", register_id=FIRST_FREE))]
    agent.run()

    resumed = Agent.resume(
        workspace=Workspace(tmp_path / "run"),
        model=SummaryModel([]),
        agent_id=agent.agent_id,
        overrides={"max_steps": 1, "summary": False},
    )
    resumed.model.script = [step(write_response(resumed.response_path.name, {"ok": 1}))]
    resumed.run()

    assert "one step in" in resumed.model.requests[0]["messages"][0]["content"]


def test_a_0_0_4_run_resumes_without_an_upgrade(tmp_path):
    """0.0.5 changed who writes register 4, not what it means, so the layout holds."""
    agent, model = make_agent(tmp_path, [], summaries=["one step in"], max_steps=1)
    model.script = [step(tool_use("set", value="x", register_id=FIRST_FREE))]
    agent.run()

    # A 0.0.4 header: same layout, and a config field this scaffold no longer has.
    path = agent.trajectory.path
    records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    records[0]["config"]["summary_max_steps"] = 6
    records[0]["summarizer"] = False
    path.chmod(0o644)
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")

    resumed = Agent.resume(
        workspace=Workspace(tmp_path / "run"),
        model=SummaryModel([]),
        agent_id=agent.agent_id,
        overrides={"max_steps": 1},
    )
    try:
        assert resumed.registers.values[SUMMARY_REGISTER] == "one step in"
        assert not hasattr(resumed.config, "summary_max_steps")
    finally:
        resumed.bash.close()


def test_the_viewer_shows_the_summary_update(tmp_path):
    from infinite.viewer.reader import list_workspaces, load_trajectory

    agent, _, _ = three_step_run(tmp_path, summaries=["what step 1 established"])
    trajectory = load_trajectory(agent.trajectory.path)

    first, last = trajectory["steps"][0], trajectory["steps"][-1]
    assert first["summary"]["summary"] == "what step 1 established"
    assert first["timing"]["summary_s"] >= 0
    assert last["summary"] is None  # the step that ended the run
    assert trajectory["registers"]["max_step_half_length"] == 200
    # Nothing in the workspace is a summariser any more.
    assert trajectory["summarizer"] is False
    listed = list_workspaces(tmp_path)[0]["agents"]
    assert [a["summarizer"] for a in listed] == [False]


# --- the prompt ---------------------------------------------------------
def test_the_reply_is_the_register_value_with_any_wrapping_removed():
    assert summary_module.clean("  the summary  ") == "the summary"
    assert summary_module.clean("```\nthe summary\n```") == "the summary"
    assert summary_module.clean("```markdown\nthe summary\n```") == "the summary"
    # A fence that is part of the summary is not wrapping and stays put.
    assert summary_module.clean("it ran ```wc -c``` twice") == "it ran ```wc -c``` twice"
    assert summary_module.clean("") == ""


def test_a_long_instruction_is_excerpted_not_passed_whole():
    body = summary_module.build_input(
        step=2,
        instruction="i" * 5000,
        target="",
        previous_summary="",
        thinking="t",
        action="a",
        observations="o",
        cut_off=False,
        budget=300,
    )

    assert "i" * summary_module.INSTRUCTION_EXCERPT in body
    assert "i" * (summary_module.INSTRUCTION_EXCERPT + 1) not in body
    assert f"cut after {summary_module.INSTRUCTION_EXCERPT} chars" in body
    assert "(it has not set one)" in body  # no target


def test_observations_are_bounded_per_result():
    class Result:
        def __init__(self, name, status, payload, record=None):
            self.name, self.status, self.payload = name, status, payload
            self.record = record or {}

    described = summary_module.describe_observations(
        [
            Result("bash", "tool_output/a.json", "x" * 50),
            Result("set", "OK set register 5 (4 chars)", ""),
            Result("load", "", "", {"error": "error: nope.txt does not exist"}),
        ],
        20,
    )

    assert "x" * 20 in described and "x" * 21 not in described
    assert "cut after 20 chars" in described
    assert "result 2: set -> OK set register 5 (4 chars)" in described
    assert "result 3: load -> error: nope.txt does not exist" in described
    assert summary_module.describe_observations([], 20) == "(no tool call ran)"


def test_the_summariser_can_be_used_on_its_own():
    """It is a plain object over the model seam: no workspace, no agent, no files."""

    class OneCall:
        def __init__(self):
            self.calls = 0

        def generate(self, **kwargs):
            self.calls += 1
            return step(text("the run so far"))

    model = OneCall()
    update = Summariser(make_config(), model).update(
        agent_id="abcd1234",
        step=7,
        instruction="do the thing",
        target="the plan",
        previous_summary="up to step 6",
        thinking="thought",
        action="bash({})",
        observations="result 1: bash -> ok",
        cut_off=False,
        limit=400,
    )

    assert model.calls == 1
    assert update.ok and update.summary == "the run so far"
    assert update.truncated is False and update.attempts == [14]
