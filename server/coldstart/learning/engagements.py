"""Engagement lifecycle: take a case, work through its tasks, grade, record.

An engagement = one client codebase, worked through a plan of tasks
(recon → incident → optional feature). Each task gets a workspace snapshot
at its start so the learner's diff can be isolated and reviewed.
"""

from __future__ import annotations

import json
import re
import shutil
import time
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any

from .. import config, db, sandbox
from ..generation import files as F
from ..runtime.workspace import Workspace
from . import scheduler

TASK_KINDS = ("recon", "incident", "feature")


class EngagementError(ValueError):
    pass


# --- cases ---------------------------------------------------------------------------

@lru_cache(maxsize=32)
def _load_case_cached(case_id: str, mtime: float) -> dict[str, Any]:
    return json.loads((config.LIBRARY_DIR / case_id / "case.json").read_text())


def load_case(case_id: str) -> dict[str, Any]:
    path = config.LIBRARY_DIR / case_id / "case.json"
    if not path.exists():
        raise EngagementError(f"case {case_id} has no case file")
    return _load_case_cached(case_id, path.stat().st_mtime)


def case_dir(case_id: str) -> Path:
    return config.LIBRARY_DIR / case_id


def _person(case: dict[str, Any], name: str | None) -> dict[str, Any]:
    team = case["company"].get("team") or []
    for p in team:
        if name and (p.get("name") == name or name.startswith(p.get("name", "~"))):
            return p
    return {"name": name or (team[0]["name"] if team else "The team"), "role": ""}


def _author(case: dict[str, Any]) -> tuple[str, str]:
    team = case["company"].get("team") or [{"name": "Eng Lead"}]
    lead = next((p for p in team if "lead" in p.get("role", "").lower() or "engineer" in p.get("role", "").lower()), team[0])
    domain = re.sub(r"[^a-z0-9]", "", case["company"]["name"].lower())[:24] or "client"
    first = re.sub(r"[^a-z]", "", lead["name"].split()[0].lower()) or "eng"
    return lead["name"], f"{first}@{domain}.example"


def public_case(case: dict[str, Any], tasks: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """What the learner may see right now. Secrets unlock as tasks finish."""
    inc_task, feat_task = tasks.get("incident"), tasks.get("feature")
    recon_task = tasks.get("recon")
    out: dict[str, Any] = {
        "id": case["id"],
        "company": case["company"],
        "repo": case["repo"],
        "card": case["card"],
        "concepts": {"incident": None, "feature": None, "flavor": case["concepts"]["flavor"]},
    }
    recon = case["recon"]
    recon_done = recon_task and recon_task["status"] in ("passed", "failed", "revealed", "skipped")
    out["recon"] = {
        "mode": recon["mode"],
        "par_minutes": recon["par_minutes"],
        "briefing": recon["briefing"],
        "tour": recon["tour"],
        "questions": [{k: q[k] for k in ("id", "kind", "prompt") if k in q} for q in recon["questions"]],
        "map": recon["map"] if recon_done else None,
    }
    if inc_task and inc_task["status"] != "pending":
        inc = case["incident"]
        out["incident"] = {
            "report": inc["report"],
            "fidelity": inc["fidelity"],
            "par_minutes": inc["par_minutes"],
            "regression_test": (inc.get("regression_test") or {}).get("path"),
        }
        if inc_task["status"] in ("passed", "revealed"):
            out["incident"]["solution"] = incident_solution(case)
            out["concepts"]["incident"] = case["concepts"]["incident"]
    if feat_task and feat_task["status"] != "pending":
        feat = case["feature"]
        out["feature"] = {
            "title": feat["title"],
            "author": _person(case, feat.get("author")),
            "ticket": feat["ticket"],
            "par_minutes": feat["par_minutes"],
            "acceptance_path": feat["acceptance"]["path"],
        }
        if feat_task["status"] in ("passed", "revealed"):
            out["feature"]["solution"] = feature_solution(case)
            out["concepts"]["feature"] = case["concepts"]["feature"]
    return out


def incident_solution(case: dict[str, Any]) -> dict[str, Any]:
    inc, meta = case["incident"], case["incident"]["meta"]
    fix_diff = _reverse_diff(case)
    return {
        "title": meta.get("title"),
        "root_cause": meta.get("root_cause"),
        "root_cause_file": meta.get("root_cause_file"),
        "root_cause_symbol": meta.get("root_cause_symbol"),
        "files_involved": meta.get("files_involved", []),
        "mechanism": meta.get("mechanism"),
        "fix": meta.get("fix"),
        "fix_diff": fix_diff,
        "expert_path": meta.get("expert_path", []),
        "concept_card": meta.get("concept_card"),
        "repro": inc.get("repro"),
        "hidden_tests": (case_dir(case["id"]) / inc["hidden_tests_path"]).read_text(),
    }


def feature_solution(case: dict[str, Any]) -> dict[str, Any]:
    feat = case["feature"]
    meta = feat["meta"]
    return {
        "reference_diff": (case_dir(case["id"]) / "feature" / "reference.diff").read_text(),
        "expert_path": meta.get("expert_path", []),
        "review_focus": meta.get("review_focus", []),
        "concept_card": meta.get("concept_card"),
        "hidden_tests": (case_dir(case["id"]) / feat["hidden_tests_path"]).read_text(),
    }


def _reverse_diff(case: dict[str, Any]) -> str:
    """The canonical fix = buggy repo → clean repo, limited to files the bug touched."""
    d = case_dir(case["id"])
    touched = {e["path"] for e in case["incident"]["bug_edits"]}
    before = {p: (d / "repo" / p).read_text() for p in touched if (d / "repo" / p).exists()}
    after = {p: (d / "clean" / p).read_text() for p in touched if (d / "clean" / p).exists()}
    return F.unified_diff(before, after)


# --- engagements ------------------------------------------------------------------------

def get(engagement_id: str) -> dict[str, Any]:
    e = db.one("SELECT * FROM engagements WHERE id = ?", engagement_id)
    if not e:
        raise EngagementError("no such engagement")
    e["plan"] = db.loads(e["plan"], [])
    return e


def tasks_for(engagement_id: str) -> dict[str, dict[str, Any]]:
    rows = db.all_("SELECT * FROM tasks WHERE engagement_id = ?", engagement_id)
    out = {}
    for r in rows:
        r["result"] = db.loads(r["result"], None)
        out[r["kind"]] = r
    return out


def task(task_id: str) -> dict[str, Any]:
    t = db.one("SELECT * FROM tasks WHERE id = ?", task_id)
    if not t:
        raise EngagementError("no such task")
    t["result"] = db.loads(t["result"], None)
    return t


def active() -> dict[str, Any] | None:
    e = db.one("SELECT * FROM engagements WHERE status = 'active' ORDER BY started_at DESC LIMIT 1")
    if e:
        e["plan"] = db.loads(e["plan"], [])
    return e


def start(case_id: str, plan: list[str]) -> dict[str, Any]:
    row = db.one("SELECT status FROM cases WHERE id = ?", case_id)
    if not row or row["status"] != "ready":
        raise EngagementError("that case isn't available")
    if active():
        raise EngagementError("finish or leave your current engagement first")
    plan = [k for k in TASK_KINDS if k in plan] or ["recon", "incident"]
    if "incident" not in plan and "feature" not in plan:
        plan.append("incident")
    case = load_case(case_id)
    eid = time.strftime("e%y%m%d-") + uuid.uuid4().hex[:6]
    Workspace.provision(eid, case_dir(case_id), _author(case))
    now = time.time()
    with db.tx() as c:
        c.execute("UPDATE cases SET status = 'taken' WHERE id = ?", (case_id,))
        c.execute("INSERT INTO engagements(id, case_id, started_at, status, phase, plan) VALUES(?,?,?,?,?,?)",
                  (eid, case_id, now, "active", "briefing", db.dumps(plan)))
        for kind in TASK_KINDS:
            c.execute("INSERT INTO tasks(id, engagement_id, kind, status) VALUES(?,?,?,?)",
                      (f"{eid}-{kind}", eid, kind, "pending" if kind in plan else "skipped"))
    log_event(eid, None, "engagement_start", {"case_id": case_id, "plan": plan})
    return get(eid)


def begin_task(engagement_id: str, kind: str) -> dict[str, Any]:
    e = get(engagement_id)
    if e["status"] != "active":
        raise EngagementError("engagement is over")
    tasks = tasks_for(engagement_id)
    t = tasks.get(kind)
    if not t:
        raise EngagementError(f"unknown task {kind}")
    if t["status"] == "active":
        return t
    if t["status"] not in ("pending", "skipped"):
        raise EngagementError(f"{kind} is already finished")
    ws = Workspace(engagement_id)
    case = load_case(e["case_id"])
    # Close out whatever was active before.
    for other in tasks.values():
        if other["status"] == "active" and other["kind"] != kind:
            _finish(other["id"], "skipped" if other["kind"] != "recon" else "failed")
    if kind == "feature":
        _prepare_feature(ws, case, tasks.get("incident"))
    ws.snapshot(t["id"])
    base = ws.head()
    db.run("UPDATE tasks SET status = 'active', started_at = ?, base_commit = ? WHERE id = ?",
           time.time(), base, t["id"])
    db.run("UPDATE engagements SET phase = ? WHERE id = ?", kind, engagement_id)
    if kind not in e["plan"]:
        db.run("UPDATE engagements SET plan = ? WHERE id = ?", db.dumps([*e["plan"], kind]), engagement_id)
    log_event(engagement_id, t["id"], "task_start", {"kind": kind})
    return task(t["id"])


def _prepare_feature(ws: Workspace, case: dict[str, Any], incident: dict[str, Any] | None) -> None:
    """Merge the canonical incident fix (unless the learner's own fix passed), add acceptance tests."""
    d = case_dir(case["id"])
    if not incident or incident["status"] != "passed":
        for edit in case["incident"]["bug_edits"]:
            clean = d / "clean" / edit["path"]
            if clean.exists():
                ws.write(edit["path"], clean.read_text())
        reg = case["incident"].get("regression_test")
        if reg:
            ws.write(reg["path"], reg["content"])
    acc = case["feature"]["acceptance"]
    ws.write(acc["path"], acc["content"])
    author = _person(case, case["feature"].get("author"))
    domain = _author(case)[1].split("@")[1]
    ws.commit(f"{case['feature'].get('title') or 'Feature'}: add acceptance tests",
              author=(author["name"], f"{author['name'].split()[0].lower()}@{domain}"))


def _finish(task_id: str, status: str, result: dict[str, Any] | None = None) -> None:
    db.run("UPDATE tasks SET status = ?, finished_at = ?, result = COALESCE(?, result) WHERE id = ?",
           status, time.time(), db.dumps(result) if result is not None else None, task_id)


def tick(task_id: str, seconds: float) -> float:
    """Heartbeat from the client timer (active, un-paused time only)."""
    seconds = max(0.0, min(float(seconds), 60.0))
    t = task(task_id)
    if t["status"] != "active":
        return t["active_seconds"]
    db.run("UPDATE tasks SET active_seconds = active_seconds + ? WHERE id = ?", seconds, task_id)
    db.add_practice_seconds(seconds)
    return t["active_seconds"] + seconds


def log_event(engagement_id: str, task_id: str | None, kind: str, data: dict[str, Any] | None = None,
              ts: float | None = None) -> None:
    db.run("INSERT INTO events(engagement_id, task_id, ts, kind, data) VALUES(?,?,?,?,?)",
           engagement_id, task_id, ts or time.time(), kind, db.dumps(data or {}))


def events_for(task_id: str) -> list[dict[str, Any]]:
    rows = db.all_("SELECT ts, kind, data FROM events WHERE task_id = ? ORDER BY ts", task_id)
    for r in rows:
        r["data"] = db.loads(r["data"], {})
    return rows


def use_hint(task_id: str) -> dict[str, Any]:
    t = task(task_id)
    e = get(t["engagement_id"])
    case = load_case(e["case_id"])
    if t["kind"] == "incident":
        hints = case["incident"]["meta"]["hints"]
    elif t["kind"] == "feature":
        hints = case["feature"]["meta"].get("hints", [])
    else:
        raise EngagementError("recon has the tour instead of hints")
    n = min(t["hints_used"] + 1, len(hints))
    db.run("UPDATE tasks SET hints_used = ? WHERE id = ?", n, task_id)
    log_event(t["engagement_id"], task_id, "hint", {"level": n})
    return {"level": n, "total": len(hints), "hints": [_strip_hint_label(h) for h in hints[:n]]}


def _strip_hint_label(h: str) -> str:
    return re.sub(r"^\s*\d\s*[A-Z ]{3,12}:\s*", "", h).strip()


def hints_seen(task_id: str) -> list[str]:
    t = task(task_id)
    if t["kind"] == "recon" or t["hints_used"] == 0:
        return []
    case = load_case(get(t["engagement_id"])["case_id"])
    hints = case["incident" if t["kind"] == "incident" else "feature"]["meta"].get("hints", [])
    return [_strip_hint_label(h) for h in hints[: t["hints_used"]]]


# --- grading: tests --------------------------------------------------------------------------

async def run_visible_tests(engagement_id: str, targets: list[str] | None = None) -> dict[str, Any]:
    ws = Workspace(engagement_id)
    tmp = sandbox.scratch_copy(ws.repo, "visible")
    try:
        rep = await sandbox.run_pytest(tmp, targets or [])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return rep.to_dict()


async def run_hidden(engagement_id: str, kind: str) -> sandbox.TestReport:
    """Hidden tests run against a scratch copy of the learner's repo (never visible to them)."""
    e = get(engagement_id)
    case = load_case(e["case_id"])
    d = case_dir(case["id"])
    hidden_rel = "tests/test_zz_hidden_incident.py" if kind == "incident" else "tests/test_zz_hidden_feature.py"
    hidden_src = d / case[kind]["hidden_tests_path"]
    tmp = sandbox.scratch_copy(Workspace(engagement_id).repo, "grade")
    try:
        (tmp / hidden_rel).write_text(hidden_src.read_text())
        return await sandbox.run_pytest(tmp, [])  # whole suite: hidden + visible (catches regressions)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def classify(t: dict[str, Any], passed: bool, revealed: bool, mentor_messages: int) -> str:
    if revealed:
        return "revealed"
    if not passed:
        return "failed"
    if t["hints_used"] <= 1 and mentor_messages <= 4:
        return "clean"
    return "assisted"


def mentor_message_count(task_id: str) -> int:
    return db.one("SELECT COUNT(*) AS n FROM chat WHERE task_id = ? AND role = 'user'", task_id)["n"]


async def submit(task_id: str) -> dict[str, Any]:
    t = task(task_id)
    if t["kind"] not in ("incident", "feature"):
        raise EngagementError("use the recon endpoint")
    if t["status"] != "active":
        raise EngagementError("this task isn't active")
    db.run("UPDATE tasks SET attempts = attempts + 1 WHERE id = ?", task_id)
    report = await run_hidden(t["engagement_id"], t["kind"])
    visible_names = {c.nodeid for c in report.cases if "test_zz_hidden" not in c.nodeid}
    failing = [
        {
            "nodeid": c.nodeid.replace("tests/test_zz_hidden_incident.py", "hidden::incident")
                              .replace("tests/test_zz_hidden_feature.py", "hidden::feature"),
            "hidden": c.nodeid not in visible_names,
            "message": c.message[:600],
            "details": c.details[-1500:] if c.nodeid in visible_names else _redact(c.details)[-1200:],
        }
        for c in report.failing()
    ]
    result = {
        "passed": report.ok,
        "counts": {"passed": report.passed, "failed": report.failed, "errors": report.errors, "total": report.total},
        "failing": failing,
        "timed_out": report.timed_out,
        "output_tail": report.output[-3000:] if not report.cases else "",
    }
    log_event(t["engagement_id"], task_id, "submit", {"passed": report.ok, "failed": len(failing)})
    if report.ok:
        await complete(task_id, passed=True)
    return result


def _redact(details: str) -> str:
    """Show hidden-test failures without dumping the hidden test source."""
    keep = [l for l in details.splitlines() if l.startswith("E ") or "Error" in l or l.startswith(">")]
    return "\n".join(keep[:25])


async def reveal(task_id: str) -> None:
    t = task(task_id)
    if t["status"] != "active":
        raise EngagementError("this task isn't active")
    log_event(t["engagement_id"], task_id, "reveal", {})
    await complete(task_id, passed=False, revealed=True)


async def complete(task_id: str, *, passed: bool, revealed: bool = False) -> None:
    t = task(task_id)
    e = get(t["engagement_id"])
    case = load_case(e["case_id"])
    outcome = classify(t, passed, revealed, mentor_message_count(task_id))
    status = "passed" if passed else "revealed" if revealed else "failed"
    concept = case["concepts"][t["kind"]]
    new_m, before = scheduler.record_attempt(concept, kind=t["kind"], outcome=outcome, case_id=case["id"])
    par = case[t["kind"]]["par_minutes"] * 60
    level = scheduler.adjust_level(t["kind"], outcome, time_ratio=(t["active_seconds"] / par) if par else None)
    root_file = case["incident"]["meta"].get("root_cause_file") if t["kind"] == "incident" else None
    result = {
        "outcome": outcome,
        "passed": passed,
        "seconds": round(t["active_seconds"]),
        "par_seconds": par,
        "hints_used": t["hints_used"],
        "attempts": t["attempts"],
        "mentor_messages": mentor_message_count(task_id),
        "time_to_root_file": _time_to_file(task_id, t["started_at"], root_file) if root_file else None,
        "concept": {"id": concept, "state": new_m["state"], "before": before},
        "level_after": level,
    }
    _finish(task_id, status, result)
    log_event(e["id"], task_id, "task_done", {"outcome": outcome})


def _time_to_file(task_id: str, started_at: float | None, path: str) -> float | None:
    for ev in events_for(task_id):
        if ev["kind"] == "open_file" and ev["data"].get("path") == path and started_at:
            return round(ev["ts"] - started_at)
    return None


def end(engagement_id: str, abandoned: bool = False) -> dict[str, Any]:
    e = get(engagement_id)
    if e["status"] != "active":
        return e
    tasks = tasks_for(engagement_id)
    for t in tasks.values():
        if t["status"] == "active":
            _finish(t["id"], "skipped")
    case = load_case(e["case_id"])
    worked = any(t["status"] in ("passed", "failed", "revealed") for t in tasks.values())
    if worked:
        for cid in case["concepts"]["flavor"]:
            scheduler.record_exposure(cid, case["id"])
        for kind in ("incident", "feature"):
            if tasks[kind]["status"] == "skipped" and kind in e["plan"]:
                pass  # planned but not attempted: no signal either way
    db.run("UPDATE engagements SET status = ?, ended_at = ?, phase = 'wrapup' WHERE id = ?",
           "abandoned" if abandoned and not worked else "done", time.time(), engagement_id)
    log_event(engagement_id, None, "engagement_end", {"abandoned": abandoned})
    return get(engagement_id)
