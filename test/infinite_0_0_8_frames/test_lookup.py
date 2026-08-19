"""7.1 — precise retrieval, which is how width becomes depth.

Two children spent 240 steps on `step_loop.py` and wrote nothing. It was not
short of room to write; it was short of room to hold an interface, because the
module calls into six others and the way to learn a signature was to read the
file that holds it. Forty facts cost forty pages.

`lookup` makes them cost forty lines — and the memo table beside it (0.0.8b §4)
is the artefact five runs kept reaching for, in the form the work actually
wants: written incrementally, read by key.
"""

from infinite.index import SymbolIndex, walk_source

from .conftest import agent, build_agent, call, run  # noqa: F401

SOURCE = '''
"""A module."""
import json

VERSION = "0.0.8"


class RegisterFile:
    """Holds the registers."""

    limit: int = 208

    def store(self, register_id: int, value, *, truncated: bool | None = None) -> bool:
        return False

    async def flush(self) -> None:
        pass


def render(step: int, max_steps: int | None = None) -> str:
    def helper():
        """Nested, and nobody's business."""
    return ""
'''


def test_a_definition_becomes_one_line():
    symbols = {s.qualname: s for s in walk_source(SOURCE, "src/registers.py")}

    assert symbols["RegisterFile.store"].render() == (
        "src/registers.py:13 def RegisterFile.store(self, register_id: int, value, *, "
        "truncated: bool | None=None) -> bool"
    )
    assert symbols["render"].render().endswith(
        "def render(step: int, max_steps: int | None=None) -> str"
    )
    assert symbols["RegisterFile.flush"].signature.startswith("async def")
    assert symbols["RegisterFile"].signature == "class RegisterFile"
    # Dataclass-shaped facts are the ones an implementer asks for by name.
    assert symbols["RegisterFile.limit"].signature == "RegisterFile.limit: int = 208"
    assert symbols["VERSION"].signature == "VERSION = '0.0.8'"
    # A nested function is private by construction, so it is not a fact.
    assert "helper" not in symbols


def test_a_file_that_does_not_parse_is_skipped_rather_than_fatal():
    assert walk_source("def broken(:\n", "x.py") == []


def test_the_index_finds_by_name_qualified_name_and_fragment(tmp_path):
    (tmp_path / "registers.py").write_text(SOURCE)
    index = SymbolIndex(tmp_path)

    exact, total = index.lookup("RegisterFile.store", 10)
    assert total == 1 and exact[0].qualname == "RegisterFile.store"
    # The last component alone, which is how a caller usually knows it.
    tail, _ = index.lookup("store", 10)
    assert tail[0].qualname == "RegisterFile.store"
    # And a fragment, only when nothing exact matches.
    fragment, _ = index.lookup("regis", 10)
    assert {s.qualname for s in fragment} >= {"RegisterFile", "RegisterFile.store"}
    assert index.lookup("nothing_of_the_sort", 10) == ([], 0)


def test_an_exact_match_is_not_buried_under_what_it_is_a_prefix_of(tmp_path):
    (tmp_path / "m.py").write_text("def run(): pass\ndef run_step(): pass\n")
    hits, total = SymbolIndex(tmp_path).lookup("run", 10)
    assert [h.qualname for h in hits] == ["run"] and total == 1


def test_the_index_notices_a_file_that_changed(tmp_path):
    path = tmp_path / "m.py"
    path.write_text("def before(): pass\n")
    index = SymbolIndex(tmp_path)
    assert index.lookup("before", 5)[1] == 1

    path.write_text("def after(): pass\n")
    assert index.lookup("before", 5)[1] == 0
    assert index.lookup("after", 5)[1] == 1

    path.unlink()
    assert index.lookup("after", 5)[1] == 0


def test_the_scaffolds_own_bookkeeping_is_not_indexed(agent):
    (agent.scratch / "throwaway.py").write_text("def scratch_only(): pass\n")
    (agent.workspace.root / "real.py").write_text("def real_thing(): pass\n")

    assert agent.index.lookup("scratch_only", 5)[1] == 0
    assert agent.index.lookup("real_thing", 5)[1] == 1


# --- the tool ------------------------------------------------------------
def test_lookup_returns_lines_and_says_how_many_there_were(agent):
    (agent.workspace.root / "registers.py").write_text(SOURCE)
    result = run(agent, "lookup", symbol="store", register_id=6)

    assert "def RegisterFile.store" in agent.registers.values[6]
    assert result.status == "OK lookup 'store': 1 of 1"


def test_a_miss_says_what_to_do_instead(agent):
    result = run(agent, "lookup", symbol="not_here", register_id=6)
    assert "no definition of 'not_here'" in result.status
    assert "grep" in result.status
    assert agent.registers.values[6] == ""


def test_too_many_matches_are_capped_and_said_to_be(tmp_path):
    built = build_agent(tmp_path, lookup_max_matches=2)
    built.step = 1
    try:
        (built.workspace.root / "m.py").write_text(
            "".join(f"def thing_{i}(): pass\n" for i in range(6))
        )
        result = run(built, "lookup", symbol="thing", register_id=6)
        assert result.status == "OK lookup 'thing': 2 of 6 (narrow it, or grep)"
        assert len(built.registers.values[6].splitlines()) == 2
    finally:
        built.bash.close()


def test_what_lookup_resolves_lands_in_the_memo_table(agent):
    (agent.workspace.root / "registers.py").write_text(SOURCE)
    run(agent, "lookup", symbol="store", register_id=6)
    run(agent, "lookup", symbol="store", register_id=6)  # twice: one line, not two

    facts = agent.workspace.facts_path().read_text()
    assert facts.count("def RegisterFile.store") == 1
    # And the agent can add what an index cannot know, and grep for both.
    agent.workspace.remember(["RegisterFile.store returns True when it cut"])
    grepped = run(
        agent, "bash", command="grep -c 'RegisterFile.store' facts.md", register_id=7
    )
    assert grepped.record["output"].strip() == "2"


def test_the_memo_table_is_named_in_the_system_message(agent):
    assert "facts.md" in agent.system_message()
    assert "memo table" in agent.system_message()


def test_lookup_can_be_left_out_for_a_comparison(tmp_path):
    built = build_agent(tmp_path, lookup=False)
    try:
        assert "lookup" not in [t["name"] for t in built.tools.specs()]
        assert "facts.md" not in built.system_message()
        assert "unknown tool" in built.tools.execute(
            call("lookup", symbol="x")
        ).status
    finally:
        built.bash.close()


# --- a surface, not a fact -----------------------------------------------
def test_a_path_asks_for_the_whole_surface_of_a_module(agent):
    """The first live 0.0.8 run never called `lookup` once.

    Asked to implement a module that calls into six others, the agent ran one
    `grep` for every `def` in the package and put 75 lines in a file. What it
    wanted was not a symbol but an interface, all at once — and one symbol at a
    time is six calls to get what one `grep` gets. So a path is a query too, and
    unlike the grep it returns real signatures rather than first lines.
    """
    (agent.workspace.root / "registers.py").write_text(SOURCE)
    result = run(agent, "lookup", symbol="registers.py", register_id=agent.config.canvas_id)

    lines = agent.registers.values[agent.config.canvas_id].splitlines()
    assert result.status.startswith("OK lookup 'registers.py': 6 of 6")
    assert any("class RegisterFile" in line for line in lines)
    assert any("def RegisterFile.store" in line for line in lines)
    assert any("VERSION" in line for line in lines)
    # In the order they appear in the file, which is how a module reads.
    assert lines == sorted(lines, key=lambda l: int(l.split(":")[1].split()[0]))


def test_a_dotted_module_name_is_a_path_and_a_dotted_symbol_is_not(agent):
    (agent.workspace.root / "pkg").mkdir()
    (agent.workspace.root / "pkg" / "registers.py").write_text(SOURCE)

    whole = run(agent, "lookup", symbol="pkg.registers", register_id=6)
    assert "6 of 6" in whole.status

    one = run(agent, "lookup", symbol="RegisterFile.store", register_id=6)
    assert "1 of 1" in one.status
    assert agent.registers.values[6].count("\n") == 0


def test_a_dotted_name_that_is_neither_falls_back_rather_than_missing(agent):
    (agent.workspace.root / "registers.py").write_text(SOURCE)
    result = run(agent, "lookup", symbol="registers.store", register_id=6)
    # No `registers/store.py`, so it is read as a symbol fragment instead.
    assert "no definition" in result.status or "1 of 1" in result.status


def test_an_outline_is_capped_at_what_a_register_can_hold(tmp_path):
    built = build_agent(tmp_path, lookup_max_outline=3)
    built.step = 1
    try:
        (built.workspace.root / "wide.py").write_text(
            "".join(f"def thing_{i}(): pass\n" for i in range(10))
        )
        result = run(built, "lookup", symbol="wide.py", register_id=6)
        assert result.status == "OK lookup 'wide.py': 3 of 10 (narrow it, or grep)"
    finally:
        built.bash.close()
