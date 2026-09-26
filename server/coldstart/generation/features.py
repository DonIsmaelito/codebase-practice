"""On-demand feature tickets: at most one background job per case.

Most sessions skip the optional ticket, so it's only written when an
engagement plans for it (generated during recon) or the learner decides to
stay late (written on the spot, ~1-2 minutes).
"""

from __future__ import annotations

import asyncio
import json
import logging

from .. import config
from . import pipeline

log = logging.getLogger("coldstart.features")

_jobs: dict[str, asyncio.Task] = {}
_errors: dict[str, str] = {}


def status(case_id: str) -> str:
    path = config.LIBRARY_DIR / case_id / "case.json"
    if path.exists() and json.loads(path.read_text()).get("feature"):
        return "ready"
    job = _jobs.get(case_id)
    if job and not job.done():
        return "generating"
    if case_id in _errors:
        return "failed"
    return "none"


def error(case_id: str) -> str | None:
    return _errors.get(case_id)


def ensure(case_id: str) -> str:
    current = status(case_id)
    if current in ("ready", "generating"):
        return current
    _errors.pop(case_id, None)

    async def run() -> None:
        try:
            await pipeline.generate_feature(case_id)
        except Exception as err:  # noqa: BLE001 — surfaced through status()
            log.warning("feature generation for %s failed: %s", case_id, err)
            _errors[case_id] = f"{type(err).__name__}: {err}"[:300]

    _jobs[case_id] = asyncio.create_task(run(), name=f"feature-{case_id}")
    return "generating"
