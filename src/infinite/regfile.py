"""The register file as a directory the shell can reach — 0.0.8a §3.

Until 0.0.8 there was exactly one route out of a register: the model read the
value off the dump and typed it again into its next generation. Register to
shell command, register to register, register to a child's brief — all three
were re-generation, in a scaffold whose writing rate is its bottleneck. So a
register was a display rather than a memory.

The cheap fix is not a family of tools. It is a directory. Around every `bash`
call the register file is written to `$REGDIR/0 … $REGDIR/N` and exported as
`$R0 … $RN`; afterwards the files are read back and any that changed are stored,
truncated and tagged exactly as a tool result is. Copy, deref-copy, and writing
a register from a computation are then all the shell, and cost one sentence of
system message rather than four tool schemas.

Registers 0-4 are the system's. Their files are written out like any other — a
command may read `$R2` — and a write to one is refused on the way back, the way
`check_destination` refuses it now.
"""

from __future__ import annotations

import shlex
from pathlib import Path

from .config import Config
from .registers import RegisterFile

#: The environment variable that names the directory. 0.0.8a's second open
#: question: inside the workspace `reg/` is discoverable but also deletable by
#: the agent's own `rm` and visible in every `ls` of the work; in the per-agent
#: scratch directory it is safe, and costs one sentence to name.
REGDIR_VAR = "REGDIR"

#: Sourced at the top of every command. A file rather than a string of exports
#: because a register may hold anything, including newlines and quotes.
LOADER = ".load"


class RegisterShell:
    """Keeps a directory and a set of shell variables in step with the registers."""

    def __init__(self, registers: RegisterFile, directory: Path, config: Config):
        self.registers = registers
        self.directory = Path(directory)
        self.config = config
        #: What each file held when it was last written, so a change can be told
        #: from an untouched file without hashing the whole dump.
        self._written: list[bytes] = []

    # --- addressing ----------------------------------------------------
    @property
    def loader(self) -> Path:
        return self.directory / LOADER

    def path(self, register_id: int) -> Path:
        return self.directory / str(register_id)

    #: The name of the variable, for a system message that has to say it.
    environment_variable = REGDIR_VAR

    def environment(self) -> dict[str, str]:
        """The one variable a shell session needs to find the rest."""
        return {REGDIR_VAR: str(self.directory)}

    def preamble(self) -> str:
        """Prefixed to every command, so `$R5` is current at the moment it runs."""
        return f'source {shlex.quote(str(self.loader))}\n'

    # --- out and back --------------------------------------------------
    def sync_out(self) -> None:
        """Write every register to its file and to the loader script."""
        self.directory.mkdir(parents=True, exist_ok=True)
        self._written = []
        lines = [f"export {REGDIR_VAR}={shlex.quote(str(self.directory))}"]
        for i, value in enumerate(self.registers.values):
            data = value.encode("utf-8")
            self.path(i).write_bytes(data)
            self._written.append(data)
            lines.append(f"export R{i}={shlex.quote(value)}")
        self.loader.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def sync_in(self) -> list[str]:
        """Store whatever the command changed. Returns one short note per register.

        A missing file is not a write: the agent's own `rm` should not clear a
        register, and the next `sync_out` puts it back.
        """
        notes: list[str] = []
        for i, before in enumerate(self._written):
            path = self.path(i)
            try:
                after = path.read_bytes()
            except OSError:
                continue
            if after == before:
                continue
            if self.registers.is_special(i):
                # Put it back rather than leave the file disagreeing with the
                # register: the next command would otherwise read a value the
                # dump does not show.
                path.write_bytes(before)
                notes.append(f"r{i} refused (system-written)")
                continue
            text = after.decode("utf-8", errors="replace")
            cut = self.registers.store(i, text)
            note = f"r{i}={len(self.registers.values[i])}c"
            if cut:
                note += f" (cut from {len(text)})"
            notes.append(note)
        self._written = []
        return notes
