"""Durability for the hosted container, whose disk is wiped on every restart.

- Case bundles (the generated repo, clean copy, hidden tests, case.json …) are
  uploaded to InsForge Storage once a case is ready, and fetched back on
  demand the first time something reads the case after a restart.
- Workspaces (your in-progress edits, their git history and task snapshots)
  are uploaded shortly after they change and restored on demand.

Locally (no InsForge Storage configured) every function here is a no-op.
"""

from __future__ import annotations

import asyncio
import io
import logging
import shutil
import tarfile
import threading
import time
from pathlib import Path

from . import cloudstore, config, sandbox

log = logging.getLogger("coldstart.persist")

_lock = threading.Lock()
_dirty: dict[str, float] = {}          # engagement id -> first time it went dirty
_restore_locks: dict[str, threading.Lock] = {}


def enabled() -> bool:
    return cloudstore.enabled()


# --- packing -----------------------------------------------------------------------

def _pack(root: Path, skip: set[str]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz", compresslevel=6) as tar:
        for path in sorted(root.rglob("*")):
            rel = path.relative_to(root)
            if rel.parts and rel.parts[0] in skip:
                continue
            if any(part in ("__pycache__", ".pytest_cache") for part in rel.parts):
                continue
            tar.add(path, arcname=rel.as_posix(), recursive=False)
    return buf.getvalue()


def _unpack(data: bytes, dest: Path) -> None:
    tmp = dest.with_name(dest.name + ".restoring")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        tar.extractall(tmp, filter="data")  # refuses absolute paths, .., device files
    shutil.rmtree(dest, ignore_errors=True)
    tmp.rename(dest)


def _restore_lock(key: str) -> threading.Lock:
    with _lock:
        return _restore_locks.setdefault(key, threading.Lock())


# --- case bundles ----------------------------------------------------------------------

def _case_key(case_id: str) -> str:
    return f"cases/{case_id}.tar.gz"


def upload_case(case_id: str) -> None:
    if not enabled():
        return
    root = config.LIBRARY_DIR / case_id
    if not (root / "case.json").exists():
        return
    data = _pack(root, skip={"work"})
    cloudstore.put(_case_key(case_id), data)
    log.info("uploaded case %s (%d KB)", case_id, len(data) // 1024)


def ensure_case(case_id: str) -> bool:
    """Make sure the case bundle is on local disk; returns False if it doesn't exist anywhere."""
    root = config.LIBRARY_DIR / case_id
    if (root / "case.json").exists():
        return True
    if not enabled():
        return False
    with _restore_lock(f"case:{case_id}"):
        if (root / "case.json").exists():
            return True
        data = cloudstore.get(_case_key(case_id))
        if data is None:
            return False
        config.LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
        _unpack(data, root)
        log.info("restored case %s from storage", case_id)
        return True


# --- workspaces ----------------------------------------------------------------------------

def _ws_key(engagement_id: str) -> str:
    return f"workspaces/{engagement_id}.tar.gz"


def mark_dirty(engagement_id: str) -> None:
    if not enabled():
        return
    with _lock:
        _dirty.setdefault(engagement_id, time.time())


def upload_workspace(engagement_id: str) -> None:
    if not enabled():
        return
    root = config.WORKSPACES_DIR / engagement_id
    if not (root / "repo").exists():
        return
    with _lock:
        _dirty.pop(engagement_id, None)
    try:
        cloudstore.put(_ws_key(engagement_id), _pack(root, skip=set()))
    except Exception:
        mark_dirty(engagement_id)  # try again on the next flush
        raise


def ensure_workspace(engagement_id: str) -> bool:
    root = config.WORKSPACES_DIR / engagement_id
    if (root / "repo").exists():
        return True
    if not enabled():
        return False
    with _restore_lock(f"ws:{engagement_id}"):
        if (root / "repo").exists():
            return True
        data = cloudstore.get(_ws_key(engagement_id))
        if data is None:
            return False
        config.WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)
        _unpack(data, root)
        sandbox.hand_over(root)
        log.info("restored workspace %s from storage", engagement_id)
        return True


def flush_dirty(max_age: float = 0.0) -> None:
    """Upload workspaces that have been dirty for at least `max_age` seconds."""
    if not enabled():
        return
    now = time.time()
    with _lock:
        due = [eid for eid, since in _dirty.items() if now - since >= max_age]
    for eid in due:
        try:
            upload_workspace(eid)
        except Exception as err:  # noqa: BLE001 — keep flushing the others
            log.warning("workspace %s upload failed: %s", eid, err)


async def flush_loop(interval: float = 10.0) -> None:
    """Background task: persist changed workspaces a few seconds after they change."""
    while True:
        await asyncio.sleep(interval)
        await asyncio.to_thread(flush_dirty, 5.0)
