"""The coach: notices when the contractor is stuck and asks one good question.

Novices lose most of their time not to a lack of knowledge but to process —
circling the wrong module, re-running the same test, theorizing without
evidence. A well-timed question about their evidence beats any after-the-fact
review. So while a task runs, the activity log is watched for progress
(opening a file on the path to the bug, edits, a new hypothesis, test results
that change, asking for help); after ~5 active minutes without any, the
mentor gets a look at what they've done and — if they really look stuck —
checks in with a single Socratic question. Never the answer; at most three
per task; mutable per session.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from .. import db, llm
from ..runtime.workspace import Workspace
from . import bg
from . import engagements as E
from . import mentor, scheduler

log = logging.getLogger("coldstart.coach")

STUCK_SECONDS = 300      # active seconds without progress before checking in
WARMUP_SECONDS = 300     # let them read the brief first
MAX_NUDGES = 3
SKIP_BACKOFF = 180       # the mentor judged them on track; look again later

PROGRESS = {"edit", "hypothesis", "submit", "chat", "hint", "thread_post", "nudge", "reveal"}

_state: dict[str, dict[str, Any]] = {}


def nudges(task_id: str, after: int = 0) -> list[dict[str, Any]]:
    return db.all_("SELECT id, ts, content FROM chat WHERE task_id = ? AND role = 'nudge' AND id > ? ORDER BY id",
                   task_id, after)


def _relevant_files(case: dict[str, Any], kind: str) -> set[str]:
    if kind == "incident":
        return set(case["incident"]["meta"].get("files_involved") or [])
    try:
        diff = (E.case_dir(case["id"]) / "feature" / "reference.diff").read_text()
    except OSError:
        return set()
    return set(re.findall(r"^\+\+\+ b/(\S+)", diff, re.M))


def _observe(t: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    """Fold new events into this task's progress clock (in active seconds)."""
    active = t["active_seconds"] or 0
    st = _state.get(t["id"])
    if st is None:
        st = _state[t["id"]] = {
            "event_id": 0, "progress_at": active, "last_nudge_at": -1e9, "skip_until": 0.0,
            "seen": set(), "tests": None, "count": len(nudges(t["id"])),
            "relevant": _relevant_files(case, t["kind"]),
        }
    rows = db.all_("SELECT id, kind, data FROM events WHERE task_id = ? AND id > ? ORDER BY id", t["id"], st["event_id"])
    for ev in rows:
        st["event_id"] = ev["id"]
        data = db.loads(ev["data"], {})
        kind = ev["kind"]
        progressed = kind in PROGRESS
        if kind == "open_file":
            path = data.get("path")
            if path in st["relevant"] and path not in st["seen"]:
                st["seen"].add(path)
                progressed = True
        elif kind == "run_tests":
            summary = data.get("summary")
            progressed = st["tests"] is not None and summary != st["tests"]
            st["tests"] = summary
        if progressed:
            st["progress_at"] = active
    return st


def tick(t: dict[str, Any], case_id: str) -> None:
    """Called on every poll while a task runs; may start a check-in in the background."""
    if t["kind"] not in ("incident", "feature") or t["status"] != "active":
        return
    if not db.settings().get("coach_nudges", True):
        return
    case = E.load_case(case_id)
    st = _observe(t, case)
    active = t["active_seconds"] or 0
    key = f"nudge:{t['id']}"
    if st["count"] >= MAX_NUDGES or bg.running(key) or bg.running(f"reply:{t['id']}"):
        return
    if active < WARMUP_SECONDS or active < st["skip_until"]:
        return
    if active - st["progress_at"] < STUCK_SECONDS or active - st["last_nudge_at"] < STUCK_SECONDS:
        return
    st["last_nudge_at"] = active
    idle = (active - st["progress_at"]) / 60
    bg.spawn(key, lambda: _check_in(t["id"], idle), retry_after=300)


def _instruction(n: int, idle: float) -> str:
    focus = [
        "Keep it broad: a question about the evidence in the report or their approach — not a location.",
        "You may narrow to a part of the system (a module or a stage of the flow), still as a question.",
        "You may point at a specific file or function to look at, still as a question.",
    ][min(n, 2)]
    return f"""[COACH CHECK-IN — this is not a message from the contractor]
They've shown no visible progress for about {idle:.0f} active minutes: no new files on the path to the problem, no edits, no test result that changed, no questions. This would be check-in #{n + 1} of at most {MAX_NUDGES}.
If they look genuinely stuck or off-track, write ONE short Socratic question (1-2 sentences) that points them at evidence they already have, or at a cheap way to get evidence (a test to run, a value to print, a search). Build on anything you've already said instead of repeating it. {focus}
Never state the cause, the fix, or the faulty line. No greeting, no apology for interrupting.
If they look on track and just busy — reading the right code, mid-experiment — reply with exactly: SKIP"""


async def _check_in(task_id: str, idle: float) -> None:
    t = E.task(task_id)
    if t["status"] != "active":
        return
    e = E.get(t["engagement_id"])
    case = E.load_case(e["case_id"])
    ws = Workspace(e["id"])
    ws.exists()  # restores from storage after a restart
    st = _state.get(task_id) or {"count": 0}
    name = db.settings().get("mentor_name", "Sam")
    msgs: list[llm.Message] = [
        {"role": "system", "content": mentor._system(case, t, name, scheduler.learner()["level"])},
        {"role": "user", "content": [llm.cached(mentor._codebase_block(case))]},
        {"role": "assistant", "content": "I've read through the codebase. What are you looking at?"},
    ]
    for m in mentor.history(task_id)[-12:]:
        msgs.append({"role": "assistant" if m["role"] == "nudge" else m["role"], "content": m["content"]})
    live = mentor._live_context(ws, task_id, t, {})
    msgs.append({"role": "user", "content": f"{live}\n\n{_instruction(st.get('count', 0), idle)}"})
    c = await llm.complete(msgs, role="mentor", max_tokens=1200, reasoning=1500, case_id=case["id"])
    text = c.text.strip()
    if not text or text.upper().startswith("SKIP"):
        if task_id in _state:
            _state[task_id]["skip_until"] = (E.task(task_id)["active_seconds"] or 0) + SKIP_BACKOFF
        log.info("coach: %s looks on track, skipping", task_id)
        return
    db.run("INSERT INTO chat(engagement_id, task_id, ts, role, content) VALUES(?,?,?,?,?)",
           e["id"], task_id, time.time(), "nudge", text)
    E.log_event(e["id"], task_id, "nudge", {"message": text[:300]})
    if task_id in _state:
        _state[task_id]["count"] += 1
