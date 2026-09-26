"""HTTP + WebSocket API, and the static frontend.

Because this server can run a shell, other websites are kept out: Host must be
localhost or the configured public host (DNS-rebinding), mutating requests
need a custom header (CSRF), and the terminal WebSocket checks Origin. There is
no login; AI spend is capped per day (llm.py) and generated code is jailed
(sandbox.py).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import config, curriculum, db, llm, persist, sandbox
from .generation import features
from .generation.manager import manager
from .learning import engagements as E
from .learning import bg, cast, coach, drills, mentor, replay, review, scheduler
from .runtime import intel, search
from .runtime.terminal import TerminalSession
from .runtime.workspace import Workspace, WorkspaceError

log = logging.getLogger("coldstart")


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.ensure_dirs()
    db.conn()
    manager.start()
    flusher = asyncio.create_task(persist.flush_loop(), name="workspace-flush")
    waker = asyncio.create_task(_keep_awake_while_busy(), name="keep-awake")
    if sandbox.JAIL:
        report = await sandbox.self_check()
        log.warning("sandbox self-check: %s", report)
        db.kv_set("sandbox_selfcheck", {**report, "ts": time.time()})
    yield
    flusher.cancel()
    waker.cancel()
    await manager.stop()
    await asyncio.to_thread(persist.flush_dirty)  # last chance before the container goes away


app = FastAPI(title="Cold Start", lifespan=lifespan)


def _background_busy() -> bool:
    return manager.busy() or features.busy() or bg.busy() or bool(_drill_task and not _drill_task.done())


async def _keep_awake_while_busy(interval: float = 45.0) -> None:
    """The hosted machine scales to zero when nobody's visiting, which would kill a
    half-generated client. While background work runs, visit ourselves through the
    public URL so the platform sees traffic; once idle, let it sleep."""
    if not config.PUBLIC_HOSTS:
        return
    import httpx

    url = f"https://{config.PUBLIC_HOSTS[0]}/api/health"
    async with httpx.AsyncClient(timeout=15) as http:
        while True:
            await asyncio.sleep(interval)
            if _background_busy():
                try:
                    await http.get(url)
                except httpx.HTTPError as err:
                    log.debug("keep-awake ping failed: %s", err)

ALLOWED_HOSTS = {"127.0.0.1", "localhost", *(h.lower() for h in config.PUBLIC_HOSTS)}


def _host_ok(host_header: str | None) -> bool:
    host = (host_header or "").strip().lower()
    return not host.startswith("[") and host.rsplit(":", 1)[0] in ALLOWED_HOSTS


@app.middleware("http")
async def guards(request: Request, call_next):
    path = request.url.path
    if path == "/api/health":
        return await call_next(request)  # platform health checks may use any Host
    if not _host_ok(request.headers.get("host")):
        return JSONResponse({"detail": "invalid host"}, status_code=400)
    if path.startswith("/api/") and request.method not in ("GET", "HEAD", "OPTIONS"):
        if request.headers.get("x-coldstart") != "1":
            return JSONResponse({"detail": "missing X-Coldstart header"}, status_code=403)
    return await call_next(request)


@app.get("/api/health", include_in_schema=False)
async def health() -> dict[str, Any]:
    return {"ok": True}




@app.exception_handler(E.EngagementError)
async def engagement_error(_: Request, err: E.EngagementError):
    return JSONResponse({"detail": str(err)}, status_code=400)


@app.exception_handler(WorkspaceError)
async def workspace_error(_: Request, err: WorkspaceError):
    return JSONResponse({"detail": str(err)}, status_code=400)


@app.exception_handler(llm.LLMError)
async def llm_error(_: Request, err: llm.LLMError):
    return JSONResponse({"detail": f"AI request failed: {err}"}, status_code=502)


def _ws(eid: str) -> Workspace:
    ws = Workspace(eid)
    if not ws.exists():
        raise HTTPException(404, "workspace not found")
    return ws


def _active_task_id(eid: str) -> str | None:
    row = db.one("SELECT id FROM tasks WHERE engagement_id = ? AND status = 'active'", eid)
    return row["id"] if row else None


# --- home ----------------------------------------------------------------------------

@app.get("/api/state")
async def state() -> dict[str, Any]:
    ready = db.all_("SELECT id, card, created_at FROM cases WHERE status = 'ready' ORDER BY created_at")
    pipeline = db.all_("SELECT id, status, stage, spec, created_at FROM cases "
                       "WHERE status IN ('queued', 'generating') ORDER BY created_at")
    failed = db.all_("SELECT id, error, finished_at FROM cases WHERE status = 'failed' "
                     "ORDER BY created_at DESC LIMIT 1")
    act = E.active()
    active_summary = None
    if act:
        case = E.load_case(act["case_id"])
        active_summary = {"id": act["id"], "company": case["company"]["name"], "phase": act["phase"],
                          "subject": case["card"]["subject"], "started_at": act["started_at"]}
    done = db.one("SELECT COUNT(*) AS n FROM engagements WHERE status = 'done'")["n"]
    return {
        "inbox": [{"id": r["id"], **db.loads(r["card"], {}), "arrived_at": r["created_at"]} for r in ready],
        "pipeline": [
            {"id": r["id"], "status": r["status"], "stage": db.loads(r["stage"], None),
             "domain": db.loads(r["spec"], {}).get("domain", {}).get("name"), "created_at": r["created_at"]}
            for r in pipeline
        ],
        "last_failure": failed[0] if failed else None,
        "manager": manager.status(),
        "active": active_summary,
        "recall": _due_recall(),
        "calendar": _calendar(),
        "engagements_done": done,
        "first_run": done == 0 and not act,
        "budget": await llm.key_status(),
        "settings": db.settings(),
        "learner": scheduler.learner(),
    }


def _calendar(days: int = 182) -> list[dict[str, Any]]:
    since = time.strftime("%Y-%m-%d", time.localtime(time.time() - days * 86400))
    return db.all_("SELECT day, seconds FROM practice_days WHERE day >= ? ORDER BY day", since)


def _due_recall() -> dict[str, Any] | None:
    row = db.one("SELECT id, title, recall_q, recall_a, case_id, concept_ids FROM journal "
                 "WHERE recall_q IS NOT NULL AND recall_due <= ? ORDER BY recall_due LIMIT 1", time.time())
    if not row:
        return None
    row["concept_ids"] = db.loads(row["concept_ids"], [])
    return row


# --- cases ---------------------------------------------------------------------------

@app.post("/api/cases/generate")
async def generate_case(body: dict = Body(default={})) -> dict[str, Any]:
    focus = body.get("focus")
    if focus and focus not in curriculum.load().concepts:
        raise HTTPException(400, "unknown concept")
    return {"case_id": manager.request(focus=focus)}


@app.get("/api/cases/{case_id}")
async def case_preview(case_id: str) -> dict[str, Any]:
    row = db.one("SELECT status FROM cases WHERE id = ?", case_id)
    if not row:
        raise HTTPException(404, "no such case")
    case = E.load_case(case_id)
    return {
        "id": case_id,
        "status": row["status"],
        "company": case["company"],
        "repo": case["repo"],
        "card": case["card"],
        "recon_mode": case["recon"]["mode"],
        "default_plan": db.settings().get("default_plan", ["recon", "incident"]),
    }


@app.post("/api/cases/{case_id}/dismiss")
async def dismiss_case(case_id: str) -> dict[str, Any]:
    db.run("UPDATE cases SET status = 'dismissed' WHERE id = ? AND status = 'ready'", case_id)
    manager.poke()
    return {"ok": True}


@app.get("/api/cases/{case_id}/log")
async def case_log(case_id: str) -> dict[str, Any]:
    p = config.LIBRARY_DIR / case_id / "gen.log"
    return {"log": p.read_text()[-20000:] if p.exists() else ""}


# --- engagements -------------------------------------------------------------------------

@app.post("/api/engagements")
async def start_engagement(body: dict = Body(...)) -> dict[str, Any]:
    e = E.start(body["case_id"], body.get("plan") or db.settings().get("default_plan", ["recon", "incident"]))
    if "feature" in e["plan"]:
        features.ensure(e["case_id"])  # written while they do recon + the incident
    cast.ensure(e["case_id"])  # the people in the incident thread, ready by the time it lands
    manager.poke()  # a slot opened in the inbox
    return engagement_payload(e["id"])


@app.post("/api/engagements/{eid}/feature/prepare")
async def prepare_feature(eid: str) -> dict[str, Any]:
    e = E.get(eid)
    return {"status": features.ensure(e["case_id"]), "error": features.error(e["case_id"])}


@app.get("/api/engagements/{eid}/feature/status")
async def feature_status(eid: str) -> dict[str, Any]:
    e = E.get(eid)
    return {"status": features.status(e["case_id"]), "error": features.error(e["case_id"])}


@app.get("/api/engagements/{eid}")
async def get_engagement(eid: str) -> dict[str, Any]:
    return engagement_payload(eid)


def engagement_payload(eid: str) -> dict[str, Any]:
    e = E.get(eid)
    tasks = E.tasks_for(eid)
    case = E.load_case(e["case_id"])
    return {
        "engagement": {k: e[k] for k in ("id", "case_id", "status", "phase", "plan", "started_at", "ended_at", "notes")},
        "case": E.public_case(case, tasks),
        "tasks": {
            k: {key: t[key] for key in ("id", "kind", "status", "started_at", "finished_at", "active_seconds",
                                         "hints_used", "attempts", "result")}
            for k, t in tasks.items()
        },
        "hints": {k: E.hints_seen(t["id"]) for k, t in tasks.items() if k != "recon"},
        "hint_total": {"incident": len(case["incident"]["meta"].get("hints", [])),
                       "feature": len((case.get("feature") or {}).get("meta", {}).get("hints", []))},
        "settings": {k: db.settings().get(k) for k in ("mentor_name", "timer_mode", "sound", "coach_nudges")},
        "habit": _habit_for(e["case_id"]),
    }


def _habit_for(case_id: str) -> dict[str, Any] | None:
    habit = db.kv_get("habit")
    return habit if habit and habit.get("case_id") != case_id else None


@app.post("/api/engagements/{eid}/tasks/{kind}/begin")
async def begin_task(eid: str, kind: str) -> dict[str, Any]:
    E.begin_task(eid, kind)
    if kind == "incident":
        cast.ensure(E.get(eid)["case_id"])
    return engagement_payload(eid)


@app.post("/api/engagements/{eid}/end")
async def end_engagement(eid: str, body: dict = Body(default={})) -> dict[str, Any]:
    E.end(eid, abandoned=bool(body.get("abandon")))
    manager.poke()
    return engagement_payload(eid)


@app.put("/api/engagements/{eid}/notes")
async def save_notes(eid: str, body: dict = Body(...)) -> dict[str, Any]:
    db.run("UPDATE engagements SET notes = ? WHERE id = ?", str(body.get("notes", ""))[:50_000], eid)
    return {"ok": True}


@app.post("/api/engagements/{eid}/events")
async def post_events(eid: str, body: dict = Body(...)) -> dict[str, Any]:
    task_id = body.get("task_id") or _active_task_id(eid)
    for ev in (body.get("events") or [])[:200]:
        kind = str(ev.get("kind", ""))[:40]
        if kind:
            E.log_event(eid, task_id, kind, ev.get("data") or {}, ts=ev.get("ts"))
    return {"ok": True}


@app.get("/api/engagements/{eid}/wrapup")
async def wrapup(eid: str) -> dict[str, Any]:
    e = E.get(eid)
    case = E.load_case(e["case_id"])
    tasks = E.tasks_for(eid)
    cur = curriculum.load()
    touched = [c for c in [case["concepts"]["incident"], case["concepts"]["feature"], *case["concepts"]["flavor"]]
               if c in cur.concepts]
    return {
        "company": case["company"],
        "tasks": {k: {"status": t["status"], "result": t["result"], "active_seconds": t["active_seconds"]}
                  for k, t in tasks.items()},
        "concepts": [{**cur.concepts[c].to_dict(), "mastery": scheduler.mastery(c)["state"]} for c in touched],
        "next": db.one("SELECT id, card FROM cases WHERE status = 'ready' ORDER BY created_at LIMIT 1"),
    }


# --- tasks --------------------------------------------------------------------------------

@app.post("/api/tasks/{task_id}/tick")
async def task_tick(task_id: str, body: dict = Body(...)) -> dict[str, Any]:
    return {"active_seconds": E.tick(task_id, float(body.get("seconds", 0)))}


@app.post("/api/tasks/{task_id}/hint")
async def task_hint(task_id: str) -> dict[str, Any]:
    return E.use_hint(task_id)


@app.post("/api/tasks/{task_id}/recon")
async def task_recon(task_id: str, body: dict = Body(...)) -> dict[str, Any]:
    return await review.grade_recon(task_id, body.get("answers") or {})


@app.post("/api/tasks/{task_id}/submit")
async def task_submit(task_id: str) -> dict[str, Any]:
    result = await E.submit(task_id)
    if result["passed"]:
        _incident_over(task_id)
    return result


@app.post("/api/tasks/{task_id}/reveal")
async def task_reveal(task_id: str) -> dict[str, Any]:
    await E.reveal(task_id)
    _incident_over(task_id)
    return {"ok": True}


def _incident_over(task_id: str) -> None:
    t = E.task(task_id)
    if t["kind"] == "incident":
        cast.resolve(task_id)                           # the thread closes the loop
        replay.ensure(E.get(t["engagement_id"])["case_id"])  # ready by the time the debrief is read


@app.get("/api/tasks/{task_id}/live")
async def task_live(task_id: str, thread_after: int = 0, chat_after: int = 0, coach_on: bool = True) -> dict[str, Any]:
    """Polled while a task is open: new thread messages, who's typing, coach check-ins."""
    t = E.task(task_id)
    e = E.get(t["engagement_id"])
    if e["status"] == "active":
        cast.tick(t, e["case_id"])
        if coach_on:
            coach.tick(t, e["case_id"])
    incident = t["kind"] == "incident"
    return {
        "thread": cast.messages(task_id, after=thread_after) if incident else [],
        "typing": cast.typing(task_id) if incident else None,
        "reply_error": cast.reply_error(task_id) if incident else None,
        "cast": cast.status(e["case_id"]) if incident else None,
        "nudges": coach.nudges(task_id, after=chat_after),
    }


@app.post("/api/tasks/{task_id}/thread")
async def thread_post(task_id: str, body: dict = Body(...)) -> dict[str, Any]:
    return {"message": cast.post(task_id, str(body.get("body", "")))}


@app.post("/api/tasks/{task_id}/thread/retry")
async def thread_retry(task_id: str) -> dict[str, Any]:
    cast.retry(task_id)
    return {"ok": True}


@app.get("/api/tasks/{task_id}/replay")
async def task_replay(task_id: str) -> dict[str, Any]:
    return replay.payload(task_id)


@app.post("/api/tasks/{task_id}/debrief")
async def task_debrief(task_id: str, body: dict = Body(default={})) -> dict[str, Any]:
    return await review.debrief(task_id, str(body.get("explanation", "")))


@app.get("/api/tasks/{task_id}/chat")
async def chat_history(task_id: str) -> dict[str, Any]:
    return {"messages": mentor.history(task_id)}


@app.post("/api/tasks/{task_id}/chat")
async def chat(task_id: str, body: dict = Body(...)) -> StreamingResponse:
    message = str(body.get("message", "")).strip()[:4000]
    if not message:
        raise HTTPException(400, "empty message")

    async def events():
        try:
            async for piece in mentor.chat(task_id, message, body.get("context") or {}):
                yield f"data: {json.dumps({'t': piece})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as err:  # noqa: BLE001 — surface to the UI
            yield f"data: {json.dumps({'error': str(err)[:300]})}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# --- workspace ------------------------------------------------------------------------------

@app.get("/api/ws/{eid}/tree")
async def ws_tree(eid: str) -> dict[str, Any]:
    ws = _ws(eid)
    task_id = _active_task_id(eid)
    changed = [c["path"] for c in ws.changes(task_id)] if task_id else []
    return {"entries": ws.tree(), "changed": changed}


@app.get("/api/ws/{eid}/file")
async def ws_read(eid: str, path: str) -> dict[str, Any]:
    return {"path": path, "content": _ws(eid).read(path)}


@app.put("/api/ws/{eid}/file")
async def ws_write(eid: str, body: dict = Body(...)) -> dict[str, Any]:
    _ws(eid).write(body["path"], body.get("content", ""))
    return {"ok": True}


@app.post("/api/ws/{eid}/fs")
async def ws_fs(eid: str, body: dict = Body(...)) -> dict[str, Any]:
    ws = _ws(eid)
    op = body.get("op")
    if op == "create":
        ws.create(body["path"], body.get("kind", "file"))
    elif op == "delete":
        ws.delete(body["path"])
    elif op == "rename":
        ws.rename(body["path"], body["to"])
    else:
        raise HTTPException(400, "unknown op")
    return {"ok": True}


@app.get("/api/ws/{eid}/search")
async def ws_search(eid: str, q: str, regex: bool = False, case: bool = False, word: bool = False,
                    include: str | None = None) -> dict[str, Any]:
    return search.search(_ws(eid), q, regex=regex, case=case, word=word, include=include)


@app.post("/api/ws/{eid}/intel/{op}")
async def ws_intel(eid: str, op: str, body: dict = Body(...)) -> Any:
    ws = _ws(eid)
    args = (ws, body["path"], int(body["line"]), int(body["column"]), body.get("content"))
    fn = {"definition": intel.definition, "references": intel.references, "hover": intel.hover}.get(op)
    if not fn:
        raise HTTPException(400, "unknown op")
    try:
        return await asyncio.to_thread(fn, *args)
    except Exception as err:  # noqa: BLE001 — jedi on half-typed code can throw anything
        log.debug("intel %s failed: %s", op, err)
        return [] if op != "hover" else None


@app.get("/api/ws/{eid}/symbols")
async def ws_symbols(eid: str, path: str) -> list[dict[str, Any]]:
    return intel.symbols(_ws(eid), path)


@app.get("/api/external")
async def external_file(path: str) -> dict[str, Any]:
    try:
        return {"path": path, "content": intel.read_external(path), "readonly": True}
    except PermissionError as err:
        raise HTTPException(403, str(err)) from err
    except FileNotFoundError as err:
        raise HTTPException(404, "not found") from err


@app.get("/api/ws/{eid}/changes")
async def ws_changes(eid: str, task_id: str | None = None) -> dict[str, Any]:
    ws = _ws(eid)
    tid = task_id or _active_task_id(eid)
    return {"task_id": tid, "changes": ws.changes(tid) if tid else []}


@app.post("/api/ws/{eid}/revert")
async def ws_revert(eid: str, body: dict = Body(default={})) -> dict[str, Any]:
    ws = _ws(eid)
    tid = body.get("task_id") or _active_task_id(eid)
    if not tid:
        raise HTTPException(400, "no active task")
    ws.revert(tid, body.get("path"))
    return {"ok": True}


@app.post("/api/ws/{eid}/tests")
async def ws_tests(eid: str, body: dict = Body(default={})) -> dict[str, Any]:
    _ws(eid)
    targets = [str(t) for t in (body.get("targets") or [])][:20]
    report = await E.run_visible_tests(eid, targets)
    summary = f"{report['passed']} passed, {report['failed']} failed, {report['errors']} errors"
    E.log_event(eid, _active_task_id(eid), "run_tests", {"summary": summary, "targets": targets})
    return report


@app.websocket("/api/ws/{eid}/terminal")
async def ws_terminal(websocket: WebSocket, eid: str) -> None:
    origin = websocket.headers.get("origin", "")
    allowed = {f"http://{h}:{p}" for h in ("127.0.0.1", "localhost") for p in (config.PORT, 5173)}
    allowed |= {f"https://{h}" for h in config.PUBLIC_HOSTS}
    if origin not in allowed or not _host_ok(websocket.headers.get("host")):
        await websocket.close(code=4403)
        return
    ws = Workspace(eid)
    if not ws.exists():
        await websocket.close(code=4404)
        return
    await websocket.accept()
    cols = int(websocket.query_params.get("cols", 100))
    rows = int(websocket.query_params.get("rows", 30))
    session = TerminalSession(
        ws.root, ws.repo, cols=cols, rows=rows,
        on_command=lambda cmd: (E.log_event(eid, _active_task_id(eid), "terminal", {"command": cmd[:300]}),
                                persist.mark_dirty(eid)),
    )

    async def send(text: str) -> None:
        await websocket.send_text(text)

    pump = asyncio.create_task(session.pump(send))
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if msg.get("t") == "i":
                session.write(str(msg.get("d", "")))
            elif msg.get("t") == "r":
                session.resize(int(msg.get("c", 100)), int(msg.get("r", 30)))
    except WebSocketDisconnect:
        pass
    finally:
        session.close()
        pump.cancel()
        persist.mark_dirty(eid)


# --- learning views ------------------------------------------------------------------------------

@app.get("/api/atlas")
async def atlas() -> dict[str, Any]:
    cur = curriculum.load()
    ms = scheduler.all_mastery()
    journal = db.all_("SELECT id, case_id, concept_ids, title, lesson, created_at FROM journal ORDER BY created_at")
    by_concept: dict[str, list[dict[str, Any]]] = {}
    for j in journal:
        for cid in db.loads(j["concept_ids"], []):
            by_concept.setdefault(cid, []).append({"journal_id": j["id"], "title": j["title"],
                                                   "lesson": j["lesson"], "when": j["created_at"]})
    concepts = []
    for c in cur.concepts.values():
        m = ms.get(c.id, {})
        concepts.append({
            **c.to_dict(),
            "state": m.get("state", "fog"),
            "attempts": m.get("attempts", 0),
            "successes": m.get("successes", 0),
            "due": m.get("due"),
            "last_seen": m.get("last_seen"),
            "journal": by_concept.get(c.id, []),
        })
    return {"regions": cur.regions, "concepts": concepts}


@app.get("/api/journal")
async def journal() -> dict[str, Any]:
    rows = db.all_("SELECT * FROM journal ORDER BY created_at DESC")
    cur = curriculum.load()
    for r in rows:
        r["concept_ids"] = db.loads(r["concept_ids"], [])
        r["concepts"] = [{"id": c, "name": cur.concepts[c].name, "region": cur.concepts[c].region}
                         for c in r["concept_ids"] if c in cur.concepts]
        try:
            case = E.load_case(r["case_id"])
            r["company"] = case["company"]["name"]
            r["subject"] = case["card"]["subject"]
        except E.EngagementError:
            r["company"] = r["subject"] = None
    return {"entries": rows}


@app.put("/api/journal/{entry_id}")
async def journal_update(entry_id: int, body: dict = Body(...)) -> dict[str, Any]:
    db.run("UPDATE journal SET lesson = ? WHERE id = ?", str(body.get("lesson", ""))[:4000], entry_id)
    return {"ok": True}


@app.post("/api/recall/{entry_id}")
async def recall(entry_id: int, body: dict = Body(...)) -> dict[str, Any]:
    row = db.one("SELECT recall_interval FROM journal WHERE id = ?", entry_id)
    if not row:
        raise HTTPException(404)
    interval = row["recall_interval"] * 2.5 if body.get("remembered") else 1.0
    interval = min(120.0, interval)
    db.run("UPDATE journal SET recall_interval = ?, recall_due = ? WHERE id = ?",
           interval, time.time() + interval * 86400, entry_id)
    return {"next_in_days": interval, "next": _due_recall()}


@app.get("/api/progress")
async def progress() -> dict[str, Any]:
    rows = db.all_("SELECT e.id, e.case_id, e.started_at, e.status FROM engagements e "
                   "WHERE e.status IN ('done', 'active') ORDER BY e.started_at")
    out = []
    for e in rows:
        try:
            case = E.load_case(e["case_id"])
        except E.EngagementError:
            continue
        tasks = E.tasks_for(e["id"])

        def res(kind: str) -> dict[str, Any]:
            t = tasks.get(kind)
            return (t or {}).get("result") or {}

        out.append({
            "id": e["id"],
            "when": e["started_at"],
            "company": case["company"]["name"],
            "domain": case["card"].get("domain"),
            "level": case["spec"]["level"],
            "loc": case["repo"]["stats"]["loc"],
            "files": case["repo"]["stats"]["py_files"],
            "recon_accuracy": res("recon").get("accuracy"),
            "recon_seconds": res("recon").get("seconds"),
            "incident": {k: res("incident").get(k) for k in ("outcome", "seconds", "par_seconds",
                                                             "time_to_root_file", "hints_used")}
            if tasks.get("incident", {}).get("status") in ("passed", "revealed", "failed") else None,
            "feature": {k: res("feature").get(k) for k in ("outcome", "seconds", "par_seconds", "hints_used")}
            if tasks.get("feature", {}).get("status") in ("passed", "revealed", "failed") else None,
        })
    return {"engagements": out, "calendar": _calendar(365), "learner": scheduler.learner()}


@app.get("/api/playbook")
async def playbook_list() -> list[dict[str, Any]]:
    return [{k: a[k] for k in ("slug", "title", "summary", "order")} for a in curriculum.playbook()]


@app.get("/api/playbook/{slug}")
async def playbook_article(slug: str) -> dict[str, Any]:
    for a in curriculum.playbook():
        if a["slug"] == slug:
            return a
    raise HTTPException(404)


# --- drills ---------------------------------------------------------------------------------------

_drill_task: asyncio.Task | None = None


def _top_up_drills() -> None:
    global _drill_task
    if drills.pending() >= 3 or (_drill_task and not _drill_task.done()):
        return

    async def run() -> None:
        try:
            await drills.generate_batch(6)
        except Exception as err:  # noqa: BLE001
            log.warning("drill generation failed: %s", err)

    _drill_task = asyncio.create_task(run())


@app.get("/api/drills/next")
async def drill_next() -> dict[str, Any]:
    _top_up_drills()
    return {"drill": drills.next_drill(), "generating": bool(_drill_task and not _drill_task.done()),
            "stats": drills.stats()}


@app.post("/api/drills/{drill_id}/answer")
async def drill_answer(drill_id: int, body: dict = Body(...)) -> dict[str, Any]:
    try:
        result = drills.answer(drill_id, str(body.get("answer", "")))
    except ValueError as err:
        raise HTTPException(404, str(err)) from err
    _top_up_drills()
    return result


# --- settings & spend -------------------------------------------------------------------------

@app.get("/api/settings")
async def get_settings() -> dict[str, Any]:
    return {"settings": db.settings(), "presets": config.MODEL_PRESETS, "learner": scheduler.learner(),
            "spend": llm.spend_summary(), "budget": await llm.key_status(force=True),
            "sandbox": db.kv_get("sandbox_selfcheck") if sandbox.JAIL else None}


@app.put("/api/settings")
async def put_settings(body: dict = Body(...)) -> dict[str, Any]:
    allowed = {"models", "buffer_size", "auto_generate", "budget_floor_usd", "daily_budget_usd",
               "default_plan", "timer_mode", "mentor_name", "sound", "coach_nudges"}
    patch = {k: v for k, v in body.items() if k in allowed}
    if "level" in body:
        scheduler.set_level(float(body["level"]))
    s = db.update_settings(patch)
    manager.poke()
    return {"settings": s, "learner": scheduler.learner()}


_models_cache: tuple[float, list[dict[str, Any]]] | None = None


@app.get("/api/models")
async def models() -> list[dict[str, Any]]:
    global _models_cache
    if _models_cache and time.time() - _models_cache[0] < 3600:
        return _models_cache[1]
    r = await llm._http().get("/models")
    r.raise_for_status()
    keep = ("anthropic/", "openai/", "google/", "deepseek/", "qwen/", "moonshotai/", "z-ai/", "x-ai/", "mistralai/")
    out = []
    for m in r.json().get("data", []):
        if not m["id"].startswith(keep) or ":" in m["id"]:
            continue
        p = m.get("pricing") or {}
        out.append({"id": m["id"], "name": m.get("name", m["id"]), "created": m.get("created", 0),
                    "prompt": float(p.get("prompt") or 0) * 1e6, "completion": float(p.get("completion") or 0) * 1e6,
                    "context": m.get("context_length")})
    out.sort(key=lambda m: -m["created"])
    _models_cache = (time.time(), out)
    return out


# --- frontend -------------------------------------------------------------------------------------

if (config.WEB_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=config.WEB_DIST / "assets"), name="assets")


@app.get("/{full_path:path}", include_in_schema=False)
async def spa(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(404)
    candidate = (config.WEB_DIST / full_path).resolve()
    if full_path and candidate.is_file() and config.WEB_DIST.resolve() in candidate.parents:
        return FileResponse(candidate)
    index = config.WEB_DIST / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse({"detail": "frontend not built — run ./coldstart setup"}, status_code=503)
