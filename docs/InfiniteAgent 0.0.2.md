# InfiniteAgent 0.0.2-simple

0.0.1-simple established the shape: a fixed register file as the whole active
context, everything else on disk behind tools. 0.0.2 leaves that untouched and
adds the three things a run needs in order to be *operated* rather than merely
started — a boundary, a way to continue, and a record of where time went.

Nothing in the register model, the tool set, or the termination condition
changes. See [`InfiniteAgent 0.0.1.md`](InfiniteAgent%200.0.1.md) for those, and
[`Trajectory Format.md`](Trajectory%20Format.md) for the file this writes.

## 1. Firewall

**Writes go to the workspace and nowhere else. Reads go to the workspace and
whatever the operator explicitly adds.** The asymmetry is deliberate: a run
usually needs to read a corpus it must not modify, and there is no symmetric
need to write outside the directory that exists to hold its output.

```bash
infinite "…" -w runs/x                          # workspace-only, read and write
infinite "…" -w runs/x --allow-read ~/corpus    # + read-only corpus
infinite "…" -w runs/x --no-firewall            # off, explicitly
```

There is no flag that widens *writing*. If a run needs to produce something
elsewhere, the operator moves it afterwards.

### Where it is enforced

Not in the agent's prompt, and not by inspecting commands. A command allowlist
is guesswork — `sh -c`, a python one-liner, a Makefile, or a symlink all route
around it — so enforcement is the operating system's:

| Surface | Mechanism |
| --- | --- |
| `bash` | The session is spawned inside a sandbox: seatbelt (`sandbox-exec`) on macOS, bubblewrap (`bwrap`) on Linux. Every child of the shell inherits it. |
| `load` | Checked in Python against the same policy — it reads directly, so the sandbox around bash never sees it. |
| `spawn` | Sub-agents share the workspace and are built from the same config, so they get the same policy. |

The system message tells the model what the boundary is and that a denial is
final. That is a courtesy so it does not waste steps retrying, not the
mechanism.

### System paths

A shell cannot start without reading `/bin/bash`, the dyld cache, and its
libraries; `python3` cannot start without more. So "read only the workspace"
cannot be taken literally, and pretending otherwise would mean a firewall that
turns the sandbox off in practice. The honest split:

- **Toolchain paths** — `/usr`, `/bin`, `/sbin`, `/System`, `/Library`,
  `/Applications`, `/dev`, `/private/etc`, `/private/var/db`,
  `/private/var/select`, `/opt`. Read-only, always, not part of the policy the
  operator sets. Never writable.
- **Data paths** — the workspace (read+write) and `--allow-read` directories
  (read-only). This is the policy.

Metadata reads (`stat`) are allowed globally, because path resolution needs
them; that leaks the existence of paths, not their contents.

**Network is not restricted.** 0.0.1 runs fetch web pages, and confining the
filesystem does not imply confining the network. If that becomes a requirement
it is a separate switch, not a widening of this one.

### The run record

`trajectory-*.jsonl` and `tool_output/` sit inside the workspace but are denied
to the agent. This makes an existing 0.0.1 claim actually true: the trajectory
was left mode `0444`, but the agent runs as the file's owner and could always
have chmod'd it back. Under the sandbox both the write and the chmod fail.

On Linux the same is done by re-binding each record file read-only. bubblewrap
binds paths, not patterns, so a trajectory created *after* the shell starts — a
sub-agent's — keeps only the `0444` guard. On macOS the rule is a regex and
covers files created later too.

### Failure mode

Fail closed. If no backend is available the run refuses to start and says so,
rather than continuing unconfined. `--no-firewall` is the way to say "I know,
proceed anyway", and it is recorded in the trajectory header so a reader can
tell which runs were confined.

> The Linux backend is implemented but has not been exercised on a Linux host;
> the macOS backend is covered by tests that assert real denials.

## 2. Resuming

A run that exhausts its step budget is not finished — it is stopped, with a
workspace full of work and a register file describing where it was. 0.0.2 lets
it continue:

```bash
infinite -w runs/reconstruct_infinite --resume 0ac207e0 --max-steps 40
infinite -w runs/reconstruct_infinite --resume 0ac207e0 --max-steps none
```

**The budget is per segment.** `--max-steps 40` on a resume means forty *more*
steps, not a total of forty. `none` removes the cap. Step numbers continue
across the seam, so step 41 follows step 40 in the same file.

**The continuation goes into the same trajectory**, after a `resume` record.
One run has one history; a reader sees the seam rather than two files it has to
correlate. This is the change that makes the format v2, since `final` is no
longer the last record.

**What carries over.** The workspace is on disk already. Registers come from
the previous segment's `final.registers`, which is exactly the state the loop
ended with. If the process was killed before writing one, the last step's
`registers_before` is used instead and that step is re-done — one wasted step,
no invented state. The trajectory records which of the two happened.

**What may change.** Budgets (`--max-steps`, `--max-depth`) and the model
(`--model`, `--effort`). Register geometry may not: the stored values were
sized for the stored config, so `num_registers` and the length limits come from
the header. Only flags the operator actually passes are applied — everything
else is inherited rather than reset to a default.

## 3. Step timing

Every step records `{started_at, generation_s, tools_s, total_s}`, and every
tool result records its own `duration_s`.

The split matters more than the total. A step is slow either because the model
thought for a long time or because a command did, and those have opposite
fixes — a smaller workspace budget or a different effort setting in the first
case, a faster command or a longer `bash_timeout` in the second. A single
`duration` would hide which one you are looking at. Per-tool durations then
attribute the tool half to a specific call.

Durations use a monotonic clock, so they are unaffected by clock adjustments;
`started_at` is a UTC wall-clock stamp and is the only field comparable across
machines.

## Config

| Field | Default | Meaning |
| --- | --- | --- |
| `firewall` | `True` | Enforce the path policy. |
| `readable_dirs` | `()` | Extra read-only roots. |
| `max_steps` | `40` | Per segment; `None` for no cap. |

## Not in this version

- **Network confinement.** Filesystem only, deliberately.
- **Resuming a sub-agent.** `--resume` takes any agent id in the workspace, but
  a resumed child returns to nobody: its parent's segment is already closed.
  Resuming a root agent is the supported path.
- **Cross-machine trajectories.** Paths in the header are absolute, so a
  trajectory resumes on the machine that produced it.
