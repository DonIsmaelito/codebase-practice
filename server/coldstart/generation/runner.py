"""Run code against a case's repo the way the incident really happened.

Everything the learner is shown as output — the report's traceback, a
teammate's pasted staging run, a command in the expert replay — comes from
executing code in the jail on a throwaway copy of the repo. Machine paths are
scrubbed so the output reads like it came from the client's servers.
"""

from __future__ import annotations

import shlex
import shutil
from dataclasses import dataclass
from pathlib import Path

from .. import config, sandbox
from . import files as F


def _scrub(text: str, tmp: Path, repo_name: str) -> str:
    deploy = f"/srv/{repo_name or 'app'}"
    venv, base = sandbox.runtime_prefixes()
    mapping = {p: deploy for p in (str(tmp), str(tmp.resolve()), str(tmp).replace("/private/", "/", 1))}
    mapping[venv] = f"{deploy}/.venv"
    mapping[str(Path(venv).resolve())] = f"{deploy}/.venv"
    mapping[base] = "/usr/local"
    mapping[str(Path(base).resolve())] = "/usr/local"
    return sandbox.scrub_paths(text, mapping)


async def run_script(base: Path, code: str, repo_name: str, *, overlay: dict[str, str] | None = None,
                     filename: str = "repro.py", timeout: float = 30) -> sandbox.ProcResult:
    """Execute a standalone script from the root of a scratch copy of `base`."""
    tmp = sandbox.scratch_copy(base, "run")
    try:
        if overlay:
            F.write_repo(tmp, overlay)
        res = await sandbox.run_python(code, tmp, timeout=timeout, filename=filename)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    res.stdout = _scrub(res.stdout, tmp, repo_name)
    res.stderr = _scrub(res.stderr, tmp, repo_name)
    return res


@dataclass
class CommandResult:
    command: str
    output: str
    returncode: int
    timed_out: bool


class CommandError(ValueError):
    pass


def _argv(command: str) -> list[str]:
    try:
        argv = shlex.split(command)
    except ValueError as err:
        raise CommandError(f"can't parse command: {err}") from None
    if not argv:
        raise CommandError("empty command")
    if argv[0] in ("pytest", "py.test"):
        return [str(config.RUNTIME_PYTHON), "-m", "pytest", "-p", "no:cacheprovider", "--color=no", *argv[1:]]
    if argv[0] in ("python", "python3"):
        if argv[1:3] == ["-m", "pytest"]:
            return [str(config.RUNTIME_PYTHON), "-m", "pytest", "-p", "no:cacheprovider", "--color=no", *argv[3:]]
        return [str(config.RUNTIME_PYTHON), *argv[1:]]
    raise CommandError("only `pytest …` and `python …` commands can be replayed")


async def run_command(base: Path, command: str, repo_name: str, *, overlay: dict[str, str] | None = None,
                      timeout: float = 45) -> CommandResult:
    """Run one `pytest …` / `python …` command line from the root of a scratch copy of `base`."""
    argv = _argv(command)
    tmp = sandbox.scratch_copy(base, "cmd")
    try:
        if overlay:
            F.write_repo(tmp, overlay)
        res = await sandbox.run(argv, cwd=tmp, timeout=timeout, env={"PYTHONPATH": str(tmp)})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    out = res.stdout + ("\n" + res.stderr if res.stderr.strip() else "")
    return CommandResult(command=command, output=_scrub(out, tmp, repo_name).strip(),
                         returncode=res.returncode, timed_out=res.timed_out)


# Output that means the *script* was wrong, not that it found something.
_SCRIPT_BUGS = ("SyntaxError", "IndentationError", "ModuleNotFoundError", "No module named",
                "ImportError: cannot import", "NameError: name", "has no attribute '__",
                "ERROR: file or directory not found", "no tests ran", "error: unrecognized arguments",
                "usage: ", "can't open file")


def looks_broken(output: str) -> bool:
    return not output.strip() or any(s in output for s in _SCRIPT_BUGS)
