"""Run untrusted (AI-generated) code with guard rails.

macOS (local): every process is wrapped in `sandbox-exec` with a profile that
denies outbound network (except localhost) and file writes outside the
directories we explicitly allow.

Linux as root (the hosted container): every process drops to an unprivileged
`runner` user inside a fresh, empty network namespace, with resource limits.
It can't reach the network, can't read the server's environment (API keys,
database URL), and only owns the directories handed over to it.

Anywhere else we fall back to a plain subprocess with a timeout.
"""

from __future__ import annotations

import asyncio
import functools
import os
import shutil
import signal
import sys
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from . import config

SANDBOX_EXEC = shutil.which("sandbox-exec") if sys.platform == "darwin" else None
MAX_OUTPUT = 24_000

JAIL_USER = os.environ.get("COLDSTART_JAIL_USER", "runner")


def _jail_ids() -> tuple[int, int, str] | None:
    if sys.platform != "linux" or os.geteuid() != 0:
        return None
    try:
        import pwd

        pw = pwd.getpwnam(JAIL_USER)
    except (ImportError, KeyError):
        return None
    return pw.pw_uid, pw.pw_gid, pw.pw_dir


JAIL = _jail_ids()


@functools.lru_cache(maxsize=1)
def net_isolation() -> bool:
    """Can we give children their own empty network namespace? (root on Linux)"""
    if not JAIL:
        return False
    import subprocess

    probe = subprocess.run([sys.executable, "-c", "import os; os.unshare(os.CLONE_NEWNET)"],
                           capture_output=True)
    return probe.returncode == 0


def _jail_preexec(isolate_net: bool):
    uid, gid, _ = JAIL  # type: ignore[misc]
    unshare = isolate_net and net_isolation()

    def preexec() -> None:  # runs in the child between fork and exec
        import resource

        if unshare:
            os.unshare(os.CLONE_NEWNET)
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_NPROC, (512, 512))
        resource.setrlimit(resource.RLIMIT_FSIZE, (512 * 2**20, 512 * 2**20))
        resource.setrlimit(resource.RLIMIT_NOFILE, (2048, 2048))
        os.setgroups([])
        os.setgid(gid)
        os.setuid(uid)

    return preexec


def spawn_kwargs(isolate_net: bool = True) -> dict[str, Any]:
    """Extra Popen/create_subprocess_exec kwargs that jail the child (Linux+root only)."""
    return {"preexec_fn": _jail_preexec(isolate_net)} if JAIL else {}


def hand_over(*paths: Path) -> None:
    """Give the jail user ownership of these trees so jailed children can write them."""
    if not JAIL:
        return
    uid, gid, _ = JAIL
    for root in paths:
        root = Path(root)
        if not root.exists():
            continue
        os.chown(root, uid, gid)
        for dirpath, dirnames, filenames in os.walk(root):
            for name in (*dirnames, *filenames):
                try:
                    os.chown(os.path.join(dirpath, name), uid, gid, follow_symlinks=False)
                except FileNotFoundError:
                    pass


def sandbox_profile(write_dirs: list[Path]) -> str:
    allowed = "\n".join(
        f'    (subpath "{os.path.realpath(d)}")' for d in write_dirs
    )
    return f"""(version 1)
(allow default)
(deny network-outbound (remote ip "*:*"))
(allow network-outbound (remote ip "localhost:*"))
(allow network-outbound (remote unix-socket))
(deny file-write*)
(allow file-write*
{allowed}
    (subpath "/private/var/folders")
    (subpath "/private/tmp")
    (subpath "/dev"))
"""


def runtime_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    venv_bin = str(config.RUNTIME_VENV / "bin")
    env = {
        "PATH": f"{venv_bin}:/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": JAIL[2] if JAIL else os.environ.get("HOME", "/tmp"),
        "LANG": "en_US.UTF-8",
        "LC_ALL": "en_US.UTF-8",
        "TZ": "UTC",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "PYTHONUNBUFFERED": "1",
        "VIRTUAL_ENV": str(config.RUNTIME_VENV),
        "TMPDIR": tempfile.gettempdir(),
    }
    if extra:
        env.update(extra)
    return env


def wrap(cmd: list[str], write_dirs: list[Path]) -> tuple[list[str], Path | None]:
    """Prefix a command with sandbox-exec; returns (argv, profile_path_to_cleanup)."""
    if not SANDBOX_EXEC:
        return cmd, None
    fd, profile_path = tempfile.mkstemp(prefix="coldstart-", suffix=".sb")
    with os.fdopen(fd, "w") as fh:
        fh.write(sandbox_profile(write_dirs))
    return [SANDBOX_EXEC, "-f", profile_path, *cmd], Path(profile_path)


@dataclass
class ProcResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    duration_s: float


def _clip(s: str, limit: int = MAX_OUTPUT) -> str:
    if len(s) <= limit:
        return s
    return f"... [{len(s) - limit} chars truncated] ...\n" + s[-limit:]


async def run(cmd: list[str], *, cwd: Path, write_dirs: list[Path] | None = None,
              timeout: float = 60, env: dict[str, str] | None = None,
              stdin: str | None = None) -> ProcResult:
    argv, profile = wrap(cmd, write_dirs or [cwd])
    hand_over(cwd, *(write_dirs or []))
    started = time.monotonic()
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(cwd),
        env=runtime_env(env),
        stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,  # own process group so we can kill children on timeout
        **spawn_kwargs(),
    )
    timed_out = False
    try:
        out, err = await asyncio.wait_for(
            proc.communicate(stdin.encode() if stdin is not None else None), timeout
        )
    except asyncio.TimeoutError:
        timed_out = True
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        out, err = await proc.communicate()
    finally:
        if profile:
            profile.unlink(missing_ok=True)
    return ProcResult(
        returncode=proc.returncode if proc.returncode is not None else -9,
        stdout=_clip(out.decode("utf-8", "replace")),
        stderr=_clip(err.decode("utf-8", "replace")),
        timed_out=timed_out,
        duration_s=time.monotonic() - started,
    )


# --- pytest -------------------------------------------------------------------

@dataclass
class TestCase:
    nodeid: str
    file: str
    name: str
    outcome: str  # passed | failed | error | skipped
    duration_s: float = 0.0
    message: str = ""
    details: str = ""


@dataclass
class TestReport:
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    total: int = 0
    exit_code: int = 0
    timed_out: bool = False
    duration_s: float = 0.0
    output: str = ""
    cases: list[TestCase] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return (not self.timed_out and self.failed == 0 and self.errors == 0
                and self.total > 0 and self.exit_code == 0)

    def failing(self) -> list[TestCase]:
        return [c for c in self.cases if c.outcome in ("failed", "error")]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["ok"] = self.ok
        return d

    def summary(self, max_failures: int = 6, detail_chars: int = 1800) -> str:
        """Compact text for feeding back to a model or showing in a log."""
        lines = [
            f"passed={self.passed} failed={self.failed} errors={self.errors} "
            f"skipped={self.skipped} exit={self.exit_code}{' TIMEOUT' if self.timed_out else ''}"
        ]
        for c in self.failing()[:max_failures]:
            lines.append(f"\n--- {c.outcome.upper()}: {c.nodeid}\n{c.message}\n{c.details[:detail_chars]}")
        if not self.cases or (self.exit_code not in (0, 1) and not self.failing()):
            lines.append("\n--- pytest output ---\n" + self.output[-4000:])
        return "\n".join(lines)


def _parse_junit(path: Path, repo_dir: Path) -> list[TestCase]:
    try:
        tree = ET.parse(path)
    except (ET.ParseError, FileNotFoundError):
        return []
    cases: list[TestCase] = []
    for tc in tree.iter("testcase"):
        classname = tc.get("classname", "")
        name = tc.get("name", "")
        file = tc.get("file") or classname.replace(".", "/") + ".py"
        # classname "tests.test_x.TestFoo" -> file tests/test_x.py, class TestFoo
        parts = classname.split(".")
        rel = None
        for i in range(len(parts), 0, -1):
            cand = "/".join(parts[:i]) + ".py"
            if (repo_dir / cand).exists():
                rel = cand
                cls = parts[i:]
                break
        if rel is None:
            rel, cls = file, []
        nodeid = "::".join([rel, *cls, name])
        outcome, message, details = "passed", "", ""
        for tag in ("failure", "error", "skipped"):
            el = tc.find(tag)
            if el is not None:
                outcome = {"failure": "failed", "error": "error", "skipped": "skipped"}[tag]
                message = (el.get("message") or "").strip()
                details = (el.text or "").strip()
                break
        cases.append(TestCase(
            nodeid=nodeid, file=rel, name=name, outcome=outcome,
            duration_s=float(tc.get("time") or 0), message=message[:2000], details=details[:6000],
        ))
    return cases


async def run_pytest(repo_dir: Path, targets: list[str] | None = None, *,
                     timeout: float = config.SANDBOX_TEST_TIMEOUT,
                     extra_args: list[str] | None = None) -> TestReport:
    """Run pytest inside `repo_dir` (which must be a disposable or user-owned dir)."""
    repo_dir = repo_dir.resolve()
    junit_dir = Path(tempfile.mkdtemp(prefix="coldstart-junit-"))
    junit = junit_dir / "report.xml"
    cmd = [
        str(config.RUNTIME_PYTHON), "-m", "pytest",
        "-q", "--tb=short", "--no-header", "--color=no", "-rfE",
        "-p", "no:cacheprovider",
        f"--junitxml={junit}", "-o", "junit_family=xunit2",
        *(extra_args or []),
        *(targets or []),
    ]
    res = await run(cmd, cwd=repo_dir, write_dirs=[repo_dir, junit_dir], timeout=timeout)
    cases = _parse_junit(junit, repo_dir)
    shutil.rmtree(junit_dir, ignore_errors=True)
    rep = TestReport(
        exit_code=res.returncode,
        timed_out=res.timed_out,
        duration_s=res.duration_s,
        output=(res.stdout + ("\n" + res.stderr if res.stderr.strip() else "")).strip(),
        cases=cases,
    )
    counts = {"passed": 0, "failed": 0, "error": 0, "skipped": 0}
    for c in cases:
        counts[c.outcome] += 1
    rep.passed, rep.failed, rep.errors, rep.skipped = (
        counts["passed"], counts["failed"], counts["error"], counts["skipped"])
    rep.total = len(cases)
    # Exit code 2/3/4 = interrupted / internal error / usage error; 5 = no tests collected.
    if not cases and res.returncode not in (0,):
        rep.errors = max(rep.errors, 1)
    return rep


@functools.lru_cache(maxsize=1)
def runtime_prefixes() -> tuple[str, str]:
    """(venv prefix, base interpreter prefix) of the runtime Python, for path scrubbing."""
    import subprocess

    out = subprocess.run([str(config.RUNTIME_PYTHON), "-c", "import sys; print(sys.prefix); print(sys.base_prefix)"],
                         capture_output=True, text=True, check=True).stdout.split()
    return out[0], out[1]


def scrub_paths(text: str, replacements: dict[str, str]) -> str:
    """Replace machine-specific paths (longest first) so output reads like it came from a server."""
    for old in sorted(replacements, key=len, reverse=True):
        if old:
            text = text.replace(old, replacements[old])
    return text


def scratch_copy(src: Path, label: str = "run") -> Path:
    """Copy a repo into a fresh scratch dir (ignoring VCS/caches) and return it."""
    config.ensure_dirs()
    dest = config.SCRATCH_DIR / f"{label}-{uuid.uuid4().hex[:10]}"
    shutil.copytree(
        src, dest,
        ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", "*.pyc", ".coldstart"),
    )
    return dest


async def run_python(code: str, cwd: Path, *, timeout: float = 20, filename: str | None = None) -> ProcResult:
    """Execute a Python snippet with `cwd` importable (used for repro scripts)."""
    if filename:
        path = str(cwd / filename)
        Path(path).write_text(code)
    else:
        fd, path = tempfile.mkstemp(prefix="coldstart-snippet-", suffix=".py", dir=str(cwd))
        with os.fdopen(fd, "w") as fh:
            fh.write(code)
    try:
        return await run([str(config.RUNTIME_PYTHON), path], cwd=cwd, timeout=timeout,
                         env={"PYTHONPATH": str(cwd)})
    finally:
        Path(path).unlink(missing_ok=True)


SELF_CHECK = """
import json, os, socket
out = {"uid": os.getuid()}
for label, pid in (("init_environ", 1), ("server_environ", os.getppid())):
    try:
        open(f"/proc/{pid}/environ", "rb").read()
        out[label] = "READABLE"
    except OSError:
        out[label] = "blocked"
try:
    socket.create_connection(("1.1.1.1", 443), timeout=3).close()
    out["network"] = "OPEN"
except OSError:
    out["network"] = "blocked"
print(json.dumps(out))
"""


async def self_check() -> dict[str, Any]:
    """Prove the jail from the inside: can a jailed child read secrets or reach the internet?"""
    import json

    tmp = config.SCRATCH_DIR / f"selfcheck-{uuid.uuid4().hex[:6]}"
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        res = await run_python(SELF_CHECK, tmp, timeout=20, filename="check.py")
        report = json.loads(res.stdout.strip().splitlines()[-1]) if res.stdout.strip() else {"error": res.stderr[-300:]}
    except Exception as err:  # noqa: BLE001
        report = {"error": str(err)}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    report["jail"] = bool(JAIL)
    report["net_isolation"] = net_isolation()
    return report
