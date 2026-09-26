"""Drills: one-to-two-minute reps on Python semantics, between engagements.

Two kinds:
- predict: read a short program, type exactly what it prints. The answer is
  the program's REAL output (we execute it in the sandbox), never the model's
  claim about it.
- spot: which line holds the bug? The model's claim is checked by running the
  snippet's own assertion: it must fail as written and pass with the fixed line.

Drills target concepts the learner has already met (spaced review) plus the
occasional frontier concept, and feed the same mastery model lightly.
"""

from __future__ import annotations

import json
import random
import re
import shutil
import time
from typing import Any

from .. import config, curriculum, db, llm, sandbox
from . import scheduler

DRILL_SYSTEM = """You write short, sharp Python drills for Cold Start. Each drill isolates one concept in 5-18 lines of realistic-looking code (names from real domains — invoices, sensors, playlists — never foo/bar). The best drills have one surprising-but-fair twist that separates people who *know* Python semantics from people who guess. No trick questions about formatting, no reliance on dict/set iteration order of hash-randomized strings, no randomness, no time, no I/O."""


def _pick_concepts(n: int) -> list[curriculum.Concept]:
    """Mostly concepts you've met (due ones first), plus a little frontier."""
    cur = curriculum.load()
    ms = scheduler.all_mastery()
    level = scheduler.learner()["level"]
    max_tier = 1 if level < 3 else 2 if level < 6 else 3
    now = time.time()
    weighted: list[tuple[curriculum.Concept, float]] = []
    for c in cur.concepts.values():
        m = ms.get(c.id, {})
        state = m.get("state", "fog")
        if state != "fog":
            weighted.append((c, 5.0 if (m.get("due") or 0) <= now else 3.0))
        elif c.tier <= max_tier and c.region in ("core", "datamodel", "stdlib", "ds", "algo"):
            weighted.append((c, 1.0))
    picks: list[curriculum.Concept] = []
    while weighted and len(picks) < n:
        concepts, weights = zip(*weighted)
        choice = random.choices(concepts, weights=weights)[0]
        picks.append(choice)
        weighted = [(c, w) for c, w in weighted if c.id != choice.id]
    return picks


async def generate_batch(n: int = 6) -> int:
    """Generate and verify a batch of drills. Returns how many were kept."""
    concepts = _pick_concepts(n)
    spec = [{"concept_id": c.id, "name": c.name, "summary": c.summary, "patterns": list(c.bug_patterns[:2]),
             "kind": "predict" if i % 3 != 2 else "spot"} for i, c in enumerate(concepts)]
    prompt = f"""Write one drill per entry below (same order, same kind).

{json.dumps(spec, indent=1)}

For kind "predict": a complete program that PRINTS 1-4 short lines. The learner must type the exact output.
For kind "spot": a complete program containing exactly ONE buggy line relevant to the concept, followed by an `assert` that states the intended behavior (so the assert FAILS as written). Also give the corrected version of that line.

Reply with ONLY a JSON object: {{"drills": [
  {{"concept_id": "...", "kind": "predict", "title": "4-7 word title", "code": "...", "question": "What does this print?", "explanation": "2-4 sentences: why it prints that — the underlying rule", "takeaway": "one-line rule to remember"}},
  {{"concept_id": "...", "kind": "spot", "title": "...", "code": "...", "question": "One line makes the assert fail. Which line, and why?", "bug_line": 7, "fixed_line": "the corrected line, same indentation", "explanation": "...", "takeaway": "..."}}
]}}
Line numbers are 1-based over `code`."""
    data, _ = await llm.complete_json(
        [{"role": "system", "content": DRILL_SYSTEM}, {"role": "user", "content": prompt}],
        role="designer", max_tokens=9000, reasoning="low",
    )
    kept = 0
    for d in data.get("drills", []):
        try:
            verified = await _verify(d)
        except Exception:  # noqa: BLE001 — a bad drill is just dropped
            verified = None
        if verified:
            db.run("INSERT INTO drills(created_at, concept_id, kind, payload) VALUES(?,?,?,?)",
                   time.time(), verified["concept_id"], verified["kind"], db.dumps(verified))
            kept += 1
    return kept


async def _run(code: str) -> sandbox.ProcResult:
    tmp = config.SCRATCH_DIR / f"drill-{time.time_ns()}"
    tmp.mkdir(parents=True)
    try:
        return await sandbox.run_python(code, tmp, timeout=8, filename="drill.py")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


async def _verify(d: dict[str, Any]) -> dict[str, Any] | None:
    code = (d.get("code") or "").strip("\n")
    if not code or d.get("concept_id") not in curriculum.load().concepts:
        return None
    lines = code.splitlines()
    if not 3 <= len(lines) <= 30:
        return None
    if d["kind"] == "predict":
        a, b = await _run(code), await _run(code)
        if a.returncode != 0 or a.stdout != b.stdout or not a.stdout.strip():
            return None
        out = a.stdout.rstrip("\n")
        if len(out.splitlines()) > 6 or len(out) > 300:
            return None
        return {**d, "code": code, "answer": out}
    if d["kind"] == "spot":
        n = int(d.get("bug_line") or 0)
        fixed = d.get("fixed_line")
        if not (1 <= n <= len(lines)) or not fixed:
            return None
        broken = await _run(code)
        if broken.returncode == 0:
            return None  # the assert must fail as written
        patched = lines[:]
        indent = re.match(r"\s*", lines[n - 1]).group(0)
        patched[n - 1] = indent + fixed.strip()
        good = await _run("\n".join(patched))
        if good.returncode != 0:
            return None
        return {**d, "code": code, "bug_line": n, "fixed_line": patched[n - 1]}
    return None


def next_drill() -> dict[str, Any] | None:
    row = db.one("SELECT id, concept_id, kind, payload FROM drills WHERE answered_at IS NULL ORDER BY id LIMIT 1")
    if not row:
        return None
    p = db.loads(row["payload"])
    c = curriculum.load().concepts.get(row["concept_id"])
    return {"id": row["id"], "kind": row["kind"], "title": p.get("title"), "code": p["code"],
            "question": p.get("question"), "concept": {"id": c.id, "name": c.name, "region": c.region} if c else None}


def pending() -> int:
    return db.one("SELECT COUNT(*) AS n FROM drills WHERE answered_at IS NULL")["n"]


def _norm(s: str) -> str:
    return "\n".join(line.rstrip() for line in s.strip().splitlines())


def answer(drill_id: int, given: str) -> dict[str, Any]:
    row = db.one("SELECT * FROM drills WHERE id = ?", drill_id)
    if not row:
        raise ValueError("no such drill")
    p = db.loads(row["payload"])
    if row["kind"] == "predict":
        correct = _norm(given) == _norm(p["answer"])
    else:
        m = re.search(r"\d+", given or "")
        correct = bool(m) and int(m.group(0)) == int(p["bug_line"])
    db.run("UPDATE drills SET answered_at = ?, correct = ?, given = ? WHERE id = ?",
           time.time(), 1 if correct else 0, given[:2000], drill_id)
    scheduler.record_exposure(row["concept_id"], f"drill-{drill_id}")
    return {
        "correct": correct,
        "answer": p.get("answer"),
        "bug_line": p.get("bug_line"),
        "fixed_line": p.get("fixed_line"),
        "explanation": p.get("explanation"),
        "takeaway": p.get("takeaway"),
    }


def stats() -> dict[str, Any]:
    row = db.one("SELECT COUNT(*) AS n FROM drills WHERE answered_at IS NOT NULL AND answered_at > ?",
                 time.time() - 7 * 86400)
    return {"week_answered": row["n"] or 0, "pending": pending()}
