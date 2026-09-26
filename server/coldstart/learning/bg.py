"""Small keyed background jobs: at most one running per key.

Used for the AI work that happens around a session — writing a case's cast,
a character's reply, a coach check-in, the expert replay — so HTTP requests
return immediately and the UI polls for results.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable

log = logging.getLogger("coldstart.bg")

_jobs: dict[str, asyncio.Task] = {}
_failures: dict[str, tuple[float, str]] = {}


def running(key: str) -> bool:
    job = _jobs.get(key)
    return bool(job and not job.done())


def busy() -> bool:
    return any(not job.done() for job in _jobs.values())


def error(key: str) -> str | None:
    failure = _failures.get(key)
    return failure[1] if failure else None


def spawn(key: str, factory: Callable[[], Awaitable[object]], *, retry_after: float = 600) -> bool:
    """Start `factory()` unless it's already running, or failed less than `retry_after` s ago."""
    if running(key):
        return False
    failure = _failures.get(key)
    if failure and time.time() - failure[0] < retry_after:
        return False

    async def run() -> None:
        try:
            await factory()
            _failures.pop(key, None)
        except Exception as err:  # noqa: BLE001 — surfaced through error()
            log.warning("%s failed: %s: %s", key, type(err).__name__, err)
            _failures[key] = (time.time(), f"{type(err).__name__}: {err}"[:300])

    _jobs[key] = asyncio.create_task(run(), name=key)
    return True


def forget_failure(key: str) -> None:
    _failures.pop(key, None)
