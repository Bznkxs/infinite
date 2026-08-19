"""The firewall: writes stay in the workspace, reads stay in the whitelist."""

import shutil
import sys

import pytest

from infinite.agent import Agent
from infinite.config import Config
from infinite.firewall import Firewall
from infinite.model import ToolCall
from infinite.workspace import Workspace

from .fake_model import FakeModel

MACOS = sys.platform == "darwin" and shutil.which("sandbox-exec")


@pytest.fixture
def tree(tmp_path):
    (tmp_path / "ws").mkdir()
    (tmp_path / "shared").mkdir()
    (tmp_path / "private").mkdir()
    (tmp_path / "shared" / "notes.txt").write_text("shared notes")
    (tmp_path / "private" / "secret.txt").write_text("SECRET")
    return tmp_path


# --- policy ------------------------------------------------------------
def test_writes_are_confined_to_the_workspace(tree):
    firewall = Firewall.build(tree / "ws", [tree / "shared"])

    assert firewall.may_write(tree / "ws" / "out.txt")
    assert firewall.may_write(tree / "ws" / "deep" / "nested.txt")
    # A readable directory is readable, not writable — the two are not symmetric.
    assert not firewall.may_write(tree / "shared" / "out.txt")
    assert not firewall.may_write(tree / "private" / "out.txt")


def test_without_a_whitelist_only_the_workspace_is_readable(tree):
    firewall = Firewall.build(tree / "ws")

    assert firewall.may_read(tree / "ws" / "in.txt")
    assert not firewall.may_read(tree / "shared" / "notes.txt")
    assert not firewall.may_read(tree / "private" / "secret.txt")


def test_a_whitelisted_directory_becomes_readable(tree):
    firewall = Firewall.build(tree / "ws", [tree / "shared"])

    assert firewall.may_read(tree / "shared" / "notes.txt")
    assert not firewall.may_read(tree / "private" / "secret.txt")


def test_a_symlink_out_of_the_workspace_does_not_widen_the_policy(tree):
    (tree / "ws" / "escape").symlink_to(tree / "private")

    firewall = Firewall.build(tree / "ws")
    assert not firewall.may_read(tree / "ws" / "escape" / "secret.txt")
    assert not firewall.may_write(tree / "ws" / "escape" / "new.txt")


def test_a_missing_whitelist_directory_is_rejected_up_front(tree):
    with pytest.raises(ValueError, match="does not exist"):
        Firewall.build(tree / "ws", [tree / "nope"])


def test_disabling_the_firewall_allows_every_read(tree):
    firewall = Firewall.build(tree / "ws", enabled=False)

    assert firewall.may_read(tree / "private" / "secret.txt")
    assert firewall.wrap(["/bin/bash"]) == ["/bin/bash"]


# --- the load tool -----------------------------------------------------
def load_call(path, register_id=5):
    return ToolCall(id="t", name="load", input={"path": str(path), "start": 0, "register_id": register_id})


def make_agent(root, **overrides):
    config = Config(max_register_length=200, max_special_length=400, max_step_half_length=200, max_canvas_length=800, summary=False, bash_timeout=5.0, **overrides)
    return Agent(
        config=config,
        workspace=Workspace(root),
        model=FakeModel([]),
        instruction="read things",
    )


def test_load_is_blocked_outside_the_policy(tree):
    agent = make_agent(tree / "ws")
    try:
        result = agent.tools.execute(load_call(tree / "private" / "secret.txt"))
    finally:
        agent.bash.close()

    assert "firewall does not allow reading" in result.status
    assert result.register_id is None  # nothing was stored
    assert "SECRET" not in result.payload


def test_load_reads_a_whitelisted_directory(tree):
    agent = make_agent(tree / "ws", readable_dirs=(str(tree / "shared"),))
    try:
        result = agent.tools.execute(load_call(tree / "shared" / "notes.txt"))
    finally:
        agent.bash.close()

    assert result.payload == "shared notes"


# --- enforcement in bash ----------------------------------------------
@pytest.mark.skipif(not MACOS, reason="needs the seatbelt backend")
def test_the_profile_confines_writes_and_protects_the_record(tree):
    firewall = Firewall.build(tree / "ws", [tree / "shared"])
    profile = firewall.seatbelt_profile()

    assert f'(allow file-write*\n  (subpath "{tree / "ws"}")' in profile
    assert "(deny file-write*)" in profile
    assert "trajectory-" in profile  # the run record is denied even inside the workspace
    assert f'(subpath "{tree / "shared"}")' in profile
    assert str(tree / "private") not in profile


@pytest.mark.skipif(not MACOS, reason="needs the seatbelt backend")
def test_bash_cannot_write_outside_the_workspace(tree):
    agent = make_agent(tree / "ws", readable_dirs=(str(tree / "shared"),))
    target = tree / "private" / "hacked.txt"
    try:
        if "sandbox" in agent.bash.execute_command("echo probe").lower():
            pytest.skip("already inside a sandbox that blocks nesting")
        inside = agent.bash.execute_command("echo mine > mine.txt; echo rc=$?")
        outside = agent.bash.execute_command(f"echo bad > {target}; echo rc=$?")
        secret = agent.bash.execute_command(f"cat {tree / 'private' / 'secret.txt'}")
        shared = agent.bash.execute_command(f"cat {tree / 'shared' / 'notes.txt'}")
        record = agent.bash.execute_command(
            f"chmod 666 {agent.trajectory.path.name}; echo rc=$?"
        )
    finally:
        agent.bash.close()

    assert "rc=0" in inside and (tree / "ws" / "mine.txt").exists()
    assert "rc=1" in outside and not target.exists()
    assert "SECRET" not in secret
    assert "shared notes" in shared
    assert "rc=1" in record  # the trajectory is immutable, chmod included
