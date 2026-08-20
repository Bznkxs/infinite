"""0.0.8d: `lookup` is gone, and the memo table it used to write is not.

0.0.8's `lookup` answered a symbol with one index line, which was the right
shape for the wrong reason: the index was an AST walk over the workspace's
*Python*, so the one tool that was supposed to turn width into depth could only
do it for one language. `grep` is language-agnostic, the agent already has it,
and the 0.0.8 runs said the agent reached for it anyway — 29 read calls and
fifteen hand-built signature files in the arm that had `lookup` available.

What survives is `facts.md`: the shared, append-only table 0.0.8b §4 asked for,
which no longer depends on a tool to fill it. These tests pin the two halves —
the tool is not offered and not callable, and the table exists before anything
writes to it.
"""

from infinite.workspace import FACTS_HEADER, Workspace

from .conftest import build_agent, run


# --- the tool is gone -------------------------------------------------
def test_lookup_is_not_offered(agent):
    assert "lookup" not in [spec["name"] for spec in agent.tools.specs()]


def test_calling_lookup_is_refused_like_any_unknown_tool(agent):
    result = run(agent, "lookup", symbol="RegisterFile.store", register_id=5)

    assert result.status == "error: unknown tool 'lookup'"
    assert result.record["error"] == result.status
    # The payload never lands, so a model that guesses at a tool it was not
    # given loses the step and not the register.
    assert result.register_id is None
    assert agent.registers.values[5] == ""


def test_no_configuration_brings_it_back(agent):
    """There is no `lookup` knob any more — a stale one would fail loudly."""
    import dataclasses

    fields = {f.name for f in dataclasses.fields(agent.config)}
    assert not {name for name in fields if "lookup" in name}


# --- the table stays --------------------------------------------------
def test_the_memo_table_exists_before_anything_writes_to_it(tmp_path):
    """The 0.0.8 bug: the system message named a file nothing had created.

    `lookup` was its only writer, so in the four arms that never called it the
    file was absent while every step told the agent it was the run's memo table.
    Three of those runs opened by `cat`ing it and getting nothing.
    """
    workspace = Workspace(tmp_path / "run")

    facts = workspace.facts_path()
    assert facts.is_file()
    assert facts.read_text(encoding="utf-8") == FACTS_HEADER


def test_the_system_message_names_the_table_and_the_header_names_no_tool(tmp_path):
    built = build_agent(tmp_path)
    try:
        message = built.system_message()
    finally:
        built.bash.close()

    assert "facts.md" in message
    assert "lookup" not in message
    assert "lookup" not in FACTS_HEADER


def test_an_agent_appends_to_it_with_the_shell(tmp_path):
    """The whole interface now: `>>` to write, `grep` to read."""
    built = build_agent(tmp_path)
    built.step = 1
    try:
        run(
            built,
            "bash",
            command="echo 'RegisterFile.store returns True when it cut' >> facts.md",
            register_id=5,
        )
        result = run(
            built, "bash", command="grep -c 'RegisterFile.store' facts.md", register_id=6
        )
    finally:
        built.bash.close()

    assert result.payload.strip() == "1"
    # And the header survived the append, so the next `grep` still sees the rule.
    assert built.workspace.facts_path().read_text(encoding="utf-8").startswith("# facts")


def test_the_table_is_shared_by_every_agent_in_the_workspace(tmp_path):
    """A fact one frame paid for is one the next frame should not pay for again."""
    workspace = Workspace(tmp_path / "run")
    workspace.facts_path().write_text(FACTS_HEADER + "one fact\n", encoding="utf-8")

    # A second Workspace over the same root is what a child gets.
    again = Workspace(tmp_path / "run")

    assert "one fact" in again.facts_path().read_text(encoding="utf-8")
