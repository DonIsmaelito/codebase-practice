"""The learner model and the scheduler that decides what to generate next.

Learning-science levers used here:
- Spaced repetition: each concept has an interval that grows on clean
  successes and resets on failure; due concepts come back in a *new* domain.
- Interleaving: consecutive cases avoid the same concept and region, so the
  learner has to identify which idea applies (the real skill), not just apply
  the one from the chapter they're in.
- Desirable difficulty: the level drifts with outcomes so success stays likely
  but not guaranteed; size, report fidelity and recon mode scale with it.
"""

from __future__ import annotations

import math
import random
import time
from typing import Any

from .. import curriculum, db

DAY = 86_400.0

# level → case parameters. Files/LOC are for non-test code.
LEVELS: dict[int, dict[str, Any]] = {
    1: dict(files=(4, 6), loc=(300, 550), fidelities=["failing_test", "traceback"], hops=1, recon="guided", par=12),
    2: dict(files=(5, 8), loc=(450, 800), fidelities=["failing_test", "traceback", "repro_steps"], hops=1, recon="guided", par=15),
    3: dict(files=(6, 9), loc=(650, 1050), fidelities=["traceback", "repro_steps", "user_report"], hops=2, recon="open", par=18),
    4: dict(files=(8, 11), loc=(850, 1350), fidelities=["repro_steps", "user_report", "logs"], hops=2, recon="open", par=20),
    5: dict(files=(9, 13), loc=(1100, 1700), fidelities=["user_report", "logs", "vague"], hops=2, recon="closed", par=22),
    6: dict(files=(11, 15), loc=(1400, 2100), fidelities=["logs", "vague", "misleading"], hops=3, recon="closed", par=25),
    7: dict(files=(13, 18), loc=(1700, 2600), fidelities=["vague", "misleading", "logs"], hops=3, recon="closed", par=28),
    8: dict(files=(15, 21), loc=(2000, 3100), fidelities=["vague", "misleading"], hops=3, recon="closed", par=30),
    9: dict(files=(17, 24), loc=(2400, 3600), fidelities=["vague", "misleading"], hops=4, recon="closed", par=32),
    10: dict(files=(20, 28), loc=(2800, 4200), fidelities=["vague", "misleading"], hops=4, recon="closed", par=35),
}
RECON_PAR = {"guided": 8, "open": 7, "closed": 6}

VINTAGES = [
    "modern: Python 3.12, dataclasses and type hints throughout, pathlib, small focused modules",
    "pragmatic: mostly typed; some dicts passed around between layers; a utils.py that grew organically",
    "legacy-in-transition: one older module uses dicts/tuples and positional args; newer modules use dataclasses and typed services",
    "OOP-heavy: base classes and a small registry/plugin mechanism; services wired together in one place",
    "functional pipeline style: small pure functions and generators with a thin I/O shell",
]

LIBRARY_WORDS = {
    "pydantic": "pydantic", "fastapi": "fastapi", "sqlalchemy": "sqlalchemy", "pandas": "pandas",
    "numpy": "numpy", "click": "click", "attrs": "attrs", "dateutil": "python-dateutil",
    "jinja": "jinja2", "yaml": "pyyaml", "networkx": "networkx", "httpx": "httpx",
    "hypothesis": "hypothesis", "freezegun": "freezegun",
}
PERF_WORDS = ("complexity", "n-plus-one", "performance", "profiling")

STATES = ["fog", "glimpsed", "practiced", "solid", "mastered"]


# --- learner state ----------------------------------------------------------------

def learner() -> dict[str, Any]:
    state = db.kv_get("learner")
    if not state:
        state = {"level": 1.0, "created_at": time.time()}
        db.kv_set("learner", state)
    return state


def set_level(level: float) -> None:
    state = learner()
    state["level"] = max(1.0, min(10.0, level))
    db.kv_set("learner", state)


def mastery(cid: str) -> dict[str, Any]:
    row = db.one("SELECT data FROM mastery WHERE concept_id = ?", cid)
    base = {"state": "fog", "exposures": 0, "attempts": 0, "successes": 0, "clean": 0,
            "interval_days": 1.0, "due": None, "last_seen": None, "last_success": None,
            "last_outcome": None, "history": []}
    return {**base, **(db.loads(row["data"]) if row else {})}


def all_mastery() -> dict[str, dict[str, Any]]:
    return {r["concept_id"]: {**mastery(r["concept_id"])} for r in db.all_("SELECT concept_id FROM mastery")}


def _save(cid: str, m: dict[str, Any]) -> None:
    m["history"] = m["history"][-30:]
    db.run(
        "INSERT INTO mastery(concept_id, data, updated_at) VALUES(?, ?, ?) "
        "ON CONFLICT(concept_id) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at",
        cid, db.dumps(m), time.time(),
    )


def record_exposure(cid: str, case_id: str) -> dict[str, Any]:
    """The concept showed up in an engagement the learner worked in (not as the target)."""
    m = mastery(cid)
    m["exposures"] += 1
    m["last_seen"] = time.time()
    if m["state"] == "fog":
        m["state"] = "glimpsed"
    m["history"].append({"ts": time.time(), "kind": "exposure", "case_id": case_id})
    _save(cid, m)
    return m


def record_attempt(cid: str, *, kind: str, outcome: str, case_id: str) -> tuple[dict[str, Any], str]:
    """Update a targeted concept after an incident/feature/drill.

    outcome: clean (solved with ≤1 hint) | assisted (solved with more help) |
             revealed (gave up) | failed
    Returns (new mastery, previous state).
    """
    now = time.time()
    m = mastery(cid)
    before = m["state"]
    m["attempts"] += 1
    m["last_seen"] = now
    m["last_outcome"] = outcome
    was_due = m["due"] is not None and m["due"] <= now
    if outcome in ("clean", "assisted"):
        m["successes"] += 1
        if outcome == "clean":
            m["clean"] += 1
        grow = 2.5 if outcome == "clean" else 1.5
        m["interval_days"] = min(90.0, max(1.0, m["interval_days"] * grow))
        spaced = m["last_success"] is None or now - m["last_success"] >= 0.75 * DAY
        m["last_success"] = now
        if STATES.index(m["state"]) < STATES.index("practiced"):
            m["state"] = "practiced"
        if m["state"] == "practiced" and m["successes"] >= 2 and m["clean"] >= 1 and spaced:
            m["state"] = "solid"
        elif m["state"] == "solid" and outcome == "clean" and was_due and m["interval_days"] >= 7:
            m["state"] = "mastered"
    else:
        m["interval_days"] = 1.0
        if m["state"] in ("solid", "mastered"):
            m["state"] = "practiced"
        elif m["state"] == "fog":
            m["state"] = "glimpsed"
    m["due"] = now + m["interval_days"] * DAY
    m["history"].append({"ts": now, "kind": kind, "outcome": outcome, "case_id": case_id})
    _save(cid, m)
    return m, before


def adjust_level(kind: str, outcome: str, *, time_ratio: float | None = None,
                 recon_accuracy: float | None = None) -> float:
    state = learner()
    level = float(state["level"])
    if kind in ("incident", "feature"):
        if outcome == "clean":
            level += 0.5 if (time_ratio or 1) <= 1.1 else 0.3
        elif outcome == "assisted":
            level += 0.1
        else:
            level -= 0.3
    elif kind == "recon" and recon_accuracy is not None:
        if recon_accuracy >= 0.75:
            level += 0.1
        elif recon_accuracy <= 0.25:
            level -= 0.1
    set_level(level)
    return learner()["level"]


# --- spec building -----------------------------------------------------------------

def _recent_specs(limit: int = 25) -> list[dict[str, Any]]:
    rows = db.all_("SELECT spec FROM cases WHERE status != 'failed' ORDER BY created_at DESC LIMIT ?", limit)
    return [db.loads(r["spec"], {}) for r in rows]


def _prereqs_met(c: curriculum.Concept, ms: dict[str, dict[str, Any]]) -> bool:
    return all(ms.get(p, {}).get("state", "fog") in ("practiced", "solid", "mastered") for p in c.prereqs)


def _weight(c: curriculum.Concept, m: dict[str, Any], now: float) -> float:
    state = m.get("state", "fog")
    if state in ("practiced", "solid") and m.get("due") and m["due"] <= now:
        return 3.0  # due for spaced review
    if m.get("last_outcome") in ("revealed", "failed"):
        return 2.5  # recently struggled
    if state == "glimpsed":
        return 2.2
    if state == "fog":
        return 2.0
    if state == "mastered":
        return 0.1
    return 0.3


def pick_concept(role: str, *, level: int, exclude: set[str], recent: list[dict[str, Any]]) -> curriculum.Concept:
    cur = curriculum.load()
    ms = all_mastery()
    now = time.time()
    max_tier = 1 if level <= 2 else 2 if level <= 5 else 3
    recent_targets = [s.get(f"{role}_concept", {}).get("id") for s in recent[:3]]
    recent_regions = [s.get("incident_concept", {}).get("region") for s in recent[:2]]
    pool = []
    for c in cur.concepts.values():
        if c.id in exclude or c.tier > max_tier:
            continue
        if role == "incident" and not c.bug_patterns:
            continue
        if role == "feature" and not c.feature_patterns:
            continue
        if not _prereqs_met(c, ms):
            continue
        w = _weight(c, ms.get(c.id, {}), now)
        if c.id in recent_targets:
            w *= 0.1
        if role == "incident" and c.region in recent_regions:
            w *= 0.5
        if c.tier < max_tier:
            w *= 0.8  # slight pull toward the current frontier once lower tiers are available
        pool.append((c, w))
    if not pool:  # fall back to anything at an allowed tier
        pool = [(c, 1.0) for c in cur.concepts.values()
                if c.tier <= max_tier and c.id not in exclude
                and (c.bug_patterns if role == "incident" else c.feature_patterns)]
    concepts, weights = zip(*pool)
    return random.choices(concepts, weights=weights, k=1)[0]


def pick_domain(targets: list[str], recent: list[dict[str, Any]]) -> curriculum.Domain:
    cur = curriculum.load()
    used = {s.get("domain", {}).get("id") for s in recent[:20]}
    recent_sectors = [s.get("domain", {}).get("sector") for s in recent[:3]]
    pool = []
    for d in cur.domains.values():
        if d.id in used:
            continue
        w = 3.0 if set(d.affinities) & set(targets) else 1.0
        if d.sector in recent_sectors:
            w *= 0.4
        pool.append((d, w))
    if not pool:
        pool = [(d, 1.0) for d in cur.domains.values()]
    domains, weights = zip(*pool)
    return random.choices(domains, weights=weights, k=1)[0]


def _library_for(c: curriculum.Concept) -> str | None:
    text = f"{c.id} {c.name}".lower()
    for word, lib in LIBRARY_WORDS.items():
        if word in text:
            return lib
    return None


def build_spec(*, focus: str | None = None, level_override: int | None = None) -> dict[str, Any]:
    cur = curriculum.load()
    level = level_override or max(1, min(10, int(math.floor(learner()["level"]))))
    params = LEVELS[level]
    recent = _recent_specs()

    if focus and focus in cur.concepts:
        incident = cur.concepts[focus]
    else:
        incident = pick_concept("incident", level=level, exclude=set(), recent=recent)
    feature = pick_concept("feature", level=level, exclude={incident.id}, recent=recent)

    ms = all_mastery()
    flavor_pool = [c for c in cur.concepts.values()
                   if c.id not in (incident.id, feature.id) and c.tier <= max(1, (level + 2) // 3)]
    seen_first = sorted(flavor_pool, key=lambda c: (ms.get(c.id, {}).get("state", "fog") == "fog", random.random()))
    flavor = seen_first[:2] + random.sample(flavor_pool, k=min(1, len(flavor_pool)))
    flavor = list({c.id: c for c in flavor}.values())

    domain = pick_domain([incident.id, feature.id], recent)

    fidelities = list(params["fidelities"])
    if any(w in incident.id for w in PERF_WORDS) and level >= 4:
        fidelities.append("metrics")
    fidelity = random.choice(fidelities)

    libs = [l for l in (_library_for(incident), _library_for(feature)) if l]
    if libs:
        library_hint = f"The codebase MUST use {', '.join(dict.fromkeys(libs))} (a target concept is about it); other third-party packages only if natural."
    elif level <= 2:
        library_hint = "Prefer the standard library; use at most one third-party package, and only if it's clearly natural for this kind of codebase."
    else:
        library_hint = "Use 0-2 third-party packages where they're natural for this kind of codebase."

    vintages = VINTAGES[:2] if level <= 2 else VINTAGES
    return {
        "level": level,
        "domain": {"id": domain.id, "name": domain.name, "sector": domain.sector,
                   "flavor": domain.flavor, "shapes": list(domain.shapes)},
        "incident_concept": incident.to_dict(),
        "feature_concept": feature.to_dict(),
        "flavor_concepts": [c.to_dict() for c in flavor],
        "fidelity": fidelity,
        "hops": params["hops"],
        "recon_mode": params["recon"],
        "files": list(params["files"]),
        "loc": list(params["loc"]),
        "vintage": random.choice(vintages),
        "library_hint": library_hint,
        "par_incident": params["par"],
        "par_recon": RECON_PAR[params["recon"]],
        "focus": focus,
    }
