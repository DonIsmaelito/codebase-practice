import time

import pytest

from coldstart import config, db
from coldstart.learning import scheduler


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(config, "LIBRARY_DIR", tmp_path / "library")
    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "ws")
    monkeypatch.setattr(config, "SCRATCH_DIR", tmp_path / "scratch")
    monkeypatch.setattr(db, "_initialized", False)
    if hasattr(db._local, "conn"):
        del db._local.conn
    yield
    if hasattr(db._local, "conn"):
        db._local.conn.close()
        del db._local.conn


def test_state_progression_needs_spaced_clean_success():
    m, before = scheduler.record_attempt("mutable-defaults", kind="incident", outcome="assisted", case_id="c1")
    assert (before, m["state"]) == ("fog", "practiced")
    # A second success the same day doesn't count as spaced practice.
    m, _ = scheduler.record_attempt("mutable-defaults", kind="incident", outcome="clean", case_id="c2")
    assert m["state"] == "practiced"
    # Pretend the last success was two days ago.
    data = scheduler.mastery("mutable-defaults")
    data["last_success"] = time.time() - 2 * 86400
    scheduler._save("mutable-defaults", data)
    m, _ = scheduler.record_attempt("mutable-defaults", kind="incident", outcome="clean", case_id="c3")
    assert m["state"] == "solid"


def test_failure_resets_interval_and_demotes():
    for i, outcome in enumerate(["clean", "clean"]):
        scheduler.record_attempt("dict-semantics", kind="incident", outcome=outcome, case_id=f"c{i}")
    data = scheduler.mastery("dict-semantics")
    data.update(state="solid", interval_days=16)
    scheduler._save("dict-semantics", data)
    m, before = scheduler.record_attempt("dict-semantics", kind="incident", outcome="revealed", case_id="c9")
    assert before == "solid" and m["state"] == "practiced" and m["interval_days"] == 1.0
    assert m["due"] - time.time() == pytest.approx(86400, abs=5)


def test_exposure_only_lifts_fog():
    m = scheduler.record_exposure("enums", "c1")
    assert m["state"] == "glimpsed" and m["attempts"] == 0


def test_level_moves_with_outcomes_and_is_clamped():
    assert scheduler.learner()["level"] == 1.0
    scheduler.adjust_level("incident", "failed")
    assert scheduler.learner()["level"] == 1.0  # clamped at the floor
    scheduler.adjust_level("incident", "clean", time_ratio=0.8)
    assert scheduler.learner()["level"] == 1.5
    scheduler.adjust_level("incident", "assisted")
    assert scheduler.learner()["level"] == pytest.approx(1.6)


def test_first_specs_use_classic_starter_incidents():
    for _ in range(10):
        spec = scheduler.build_spec()
        assert spec["incident_concept"]["id"] in scheduler.STARTER_INCIDENTS
        assert spec["level"] == 1
        assert spec["recon_mode"] == "guided"
        assert spec["fidelity"] in ("failing_test", "traceback")
        assert spec["feature_concept"]["id"] != spec["incident_concept"]["id"]


def test_focus_overrides_incident_choice():
    spec = scheduler.build_spec(focus="ds-heaps", level_override=4)
    assert spec["incident_concept"]["id"] == "ds-heaps"
    assert spec["level"] == 4 and spec["recon_mode"] == "open"


def test_daily_budget_blocks_new_ai_calls():
    import asyncio

    from coldstart import llm

    db.run("INSERT INTO llm_calls(ts, role, model, cost_usd, ok) VALUES(?,?,?,?,?)", time.time(), "designer", "m", 20.0, 1)
    llm._spend_cache = None
    with pytest.raises(llm.LLMError, match="budget"):
        asyncio.run(llm.complete([{"role": "user", "content": "hi"}], role="grader"))
    db.update_settings({"daily_budget_usd": 0})  # 0 turns the cap off
    llm.check_budget()
