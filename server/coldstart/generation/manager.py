"""Keeps the inbox stocked: generates cases in the background, one at a time.

Guards against burning the budget: stops auto-generation when the key's
remaining credit drops below the configured floor, and backs off after
repeated failures (a systematic problem shouldn't retry forever).
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from .. import db, llm
from ..learning import scheduler
from . import pipeline

log = logging.getLogger("coldstart.manager")


def new_case_id() -> str:
    return time.strftime("c%y%m%d-") + uuid.uuid4().hex[:6]


def enqueue(spec: dict[str, Any] | None = None, *, focus: str | None = None) -> str:
    spec = spec or scheduler.build_spec(focus=focus)
    case_id = new_case_id()
    db.run(
        "INSERT INTO cases(id, created_at, status, spec) VALUES(?, ?, 'queued', ?)",
        case_id, time.time(), db.dumps(spec),
    )
    return case_id


class GenerationManager:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._wake = asyncio.Event()
        self._running: dict[str, asyncio.Task] = {}
        self._consecutive_failures = 0
        self._paused_until = 0.0
        self.last_error: str | None = None

    def start(self) -> None:
        self._reap_stale()
        self._task = asyncio.create_task(self._loop(), name="generation-manager")

    def _reap_stale(self, max_age_s: float = 20 * 60) -> None:
        """Fail 'generating' cases nobody is working on (e.g. the server died mid-run).

        Staleness is judged by the last stage heartbeat, not by this process's
        memory, so a CLI generation running alongside the server is left alone.
        """
        now = time.time()
        for row in db.all_("SELECT id, stage, created_at FROM cases WHERE status = 'generating'"):
            if row["id"] in self._running:
                continue
            stage = db.loads(row["stage"], None) or {}
            last = stage.get("ts") or row["created_at"]
            if now - last > max_age_s:
                db.run("UPDATE cases SET status = 'failed', error = 'interrupted (no progress for 20 min)' "
                       "WHERE id = ? AND status = 'generating'", row["id"])

    async def stop(self) -> None:
        for t in list(self._running.values()):
            t.cancel()
        if self._task:
            self._task.cancel()

    def poke(self) -> None:
        self._wake.set()

    def request(self, focus: str | None = None) -> str:
        case_id = enqueue(focus=focus)
        self._paused_until = 0.0
        self.poke()
        return case_id

    def busy(self) -> bool:
        return bool(self._running)

    def status(self) -> dict[str, Any]:
        return {
            "running": list(self._running),
            "paused_until": self._paused_until if self._paused_until > time.time() else None,
            "consecutive_failures": self._consecutive_failures,
            "last_error": self.last_error,
        }

    async def _loop(self) -> None:
        while True:
            try:
                await self._tick()
            except Exception:  # noqa: BLE001 — the loop must survive anything
                log.exception("generation manager tick failed")
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=20)
            except asyncio.TimeoutError:
                pass
            self._wake.clear()

    async def _tick(self) -> None:
        self._reap_stale()
        if self._running:
            return
        queued = db.one("SELECT id, spec FROM cases WHERE status = 'queued' ORDER BY created_at LIMIT 1")
        if queued:
            self._launch(queued["id"], db.loads(queued["spec"]))
            return
        settings = db.settings()
        if not settings.get("auto_generate") or time.time() < self._paused_until:
            return
        ready = db.one("SELECT COUNT(*) AS n FROM cases WHERE status IN ('ready', 'generating', 'queued')")["n"]
        if ready >= int(settings.get("buffer_size", 2)):
            return
        try:
            llm.check_budget()
        except llm.LLMError as err:
            self.last_error = str(err)
            return
        key = await llm.key_status()
        remaining = key.get("remaining")
        if key.get("ok") and remaining is not None and remaining < float(settings.get("budget_floor_usd", 1.0)):
            self.last_error = (f"Paused: your OpenRouter account has ${remaining:.2f} left — add credits at "
                               "openrouter.ai/settings/credits.")
            return
        case_id = enqueue()
        spec = db.loads(db.one("SELECT spec FROM cases WHERE id = ?", case_id)["spec"])
        self._launch(case_id, spec)

    def _launch(self, case_id: str, spec: dict[str, Any]) -> None:
        async def run() -> None:
            try:
                await pipeline.generate(case_id, spec)
                self._consecutive_failures = 0
                self.last_error = None
            except asyncio.CancelledError:
                db.run("UPDATE cases SET status = 'failed', error = 'cancelled' WHERE id = ?", case_id)
                raise
            except llm.CreditError as err:
                self.last_error = str(err)
                self._paused_until = time.time() + 60 * 60  # nothing to do until someone tops up
                log.warning("case %s stopped: %s", case_id, err)
            except Exception as err:  # noqa: BLE001
                self._consecutive_failures += 1
                self.last_error = f"{type(err).__name__}: {err}"[:400]
                log.warning("case %s failed: %s", case_id, err)
                if self._consecutive_failures >= 3:
                    self._paused_until = time.time() + 15 * 60
            finally:
                self._running.pop(case_id, None)
                self.poke()

        self._running[case_id] = asyncio.create_task(run(), name=f"generate-{case_id}")


manager = GenerationManager()
