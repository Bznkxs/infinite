"""The 0.0.2 firewall: what the agent's bash session and `load` tool may touch.

Two rules, and they are not symmetric:

* **Write** — the workspace, and nothing else. There is no way to widen this.
* **Read** — the workspace, plus any directories the operator explicitly
  allows with `--allow-read`. With no whitelist, the workspace is all there is.

Read access to system paths (`/usr`, `/bin`, the dyld cache, …) is not part of
that policy — a shell cannot start without them, and neither can any program it
runs. They are allowed read-only and are never writable, so the toolchain works
while the operator's data does not leak. `SYSTEM_READ` is that set.

`load` is checked in Python, exactly. `bash` is checked by the OS: the session
runs under seatbelt (macOS) or bubblewrap (Linux). A missing backend is fatal
rather than silently unenforced — see `FirewallUnavailable`.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

#: Read-only paths a shell and its toolchain need in order to run at all.
SYSTEM_READ_DARWIN = (
    "/usr", "/bin", "/sbin", "/System", "/Library", "/Applications",
    "/dev", "/private/etc", "/private/var/db", "/private/var/select", "/opt",
)
SYSTEM_READ_LINUX = (
    "/usr", "/bin", "/sbin", "/lib", "/lib64", "/etc", "/opt",
)


#: The interpreter running the scaffold, which is not necessarily under any of
#: the paths above. Under `uv run`, `python3` on the agent's PATH resolves into
#: `.venv/bin/` and from there into `~/.local/share/uv/python/cpython-…`, so a
#: sandboxed shell that reached for it could not read its own stdlib and died
#: with `ModuleNotFoundError: No module named 'encodings'` — with stderr
#: swallowed, an empty register and no explanation. Every `check` in the 0.0.8
#: arms was a `python3 -c 'import …'` and they worked only because those runs
#: happened to resolve `python3` to `/usr/bin/python3`. Whichever interpreter
#: this scaffold is running under is one the agent may read.
def system_read(platform: str | None = None) -> tuple[str, ...]:
    base = SYSTEM_READ_DARWIN if (platform or sys.platform) == "darwin" else SYSTEM_READ_LINUX
    extra = []
    for root in (sys.base_prefix, sys.prefix, os.path.realpath(sys.base_prefix)):
        resolved = str(Path(root).resolve())
        if resolved in extra or any(
            resolved == p or resolved.startswith(p + "/") for p in base
        ):
            continue
        extra.append(resolved)
    return base + tuple(extra)

#: Files inside the workspace that record the run and are never the agent's to
#: write. The chmod in `Trajectory` is advisory — the owner can always undo it;
#: under the sandbox this is the rule that actually holds.
RECORD_PATTERN = r"trajectory-[^/]*\.jsonl"
RECORD_DIR = "tool_output"


class FirewallUnavailable(RuntimeError):
    """No sandbox backend on this platform. Fail closed, never silently open."""


def _escape(text: str) -> str:
    """Escape a path for a seatbelt string literal."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _escape_regex(pattern: str) -> str:
    """Escape a *regex* for a seatbelt `#"..."` literal.

    Only the quote is escaped: the backslashes in the pattern are regex syntax,
    and doubling them would ask the OS to match a literal backslash instead.
    """
    return pattern.replace('"', '\\"')


@dataclass(frozen=True)
class Firewall:
    """The path policy for one workspace."""

    workspace: Path
    #: Extra read-only roots, from `--allow-read`.
    readable: tuple[Path, ...] = ()
    enabled: bool = True
    _profile: list[Path] = field(default_factory=list, compare=False, repr=False)

    @classmethod
    def build(
        cls,
        workspace: str | Path,
        readable: tuple[str, ...] | list[str] = (),
        *,
        enabled: bool = True,
    ) -> "Firewall":
        root = Path(workspace).resolve()
        roots = []
        for entry in readable:
            path = Path(entry).expanduser().resolve()
            if not path.exists():
                raise ValueError(f"--allow-read path does not exist: {path}")
            roots.append(path)
        return cls(workspace=root, readable=tuple(roots), enabled=enabled)

    # --- policy --------------------------------------------------------
    def _under(self, path: Path, root: Path) -> bool:
        try:
            return path == root or path.is_relative_to(root)
        except (OSError, ValueError):
            return False

    def resolve(self, path: str | Path) -> Path:
        """Resolve a path the way the check will see it: symlinks and all.

        `strict=False` so a not-yet-existing file still resolves; the parent
        chain is what matters for containment.
        """
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = self.workspace / candidate
        return candidate.resolve()

    def may_write(self, path: str | Path) -> bool:
        return self._under(self.resolve(path), self.workspace)

    def may_read(self, path: str | Path) -> bool:
        target = self.resolve(path)
        if not self.enabled:
            return True
        roots = (self.workspace, *self.readable)
        return any(self._under(target, root) for root in roots)

    def check_read(self, path: str | Path, display: str) -> str | None:
        """An error message for a `load` outside the policy, or None."""
        if self.may_read(path):
            return None
        allowed = ", ".join(str(p) for p in self.readable)
        return (
            f"error: the firewall does not allow reading {display}; readable roots are "
            f"the workspace{' and ' + allowed if allowed else ''} "
            "(the operator can widen this with --allow-read)"
        )

    def describe(self) -> str:
        """The paragraph the system message shows the model."""
        if not self.enabled:
            return "The firewall is off: this session can read and write anywhere."
        extra = "".join(f"\n- {p} (read-only)" for p in self.readable)
        # Sent every step, so it says each rule once. 0.0.7g cut it from 590
        # chars to a little over half that; nothing in it stopped being true.
        return (
            "Enforced by the OS for every command and every `load`, not by convention:\n"
            f"- {self.workspace} — your workspace, the only place you can write.{extra}\n"
            "Nothing else is readable but system paths, which are never writable. Your "
            "own run record (trajectory files, tool_output/) is read-only. Network is "
            "open. A blocked call fails with 'Operation not permitted' — the firewall, "
            "not a bug."
        )

    # --- enforcement for bash -----------------------------------------
    def wrap(self, argv: list[str]) -> list[str]:
        """The command line that runs `argv` under the sandbox."""
        if not self.enabled:
            return argv
        if sys.platform == "darwin":
            return self._wrap_seatbelt(argv)
        if sys.platform.startswith("linux"):
            return self._wrap_bwrap(argv)
        raise FirewallUnavailable(
            f"no sandbox backend for platform {sys.platform!r}; "
            "run with --no-firewall to proceed without one"
        )

    def cleanup(self) -> None:
        for path in self._profile:
            path.unlink(missing_ok=True)
        self._profile.clear()

    # --- macOS ---------------------------------------------------------
    def seatbelt_profile(self) -> str:
        workspace = _escape(str(self.workspace))
        reads = "\n".join(
            f'  (subpath "{_escape(p)}")' for p in system_read("darwin")
        )
        allowed = "\n".join(
            f'  (subpath "{_escape(str(p))}")' for p in self.readable
        )
        record = re.escape(str(self.workspace)) + "/" + RECORD_PATTERN
        return f"""(version 1)
;; Start from a working shell, then take away file access.
(allow default)

;; --- writes: the workspace, and nothing else -----------------------
(deny file-write*)
(allow file-write*
  (subpath "{workspace}")
  (subpath "/dev"))
;; the run's own record stays immutable, chmod included
(deny file-write*
  (regex #"^{_escape_regex(record)}$")
  (subpath "{workspace}/{RECORD_DIR}"))

;; --- reads: workspace + whitelist, plus the toolchain ---------------
(deny file-read*)
;; metadata alone leaks only existence, and path resolution needs it
(allow file-read-metadata)
(allow file-read*
  (literal "/")
{reads}
  (subpath "{workspace}")
{allowed})
"""

    def _wrap_seatbelt(self, argv: list[str]) -> list[str]:
        if not shutil.which("sandbox-exec"):
            raise FirewallUnavailable(
                "sandbox-exec is missing; run with --no-firewall to proceed without a sandbox"
            )
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".sb", prefix="infinite-firewall-", delete=False
        )
        with handle:
            handle.write(self.seatbelt_profile())
        # Outside the workspace, so the sandboxed shell can neither read nor
        # edit the rules it runs under.
        self._profile.append(Path(handle.name))
        return ["sandbox-exec", "-f", handle.name, *argv]

    # --- Linux ---------------------------------------------------------
    def bwrap_args(self) -> list[str]:
        args = ["bwrap", "--die-with-parent", "--proc", "/proc", "--dev", "/dev"]
        for path in system_read("linux"):
            if os.path.exists(path):  # /lib64 and /opt are not everywhere
                args += ["--ro-bind", path, path]
        args += ["--bind", str(self.workspace), str(self.workspace)]
        for path in self.readable:
            args += ["--ro-bind", str(path), str(path)]
        # bwrap binds paths, not patterns, so each record file is re-bound
        # read-only over itself. Files created later (a sub-agent's trajectory)
        # keep only the chmod guard; see docs/InfiniteAgent 0.0.2.md.
        for record in sorted(self.workspace.glob("trajectory-*.jsonl")):
            args += ["--ro-bind", str(record), str(record)]
        output = self.workspace / RECORD_DIR
        if output.is_dir():
            args += ["--ro-bind", str(output), str(output)]
        return args + ["--chdir", str(self.workspace)]

    def _wrap_bwrap(self, argv: list[str]) -> list[str]:
        if not shutil.which("bwrap"):
            raise FirewallUnavailable(
                "bubblewrap (bwrap) is not installed; install it, or run with "
                "--no-firewall to proceed without a sandbox"
            )
        return [*self.bwrap_args(), "--", *argv]
