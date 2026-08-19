"""The scratch directory, and the caches pointed at it.

Under the firewall every default cache location is denied, and a tool that
cannot write its cache complains on every invocation rather than failing
quietly — noise that ends up in a register and then in the summary. These are
the two halves of the fix: a place inside the workspace, and an environment
that already points there.
"""

import os
from pathlib import Path

from infinite.agent import Agent
from infinite.bash_tool import BashSession
from infinite.config import Config
from infinite.workspace import SCRATCH_DIR, Workspace

from .fake_model import FakeModel, step, text, tool_use

FIRST_FREE = 5


def make_config(**overrides) -> Config:
    return Config(
        max_register_length=200,
        max_special_length=400,
        max_step_half_length=200,
        max_canvas_length=800,
        summary=False,
        bash_timeout=5.0,
        **overrides,
    )


# --- the directory ------------------------------------------------------
def test_each_agent_gets_its_own_scratch_directory(tmp_path):
    workspace = Workspace(tmp_path / "run")

    first = workspace.scratch_path("aaaa1111")
    second = workspace.scratch_path("bbbb2222")

    assert first.is_dir() and second.is_dir() and first != second
    assert first.parent == workspace.root / SCRATCH_DIR
    # Inside the workspace, so the firewall allows writing it.
    assert first.is_relative_to(workspace.root)


def test_the_scratch_directory_is_made_before_the_agent_needs_it(tmp_path):
    agent = Agent(
        config=make_config(),
        workspace=Workspace(tmp_path / "run"),
        model=FakeModel([]),
        instruction="do a thing",
    )
    try:
        assert agent.scratch.is_dir()
        assert agent.scratch.name == agent.agent_id
    finally:
        agent.bash.close()


def test_the_system_message_names_the_scratch_directory(tmp_path):
    agent = Agent(
        config=make_config(),
        workspace=Workspace(tmp_path / "run"),
        model=FakeModel([]),
        instruction="do a thing",
    )
    try:
        message = agent.system_message()
    finally:
        agent.bash.close()

    assert f"{SCRATCH_DIR}/{agent.agent_id}" in message
    assert "TMPDIR" in message and "never need /tmp" in message


# --- the environment ----------------------------------------------------
def test_the_environment_points_the_caches_into_the_workspace(tmp_path):
    workspace = Workspace(tmp_path / "run")

    env = workspace.environment("aaaa1111")

    scratch = workspace.scratch_path("aaaa1111")
    for name in ("TMPDIR", "TMP", "TEMP", "PYTHONPYCACHEPREFIX", "XDG_CACHE_HOME"):
        assert env[name].startswith(str(scratch)), name
    # TMPDIR has to exist to be usable at all; the rest are made by their tools.
    assert os.path.isdir(env["TMPDIR"])
    # Everything else the process had is still there.
    assert env["PATH"] == os.environ["PATH"]


def test_the_shell_runs_with_that_environment(tmp_path):
    workspace = Workspace(tmp_path / "run")
    session = BashSession(
        cwd=str(workspace.root), timeout=5.0, env=workspace.environment("aaaa1111")
    )
    try:
        printed = session.execute_command("echo $TMPDIR; echo $PYTHONPYCACHEPREFIX")
    finally:
        session.close()

    tmpdir, pycache = printed.strip().splitlines()
    assert tmpdir == str(workspace.scratch_path("aaaa1111") / "tmp")
    assert pycache == str(workspace.scratch_path("aaaa1111") / "pycache")


def test_an_agents_shell_puts_temporary_files_inside_the_workspace(tmp_path):
    """The firewall is the reason; TMPDIR is what stops it being a problem."""
    probe = (
        "python3 -c \"import tempfile;"
        "f=tempfile.NamedTemporaryFile(delete=False);f.write(b'ok');f.close();"
        'print(f.name)" 2>/dev/null'
    )
    agent = Agent(
        config=make_config(max_steps=2),
        workspace=Workspace(tmp_path / "run"),
        model=FakeModel(
            [
                step(tool_use("bash", command=probe, register_id=FIRST_FREE)),
                step(text("done")),
            ]
        ),
        instruction="do a thing",
    )
    try:
        agent.run()
    finally:
        agent.bash.close()

    made = agent.registers.values[FIRST_FREE].strip()
    assert made.startswith(str(agent.scratch)), made
    assert Path(made).read_bytes() == b"ok"


def test_the_session_inherits_this_process_environment_when_none_is_given(tmp_path):
    """`env=None` is the plain case, and it must stay the plain case."""
    session = BashSession(cwd=str(tmp_path), timeout=5.0)
    try:
        assert session.execute_command("echo $PATH").strip() == os.environ["PATH"]
    finally:
        session.close()
