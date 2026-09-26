"""AI grading and debriefs — where most of the learning happens.

Recon answers are graded against reference answers and key points. After an
incident or feature, a reviewer compares the learner's diff, explanation and
investigation timeline against the expert's, like a senior engineer's PR
review plus a coaching note on process.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from .. import db, llm
from ..runtime.workspace import Workspace
from . import engagements as E
from . import scheduler

GRADER_SYSTEM = """You grade answers in Cold Start, a practice gym for navigating unfamiliar Python codebases. You are fair, precise, and encouraging without flattery. A 'correct' answer captures the key points in any wording; 'partial' gets the gist but misses or muddles a key point; 'incorrect' is wrong or empty. Feedback is 1-3 sentences, concrete, and points to where in the code the learner could have confirmed the answer."""

REVIEWER_SYSTEM = """You are a senior engineer reviewing a contractor's work in Cold Start, a practice gym for getting fast at unfamiliar Python codebases. Your review is where they learn the most, so it is specific, honest, and actionable. You praise what was genuinely good, name what wasn't, and always leave them with one concrete habit to try next time. You reference exact files, functions, and lines. No filler, no flattery."""


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s.strip().strip("`").replace('"', "'"))


async def grade_recon(task_id: str, answers: dict[str, str]) -> dict[str, Any]:
    t = E.task(task_id)
    if t["kind"] != "recon":
        raise E.EngagementError("not a recon task")
    if t["status"] != "active":
        raise E.EngagementError("recon isn't active")
    e = E.get(t["engagement_id"])
    case = E.load_case(e["case_id"])
    questions = case["recon"]["questions"]
    payload, results = [], {}
    for q in questions:
        given = (answers.get(q["id"]) or "").strip()
        if q.get("kind") == "predict" and q.get("verified") and given and _norm(given) == _norm(q["answer"]):
            results[q["id"]] = {"id": q["id"], "verdict": "correct", "feedback": "Exactly right."}
            continue
        payload.append({
            "id": q["id"], "kind": q.get("kind"), "question": q["prompt"], "reference_answer": q["answer"],
            "key_points": q.get("key_points", []), "learner_answer": given or "(no answer)",
            **({"note": "The reference answer is the real repr() from executing the code; accept equivalent values/formatting only."}
               if q.get("kind") == "predict" else {}),
        })
    overall = ""
    if payload:
        prompt = f"""Grade the learner's recon answers for {case['company']['name']}'s codebase ({case['repo']['summary']}).

<answers>
{json.dumps(payload, indent=1)}
</answers>

Reply with ONLY JSON:
{{"results": [{{"id": "q1", "verdict": "correct|partial|incorrect", "feedback": "..."}}], "overall": "1-2 sentences on the learner's mental model of this codebase — what they've got, what to firm up"}}"""
        data, _ = await llm.complete_json(
            [{"role": "system", "content": GRADER_SYSTEM}, {"role": "user", "content": prompt}],
            role="grader", max_tokens=3000, case_id=case["id"],
        )
        for r in data.get("results", []):
            if r.get("id") in {p["id"] for p in payload}:
                results[r["id"]] = {"id": r["id"], "verdict": r.get("verdict", "incorrect"), "feedback": r.get("feedback", "")}
        overall = data.get("overall", "")
    ordered = []
    for q in questions:
        r = results.get(q["id"]) or {"id": q["id"], "verdict": "incorrect", "feedback": ""}
        ordered.append({**r, "answer": q["answer"], "given": answers.get(q["id"], "")})
    score = sum({"correct": 1, "partial": 0.5}.get(r["verdict"], 0) for r in ordered)
    accuracy = score / max(1, len(ordered))
    level = scheduler.adjust_level("recon", "", recon_accuracy=accuracy)
    result = {
        "results": ordered, "overall": overall, "accuracy": accuracy,
        "seconds": round(t["active_seconds"]), "map": case["recon"]["map"], "level_after": level,
    }
    E._finish(task_id, "passed", result)
    E.log_event(e["id"], task_id, "recon_graded", {"accuracy": accuracy})
    return result


def _timeline(task_id: str, started_at: float | None) -> str:
    lines = []
    last_open = None
    for ev in E.events_for(task_id):
        rel = int(ev["ts"] - (started_at or ev["ts"]))
        stamp = f"{rel // 60:02d}:{rel % 60:02d}"
        d = ev["data"]
        k = ev["kind"]
        if k == "open_file":
            if d.get("path") == last_open:
                continue
            last_open = d.get("path")
            lines.append(f"{stamp} opened {d.get('path')}")
        elif k == "search":
            lines.append(f"{stamp} searched {d.get('query')!r}")
        elif k == "definition":
            lines.append(f"{stamp} go-to-definition {d.get('name') or ''} → {d.get('target')}")
        elif k == "run_tests":
            lines.append(f"{stamp} ran tests: {d.get('summary', '')}")
        elif k == "terminal":
            lines.append(f"{stamp} $ {d.get('command', '')[:120]}")
        elif k == "hint":
            lines.append(f"{stamp} took hint #{d.get('level')}")
        elif k == "chat":
            lines.append(f"{stamp} asked mentor: {d.get('message', '')[:140]!r}")
        elif k == "edit":
            lines.append(f"{stamp} first edit to {d.get('path')}")
        elif k == "submit":
            verdict = "passed" if d.get("passed") else f"{d.get('failed', '?')} failing"
            lines.append(f"{stamp} submitted ({verdict})")
        elif k == "hypothesis":
            lines.append(f"{stamp} wrote hypothesis: {d.get('text', '')[:200]!r}")
        elif k == "reveal":
            lines.append(f"{stamp} revealed the solution")
    return "\n".join(lines[-80:]) or "(no activity recorded)"


async def debrief(task_id: str, explanation: str) -> dict[str, Any]:
    t = E.task(task_id)
    if t["status"] not in ("passed", "revealed", "failed"):
        raise E.EngagementError("finish the task first")
    if t["result"] and t["result"].get("review"):
        return t["result"]
    e = E.get(t["engagement_id"])
    case = E.load_case(e["case_id"])
    ws = Workspace(e["id"])
    learner_diff = ws.diff(task_id) or "(no changes)"
    timeline = _timeline(task_id, t["started_at"])
    result = dict(t["result"] or {})
    minutes = round((t["active_seconds"] or 0) / 60, 1)

    if t["kind"] == "incident":
        sol = E.incident_solution(case)
        prompt = f"""Debrief the contractor's work on this incident at {case['company']['name']}.

<incident>
report: {json.dumps(case['incident']['report'])}
root cause: {sol['root_cause']} ({sol['root_cause_file']} :: {sol['root_cause_symbol']})
mechanism: {sol['mechanism']}
canonical fix:
{sol['fix_diff']}
fix notes: {sol['fix']}
expert path: {json.dumps(sol['expert_path'])}
</incident>

<learner>
outcome: {result.get('outcome')} (hidden tests {'passed' if result.get('passed') else 'did not pass'}); {minutes} active minutes vs par {case['incident']['par_minutes']}; hints used {t['hints_used']}/4; mentor messages {result.get('mentor_messages', 0)}
their one-sentence explanation of the root cause: {explanation.strip() or '(none given)'}
their diff:
{learner_diff[:12000]}
their investigation timeline (mm:ss since the report arrived):
{timeline}
</learner>

Reply with ONLY JSON:
{{
  "explanation_verdict": "correct|partial|incorrect|missing",
  "explanation_feedback": "1-2 sentences",
  "fix_quality": "root-cause|partial|symptom-patch|incorrect|none",
  "fix_review": "markdown bullets (2-5): correctness, edge cases, whether it fixes the cause or patches the symptom, idiomatic Python, consistency with the codebase — cite files/lines",
  "process_review": "markdown, 3-6 sentences: compare their timeline with the expert path. Where did the time go? What evidence in the report did they use or miss? Be specific about moments in the timeline.",
  "strengths": ["1-3 specific things they did well"],
  "next_time": "ONE concrete, actionable technique to try in the next engagement",
  "lesson": "one sentence, second person: the transferable TECHNICAL lesson about the concept at the heart of this bug, phrased so it applies in any codebase (process advice belongs in next_time, not here)"
}}"""
    else:
        sol = E.feature_solution(case)
        feat = case["feature"]
        prompt = f"""Review the contractor's implementation of this feature ticket at {case['company']['name']} like a senior engineer reviewing a pull request.

<ticket>
{feat['title']}
{json.dumps(feat['ticket'], indent=1)}
</ticket>
<review_focus>{json.dumps(sol['review_focus'])}</review_focus>
<reference_implementation>
{sol['reference_diff'][:10000]}
</reference_implementation>

<learner>
outcome: {result.get('outcome')} (tests {'passed' if result.get('passed') else 'did not pass'}); {minutes} active minutes vs par {feat['par_minutes']}; hints {t['hints_used']}/4
their diff:
{learner_diff[:14000]}
timeline:
{timeline}
</learner>

Reply with ONLY JSON:
{{
  "verdict": "ship|ship-with-nits|needs-work",
  "summary": "2-3 sentences",
  "comments": [{{"path": "file", "line": 12, "severity": "blocker|suggestion|nit|praise", "body": "markdown"}}],
  "idioms": ["idiomatic-Python or stdlib tips that apply to THEIR code, each with a tiny before → after"],
  "complexity": "one or two sentences on time/space complexity or data-structure choice, if relevant, else empty",
  "process_review": "2-4 sentences on how they approached it vs the expert path",
  "strengths": ["1-3 specific things done well"],
  "next_time": "ONE concrete, actionable habit for next time",
  "lesson": "one sentence, second person: the transferable TECHNICAL lesson about the concept this feature exercised (process advice belongs in next_time)"
}}
Line numbers in comments refer to the NEW file (the + side of their diff). 3-8 comments; include praise where deserved."""
    review, _ = await llm.complete_json(
        [{"role": "system", "content": REVIEWER_SYSTEM}, {"role": "user", "content": prompt}],
        role="reviewer", max_tokens=6000, reasoning="low", case_id=case["id"],
    )
    result["review"] = review
    result["explanation"] = explanation
    result["learner_diff"] = learner_diff
    result["timeline"] = timeline
    result["solution"] = sol
    result["previous_encounters"] = previous_encounters(case["concepts"][t["kind"]], exclude_case=case["id"])
    result["speed"] = _speed(t, result)
    if review.get("next_time"):
        # Carried into the next engagement: a concrete habit to practice, in context.
        db.kv_set("habit", {"text": review["next_time"], "case_id": case["id"],
                            "company": case["company"]["name"], "ts": time.time()})
    entry_id = _journal_entry(case, t, review)
    result["journal_id"] = entry_id
    E._finish(task_id, t["status"], result)
    return result


def _speed(t: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """This task's pace next to the learner's own history (never a score)."""
    rows = db.all_("SELECT result FROM tasks WHERE kind = ? AND id != ? AND status IN ('passed', 'revealed', 'failed')",
                   t["kind"], t["id"])
    past_root = [r["time_to_root_file"] for r in (db.loads(x["result"], {}) for x in rows) if r.get("time_to_root_file")]
    past_ratio = [r["seconds"] / r["par_seconds"] for r in (db.loads(x["result"], {}) for x in rows)
                  if r.get("seconds") and r.get("par_seconds")]

    def median(xs: list[float]) -> float | None:
        if not xs:
            return None
        xs = sorted(xs)
        mid = len(xs) // 2
        return xs[mid] if len(xs) % 2 else (xs[mid - 1] + xs[mid]) / 2

    return {
        "root_file_seconds": result.get("time_to_root_file"),
        "usual_root_file_seconds": median(past_root[-8:]),
        "par_ratio": (result["seconds"] / result["par_seconds"]) if result.get("seconds") and result.get("par_seconds") else None,
        "usual_par_ratio": median(past_ratio[-8:]),
    }


def previous_encounters(concept_id: str, exclude_case: str) -> list[dict[str, Any]]:
    """Earlier cases where the learner met the same concept — for analogical comparison."""
    rows = db.all_(
        "SELECT j.case_id, j.title, j.lesson, j.created_at FROM journal j "
        "WHERE j.concept_ids LIKE ? AND j.case_id != ? ORDER BY j.created_at DESC LIMIT 3",
        f'%"{concept_id}"%', exclude_case,
    )
    out = []
    for r in rows:
        try:
            case = E.load_case(r["case_id"])
            out.append({"company": case["company"]["name"], "subject": case["card"]["subject"],
                        "lesson": r["lesson"], "when": r["created_at"], "case_id": r["case_id"]})
        except E.EngagementError:
            continue
    return out


def _journal_entry(case: dict[str, Any], t: dict[str, Any], review: dict[str, Any]) -> int:
    kind = t["kind"]
    meta = case["incident"]["meta"] if kind == "incident" else case["feature"]["meta"]
    card = meta.get("concept_card") or {}
    recall = meta.get("recall") or {}
    concept_ids = [case["concepts"][kind]]
    cur = db.run(
        "INSERT INTO journal(created_at, case_id, engagement_id, task_id, concept_ids, title, lesson, snippet,"
        " recall_q, recall_a, recall_due, recall_interval) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        time.time(), case["id"], t["engagement_id"], t["id"], db.dumps(concept_ids),
        card.get("headline") or meta.get("title") or case["card"]["subject"],
        review.get("lesson") or card.get("headline") or "",
        card.get("example"), recall.get("q"), recall.get("a"),
        time.time() + 86_400, 1.0,
    )
    return cur.lastrowid
