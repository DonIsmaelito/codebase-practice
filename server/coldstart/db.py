"""Persistence: SQLite locally, InsForge Postgres when hosted.

The rest of the app writes plain SQL with `?` placeholders through a tiny
helper layer (one / all_ / run / tx / kv_*). On Postgres the placeholders are
translated to `%s`; the schema itself lives in migrations/ (applied with the
InsForge CLI), while SQLite creates it on first use.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Any, Iterator

from . import config

SQLITE_SCHEMA = """
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

CREATE TABLE IF NOT EXISTS drills (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  REAL NOT NULL,
    concept_id  TEXT NOT NULL,
    kind        TEXT NOT NULL,
    payload     TEXT NOT NULL,
    answered_at REAL,
    correct     INTEGER,
    given       TEXT
);
"""

_local = threading.local()
_init_lock = threading.Lock()
_initialized = False


class _Cursor:
    """What run() returns: rows for RETURNING queries, rowcount for the rest."""

    def __init__(self, rows: list[dict[str, Any]], rowcount: int):
        self._rows = rows
        self.rowcount = rowcount

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows


class _SQLite:
    def __init__(self) -> None:
        self.raw = sqlite3.connect(config.DB_PATH, timeout=30, isolation_level=None)
        self.raw.row_factory = sqlite3.Row
        self.raw.execute("PRAGMA journal_mode=WAL")
        self.raw.execute("PRAGMA foreign_keys=ON")
        self.raw.execute("PRAGMA busy_timeout=30000")

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> _Cursor:
        cur = self.raw.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()] if cur.description else []
        return _Cursor(rows, cur.rowcount)

    def close(self) -> None:
        self.raw.close()

    @contextmanager
    def transaction(self) -> Iterator["_SQLite"]:
        self.raw.execute("BEGIN IMMEDIATE")
        try:
            yield self
        except BaseException:
            self.raw.execute("ROLLBACK")
            raise
        else:
            self.raw.execute("COMMIT")


class _Postgres:
    def __init__(self) -> None:
        import psycopg
        from psycopg.rows import dict_row

        self._psycopg = psycopg
        self.raw = psycopg.connect(
            config.DATABASE_URL, autocommit=True, row_factory=dict_row, connect_timeout=15,
            keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=3,
            application_name="coldstart",
        )

    @staticmethod
    def _sql(sql: str) -> str:
        return sql.replace("?", "%s")

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> _Cursor:
        with self.raw.cursor() as cur:
            cur.execute(self._sql(sql), params or None)
            rows = [dict(r) for r in cur.fetchall()] if cur.description else []
            return _Cursor(rows, cur.rowcount)

    def close(self) -> None:
        self.raw.close()

    @contextmanager
    def transaction(self) -> Iterator["_Postgres"]:
        with self.raw.transaction():
            yield self


def _connect() -> _SQLite | _Postgres:
    return _Postgres() if config.CLOUD_DB else _SQLite()


def conn() -> _SQLite | _Postgres:
    """A per-thread connection (neither driver's connections are thread-safe)."""
    global _initialized
    if not _initialized:
        with _init_lock:
            if not _initialized:
                config.ensure_dirs()
                if not config.CLOUD_DB:
                    c = _SQLite()
                    c.raw.executescript(SQLITE_SCHEMA)
                    c.raw.close()
                _initialized = True
    c = getattr(_local, "conn", None)
    if c is None:
        c = _local.conn = _connect()
    return c


def _execute(sql: str, params: tuple[Any, ...]) -> _Cursor:
    try:
        return conn().execute(sql, params)
    except Exception as err:
        # A dropped Postgres connection (idle timeout, deploy, network blip): reconnect once.
        if config.CLOUD_DB and _is_disconnect(err):
            _local.conn = _connect()
            return _local.conn.execute(sql, params)
        raise


def _is_disconnect(err: Exception) -> bool:
    try:
        import psycopg
    except ImportError:  # pragma: no cover
        return False
    return isinstance(err, (psycopg.OperationalError, psycopg.InterfaceError))


@contextmanager
def tx() -> Iterator[_SQLite | _Postgres]:
    """Run several statements atomically: `with db.tx() as c: c.execute(sql, params)`."""
    c = conn()
    with c.transaction():
        yield c


def one(sql: str, *params: Any) -> dict[str, Any] | None:
    return _execute(sql, params).fetchone()


def all_(sql: str, *params: Any) -> list[dict[str, Any]]:
    return _execute(sql, params).fetchall()


def run(sql: str, *params: Any) -> _Cursor:
    return _execute(sql, params)


def insert_id(sql: str, *params: Any) -> int:
    """INSERT ... and return the new row's id (both backends support RETURNING)."""
    row = _execute(sql.rstrip().rstrip(";") + " RETURNING id", params).fetchone()
    return int(row["id"]) if row else 0


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
    day = time.strftime("%Y-%m-%d", time.localtime(time.time() if when is None else when))
    run(
        "INSERT INTO practice_days(day, seconds) VALUES(?, ?) "
        "ON CONFLICT(day) DO UPDATE SET seconds = practice_days.seconds + excluded.seconds",
        day,
        seconds,
    )
