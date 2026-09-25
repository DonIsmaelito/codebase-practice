"""SQLite persistence. One file, WAL mode, tiny helper layer — no ORM.

Everything user-specific (progress, journal, settings, spend) lives here; the
generated codebases themselves live on disk under data/library/.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Any, Iterator

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    id          TEXT PRIMARY KEY,
    created_at  REAL NOT NULL,
    status      TEXT NOT NULL,            -- queued | generating | ready | failed | taken | dismissed
    stage       TEXT,                     -- pipeline stage while generating
    spec        TEXT NOT NULL,            -- JSON: what the scheduler asked for
    card        TEXT,                     -- JSON: inbox teaser once ready
    error       TEXT,
    cost_usd    REAL NOT NULL DEFAULT 0,
    finished_at REAL
);

CREATE TABLE IF NOT EXISTS engagements (
    id          TEXT PRIMARY KEY,
    case_id     TEXT NOT NULL REFERENCES cases(id),
    started_at  REAL NOT NULL,
    ended_at    REAL,
    status      TEXT NOT NULL,            -- active | done | abandoned
    phase       TEXT NOT NULL,            -- briefing | recon | incident | feature | wrapup
    plan        TEXT NOT NULL,            -- JSON list of task kinds
    notes       TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS tasks (
    id              TEXT PRIMARY KEY,
    engagement_id   TEXT NOT NULL REFERENCES engagements(id),
    kind            TEXT NOT NULL,        -- recon | incident | feature
    status          TEXT NOT NULL,        -- pending | active | passed | failed | revealed | skipped
    started_at      REAL,
    finished_at     REAL,
    active_seconds  REAL NOT NULL DEFAULT 0,
    hints_used      INTEGER NOT NULL DEFAULT 0,
    attempts        INTEGER NOT NULL DEFAULT 0,
    base_commit     TEXT,
    result          TEXT                  -- JSON: grading + debrief
);

CREATE TABLE IF NOT EXISTS events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    engagement_id   TEXT NOT NULL,
    task_id         TEXT,
    ts              REAL NOT NULL,
    kind            TEXT NOT NULL,
    data            TEXT
);
CREATE INDEX IF NOT EXISTS events_by_task ON events(task_id, ts);

CREATE TABLE IF NOT EXISTS chat (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    engagement_id   TEXT NOT NULL,
    task_id         TEXT,
    ts              REAL NOT NULL,
    role            TEXT NOT NULL,
    content         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mastery (
    concept_id  TEXT PRIMARY KEY,
    data        TEXT NOT NULL,
    updated_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS journal (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at      REAL NOT NULL,
    case_id         TEXT,
    engagement_id   TEXT,
    task_id         TEXT,
    concept_ids     TEXT NOT NULL DEFAULT '[]',
    title           TEXT NOT NULL,
    lesson          TEXT NOT NULL,
    snippet         TEXT,
    recall_q        TEXT,
    recall_a        TEXT,
    recall_due      REAL,
    recall_interval REAL NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS practice_days (
    day      TEXT PRIMARY KEY,               -- YYYY-MM-DD, local time
    seconds  REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS llm_calls (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    ts                REAL NOT NULL,
    role              TEXT,
    model             TEXT,
    case_id           TEXT,
    prompt_tokens     INTEGER,
    completion_tokens INTEGER,
    cached_tokens     INTEGER,
    cost_usd          REAL,
    duration_s        REAL,
    ok                INTEGER NOT NULL,
    error             TEXT
);

CREATE TABLE IF NOT EXISTS kv (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);
"""

_local = threading.local()
_init_lock = threading.Lock()
_initialized = False


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def conn() -> sqlite3.Connection:
    """A per-thread connection (sqlite3 connections aren't thread-safe)."""
    global _initialized
    if not _initialized:
        with _init_lock:
            if not _initialized:
                config.ensure_dirs()
                c = _connect()
                c.executescript(SCHEMA)
                c.close()
                _initialized = True
    c = getattr(_local, "conn", None)
    if c is None:
        c = _local.conn = _connect()
    return c


@contextmanager
def tx() -> Iterator[sqlite3.Connection]:
    c = conn()
    c.execute("BEGIN IMMEDIATE")
    try:
        yield c
    except BaseException:
        c.execute("ROLLBACK")
        raise
    else:
        c.execute("COMMIT")


def one(sql: str, *params: Any) -> dict[str, Any] | None:
    row = conn().execute(sql, params).fetchone()
    return dict(row) if row else None


def all_(sql: str, *params: Any) -> list[dict[str, Any]]:
    return [dict(r) for r in conn().execute(sql, params).fetchall()]


def run(sql: str, *params: Any) -> sqlite3.Cursor:
    return conn().execute(sql, params)


# --- small JSON helpers -------------------------------------------------------

def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def loads(s: str | None, default: Any = None) -> Any:
    if s is None or s == "":
        return default
    return json.loads(s)


def kv_get(key: str, default: Any = None) -> Any:
    row = one("SELECT value FROM kv WHERE key = ?", key)
    return loads(row["value"]) if row else default


def kv_set(key: str, value: Any) -> None:
    run(
        "INSERT INTO kv(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        key,
        dumps(value),
    )


def settings() -> dict[str, Any]:
    stored = kv_get("settings", {}) or {}
    merged = {**config.DEFAULT_SETTINGS, **stored}
    merged["models"] = {**config.DEFAULT_MODELS, **(stored.get("models") or {})}
    return merged


def update_settings(patch: dict[str, Any]) -> dict[str, Any]:
    stored = kv_get("settings", {}) or {}
    if "models" in patch:
        stored["models"] = {**(stored.get("models") or {}), **patch.pop("models")}
    stored.update(patch)
    kv_set("settings", stored)
    return settings()


def add_practice_seconds(seconds: float, when: float | None = None) -> None:
    if seconds <= 0:
        return
    day = time.strftime("%Y-%m-%d", time.localtime(when or time.time()))
    run(
        "INSERT INTO practice_days(day, seconds) VALUES(?, ?) "
        "ON CONFLICT(day) DO UPDATE SET seconds = seconds + excluded.seconds",
        day,
        seconds,
    )
