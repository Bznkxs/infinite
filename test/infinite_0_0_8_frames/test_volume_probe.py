"""The infinite-writing probe — 0.0.8d §4.8.

The clause of the Infinite Context Test with no live evidence at all. The
offline test in `test_fixed_context.py` asserts that appending ten thousand lines
through `bash` does not move the request, which was never in doubt; what has
never been run is a task whose *output* is the hard part.

The probe is built to be run twice, at ten times the size, so that the
measurement is a comparison rather than a threshold: same geometry, same
`max_request_tokens`, ten times the output. These tests are the contract that
makes those two rows comparable — a corpus that is the same on any machine, keys
that cannot collide, and a grader that separates *how much* was written from
*whether it was right*, because those are different results.
"""

import pytest

from eval import run
from eval.benchmarks import volume
from infinite.config import FRAME, Config


def cards(answers, fields=None, count=None, suffix=""):
    """Render answers as the file the task asks for."""
    out = []
    for answer in answers[: count if count is not None else len(answers)]:
        values = {**answer, **(fields or {})}
        out.append(
            f"### {answer['key']}\n"
            + "".join(
                f"{name}: {values[name]}{suffix if name == 'weight' else ''}\n"
                for name in volume.CARD_FIELDS
            )
        )
    return "\n".join(out)


# --- the corpus -----------------------------------------------------------


def test_the_corpus_is_the_same_on_any_machine():
    """`width` needs a corpus that only exists on one machine; this one does not.

    Two rows at two sizes are only comparable if the smaller is a prefix-like
    sample of the same generator, and a run is only reproducible if a rerun is
    the same task.
    """
    first, answers = volume.build(50)
    again, same = volume.build(50)

    assert first == again and answers == same
    assert volume.build(50, seed=9)[0] != first


def test_keys_cannot_collide_at_the_size_the_probe_is_run_at():
    """Five characters is 33.5M keys, which at 1,200 records still collides 2%
    of the time — and the grader keys the cards it parses, so a collision would
    silently halve a record's grade."""
    _, answers = volume.build(2000)
    keys = [answer["key"] for answer in answers]

    assert len(set(keys)) == len(keys) == 2000


@pytest.mark.parametrize("records", [120, 1200])
def test_the_task_states_the_real_sizes(records):
    instance = volume.load(config=str(records))[0]
    corpus = instance.files[volume.SOURCE]

    assert f"{records} records" in instance.task
    assert f"{len(corpus):,}" in instance.task
    # The budget scales with the work, because running out of steps is a result
    # here and a budget that cannot fit the task would answer in advance.
    assert instance.max_steps >= records // 4


def test_the_output_is_the_thing_that_scales():
    """Ten times the records, ten times the corpus — the premise of the two rows."""
    small = len(volume.load(config="120")[0].files[volume.SOURCE])
    large = len(volume.load(config="1200")[0].files[volume.SOURCE])

    assert 9 < large / small < 11


def test_the_acceptance_command_is_the_one_the_task_prints():
    """It is also passed to the scaffold as `--check`, so a divergence between
    the two would mean a run graded against a command it was never shown."""
    instance = volume.load(config="120")[0]

    assert instance.truth["check"] in instance.task
    assert "-eq 120" in instance.truth["check"]


# --- grading --------------------------------------------------------------


def test_a_complete_and_correct_run_passes(tmp_path):
    instance = volume.load(config="60")[0]
    (tmp_path / volume.OUTPUT).write_text(cards(instance.truth["answers"]))

    verdict = volume.grade({"answer": "60"}, instance.truth, workspace=tmp_path)
    assert verdict["correct"] and verdict["accuracy"] == 1.0
    assert verdict["cards_written"] == 60 and verdict["duplicate_keys"] == 0


def test_the_count_right_and_the_fields_wrong_is_the_failure_it_names(tmp_path):
    """The one the task warns about, because the check only counts cards.

    §4.3's shape again: an acceptance command that cannot see the thing that
    matters is a verdict without a gradient, and the grader must not inherit its
    blind spot.
    """
    instance = volume.load(config="60")[0]
    (tmp_path / volume.OUTPUT).write_text(
        cards(instance.truth["answers"], fields=dict.fromkeys(volume.CARD_FIELDS, "wrong"))
    )

    verdict = volume.grade({"answer": "60"}, instance.truth, workspace=tmp_path)
    assert verdict["correct"] is False
    # Every card is there and none of them is right: the two numbers that would
    # be lost by reporting one.
    assert verdict["coverage"] == 1.0 and verdict["accuracy"] == 0.0
    assert verdict["first_wrong"]["fields"] == list(volume.CARD_FIELDS)


def test_how_much_was_written_is_reported_apart_from_whether_it_was_right(tmp_path):
    """A run that stopped a third of the way through is the volume result."""
    instance = volume.load(config="60")[0]
    (tmp_path / volume.OUTPUT).write_text(cards(instance.truth["answers"], count=20))

    verdict = volume.grade(None, instance.truth, workspace=tmp_path)
    assert verdict["cards_written"] == 20
    assert verdict["coverage"] == verdict["accuracy"] == round(20 / 60, 3)
    assert verdict["output_bytes"] > 0


def test_the_grader_is_strict_about_fields_and_loose_about_layout(tmp_path):
    """A run that wrote `41kg` and an extra line has not failed *this* test.

    Grading it as though it had would hide the result the probe exists for.
    """
    instance = volume.load(config="30")[0]
    text = cards(instance.truth["answers"], suffix="kg")
    (tmp_path / volume.OUTPUT).write_text(
        text.replace("\n\n", "\nnote: seen\n\n")
    )

    verdict = volume.grade(None, instance.truth, workspace=tmp_path)
    assert verdict["correct"] and verdict["accuracy"] == 1.0


def test_no_output_file_is_a_grade_and_not_a_crash(tmp_path):
    instance = volume.load(config="30")[0]

    verdict = volume.grade(None, instance.truth, workspace=tmp_path)
    assert verdict["correct"] is False
    assert verdict["cards_written"] == 0 and verdict["output_bytes"] == 0


def test_duplicated_cards_are_counted_rather_than_ignored(tmp_path):
    """A run that appended the same batch twice wrote twice as much and did not
    get twice as far, which is a thing worth being able to see."""
    instance = volume.load(config="30")[0]
    text = cards(instance.truth["answers"])
    (tmp_path / volume.OUTPUT).write_text(text + "\n" + text)

    verdict = volume.grade(None, instance.truth, workspace=tmp_path)
    assert verdict["cards_written"] == 60 and verdict["duplicate_keys"] == 30
    assert verdict["accuracy"] == 1.0


# --- the command the harness types ---------------------------------------
# A flag the scaffold does not accept is a three-hour run that dies in its first
# second, and none of this can be caught by running the pieces separately.


@pytest.mark.parametrize("arm", sorted(run.ARMS))
@pytest.mark.parametrize("benchmark", ["volume", "width"])
def test_every_arm_of_every_probe_is_a_command_the_scaffold_accepts(
    arm, benchmark, tmp_path, monkeypatch
):
    from infinite.main import build_parser, collect_overrides

    if benchmark == "width":
        # `width`'s corpus only exists on the machine that produced it; the
        # command does not depend on it.
        monkeypatch.setattr(
            run.REGISTRY["width"], "SOURCE", _fake_width_corpus(tmp_path)
        )
    instance = run.REGISTRY[benchmark].load(count=1)[0]
    command = run.agent_command(instance, tmp_path, profile="frame", arm=arm)

    argv = command[3:]
    args = build_parser().parse_args(argv)
    overrides = collect_overrides(args, argv)
    # The profile is what the 0.0.8 arms ran at, and the check is live, which is
    # what makes the heartbeat and the progress measure mean anything.
    assert overrides["max_canvas_length"] == Config(**FRAME).max_canvas_length
    assert args.check == instance.truth["check"]
    assert Config(**overrides)  # the overrides are a valid geometry together


def _fake_width_corpus(tmp_path):
    source = tmp_path / "recon"
    (source / "infinite_agent").mkdir(parents=True)
    (source / "docs").mkdir()
    (source / "API.md").write_text("# API\n")
    (source / "docs" / "spec.md").write_text("# spec\n")
    (source / "infinite_agent" / "step_loop.py").write_text(
        "def run():\n    raise NotImplementedError\n"
    )
    return source


def test_the_arms_the_probes_are_run_with_reach_the_config_they_name():
    from infinite.main import build_parser, collect_overrides

    def config_for(arm):
        argv = ["do the thing", *run.PROFILES["frame"], *run.ARMS[arm]]
        return Config(**collect_overrides(build_parser().parse_args(argv), argv))

    assert config_for("baseline").stall_surcharge == 1
    assert config_for("no-stall-charge").stall_surcharge == 0
    assert config_for("no-stall-charge").stall_notice == 3
    assert config_for("no-stall-notice").stall_notice is None
    assert config_for("no-live-check").check_every_step is False
    assert config_for("depth-1").max_depth == 1


# --- end to end, without a key -------------------------------------------


def test_the_writing_probe_runs_end_to_end_against_a_scripted_model(tmp_path):
    """Instance -> workspace -> agent -> live check -> grade, with no API.

    Everything above this tests one piece. What kills a live run is the seam:
    a corpus the firewall will not let the agent read, a `check` that cannot run
    inside the sandbox, an output file the grader looks for in the wrong place.
    Each of those is a three-hour run that dies in its first minute, and none of
    them shows up until someone spends the three hours.

    The script takes the program route on purpose — `bash` is unbounded by
    design and the probe says so — which also puts `python3` under the firewall,
    which is §4.6's hazard.
    """
    from infinite.agent import Agent
    from infinite.config import frame_config
    from infinite.workspace import Workspace
    from test.infinite_0_0_1_simple.fake_model import FakeModel, step, tool_use

    instance = volume.load(config="30")[0]
    root = tmp_path / "runs"
    workspace_dir = instance.write(root)
    agent = Agent(
        config=frame_config(max_steps=6, summary=False),
        workspace=Workspace(workspace_dir),
        model=FakeModel([]),
        instruction=instance.task,
        return_schema=instance.schema,
        check=instance.truth["check"],
    )
    program = f'''python3 - <<'EOF'
import re
text = open("{volume.SOURCE}").read()
out = []
for block in text.split("## record ")[1:]:
    key = re.search(r"key: (\\S+)", block).group(1)
    m = re.search(
        r"The (\\w+) in the (\\w+) is (\\w+)\\. (\\w+) signed for it at (\\d\\d:\\d\\d)\\."
        r"\\s+It\\s+weighs (\\d+)kg", block)
    item, room, colour, keeper, time, weight = m.groups()
    out.append(
        f"### {{key}}\\nitem: {{item}}\\ncolour: {{colour}}\\nroom: {{room}}\\n"
        f"keeper: {{keeper}}\\ntime: {{time}}\\nweight: {{weight}}\\n")
open("{volume.OUTPUT}", "w").write("\\n".join(out))
EOF'''
    answer = '{"answer": "30 cards", "evidence": "check passed"}'
    agent.model.script = [
        step(tool_use("bash", command=program, register_id=6)),
        step(tool_use(
            "bash",
            command=f"printf '%s' '{answer}' > {agent.response_path.name}",
        )),
    ]
    try:
        result = agent.run()
    finally:
        agent.bash.close()

    # The scaffold's own verdict: the response was accepted, which means the
    # acceptance command ran inside the sandbox and succeeded.
    assert result.ok, result.error
    verdict = volume.grade(result.response, instance.truth, workspace=workspace_dir)
    assert verdict["correct"] and verdict["coverage"] == 1.0
    assert verdict["cards_written"] == 30
    # And the request did not grow while the file did.
    assert agent.context["total_tokens"] == frame_config().context_tokens(
        agent.context["fixed_chars"]
    )["total_tokens"]


def test_a_wrong_output_is_refused_by_the_check_rather_than_by_the_grader(tmp_path):
    """The count is the acceptance command's whole competence, and it is enough
    to refuse a run that wrote too few cards — which is the case that matters,
    since a truncated run is the expected failure at 1,200."""
    from infinite.agent import Agent
    from infinite.config import frame_config
    from infinite.workspace import Workspace
    from test.infinite_0_0_1_simple.fake_model import FakeModel, step, tool_use

    instance = volume.load(config="30")[0]
    workspace_dir = instance.write(tmp_path / "runs")
    agent = Agent(
        config=frame_config(max_steps=3, summary=False),
        workspace=Workspace(workspace_dir),
        model=FakeModel([]),
        instruction=instance.task,
        return_schema=instance.schema,
        check=instance.truth["check"],
    )
    answer = '{"answer": "all done", "evidence": "trust me"}'
    agent.model.script = [
        step(tool_use(
            "bash",
            command=(
                f"printf '### AAAAA\\nitem: kettle\\n' > {volume.OUTPUT}; "
                f"printf '%s' '{answer}' > {agent.response_path.name}"
            ),
        ))
    ] * 3
    try:
        result = agent.run()
    finally:
        agent.bash.close()

    assert not result.ok
    assert result.check_failure is not None
