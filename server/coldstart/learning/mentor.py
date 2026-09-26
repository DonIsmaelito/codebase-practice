"""The mentor: a senior engineer who pairs with the learner, Socratically.

The codebase goes in a cached block so a whole conversation pays for it once;
live context (open file, cursor, diff, recent activity) rides along with each
new question.
"""

from __future__ import annotations

import json
import time
from typing import Any, AsyncIterator

from .. import db, llm
from ..generation import files as F
from ..runtime.workspace import Workspace
from . import engagements as E
from . import review


def _system(case: dict[str, Any], t: dict[str, Any], name: str, level: float) -> str:
    kind = t["kind"]
    company = case["company"]["name"]
    if kind == "incident":
        meta = case["incident"]["meta"]
        secret = f"""THE ANSWER (never reveal unless the learner explicitly asks you to give it away):
root cause: {meta.get('root_cause')}
location: {meta.get('root_cause_file')} :: {meta.get('root_cause_symbol')}
fix: {meta.get('fix')}
expert path: {json.dumps(meta.get('expert_path'))}"""
        task = f"Investigating an incident. The report:\n{json.dumps(case['incident']['report'], indent=1)}"
    elif kind == "feature" and case.get("feature"):
        feat = case["feature"]
        secret = f"""REFERENCE APPROACH (don't write their code for them):
{(E.case_dir(case['id']) / 'feature' / 'reference.diff').read_text()[:6000]}
review focus: {json.dumps(feat['meta'].get('review_focus'))}"""
        task = f"Implementing a feature ticket:\n{json.dumps({'title': feat['title'], **feat['ticket']}, indent=1)}"
    else:
        secret = f"(Recon: help them build a mental model; don't answer the recon questions for them. Questions: {json.dumps([q['prompt'] for q in case['recon']['questions']])})"
        task = "Onboarding recon: exploring the codebase to build a mental model before any incident arrives."
    beginner = level < 3
    return f"""You are {name}, a senior engineer at the contracting firm, pairing with a contractor who has just been dropped into {company}'s codebase. You are an exceptional teacher of Python and of the craft of working in unfamiliar code.

HOW YOU TEACH
- Socratic by default: help them find it. Ask one sharp question, point them at evidence (a line in the report, a file, a search to run, a test to write), or explain a concept — rather than handing over the answer.
- Short replies (2-6 sentences) unless they ask you to explain a concept; then teach it properly with a tiny runnable example.
- Explaining Python semantics, library behavior, pytest/terminal/debugger usage, how to read a traceback — always welcome and never a spoiler.
- Model good process: reproduce first, form a hypothesis and test it, read the tests, search for the exact string, go to definition, follow the data.
- If they explicitly ask for the answer ("just tell me", "I give up", "what's the bug?"), give the mechanism-level explanation clearly (what goes wrong and where), and mention the Reveal button in the side panel if they want the full reference fix.
- Warm, direct, no flattery, no filler. {'They are new to unfamiliar codebases: be encouraging and more concrete — name the file to open next when they are lost for a while.' if beginner else 'They are fairly experienced: keep nudges minimal.'}
- Refer to files as `path/to/file.py` and symbols as `name`. Code snippets in ```python fences.

CURRENT TASK
{task}

{secret}"""


def _codebase_block(case: dict[str, Any]) -> str:
    files = F.read_repo(E.case_dir(case["id"]) / "repo")
    return (f"<company>{json.dumps({k: case['company'].get(k) for k in ('name', 'tagline', 'blurb', 'team')})}</company>\n"
            f"<codebase note=\"as it was when the contractor arrived\">\n{F.render_repo(files)}\n</codebase>")


def history(task_id: str) -> list[dict[str, Any]]:
    return db.all_("SELECT role, content, ts FROM chat WHERE task_id = ? ORDER BY id", task_id)


def _live_context(ws: Workspace, task_id: str, t: dict[str, Any], ctx: dict[str, Any]) -> str:
    parts = []
    elapsed = int((t["active_seconds"] or 0) // 60)
    parts.append(f"[{elapsed} active minutes into the task; hints taken: {t['hints_used']}]")
    if ctx.get("file"):
        line = ctx.get("line")
        parts.append(f"[they have `{ctx['file']}` open{f', cursor on line {line}' if line else ''}]")
        if ctx.get("selection"):
            parts.append(f"[selected text]\n```\n{ctx['selection'][:1500]}\n```")
    diff = ws.diff(task_id)
    if diff:
        parts.append(f"[their changes so far]\n```diff\n{diff[:5000]}\n```")
    seen = E.hints_seen(task_id)
    if seen:
        parts.append("[hints they've already seen]\n" + "\n".join(f"- {h}" for h in seen))
    recent = review._timeline(task_id, t["started_at"]).splitlines()[-8:]
    if recent:
        parts.append("[recent activity]\n" + "\n".join(recent))
    return "\n".join(parts)


async def chat(task_id: str, message: str, ctx: dict[str, Any]) -> AsyncIterator[str]:
    t = E.task(task_id)
    e = E.get(t["engagement_id"])
    case = E.load_case(e["case_id"])
    settings = db.settings()
    from . import scheduler

    ws = Workspace(e["id"])
    ws.exists()  # restores from storage after a restart
    past = history(task_id)[-16:]
    messages: list[llm.Message] = [
        {"role": "system", "content": _system(case, t, settings.get("mentor_name", "Sam"), scheduler.learner()["level"])},
        {"role": "user", "content": [llm.cached(_codebase_block(case))]},
        {"role": "assistant", "content": "I've read through the codebase. What are you looking at?"},
    ]
    for m in past:
        # The coach's check-ins were the mentor speaking unprompted.
        messages.append({"role": "assistant" if m["role"] == "nudge" else m["role"], "content": m["content"]})
    live = _live_context(ws, task_id, t, ctx)
    messages.append({"role": "user", "content": f"{live}\n\n{message}"})

    db.run("INSERT INTO chat(engagement_id, task_id, ts, role, content) VALUES(?,?,?,?,?)",
           e["id"], task_id, time.time(), "user", message)
    E.log_event(e["id"], task_id, "chat", {"message": message[:300]})
    reply: list[str] = []
    try:
        async for piece in llm.stream(messages, role="mentor", max_tokens=1500, case_id=case["id"]):
            reply.append(piece)
            yield piece
    finally:
        text = "".join(reply).strip()
        if text:
            db.run("INSERT INTO chat(engagement_id, task_id, ts, role, content) VALUES(?,?,?,?,?)",
                   e["id"], task_id, time.time(), "assistant", text)
