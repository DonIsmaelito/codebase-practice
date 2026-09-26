"""The people in the incident thread.

While the contractor investigates, the people who reported the incident are
still around. They answer questions (only what they'd know, in their own
voices), new information arrives as the minutes pass, and the lead checks in
for a status update. Asking sharp questions early and explaining where you
are to a non-expert are real skills; this is where they get practiced.

Per case a "cast" — who knows what, what they can pull up, what they'll post
and when — is written once, lazily, and stored with the case. Anything a
character pastes (outputs, numbers, tracebacks) was produced by running code
against the deployed, buggy system, so it's as real as the report itself.
Replies are generated live.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any

from .. import config, db, llm, persist
from ..generation import files as F
from ..generation import prompts as P
from ..generation import runner
from . import bg
from . import engagements as E

log = logging.getLogger("coldstart.cast")

MAX_POSTS_PER_TASK = 40
STATUS_QUIET_SECONDS = 300  # skip the lead's check-in if the contractor posted this recently
REVIVE_AFTER_SECONDS = 45   # re-answer a message whose reply job died (e.g. a restart)

# Learner messages that arrived while a reply was being written; the reply loop drains these.
_pending: set[str] = set()


# --- the cast (per case) ---------------------------------------------------------------

def _path(case_id: str):
    return config.LIBRARY_DIR / case_id / "cast.json"


def load(case_id: str) -> dict[str, Any] | None:
    E.case_dir(case_id)  # restores the case bundle after a restart
    path = _path(case_id)
    return json.loads(path.read_text()) if path.exists() else None


def status(case_id: str) -> str:
    if _path(case_id).exists():
        return "ready"
    if bg.running(f"cast:{case_id}"):
        return "generating"
    if bg.error(f"cast:{case_id}"):
        return "failed"
    return "none"


def ensure(case_id: str) -> str:
    current = status(case_id)
    if current != "ready" and bg.spawn(f"cast:{case_id}", lambda: generate(case_id)):
        return "generating"
    return current


async def generate(case_id: str) -> dict[str, Any]:
    case = E.load_case(case_id)
    d = E.case_dir(case_id)
    design = json.loads((d / "design.json").read_text())
    repo_name = design["repo"]["name"]
    buggy = F.read_repo(d / "repo")
    bug_diff = case["incident"].get("bug_diff") or ""
    prefix = P.designer_prefix(P.case_context({"level": int(case["spec"]["level"])}, design), F.render_repo(buggy))
    msgs = P.with_task(prefix, P.cast_task(case, bug_diff))
    data, _ = await llm.complete_json(msgs, role="designer", max_tokens=14000, reasoning=4000, case_id=case_id)
    cast = await _verify(case, repo_name, data)
    _path(case_id).write_text(json.dumps(cast, indent=2))
    await asyncio.to_thread(persist.upload_case, case_id)
    log.info("cast ready for %s: %d facts, %d evidence, %d beats", case_id,
             len(cast["facts"]), len(cast["evidence"]), len(cast["beats"]))
    return cast


async def _verify(case: dict[str, Any], repo_name: str, data: dict[str, Any]) -> dict[str, Any]:
    """Run every evidence script for real; drop what didn't run and beats that needed it."""
    d = E.case_dir(case["id"])
    team = {p["name"] for p in case["company"].get("team") or []}

    async def pull(ev: dict[str, Any]) -> dict[str, Any] | None:
        script = str(ev.get("script") or "")
        if not script.strip() or not ev.get("id"):
            return None
        base = d / ("clean" if ev.get("expected") else "repo")
        res = await runner.run_script(base, script, repo_name, filename="pull.py")
        out = (res.stdout + ("\n" + res.stderr if res.stderr.strip() else "")).strip()
        if res.timed_out or runner.looks_broken(out):
            log.info("cast %s: dropping evidence %s (didn't run cleanly)", case["id"], ev.get("id"))
            return None
        return {"id": str(ev["id"]), "who": ev.get("who"), "offer": ev.get("offer", ""),
                "expected": bool(ev.get("expected")), "output": out[-3500:]}

    evidence = [e for e in await asyncio.gather(*(pull(ev) for ev in data.get("evidence") or [])) if e]
    have = {e["id"] for e in evidence}
    beats = []
    for b in data.get("beats") or []:
        body = str(b.get("body") or "").strip()
        refs = set(re.findall(r"\{\{\s*(\w+)\s*\}\}", body))
        if not body or refs - have:
            continue
        beats.append({"id": str(b.get("id") or f"b{len(beats) + 1}"), "who": b.get("who"),
                      "kind": b.get("kind", "new_info"), "at_minute": float(b.get("at_minute") or 5), "body": body})
    beats.sort(key=lambda b: b["at_minute"])
    people = [p for p in data.get("people") or [] if p.get("name") in team] or \
             [{"name": p["name"], "role": p.get("role", "")} for p in case["company"].get("team") or []]
    return {
        "version": 1,
        "people": people,
        "facts": [f for f in data.get("facts") or [] if f.get("fact")],
        "evidence": evidence,
        "beats": beats,
        "resolution": data.get("resolution") or {},
    }


# --- the thread (per task) ----------------------------------------------------------------

def messages(task_id: str, after: int = 0) -> list[dict[str, Any]]:
    return db.all_("SELECT id, ts, author, author_role, body, kind FROM thread_messages "
                   "WHERE task_id = ? AND id > ? AND kind != 'hidden' ORDER BY id", task_id, after)


def typing(task_id: str) -> str | None:
    """Who's composing a reply right now — a best guess at who'll answer."""
    if not bg.running(f"reply:{task_id}"):
        return None
    rows = messages(task_id)
    case = E.load_case(E.get(E.task(task_id)["engagement_id"])["case_id"])
    last_learner = next((m["body"] for m in reversed(rows) if m["kind"] == "learner"), "")
    for person in case["company"].get("team") or []:
        first = person["name"].split()[0]
        if re.search(rf"\b{re.escape(first)}\b", last_learner, re.I):
            return person["name"]
    last = next((m["author"] for m in reversed(rows) if m["kind"] in ("reply", "beat")), None)
    return last or (case["incident"]["report"].get("messages") or [{}])[-1].get("from") or "Someone"


def reply_error(task_id: str) -> str | None:
    """Why the latest message is still unanswered, if a reply attempt failed."""
    if bg.running(f"reply:{task_id}"):
        return None
    last = db.one("SELECT kind FROM thread_messages WHERE task_id = ? AND kind != 'hidden' ORDER BY id DESC LIMIT 1",
                  task_id)
    return bg.error(f"reply:{task_id}") if last and last["kind"] == "learner" else None


def retry(task_id: str) -> None:
    _pending.add(task_id)
    bg.forget_failure(f"reply:{task_id}")
    bg.spawn(f"reply:{task_id}", lambda: _reply_loop(task_id), retry_after=0)


def _add(t: dict[str, Any], author: str, role: str, body: str, kind: str, beat_id: str | None = None) -> int:
    return db.insert_id(
        "INSERT INTO thread_messages(engagement_id, task_id, ts, author, author_role, body, kind, beat_id) "
        "VALUES(?,?,?,?,?,?,?,?)", t["engagement_id"], t["id"], time.time(), author, role, body, kind, beat_id)


def _paste(body: str, evidence: dict[str, dict[str, Any]]) -> str:
    def sub(m: re.Match) -> str:
        ev = evidence.get(m.group(1))
        return f"```\n{ev['output']}\n```" if ev else ""
    return re.sub(r"\{\{\s*(\w+)\s*\}\}", sub, body).strip()


def post(task_id: str, body: str) -> dict[str, Any]:
    t = E.task(task_id)
    if t["kind"] != "incident":
        raise E.EngagementError("only incidents have a thread")
    if E.get(t["engagement_id"])["status"] != "active":
        raise E.EngagementError("this engagement is over")
    body = body.strip()[:3000]
    if not body:
        raise E.EngagementError("empty message")
    n = db.one("SELECT COUNT(*) AS n FROM thread_messages WHERE task_id = ? AND kind = 'learner'", task_id)["n"]
    if n >= MAX_POSTS_PER_TASK:
        raise E.EngagementError("that's a lot of messages — the team has gone quiet for now")
    mid = _add(t, "You", "Contractor", body, "learner")
    E.log_event(t["engagement_id"], task_id, "thread_post", {"message": body[:300]})
    _pending.add(task_id)
    bg.spawn(f"reply:{task_id}", lambda: _reply_loop(task_id), retry_after=0)
    return db.one("SELECT id, ts, author, author_role, body, kind FROM thread_messages WHERE id = ?", mid)


async def _reply_loop(task_id: str) -> None:
    while task_id in _pending:
        _pending.discard(task_id)
        await _reply(task_id)


def _thread_text(t: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    lines = []
    for m in rows:
        mins = int((m["ts"] - (t["started_at"] or m["ts"])) // 60)
        who = "contractor" if m["kind"] == "learner" else f"{m['author']} ({m['author_role'] or 'team'})"
        lines.append(f"[+{mins}m] {who}: {m['body']}")
    return "\n".join(lines[-40:]) or "(nothing yet)"


def _state(t: dict[str, Any]) -> str:
    mins = int((t["active_seconds"] or 0) // 60)
    status = {"active": "investigating", "passed": "FIXED — all of the client's checks pass",
              "revealed": "the contractor gave up and was shown the solution"}.get(t["status"], t["status"])
    return f"{mins} active minutes since the report arrived; status: {status}"


def _context_block(case: dict[str, Any], cast: dict[str, Any] | None, design: dict[str, Any]) -> str:
    meta = case["incident"]["meta"]
    files = sorted(F.read_repo(E.case_dir(case["id"]) / "repo"))
    cast = cast or {"people": case["company"].get("team", []), "facts": [], "evidence": []}
    evidence = [{k: e.get(k) for k in ("id", "who", "offer", "output")} for e in cast.get("evidence", [])]
    return f"""<company>{json.dumps({k: case['company'].get(k) for k in ('name', 'tagline', 'industry', 'blurb')})}</company>
<team>{json.dumps(case['company'].get('team', []))}</team>
<people_in_thread>{json.dumps(cast.get('people', []))}</people_in_thread>
<facts>{json.dumps(cast.get('facts', []), indent=1)}</facts>
<evidence>{json.dumps(evidence, indent=1)}</evidence>
<architecture>{design['repo'].get('architecture', '')}</architecture>
<files>{json.dumps(files)}</files>
<report>{json.dumps(case['incident']['report'], indent=1)}</report>
<ground_truth note="NOBODY in the thread knows this. Use it only to stay consistent — never reveal, hint at, or confirm it.">
symptom: {meta.get('symptom')}
root cause: {meta.get('root_cause')} ({meta.get('root_cause_file')} :: {meta.get('root_cause_symbol')})
</ground_truth>"""


async def _reply(task_id: str) -> None:
    t = E.task(task_id)
    case = E.load_case(E.get(t["engagement_id"])["case_id"])
    rows = messages(task_id)
    if not rows or rows[-1]["kind"] != "learner":
        return
    cast = load(case["id"])
    design = json.loads((E.case_dir(case["id"]) / "design.json").read_text())
    msgs: list[llm.Message] = [
        {"role": "system", "content": P.REPLY_SYSTEM},
        {"role": "user", "content": [llm.cached(_context_block(case, cast, design)),
                                     llm.text_part(P.reply_task(_thread_text(t, rows), _state(t)))]},
    ]
    data, _ = await llm.complete_json(msgs, role="writer", max_tokens=2500, reasoning=1024, case_id=case["id"])
    evidence = {e["id"]: e for e in (cast or {}).get("evidence", [])}
    for r in (data.get("replies") or [])[:2]:
        body = str(r.get("body") or "").strip()
        if not body:
            continue
        ev = evidence.get(str(r.get("evidence") or ""))
        if ev:
            body += f"\n\n```\n{ev['output']}\n```"
        person = E._person(case, r.get("from"))
        _add(t, person["name"], person.get("role", ""), body, "reply")
        E.log_event(t["engagement_id"], task_id, "thread_reply", {"from": person["name"], "message": body[:300]})


def tick(t: dict[str, Any], case_id: str) -> None:
    """Called on every poll during an incident: deliver beats that are due, keep things moving."""
    if t["kind"] != "incident":
        return
    cast = load(case_id)
    if not cast:
        ensure(case_id)
        return
    if t["status"] != "active":
        return
    done = {r["beat_id"] for r in db.all_("SELECT beat_id FROM thread_messages WHERE task_id = ? AND beat_id IS NOT NULL",
                                          t["id"])}
    active = t["active_seconds"] or 0
    evidence = {e["id"]: e for e in cast.get("evidence", [])}
    case = None
    for beat in cast.get("beats", []):
        if beat["id"] in done or active < beat["at_minute"] * 60:
            continue
        if beat.get("kind") == "status_check":
            last = db.one("SELECT MAX(ts) AS ts FROM thread_messages WHERE task_id = ? AND kind = 'learner'", t["id"])
            if last["ts"] and time.time() - last["ts"] < STATUS_QUIET_SECONDS:
                _add(t, "", "", "", "hidden", beat["id"])  # they just heard from you; no need to ask
                continue
        case = case or E.load_case(case_id)
        person = E._person(case, beat.get("who"))
        body = _paste(beat["body"], evidence)
        _add(t, person["name"], person.get("role", ""), body, "beat", beat["id"])
        E.log_event(t["engagement_id"], t["id"], "thread_beat", {"from": person["name"], "message": body[:300]})
        break  # one at a time, like people typing
    # A reply job that died (restart, transient error) leaves the contractor hanging.
    last = db.one("SELECT kind, ts FROM thread_messages WHERE task_id = ? AND kind != 'hidden' ORDER BY id DESC LIMIT 1",
                  t["id"])
    if last and last["kind"] == "learner" and time.time() - last["ts"] > REVIVE_AFTER_SECONDS \
            and not bg.running(f"reply:{t['id']}"):
        _pending.add(t["id"])
        bg.spawn(f"reply:{t['id']}", lambda: _reply_loop(t["id"]), retry_after=120)


def resolve(task_id: str) -> None:
    """Close the loop in the thread once the incident is fixed (or handed back)."""
    t = E.task(task_id)
    if t["kind"] != "incident" or t["status"] not in ("passed", "revealed"):
        return
    if db.one("SELECT id FROM thread_messages WHERE task_id = ? AND kind = 'resolution'", task_id):
        return
    e = E.get(t["engagement_id"])
    cast = load(e["case_id"])
    msg = ((cast or {}).get("resolution") or {}).get("fixed" if t["status"] == "passed" else "not_fixed")
    if not msg or not msg.get("body"):
        return
    person = E._person(E.load_case(e["case_id"]), msg.get("who"))
    _add(t, person["name"], person.get("role", ""), msg["body"], "resolution")


def transcript(task_id: str) -> str:
    """The thread after the report, for the debrief."""
    rows = messages(task_id)
    return _thread_text(E.task(task_id), rows) if rows else ""
