"""The expert replay: watch a senior engineer work the incident you just finished.

After the learner has struggled with an incident themselves (the order
matters — the replay lands because they know where they got stuck), they can
watch it the way an expert would do it: files open and lines light up,
searches and commands run with their real output, and a caption narrates the
thinking. Each step shows when the learner reached the same point, if at all.

Written once per case, lazily when an incident is finished, and stored with
the case. Commands really run in the jail — against the buggy code, and the
final verification against the fixed code.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from .. import config, llm, persist
from ..generation import files as F
from ..generation import prompts as P
from ..generation import runner
from . import bg
from . import engagements as E

log = logging.getLogger("coldstart.replay")

KINDS = ("read", "search", "run", "think", "fix", "verify")
MAX_OUTPUT = 4000


def _path(case_id: str) -> Path:
    return config.LIBRARY_DIR / case_id / "replay.json"


def load(case_id: str) -> dict[str, Any] | None:
    E.case_dir(case_id)  # restores the case bundle after a restart
    path = _path(case_id)
    return json.loads(path.read_text()) if path.exists() else None


def status(case_id: str) -> str:
    if _path(case_id).exists():
        return "ready"
    if bg.running(f"replay:{case_id}"):
        return "generating"
    if bg.error(f"replay:{case_id}"):
        return "failed"
    return "none"


def ensure(case_id: str) -> str:
    current = status(case_id)
    if current != "ready" and bg.spawn(f"replay:{case_id}", lambda: generate(case_id), retry_after=120):
        return "generating"
    return status(case_id)


def error(case_id: str) -> str | None:
    return bg.error(f"replay:{case_id}")


# --- writing it --------------------------------------------------------------------------

class _Ctx:
    def __init__(self, case: dict[str, Any], repo_name: str):
        self.case = case
        self.dir = E.case_dir(case["id"])
        self.repo_name = repo_name
        self.files = F.read_repo(self.dir / "repo")
        self.fix_diff = E._reverse_diff(case)
        self.fixed = {e["path"]: (self.dir / "clean" / e["path"]).read_text()
                      for e in case["incident"]["bug_edits"] if (self.dir / "clean" / e["path"]).exists()}


def _search(files: dict[str, str], query: str) -> list[dict[str, Any]]:
    hits = []
    for path in sorted(files):
        for i, line in enumerate(files[path].splitlines(), start=1):
            if query in line:
                hits.append({"path": path, "line": i, "text": line.strip()[:160]})
                if len(hits) >= 20:
                    return hits
    return hits


async def _realize(step: dict[str, Any], ctx: _Ctx) -> tuple[dict[str, Any] | None, str | None]:
    """Turn a scripted step into a concrete one: resolved lines, real output. (step, why it's broken)"""
    kind = step.get("kind")
    say = str(step.get("say") or "").strip()
    base = {"kind": kind, "say": say, "at": step.get("at")}
    if kind not in KINDS or not say:
        return None, None
    if kind == "read":
        try:
            path = F.safe_rel(str(step.get("path") or ""))
        except F.EditError:
            return None, f"bad path {step.get('path')!r}"
        content = ctx.files.get(path)
        if content is None:
            return None, f"no file {path!r} in the repo"
        line = F.line_of(content, str(step.get("anchor") or ""))
        span = max(1, min(int(step.get("lines") or 6), 20))
        total = len(content.splitlines())
        return {**base, "path": path, "line": line or 1,
                "end_line": min(total, (line or 1) + span - 1) if line else None}, None
    if kind == "search":
        query = str(step.get("query") or "").strip()
        if not query:
            return None, None
        return {**base, "query": query, "hits": _search(ctx.files, query)}, None
    if kind in ("run", "verify"):
        command = str(step.get("command") or "").strip()
        try:
            res = await runner.run_command(ctx.dir / "repo", command, ctx.repo_name,
                                           overlay=ctx.fixed if kind == "verify" else None)
        except runner.CommandError as err:
            return None, str(err)
        if res.timed_out or runner.looks_broken(res.output):
            return None, res.output[-1500:] or "(no output)"
        return {**base, "command": command, "output": res.output[-MAX_OUTPUT:], "exit_code": res.returncode}, None
    if kind == "fix":
        return {**base, "diff": ctx.fix_diff}, None
    return base, None  # think


async def generate(case_id: str) -> dict[str, Any]:
    case = E.load_case(case_id)
    d = E.case_dir(case_id)
    design = json.loads((d / "design.json").read_text())
    ctx = _Ctx(case, design["repo"]["name"])
    prefix = P.designer_prefix(P.case_context({"level": int(case["spec"]["level"])}, design), F.render_repo(ctx.files))
    msgs = P.with_task(prefix, P.replay_task(case, ctx.fix_diff))
    data, c = await llm.complete_json(msgs, role="designer", max_tokens=12000, reasoning=4000, case_id=case_id)
    scripted = [s for s in data.get("steps") or [] if isinstance(s, dict)]
    realized = await asyncio.gather(*(_realize(s, ctx) for s in scripted))
    steps: list[dict[str, Any] | None] = [r for r, _ in realized]
    broken = [{"index": i, **scripted[i], "real_output": why} for i, (_, why) in enumerate(realized) if why]
    if broken:
        # One repair round with the real error output in hand; anything still broken is dropped.
        fix_msgs = msgs + [{"role": "assistant", "content": c.text}, {"role": "user", "content": P.replay_repair(broken)}]
        try:
            repaired, _ = await llm.complete_json(fix_msgs, role="designer", max_tokens=5000, reasoning=1500,
                                                  case_id=case_id)
            for s in repaired.get("steps") or []:
                i = int(s.get("index", -1)) if str(s.get("index", "")).lstrip("-").isdigit() else -1
                if 0 <= i < len(steps) and steps[i] is None:
                    steps[i], _ = await _realize({**scripted[i], **s}, ctx)
        except llm.LLMError as err:
            log.warning("replay repair for %s failed: %s", case_id, err)
    final = [s for s in steps if s]
    if len(final) < 5 or not any(s["kind"] in ("read", "search") for s in final):
        raise RuntimeError(f"replay too thin ({len(final)} usable steps)")
    last = 0
    for s in final:  # a monotonic expert clock
        at = s.get("at")
        s["at"] = at if isinstance(at, (int, float)) and at >= last else last + 20
        last = s["at"]
    replay = {"version": 1, "steps": final, "takeaway": str(data.get("takeaway") or "")}
    _path(case_id).write_text(json.dumps(replay, indent=2))
    await asyncio.to_thread(persist.upload_case, case_id)
    log.info("replay ready for %s: %d steps", case_id, len(final))
    return replay


# --- watching it ---------------------------------------------------------------------------

def payload(task_id: str) -> dict[str, Any]:
    t = E.task(task_id)
    if t["kind"] != "incident":
        raise E.EngagementError("replays are for incidents")
    if t["status"] not in ("passed", "revealed", "failed"):
        raise E.EngagementError("finish the incident first — the replay gives it away")
    case_id = E.get(t["engagement_id"])["case_id"]
    state = ensure(case_id)
    data = load(case_id) if state == "ready" else None
    if not data:
        return {"status": state, "error": error(case_id) if state == "failed" else None}

    # When did the learner reach the same places? (seconds since their incident started)
    started = t["started_at"] or 0
    first_open: dict[str, float] = {}
    searches: list[tuple[float, str]] = []
    for ev in E.events_for(task_id):
        rel = max(0.0, ev["ts"] - started)
        if ev["kind"] == "open_file":
            first_open.setdefault(ev["data"].get("path", ""), rel)
        elif ev["kind"] == "search":
            searches.append((rel, str(ev["data"].get("query") or "").lower()))
    steps = []
    for s in data["steps"]:
        you = None
        if s["kind"] == "read":
            you = first_open.get(s["path"])
        elif s["kind"] == "search":
            q = s["query"].lower()
            you = next((rel for rel, mine in searches if mine and (mine in q or q in mine)), None)
        steps.append({**s, "you_at": you})
    d = E.case_dir(case_id)
    touched = [e["path"] for e in E.load_case(case_id)["incident"]["bug_edits"]]
    wanted = {s["path"] for s in steps if s["kind"] == "read"} | {h["path"] for s in steps if s["kind"] == "search"
                                                               for h in s["hits"]} | set(touched)
    files = {p: (d / "repo" / p).read_text() for p in sorted(wanted) if (d / "repo" / p).is_file()}
    fixed = {p: (d / "clean" / p).read_text() for p in touched if (d / "clean" / p).is_file()}
    return {
        "status": "ready",
        "steps": steps,
        "takeaway": data.get("takeaway", ""),
        "files": files,
        "fixed": fixed,  # the touched files after the canonical fix, for the fix step's diff
        "expert_seconds": (steps[-1]["at"] + 30) if steps else 0,
        "your_seconds": round(t["active_seconds"] or 0),
    }
