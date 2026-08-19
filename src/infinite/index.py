"""A symbol index over the workspace, so a signature costs a line — 7.1.

[Depth, Volume and Width](../../docs/Depth,%20Volume%20and%20Width.md) named the
axis a fixed context is actually defeated by: not the size of the corpus but the
number of facts that must be true at once. Two children spent 240 steps on one
module and wrote nothing, because implementing it needed some forty signatures
live at the same time and the way to get a signature was to read the file that
holds it.

`lookup` is the other way. One AST walk over the workspace's Python turns every
definition into a line — where it is, and what it takes — so forty facts cost
forty lines rather than forty pages, six of them fit in one step, and the answer
fits in the canvas at once, which is the condition for committing against it.

The index is rebuilt lazily and per file: a file whose mtime and size have not
moved is not parsed again, so a `lookup` after a step that wrote one module
costs one parse.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

#: Never walked: the scaffold's own bookkeeping, the agent's scratch, and the
#: places a toolchain keeps other people's code.
SKIP_DIRS = frozenset(
    {
        ".scratch", "tool_output", ".git", ".venv", "venv", "node_modules",
        "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache", "build",
        "dist", ".tox", "site-packages", ".eggs",
    }
)

#: A constant's value is shown, up to here, because "which of the two plausible
#: spellings is it" is the question being asked.
MAX_VALUE_CHARS = 60


@dataclass(frozen=True)
class Symbol:
    qualname: str
    kind: str
    path: str
    line: int
    signature: str

    def render(self) -> str:
        return f"{self.path}:{self.line} {self.signature}"


def _truncate(text: str, limit: int = MAX_VALUE_CHARS) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _unparse(node) -> str:
    try:
        return ast.unparse(node)
    except Exception:  # a node this Python cannot render is not worth a crash
        return "?"


class _FileWalker(ast.NodeVisitor):
    def __init__(self, path: str):
        self.path = path
        self.symbols: list[Symbol] = []
        self._scope: list[str] = []

    def _qualname(self, name: str) -> str:
        return ".".join([*self._scope, name])

    def _add(self, name: str, kind: str, line: int, signature: str) -> None:
        self.symbols.append(
            Symbol(self._qualname(name), kind, self.path, line, signature)
        )

    def _function(self, node, prefix: str) -> None:
        returns = f" -> {_unparse(node.returns)}" if node.returns else ""
        signature = f"{prefix}{self._qualname(node.name)}({_unparse(node.args)}){returns}"
        self._add(node.name, "function", node.lineno, signature)
        # Nested functions are private by construction and only add noise; a
        # method is not nested in that sense, so a class opens a scope and a
        # function does not.

    def visit_FunctionDef(self, node) -> None:  # noqa: N802
        self._function(node, "def ")

    def visit_AsyncFunctionDef(self, node) -> None:  # noqa: N802
        self._function(node, "async def ")

    def visit_ClassDef(self, node) -> None:  # noqa: N802
        bases = ", ".join(_unparse(b) for b in node.bases)
        signature = f"class {self._qualname(node.name)}({bases})" if bases else (
            f"class {self._qualname(node.name)}"
        )
        self._add(node.name, "class", node.lineno, signature)
        self._scope.append(node.name)
        for child in node.body:
            self.visit(child)
        self._scope.pop()

    def visit_AnnAssign(self, node) -> None:  # noqa: N802
        # `field: type = default` — a dataclass field is a fact an agent
        # implementing against it needs by name, and it is exactly one line.
        if not isinstance(node.target, ast.Name):
            return
        value = f" = {_truncate(_unparse(node.value))}" if node.value else ""
        signature = f"{self._qualname(node.target.id)}: {_unparse(node.annotation)}{value}"
        self._add(node.target.id, "attribute", node.lineno, signature)

    def visit_Assign(self, node) -> None:  # noqa: N802
        for target in node.targets:
            if isinstance(target, ast.Name):
                signature = f"{self._qualname(target.id)} = {_truncate(_unparse(node.value))}"
                self._add(target.id, "attribute", node.lineno, signature)


def walk_source(source: str, path: str) -> list[Symbol]:
    """Every definition in one file, as one line each."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    walker = _FileWalker(path)
    for node in tree.body:
        walker.visit(node)
    return walker.symbols


class SymbolIndex:
    """The workspace's Python definitions, kept current per file."""

    def __init__(self, root: Path | str, *, display=None):
        self.root = Path(root).resolve()
        #: How a path is named to the model; the workspace's own `display`.
        self.display = display or (lambda p: str(Path(p).relative_to(self.root)))
        self._cache: dict[Path, tuple[tuple[int, int], list[Symbol]]] = {}

    def _sources(self):
        for path in self.root.rglob("*.py"):
            if any(part in SKIP_DIRS for part in path.relative_to(self.root).parts):
                continue
            yield path

    def symbols(self) -> list[Symbol]:
        """Every symbol in the workspace, reparsing only what has changed."""
        found: list[Symbol] = []
        live: set[Path] = set()
        for path in self._sources():
            live.add(path)
            try:
                stat = path.stat()
            except OSError:
                continue
            stamp = (stat.st_mtime_ns, stat.st_size)
            cached = self._cache.get(path)
            if cached is None or cached[0] != stamp:
                try:
                    source = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                cached = (stamp, walk_source(source, self.display(path)))
                self._cache[path] = cached
            found.extend(cached[1])
        for gone in set(self._cache) - live:
            del self._cache[gone]
        return found

    def lookup(self, symbol: str, limit: int) -> tuple[list[Symbol], int]:
        """Matches for `symbol`, most exact first, and how many there were.

        Three passes, narrowest first, and the first that finds anything wins:
        the whole qualified name, then the last component (so `store` finds
        `RegisterFile.store`), then a case-insensitive substring. A query that
        matches exactly should never be buried under the things it is a prefix
        of.
        """
        query = symbol.strip()
        if not query:
            return [], 0
        everything = self.symbols()
        lowered = query.lower()
        for match in (
            lambda s: s.qualname == query,
            lambda s: s.qualname.split(".")[-1] == query,
            lambda s: lowered in s.qualname.lower(),
        ):
            hits = [s for s in everything if match(s)]
            if hits:
                hits.sort(key=lambda s: (s.path, s.line))
                return hits[:limit], len(hits)
        return [], 0
