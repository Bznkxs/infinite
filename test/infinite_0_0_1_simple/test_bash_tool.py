import pytest

from infinite.bash_tool import BashSession


@pytest.fixture
def session(tmp_path):
    bash = BashSession(cwd=str(tmp_path), timeout=5.0)
    yield bash
    bash.close()


def test_state_persists_between_commands(session, tmp_path):
    session.execute_command("mkdir -p sub && cd sub")
    assert session.execute_command("pwd").strip().endswith("sub")


def test_stdout_and_stderr_share_one_pipe(session):
    output = session.execute_command("echo out; echo err >&2")
    assert "out" in output and "err" in output


def test_starts_in_the_workspace(session, tmp_path):
    assert session.execute_command("pwd").strip() == str(tmp_path.resolve())


def test_timeout_restarts_the_session(session):
    output = session.execute_command("echo before; sleep 30", timeout=1.0)
    assert "before" in output
    assert "timed out" in output
    assert session.execute_command("echo alive").strip() == "alive"


def test_partial_output_before_the_sentinel_is_returned(session):
    assert session.execute_command("printf 'no-newline'") == "no-newline"
