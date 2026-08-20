"""0.0.8d §4.1 — a step either leaves something behind or it does not.

The first Design Test asks for infinite complexity at a fixed context, which is
a claim about steps buying progress. A run that loops fails at eighty steps and
would fail at eight hundred, and nothing in 0.0.8 could tell that run from one
that was working: a `grep` and a module cost one step each.

What is measured here is *durable* state — the workspace, the target register,
the memo table, the check's verdict — because everything else a step makes is
overwritten by the step after it. What is deliberately not measured is
repetition: reading one file twice is progress if something happened in between
and a loop if nothing did, so the second read is not the observable.
"""

import json

from infinite.progress import Progress, stall_line
from infinite.registers import RegisterFile
from infinite.config import Config

from .conftest import agent, build_agent, run  # noqa: F401
from test.infinite_0_0_1_simple.fake_model import step, text, tool_use


def reading(path="TASK.md"):
    return step(tool_use("bash", command=f"cat {path}", register_id=6))


# --- what counts as progress ---------------------------------------------


def test_a_step_that_writes_a_file_moved(tmp_path):
    root = tmp_path / "w"
    root.mkdir()
    progress = Progress(root)
    (root / "out.py").write_text("x = 1\n")

    record = progress.record(target="", check=None)
    assert record["moved"] and record["created"] == 1
    assert record["paths"] == ["out.py"]
    assert progress.streak == 0


def test_a_step_that_only_reads_stalls(tmp_path):
    root = tmp_path / "w"
    root.mkdir()
    (root / "TASK.md").write_text("do it\n")
    progress = Progress(root)

    record = progress.record(target="", check=None)
    assert not record["moved"] and record["stall_streak"] == 1
    assert record["paths"] == []


def test_rewriting_a_file_moved_even_at_the_same_size(tmp_path):
    root = tmp_path / "w"
    root.mkdir()
    target = root / "out.py"
    target.write_text("x = 1\n")
    progress = Progress(root)
    # Same length, different bytes, and the mtime moves either way: the agent
    # did something, and hashing the workspace every step to decide otherwise
    # would cost more than the measure is worth.
    target.write_text("x = 2\n")

    assert progress.record(target="", check=None)["modified"] == 1


def test_deleting_a_file_moved(tmp_path):
    root = tmp_path / "w"
    root.mkdir()
    (root / "scratch.txt").write_text("junk\n")
    progress = Progress(root)
    (root / "scratch.txt").unlink()

    record = progress.record(target="", check=None)
    assert record["moved"] and record["removed"] == 1


def test_rewriting_the_target_register_moved(tmp_path):
    """The plan changing is progress even when nothing on disk did."""
    root = tmp_path / "w"
    root.mkdir()
    progress = Progress(root, target="find the interface")

    assert progress.record(target="find the interface", check=None)["moved"] is False
    record = progress.record(target="write the module", check=None)
    assert record["moved"] and record["target"] is True


def test_the_check_verdict_changing_moved(tmp_path):
    """A gradient check that gets closer is the clearest progress there is.

    §4.3's open question is whether a check that cannot get closer is worse than
    none. If it can, this is where the run is told.
    """
    root = tmp_path / "w"
    root.mkdir()
    progress = Progress(root, check="FAILS: 9 stubs left")

    assert not progress.record(target="", check="FAILS: 9 stubs left")["moved"]
    assert progress.record(target="", check="FAILS: 4 stubs left")["moved"]


def test_learning_the_verdict_for_the_first_time_is_not_the_agents_progress(tmp_path):
    """The scaffold runs the check, so the first verdict is not the agent's doing.

    Counting it would have made the opening step of every checked run look like
    progress — and it is the opening steps of a livelock that matter most.
    """
    root = tmp_path / "w"
    root.mkdir()
    progress = Progress(root)

    assert not progress.record(target="", check="FAILS (exit 1): ImportError")["moved"]
    assert progress.record(target="", check="PASSES")["moved"]


# --- what the scaffold writes every step regardless ------------------------


def test_the_scaffolds_own_records_do_not_count_as_progress(tmp_path):
    """Otherwise every step is progress and the measure says nothing.

    `tool_output/` gains a file whenever a tool runs, a trajectory gains a line
    every step, and the registers-as-files mirror is rewritten around every
    shell command. None of it is the agent's work.
    """
    root = tmp_path / "w"
    root.mkdir()
    (root / "tool_output").mkdir()
    (root / ".scratch" / "abc" / "reg").mkdir(parents=True)
    progress = Progress(root)

    (root / "tool_output" / "abc-step001-0001-bash.json").write_text("{}")
    (root / "trajectory-abc1234f.jsonl").write_text("{}\n")
    (root / ".scratch" / "abc" / "reg" / "6").write_text("value")

    assert not progress.record(target="", check=None)["moved"]


def test_an_agents_own_scratch_notes_do_count(tmp_path):
    """The brief both passing 0.0.8 arms wrote lived in `.scratch`.

    They read for forty-five steps, condensed it into one file there, and handed
    that file to a child which wrote the module. Calling that step a stall would
    miss the only move in the run that worked.
    """
    root = tmp_path / "w"
    root.mkdir()
    (root / ".scratch" / "abc").mkdir(parents=True)
    progress = Progress(root)
    (root / ".scratch" / "abc" / "goal.md").write_text("# Goal\nimplement it\n")

    assert progress.record(target="", check=None)["moved"]


# --- the streak, which is the thing worth acting on -----------------------


def test_stalls_in_a_row_accumulate_and_a_move_clears_them(tmp_path):
    root = tmp_path / "w"
    root.mkdir()
    progress = Progress(root)

    for expected in (1, 2, 3, 4):
        assert progress.record(target="", check=None)["stall_streak"] == expected
    (root / "out.py").write_text("x = 1\n")
    assert progress.record(target="", check=None)["stall_streak"] == 0
    assert {k: v for k, v in progress.summary().items() if k != "scan_seconds"} == {
        "steps": 5, "stalls": 4, "longest_stall_streak": 4,
    }


def test_the_dump_says_nothing_while_the_run_is_moving():
    assert stall_line(0, 3) is None
    assert stall_line(2, 3) is None
    assert stall_line(3, 3) is not None
    # A run of one long is a step spent reading, which the system message asks
    # for; the notice is for the livelock, not for the stall.
    assert stall_line(9, None) is None


def test_the_notice_says_how_long_and_why():
    line = stall_line(6, 3)
    assert "6 steps" in line
    # The reason is the argument: a step that leaves nothing behind does not
    # finish the task at any budget. Without that this is advice about tidiness.
    assert "any budget" in line


def test_the_stall_line_lands_in_the_dump_above_the_registers():
    registers = RegisterFile(Config(summary=False))
    dump = registers.render(step=8, max_steps=80, depth=0, stall=stall_line(5, 3))
    lines = dump.splitlines()

    assert lines[0].startswith("[Step]")
    assert lines[1].startswith("[Stall] 5 steps")
    assert lines[2] == "[Registers]"


def test_a_working_run_pays_nothing_for_the_measure():
    """The line is absent, not empty, so a healthy run's dump is unchanged."""
    registers = RegisterFile(Config(summary=False))
    quiet = registers.render(step=8, max_steps=80, depth=0, stall=None)
    assert "[Stall]" not in quiet


# --- through the loop -----------------------------------------------------


def test_every_step_records_what_it_left_behind(tmp_path):
    built = build_agent(tmp_path, max_steps=4, stall_surcharge=0)
    response = built.response_path.name
    built.model.script = [
        reading(),
        reading(),
        step(tool_use("bash", command=f"printf '{{}}' > {response}")),
    ]
    result = built.run()

    assert result.ok
    records = [
        json.loads(line)
        for line in built.trajectory.path.read_text().splitlines()
    ]
    steps = [r for r in records if r["role"] == "assistant"]
    assert [r["progress"]["stall_streak"] for r in steps] == [1, 2, 0]
    # The step that wrote the response is the step that moved.
    assert steps[-1]["progress"]["moved"] is True


def test_an_agent_that_stalls_is_told_so_and_only_then(tmp_path):
    built = build_agent(tmp_path, max_steps=6, stall_notice=3, stall_surcharge=0)
    response = built.response_path.name
    built.model.script = [reading()] * 4 + [
        step(tool_use("bash", command=f"printf '{{}}' > {response}"))
    ]
    built.run()

    dumps = [
        json.loads(line)["model_input"]["messages"][0]["content"]
        for line in built.trajectory.path.read_text().splitlines()
        if json.loads(line)["role"] == "assistant"
    ]
    # Steps 1-3 have nothing behind them yet to complain about; the fourth step
    # opens on three in a row and the fifth on four.
    assert [("[Stall]" in dump) for dump in dumps] == [False, False, False, True, True]
    assert "3 steps in a row" in dumps[3]


def test_the_notice_can_be_turned_off(tmp_path):
    built = build_agent(tmp_path, max_steps=5, stall_notice=None, stall_surcharge=0)
    built.model.script = [reading()] * 5
    built.run()

    dumps = built.trajectory.path.read_text()
    assert "[Stall]" not in dumps
    # Measured anyway: the knob is about telling the agent, not about knowing.
    last = json.loads(dumps.splitlines()[-1])
    assert last["progress"]["longest_stall_streak"] == 5


def test_an_unfinished_agent_hands_its_parent_the_streak(tmp_path):
    """A child that ran out of steps having stalled nine in a row is not a child
    to hand more steps to unchanged, and its parent is the only one who can
    change the brief."""
    built = build_agent(tmp_path, max_steps=3, stall_surcharge=0)
    built.model.script = [reading()] * 3
    result = built.run()

    assert not result.ok and result.handoff_path is not None
    handoff = json.loads(result.handoff_path.read_text())
    assert {
        k: v for k, v in handoff["progress"].items() if k != "scan_seconds"
    } == {"steps": 3, "stalls": 3, "longest_stall_streak": 3}


# --- the price, which is what bounds a livelock ---------------------------
# `charge_children` is the precedent: 0.0.8c made a child's steps cost the
# parent that commissioned them, and the pass-through cascade then terminated
# on budget rather than on a ceiling. A livelock is the same failure inside one
# frame, so it is priced the same way. 0.0.8c §6's rule is why it is a price and
# not a cap: the scaffold has an opinion about the resource, not about the shape
# of the work.


def test_a_run_of_stalls_short_of_the_threshold_costs_nothing_extra(tmp_path):
    """Reading four files to decide is a stall and the prompt asks for it."""
    built = build_agent(tmp_path, max_steps=8, stall_notice=3, stall_surcharge=1)
    response = built.response_path.name
    built.model.script = [reading(), reading()] + [
        step(tool_use("bash", command=f"printf '{{}}' > {response}"))
    ]
    result = built.run()

    assert result.ok and built.stalled == 0


def test_every_stall_past_the_threshold_costs_a_step(tmp_path):
    built = build_agent(tmp_path, max_steps=20, stall_notice=3, stall_surcharge=1)
    built.model.script = [reading()] * 20
    built.run()

    # Steps 1 and 2 are free; from the third onward each stall costs itself and
    # one more, so the twenty-step allowance runs out after eleven steps.
    assert built.step == 11 and built.stalled == 9


def test_a_livelock_costs_twice_what_working_costs(tmp_path):
    """The point of the price, in one comparison: the same allowance buys about
    half as many steps once a frame stops leaving anything behind."""
    working = build_agent(tmp_path / "a", max_steps=20, stall_surcharge=1)
    working.model.script = [
        step(tool_use("bash", command=f"echo {i} >> notes.md")) for i in range(20)
    ]
    working.run()

    looping = build_agent(tmp_path / "b", max_steps=20, stall_surcharge=1)
    looping.model.script = [reading()] * 20
    looping.run()

    assert working.step == 20 and working.stalled == 0
    assert looping.step == 11
    assert looping.step < working.step / 1.7


def test_the_dump_says_where_the_budget_went(tmp_path):
    built = build_agent(tmp_path, max_steps=20, stall_notice=3, stall_surcharge=1)
    built.model.script = [reading()] * 6
    built.run()

    dumps = [
        json.loads(line)["model_input"]["messages"][0]["content"]
        for line in built.trajectory.path.read_text().splitlines()
        if json.loads(line)["role"] == "assistant"
    ]
    # Two units gone by the opening of step 5: the third and fourth stalls.
    assert "2 to steps that changed nothing" in dumps[4]
    assert "14 left" in dumps[4]


def test_the_price_can_be_turned_off_for_an_arm_that_measures_it(tmp_path):
    built = build_agent(tmp_path, max_steps=6, stall_surcharge=0)
    built.model.script = [reading()] * 6
    built.run()

    assert built.step == 6 and built.stalled == 0


def test_a_parent_is_not_billed_for_its_childs_surcharge(tmp_path):
    """0.0.8c §5's invariant: a child cannot cost more than it was allocated.

    The surcharge is a rate inside the child's own allowance, so a child that
    livelocks runs out sooner and the parent is billed for the steps that
    actually happened. What the parent gets instead is the streak, in the
    handoff — which it can act on, because it is the only frame that can change
    the brief.
    """
    parent = build_agent(tmp_path, max_steps=12, stall_surcharge=1)
    # The child shares this FakeModel and consumes the entries after the spawn,
    # so the parent's own answer has to come last.
    parent.model.script = [
        step(tool_use(
            "spawn", goal="a piece of it", check="true",
            return_schema={"type": "object"}, register_id=6, max_steps=6,
        )),
    ] + [step(text("the child works and does not answer"))] * 6 + [
        step(tool_use("bash", command="printf '{}' > " + parent.response_path.name)),
    ]
    result = parent.run()

    assert result.ok
    # Six allocated; the child stalled through all of it, so its own surcharge
    # ended it at four real steps and four is what the parent paid.
    assert parent.charged == 4
    handoff = json.loads(
        next(parent.workspace.root.glob("handoff-*.json")).read_text()
    )
    assert handoff["progress"]["longest_stall_streak"] == 4


# --- the cost of measuring ------------------------------------------------


def test_the_scan_prunes_the_directories_it_ignores_rather_than_filtering_them(
    tmp_path,
):
    """The whole performance story. `tool_output/` gains a file per tool call and
    a long run's trajectories are the largest things in the workspace; walking
    them and discarding them afterwards cost 350ms a step on a real
    reconstruction workspace and 8.6 seconds on a pathological one. Pruned, the
    same scans are single-digit milliseconds.
    """
    from infinite.progress import scan

    root = tmp_path / "w"
    (root / "tool_output").mkdir(parents=True)
    (root / ".scratch" / "abc" / "reg").mkdir(parents=True)
    (root / ".scratch" / "abc" / "notes").mkdir()
    for i in range(50):
        (root / "tool_output" / f"out{i}.json").write_text("{}")
        (root / ".scratch" / "abc" / "reg" / str(i)).write_text("v")
    (root / ".scratch" / "abc" / "notes" / "goal.md").write_text("# goal\n")
    (root / "work.py").write_text("x = 1\n")
    (root / "trajectory-abc12345.jsonl").write_text("{}\n")

    # Only the agent's own work: its scratch notes and the file it wrote.
    assert set(scan(root)) == {"work.py", ".scratch/abc/notes/goal.md"}


def test_a_nested_directory_of_the_agents_own_is_walked(tmp_path):
    """Pruning is by name at a known depth, so it must not prune a `cache/` the
    agent made in its own work tree."""
    from infinite.progress import scan

    root = tmp_path / "w"
    (root / "src" / "cache").mkdir(parents=True)
    (root / "src" / "cache" / "keep.py").write_text("x = 1\n")

    assert set(scan(root)) == {"src/cache/keep.py"}


def test_the_measure_reports_what_it_cost(tmp_path):
    """Kept rather than capped: a cap would degrade the measure exactly where a
    livelock is most expensive."""
    root = tmp_path / "w"
    root.mkdir()
    progress = Progress(root)
    progress.record(target="", check=None)

    assert progress.summary()["scan_seconds"] >= 0.0
