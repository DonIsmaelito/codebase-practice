"""An engagement's working copy of a client repo.

Layout under data/workspaces/<engagement_id>/:
    repo/                 the git repo the learner edits (terminal cwd)
    snapshots/<task>.json the file contents when each task started (for diffs)
    .zsh_history          terminal history (the only other writable path)
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .. import config, persist, sandbox
from ..generation import files as F

HIDDEN_NAMES = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".DS_Store", ".ruff_cache"}


class WorkspaceError(ValueError):
    pass


class Workspace:
    def __init__(self, engagement_id: str):
        self.id = engagement_id
        self.root = config.WORKSPACES_DIR / engagement_id
        self.repo = self.root / "repo"

    # --- lifecycle -------------------------------------------------------------

    @classmethod
    def provision(cls, engagement_id: str, case_dir: Path, author: tuple[str, str]) -> "Workspace":
        ws = cls(engagement_id)
        if ws.root.exists():
            shutil.rmtree(ws.root)
        ws.root.mkdir(parents=True)
        F.copy_repo(case_dir / "repo", ws.repo)
        (ws.root / "snapshots").mkdir()
        sandbox.hand_over(ws.root)
        ws.git("init", "-q", "-b", "main")
        ws.git("add", "-A")
        ws.commit("Snapshot of main for contractor access", author=author)
        return ws

    def exists(self) -> bool:
        """True if the workspace is available, restoring it from storage if needed."""
        return self.repo.exists() or persist.ensure_workspace(self.id)

    def touched(self, *paths: Path) -> None:
        """After a server-side change: hand files to the jail user and schedule an upload."""
        sandbox.hand_over(*paths)
        persist.mark_dirty(self.id)

    # --- git -----------------------------------------------------------------------

    def git(self, *args: str, check: bool = True) -> str:
        # Runs as the jail user in the hosted container, with a scrubbed environment.
        env = sandbox.runtime_env({"GIT_TERMINAL_PROMPT": "0"})
        res = subprocess.run(["git", "-C", str(self.repo), *args], capture_output=True, text=True, env=env,
                             **sandbox.spawn_kwargs())
        if check and res.returncode != 0:
            raise WorkspaceError(f"git {' '.join(args)} failed: {res.stderr.strip()}")
        return res.stdout

    def commit(self, message: str, author: tuple[str, str] = ("Workspace", "workspace@localhost")) -> str:
        name, email = author
        self.git("add", "-A")
        self.git("-c", f"user.name={name}", "-c", f"user.email={email}",
                 "commit", "-q", "--allow-empty", "-m", message)
        persist.mark_dirty(self.id)
        return self.head()

    def head(self) -> str:
        return self.git("rev-parse", "HEAD").strip()

    # --- files -----------------------------------------------------------------------

    def resolve(self, rel: str) -> Path:
        rel = rel.strip().lstrip("/")
        path = (self.repo / rel).resolve()
        if path != self.repo.resolve() and self.repo.resolve() not in path.parents:
            raise WorkspaceError(f"path escapes the workspace: {rel}")
        if any(part == ".git" for part in Path(rel).parts):
            raise WorkspaceError("the .git directory is off limits here (use the terminal)")
        return path

    def tree(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        root = self.repo
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if d not in HIDDEN_NAMES)
            rel_dir = Path(dirpath).relative_to(root)
            for d in dirnames:
                out.append({"path": (rel_dir / d).as_posix(), "type": "dir"})
            for f in sorted(filenames):
                if f in HIDDEN_NAMES or f.endswith(".pyc"):
                    continue
                p = Path(dirpath) / f
                out.append({"path": (rel_dir / f).as_posix(), "type": "file", "size": p.stat().st_size})
        return out

    def read(self, rel: str) -> str:
        path = self.resolve(rel)
        if not path.is_file():
            raise WorkspaceError(f"no such file: {rel}")
        if path.stat().st_size > 2_000_000:
            raise WorkspaceError("file too large to open")
        return path.read_text(errors="replace")

    def write(self, rel: str, content: str) -> None:
        path = self.resolve(rel)
        new_dirs = [p for p in path.parents if not p.exists() and self.repo in p.parents]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        self.touched(path, *new_dirs)

    def create(self, rel: str, kind: str = "file") -> None:
        path = self.resolve(rel)
        if path.exists():
            raise WorkspaceError(f"already exists: {rel}")
        new_dirs = [p for p in path.parents if not p.exists() and self.repo in p.parents]
        if kind == "dir":
            path.mkdir(parents=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("")
        self.touched(path, *new_dirs)

    def delete(self, rel: str) -> None:
        path = self.resolve(rel)
        if path == self.repo.resolve():
            raise WorkspaceError("refusing to delete the repo root")
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()
        persist.mark_dirty(self.id)

    def rename(self, old: str, new: str) -> None:
        src, dst = self.resolve(old), self.resolve(new)
        if dst.exists():
            raise WorkspaceError(f"already exists: {new}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
        self.touched(dst)

    def files(self) -> dict[str, str]:
        return F.read_repo(self.repo)

    # --- per-task snapshots & diffs -----------------------------------------------------

    def snapshot(self, task_id: str) -> None:
        (self.root / "snapshots").mkdir(exist_ok=True)
        (self.root / "snapshots" / f"{task_id}.json").write_text(json.dumps(self.files()))
        persist.mark_dirty(self.id)

    def snapshot_files(self, task_id: str) -> dict[str, str]:
        p = self.root / "snapshots" / f"{task_id}.json"
        return json.loads(p.read_text()) if p.exists() else {}

    def changes(self, task_id: str) -> list[dict[str, Any]]:
        before, after = self.snapshot_files(task_id), self.files()
        out = []
        for rel in sorted(set(before) | set(after)):
            a, b = before.get(rel), after.get(rel)
            if a == b:
                continue
            status = "added" if a is None else "deleted" if b is None else "modified"
            out.append({"path": rel, "status": status, "original": a or "", "current": b or ""})
        return out

    def diff(self, task_id: str) -> str:
        return F.unified_diff(self.snapshot_files(task_id), self.files())

    def revert(self, task_id: str, rel: str | None = None) -> None:
        before = self.snapshot_files(task_id)
        current = self.files()
        targets = [rel] if rel else sorted(set(before) | set(current))
        for path in targets:
            if path in before:
                self.write(path, before[path])
            elif path in current:
                self.delete(path)

    def dispose(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def persist_now(self) -> None:
        persist.upload_workspace(self.id)
