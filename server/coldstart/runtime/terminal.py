"""A real, sandboxed shell for the in-browser terminal (xterm.js over a WebSocket).

The shell runs inside sandbox-exec with the same rules as test runs: no
outbound network and writes only inside the engagement's workspace.
"""

from __future__ import annotations

import asyncio
import codecs
import fcntl
import os
import pty
import re
import signal
import struct
import subprocess
import termios
from pathlib import Path
from typing import Callable

from .. import config, sandbox

ZSHRC = r"""
# Cold Start terminal (sandboxed: no network, writes limited to this workspace)
export PATH="$VIRTUAL_ENV/bin:$PATH"
setopt PROMPT_SUBST
unsetopt BEEP
HISTSIZE=2000
SAVEHIST=2000
setopt INC_APPEND_HISTORY HIST_IGNORE_DUPS
autoload -Uz colors && colors
_cs_branch() { git symbolic-ref --short HEAD 2>/dev/null }
PROMPT='%F{245}%1~%f %F{179}$(_cs_branch)%f %F{110}❯%f '
alias ll='ls -lah'
alias la='ls -A'
alias gs='git status -sb'
alias gd='git diff'
alias t='python -m pytest -q'
bindkey -e
bindkey '^[[A' up-line-or-search
bindkey '^[[B' down-line-or-search
printf '\e[38;5;245mCold Start shell · python %s · sandboxed (no network) · try: pytest -q, python -i, git diff\e[0m\n' "$(python -c 'import sys;print(sys.version.split()[0])')"
"""

ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b[@-Z\\-_]")


def _zdotdir() -> Path:
    d = config.DATA_DIR / "shell"
    d.mkdir(parents=True, exist_ok=True)
    rc = d / ".zshrc"
    if not rc.exists() or rc.read_text() != ZSHRC:
        rc.write_text(ZSHRC)
    return d


class TerminalSession:
    def __init__(self, workspace_root: Path, cwd: Path, cols: int = 100, rows: int = 30,
                 on_command: Callable[[str], None] | None = None):
        self.master, slave = pty.openpty()
        self._set_size(cols, rows)
        env = sandbox.runtime_env({
            "TERM": "xterm-256color",
            "COLORTERM": "truecolor",
            "ZDOTDIR": str(_zdotdir()),
            "HISTFILE": str(workspace_root / ".zsh_history"),
            "SHELL": "/bin/zsh",
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        argv, self._profile = sandbox.wrap(["/bin/zsh", "-i"], [workspace_root])
        sandbox.hand_over(workspace_root)
        jail = sandbox.spawn_kwargs().get("preexec_fn")

        def preexec() -> None:
            # We're a fresh session leader with the PTY slave on fd 0: make it our
            # controlling terminal so job control (Ctrl-C, Ctrl-Z, fg) works on Linux.
            try:
                fcntl.ioctl(0, termios.TIOCSCTTY, 0)
            except OSError:
                pass
            if jail:
                jail()

        self.proc = subprocess.Popen(
            argv, stdin=slave, stdout=slave, stderr=slave, cwd=str(cwd), env=env,
            start_new_session=True, close_fds=True, preexec_fn=preexec,
        )
        os.close(slave)
        os.set_blocking(self.master, False)
        self._on_command = on_command
        self._line = ""
        self._queue: asyncio.Queue[bytes | None] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self.closed = False

    def _set_size(self, cols: int, rows: int) -> None:
        fcntl.ioctl(self.master, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

    def resize(self, cols: int, rows: int) -> None:
        if not self.closed and cols > 0 and rows > 0:
            self._set_size(cols, rows)

    def write(self, data: str) -> None:
        if self.closed:
            return
        os.write(self.master, data.encode())
        self._track(data)

    def _track(self, data: str) -> None:
        """Approximate the command line typed, for the investigation timeline."""
        if self._on_command is None:
            return
        for ch in ANSI.sub("", data):
            if ch in "\r\n":
                cmd = self._line.strip()
                self._line = ""
                if cmd:
                    self._on_command(cmd)
            elif ch in "\x7f\b":
                self._line = self._line[:-1]
            elif ch == "\x03":
                self._line = ""
            elif ch.isprintable():
                self._line += ch

    async def pump(self, send: Callable[[str], "asyncio.Future[None]"]) -> None:
        """Forward PTY output to `send` until the shell exits."""
        loop = self._loop = asyncio.get_running_loop()
        queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._queue = queue

        def readable() -> None:
            try:
                data = os.read(self.master, 65536)
            except (BlockingIOError, InterruptedError):
                return
            except OSError:
                data = b""
            if not data:
                loop.remove_reader(self.master)
                queue.put_nowait(None)
            else:
                queue.put_nowait(data)

        loop.add_reader(self.master, readable)
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        try:
            while True:
                chunk = await queue.get()
                if chunk is None:
                    break
                text = decoder.decode(chunk)
                if text:
                    await send(text)
        finally:
            try:
                loop.remove_reader(self.master)
            except (ValueError, OSError):
                pass

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        if self._loop is not None:
            try:
                self._loop.remove_reader(self.master)
            except (ValueError, OSError):
                pass
        if self._queue is not None:
            self._queue.put_nowait(None)  # unblock pump()
        try:
            os.killpg(self.proc.pid, signal.SIGHUP)
        except ProcessLookupError:
            pass
        try:
            self.proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(self.proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        try:
            os.close(self.master)
        except OSError:
            pass
        if self._profile:
            self._profile.unlink(missing_ok=True)
