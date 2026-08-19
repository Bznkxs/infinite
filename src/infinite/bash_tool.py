import os
import select
import subprocess
import time
import uuid


class BashSession:
    """A bash process that stays alive between commands so state persists.

    stdout and stderr are bound to the same pipe, so the returned string is the
    terminal output in generation order — the simple scaffold does not
    differentiate the two.
    """

    def __init__(self, cwd=None, timeout=60.0, firewall=None, env=None):
        self.cwd = cwd
        self.timeout = timeout
        #: A Firewall, or None to run unconfined. It wraps the shell in a
        #: sandbox, so the restriction survives anything the shell then runs.
        self.firewall = firewall
        #: The shell's whole environment, or None to inherit this process's.
        #: Used to point TMPDIR and the various caches somewhere the firewall
        #: allows, so the toolchain does not trip over the sandbox.
        self.env = env
        self._start()

    def _start(self):
        argv = ["/bin/bash"]
        if self.firewall is not None:
            argv = self.firewall.wrap(argv)
        self.process = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # interleave errors with output, in order
            cwd=self.cwd,
            env=self.env,
            start_new_session=True,  # own process group: a timeout can kill every child
        )
        self._fd = self.process.stdout.fileno()

    def execute_command(self, command, timeout=None):
        """Run a command in the session and return its terminal output."""
        limit = self.timeout if timeout is None else timeout
        deadline = time.monotonic() + limit
        sentinel = f"__INFINITE_BASH_DONE_{uuid.uuid4().hex}__"  # unique per call
        marker = sentinel.encode()

        try:
            self.process.stdin.write(f"{command}\necho {sentinel}\n".encode())
            self.process.stdin.flush()
        except (BrokenPipeError, ValueError):
            self.restart()
            return "[error] bash session was not running; it has been restarted"

        buffer = bytearray()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                partial = buffer.decode("utf-8", errors="replace")
                self.restart()
                return (
                    f"{partial}\n[error] command timed out after {limit:g}s; "
                    "the bash session has been restarted and its state is gone"
                )
            ready, _, _ = select.select([self._fd], [], [], min(remaining, 0.5))
            if not ready:
                continue
            chunk = os.read(self._fd, 65536)
            if not chunk:  # the shell died
                partial = buffer.decode("utf-8", errors="replace")
                self.restart()
                return f"{partial}\n[error] bash session exited; it has been restarted"
            buffer += chunk
            if marker in buffer:  # this command's output is complete
                output, _, _ = buffer.partition(marker)
                return output.decode("utf-8", errors="replace")

    def restart(self):
        self.close()
        self._start()

    def close(self):
        if self.firewall is not None:
            self.firewall.cleanup()
        process = getattr(self, "process", None)
        if process is None:
            return
        try:
            os.killpg(os.getpgid(process.pid), 9)  # the whole group, not just bash
        except (ProcessLookupError, PermissionError, OSError):
            process.kill()
        for stream in (process.stdin, process.stdout):
            try:
                stream.close()
            except OSError:
                pass
        process.wait()


"""
bash_session = BashSession()
print(bash_session.execute_command("cd /tmp && pwd"))
print(bash_session.execute_command("pwd"))  # still /tmp: the session kept its state
"""
