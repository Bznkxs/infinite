"""The width probe as a harness, and the measures read off a run — 0.0.8d.

The probe is the project's only test of the third clause of the Infinite Context
Test, and until now it was a recipe in prose: rebuild the workspace from the
0.0.7i reconstruction, copy nine modules and a stub, strip `__pycache__`, never
reuse a workspace across arms. Every one of those is a way to spoil a three-hour
run, and §6 of the handoff exists because each of them has happened.

None of this needs the real corpus — a synthetic one with the same shape tests
the contract, which is what a fresh clone can check.
"""

import json

import pytest

from eval import analyse
from eval.benchmarks import width
from eval.run import ARMS, PROFILES


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    """A stand-in for the 0.0.7i reconstruction: siblings, a stub, a spec."""
    source = tmp_path / "recon"
    (source / "infinite_agent").mkdir(parents=True)
    (source / "docs").mkdir()
    (source / "API.md").write_text("# API\n\n`ToolRegistry.get(name)`\n")
    (source / "docs" / "spec.md").write_text("# spec\n" * 100)
    for name in ("config", "registers", "prompt", "tools", "trajectory"):
        (source / "infinite_agent" / f"{name}.py").write_text(f"# {name}\n")
    (source / "infinite_agent" / width.TARGET.split("/")[-1]).write_text(
        "\n".join(
            ["'''The step loop.'''", "from .tools import ToolRegistry", ""]
            + ["def run():", "    raise NotImplementedError", ""] * 3
        )
        + "\n"
    )
    # A compiled sibling from an earlier arm, which must not travel.
    (source / "infinite_agent" / "__pycache__").mkdir()
    (source / "infinite_agent" / "__pycache__" / "tools.cpython-313.pyc").write_bytes(b"\x00")
    monkeypatch.setattr(width, "SOURCE", source)
    return source


def test_the_probe_states_the_stub_it_found_rather_than_a_constant(corpus):
    """A task that hard-codes "99 lines" is a task that lies the day it moves."""
    instance = width.load(count=1)[0]
    lines = len((corpus / width.TARGET).read_text().splitlines())

    assert f"{lines} lines" in instance.task
    assert instance.truth["stub_lines"] == lines
    # 80, because that is what every 0.0.8 arm had.
    assert instance.max_steps == 80


def test_the_probe_asks_for_repeats_because_every_number_is_n_of_one(corpus):
    instances = width.load(count=3)
    assert len({i.instance_id for i in instances}) == 3


def test_the_workspace_is_the_siblings_and_the_stub_and_nothing_compiled(
    corpus, tmp_path
):
    instance = width.load(count=1)[0]
    workspace = tmp_path / "run"
    workspace.mkdir()
    width.materialise(instance, workspace)

    assert (workspace / "API.md").is_file()
    assert (workspace / "infinite_agent" / "tools.py").is_file()
    assert (workspace / width.TARGET).read_text().count("NotImplementedError") == 3
    assert not list(workspace.rglob("__pycache__"))


def test_materialising_twice_leaves_the_stub_a_stub(corpus, tmp_path):
    """§6: a workspace reused across arms carries the previous arm's work.

    The arm suffix in the instance id is the first defence; this is the second,
    because the harness is also used with `--fresh` off.
    """
    instance = width.load(count=1)[0]
    workspace = tmp_path / "run"
    workspace.mkdir()
    width.materialise(instance, workspace)
    (workspace / width.TARGET).write_text("# an earlier arm's answer\n")
    width.materialise(instance, workspace)

    assert (workspace / width.TARGET).read_text().count("NotImplementedError") == 3


def test_an_absent_corpus_fails_with_the_recipe_rather_than_grading_zero(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(width, "SOURCE", tmp_path / "nowhere")
    with pytest.raises(SystemExit) as raised:
        width.load(count=1)

    assert "INFINITE_WIDTH_SOURCE" in str(raised.value)


# --- grading --------------------------------------------------------------


def test_the_machine_grades_it_and_not_the_response(corpus, tmp_path):
    """Two 0.0.8 arms reported a module they had not written, one of them with
    `ok=True` while its own response said the stub was untouched."""
    instance = width.load(count=1)[0]
    workspace = tmp_path / "run"
    workspace.mkdir()
    width.materialise(instance, workspace)

    verdict = width.grade(
        {"answer": "step_loop.py, 457 lines", "evidence": "IMPORT OK"},
        instance.truth,
        workspace=workspace,
    )
    assert verdict["correct"] is False
    assert verdict["untouched"] is True and verdict["stubs_left"] == 3
    # Kept, so a run that claimed a module it did not write is on record as
    # having claimed it.
    assert verdict["answer"] == "step_loop.py, 457 lines"


def test_a_module_that_imports_with_a_stub_left_is_not_a_pass(corpus, tmp_path):
    """§4.3's two failure modes are different failures, and both are recorded."""
    instance = width.load(count=1)[0]
    workspace = tmp_path / "run"
    workspace.mkdir()
    width.materialise(instance, workspace)
    (workspace / "infinite_agent" / "__init__.py").write_text("")
    (workspace / "infinite_agent" / "tools.py").write_text("class ToolRegistry: pass\n")
    (workspace / width.TARGET).write_text(
        "from .tools import ToolRegistry\n\n\ndef run():\n    raise NotImplementedError\n"
    )

    verdict = width.grade(None, instance.truth, workspace=workspace)
    assert verdict["imports"] is True
    assert verdict["stubs_left"] == 1 and verdict["correct"] is False
    assert verdict["untouched"] is False


def test_a_written_module_that_imports_passes(corpus, tmp_path):
    instance = width.load(count=1)[0]
    workspace = tmp_path / "run"
    workspace.mkdir()
    width.materialise(instance, workspace)
    (workspace / "infinite_agent" / "__init__.py").write_text("")
    (workspace / "infinite_agent" / "tools.py").write_text("class ToolRegistry: pass\n")
    (workspace / width.TARGET).write_text(
        "from .tools import ToolRegistry\n\n\ndef run():\n    return ToolRegistry()\n"
    )

    verdict = width.grade(None, instance.truth, workspace=workspace)
    assert verdict["correct"] is True and verdict["stubs_left"] == 0


# --- the arms -------------------------------------------------------------


def test_every_arm_is_one_variable(corpus):
    """§6: two arms of the 0.0.8 A/B differed in two things, which cost the
    comparison and needed a fifth run to repair."""
    for name, flags in ARMS.items():
        if name == "baseline":
            assert flags == []
            continue
        # One flag, or one flag and its value.
        assert len([f for f in flags if f.startswith("--")]) == 1, name


def test_the_probe_is_reachable_from_the_profile_the_arms_used():
    assert "frame" in PROFILES


# --- what `analyse` reads off a run ---------------------------------------


def test_stall_measures_are_absent_rather_than_zero_for_an_older_run():
    """A trajectory recorded before the measure existed has no stalls *known*.

    Reporting 0 would be a lie in the flattering direction, and the five 0.0.8
    arms are all such trajectories.
    """
    assert analyse.stall_measures(None) == {
        "stalls": None, "longest_stall_streak": None, "livelocks": None,
    }


def test_stall_measures_count_the_runs_and_the_worst_one():
    # move, stall, stall, stall, move, stall, stall, stall, stall
    moved = [True, False, False, False, True, False, False, False, False]
    assert analyse.stall_measures(moved) == {
        "stalls": 7, "longest_stall_streak": 4, "livelocks": 2,
    }


def test_a_run_that_never_stalls_reports_no_livelock():
    assert analyse.stall_measures([True] * 10) == {
        "stalls": 0, "longest_stall_streak": 0, "livelocks": 0,
    }


def test_the_livelock_threshold_is_the_one_the_scaffold_charges_at():
    """Otherwise the report and the mechanism disagree about the same word."""
    from infinite.config import Config

    assert analyse.LIVELOCK == Config().stall_notice


def test_the_measures_come_off_a_trajectory(tmp_path):
    """End to end on the record the loop actually writes."""
    path = tmp_path / "trajectory-abc12345.jsonl"
    steps = [
        {"step": 0, "role": "user", "agent_id": "abc12345", "depth": 0,
         "content": "do it", "context_template": {"system": "s", "tools": []}},
    ]
    for i, moved in enumerate([True, False, False, False, False], start=1):
        steps.append({
            "step": i, "role": "assistant", "agent_id": "abc12345",
            "model_input": {"messages": [{"role": "user", "content": "dump"}]},
            "content": [], "usage": {"input_tokens": 7000 + i},
            "progress": {"moved": moved, "stall_streak": 0 if moved else i - 1},
        })
    steps.append({"step": 6, "role": "final", "agent_id": "abc12345", "ok": False,
                  "charged": 0, "cost": 5})
    path.write_text("\n".join(json.dumps(s) for s in steps) + "\n")

    row = analyse.summarise(path)
    assert row["stalls"] == 4 and row["longest_stall_streak"] == 4
    assert row["livelocks"] == 1
    # §6's other debt: "tokens" should come from `usage`, not chars / 2.6.
    assert row["max_request_tokens"] == 7005
