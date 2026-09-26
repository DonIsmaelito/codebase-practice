"""The live incident: the people in the thread, the coach, and the expert replay.

The model is mocked; everything else is real — evidence and replay commands
run in the sandbox against a tiny buggy repo, and the thread lives in the DB.
"""

import json
import time
import uuid

import httpx
import pytest

from coldstart import config, db, llm
from coldstart.generation import runner
from coldstart.learning import bg, cast, coach, replay, review
from coldstart.learning import engagements as E

BUGGY = "def total(prices, discount=0):\n    subtotal = sum(prices[1:])\n    return round(subtotal * (1 - discount), 2)\n"
CLEAN = "def total(prices, discount=0):\n    subtotal = sum(prices)\n    return round(subtotal * (1 - discount), 2)\n"
TEAM = [
    {"name": "Priya Raman", "role": "Engineering lead", "voice": "calm, numbered lists"},
    {"name": "Ade Okafor", "role": "Support lead", "voice": "friendly, pastes everything"},
]


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(config, "LIBRARY_DIR", tmp_path / "library")
    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "ws")
    monkeypatch.setattr(config, "SCRATCH_DIR", tmp_path / "scratch")
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(db, "_initialized", False)
    if hasattr(db._local, "conn"):
        del db._local.conn
    llm._spend_cache = None
    bg._jobs.clear()
    bg._failures.clear()
    coach._state.clear()
    cast._pending.clear()
    yield
    llm._client = None
    if hasattr(db._local, "conn"):
        db._local.conn.close()
        del db._local.conn


def make_case() -> str:
    case_id = "c-" + uuid.uuid4().hex[:8]
    d = config.LIBRARY_DIR / case_id
    for tree, pricing in (("repo", BUGGY), ("clean", CLEAN)):
        (d / tree / "shop").mkdir(parents=True)
        (d / tree / "tests").mkdir()
        (d / tree / "shop" / "__init__.py").write_text("")
        (d / tree / "shop" / "pricing.py").write_text(pricing)
        (d / tree / "tests" / "test_pricing.py").write_text(
            "from shop.pricing import total\n\n\ndef test_empty():\n    assert total([]) == 0\n")
        (d / tree / "pyproject.toml").write_text('[tool.pytest.ini_options]\npythonpath = ["."]\n')
    (d / "hidden").mkdir()
    (d / "hidden" / "incident_test.py").write_text(
        "from shop.pricing import total\n\n\ndef test_all():\n    assert total([10, 20]) == 30\n")
    report = {"channel": "slack", "title": "Totals are low", "ask": "Find out why totals are low.",
              "messages": [{"from": "Ade Okafor", "role": "Support lead", "time": "09:40",
                            "body": "Customer says their order total is missing an item."}]}
    meta = {"title": "first item dropped", "symptom": "totals miss an item",
            "root_cause": "total() slices off the first price", "root_cause_file": "shop/pricing.py",
            "root_cause_symbol": "total", "files_involved": ["shop/pricing.py"], "mechanism": "m", "fix": "f",
            "expert_path": [{"step": "read pricing", "why": "it computes totals"}], "hints": ["a", "b", "c", "d"]}
    case = {
        "id": case_id, "company": {"name": "Shopwell", "tagline": "t", "industry": "retail", "blurb": "b", "team": TEAM},
        "repo": {"name": "shopwell", "package": "shop", "summary": "a shop", "shape": "library", "stats": {}},
        "card": {"subject": "Totals are low"}, "concepts": {"incident": "slicing", "feature": "x", "flavor": []},
        "spec": {"level": 1},
        "recon": {"mode": "guided", "par_minutes": 7, "briefing": {}, "tour": [], "questions": [], "map": None},
        "incident": {"report": report, "fidelity": "user_report", "par_minutes": 15, "meta": meta,
                     "bug_edits": [{"path": "shop/pricing.py"}], "bug_diff": "-sum(prices)\n+sum(prices[1:])",
                     "repro": "print(1)", "repro_output": "1", "regression_test": None,
                     "hidden_tests_path": "hidden/incident_test.py"},
        "feature": None, "feature_plan": None,
    }
    (d / "case.json").write_text(json.dumps(case))
    (d / "design.json").write_text(json.dumps({"repo": {"name": "shopwell", "package": "shop", "summary": "a shop",
                                                        "architecture": "shop/pricing.py computes totals"},
                                               "company": case["company"]}))
    db.run("INSERT INTO cases(id, created_at, status, spec) VALUES(?,?,?,?)", case_id, time.time(), "ready", "{}")
    return case_id


def start_incident(case_id: str) -> dict:
    e = E.start(case_id, ["incident"])
    return E.begin_task(e["id"], "incident")


def set_active(task_id: str, seconds: float) -> dict:
    db.run("UPDATE tasks SET active_seconds = ? WHERE id = ?", seconds, task_id)
    return E.task(task_id)


CAST = {
    "people": [{"name": "Priya Raman", "role": "Engineering lead", "knows": "the system", "stance": "no idea"},
               {"name": "Ade Okafor", "role": "Support lead", "knows": "customers", "stance": "a UI bug?"}],
    "facts": [{"id": "f1", "who": "Ade Okafor", "topic": "scope", "fact": "every order is short", "value": "clue"}],
    "evidence": [
        {"id": "ev1", "who": "Ade Okafor", "offer": "a staging run",
         "script": "from shop.pricing import total\nprint('order 42 total:', total([10, 20, 30]))\n", "expected": False},
        {"id": "ev2", "who": "Priya Raman", "offer": "what it should be",
         "script": "from shop.pricing import total\nprint('expected:', total([10, 20, 30]))\n", "expected": True},
        {"id": "ev3", "who": "Priya Raman", "offer": "logs", "script": "import shop.logging_nope\n", "expected": False},
    ],
    "beats": [
        {"id": "b1", "at_minute": 3, "who": "Ade Okafor", "kind": "new_info", "body": "Another one just came in:\n{{ev1}}"},
        {"id": "b2", "at_minute": 6, "who": "Priya Raman", "kind": "status_check", "body": "Where are we?"},
        {"id": "b3", "at_minute": 8, "who": "Priya Raman", "kind": "new_info", "body": "Logs:\n{{ev3}}"},
    ],
    "resolution": {"fixed": {"who": "Priya Raman", "body": "Confirmed fixed — two lines for the log?"},
                   "not_fixed": {"who": "Priya Raman", "body": "We'll take it from here."}},
}


# --- a scripted OpenRouter ---------------------------------------------------------------------

def sse(text: str) -> httpx.Response:
    chunks = [{"choices": [{"delta": {"content": text}}]},
              {"choices": [{"delta": {}, "finish_reason": "stop"}],
               "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.001}}]
    body = b"".join(f"data: {json.dumps(c)}\n\n".encode() for c in chunks) + b"data: [DONE]\n\n"
    return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})


def all_text(request: httpx.Request) -> str:
    body = json.loads(request.content)
    out = []
    for m in body["messages"]:
        content = m["content"]
        out.append(content if isinstance(content, str) else " ".join(p.get("text", "") for p in content))
    return "\n".join(out)


class FakeRouter:
    def __init__(self, **answers):
        self.answers = answers  # marker text in the prompt -> reply text (or a list, consumed in order)
        self.seen: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        text = all_text(request)
        self.seen.append(text)
        for marker, reply in self.answers.items():
            if marker in text:
                if isinstance(reply, list):
                    reply = reply.pop(0) if len(reply) > 1 else reply[0]
                if isinstance(reply, httpx.Response):
                    return reply
                return sse(reply if isinstance(reply, str) else json.dumps(reply))
        raise AssertionError(f"unexpected prompt: {text[-400:]}")

    def install(self):
        llm._client = httpx.AsyncClient(base_url=config.OPENROUTER_BASE, transport=httpx.MockTransport(self))
        return self


async def finish(key: str) -> None:
    job = bg._jobs.get(key)
    if job:
        await job


# --- the cast ----------------------------------------------------------------------------------

async def test_cast_evidence_really_runs_and_beats_needing_broken_evidence_are_dropped():
    case_id = make_case()
    FakeRouter(**{"Bring the people in this incident thread to life": CAST}).install()
    result = await cast.generate(case_id)
    outputs = {e["id"]: e["output"] for e in result["evidence"]}
    assert outputs == {"ev1": "order 42 total: 50", "ev2": "expected: 60"}  # ev3 couldn't import: dropped
    assert [b["id"] for b in result["beats"]] == ["b1", "b2"]
    assert cast.load(case_id)["evidence"][0]["output"] == "order 42 total: 50"


async def test_beats_arrive_on_the_clock_and_the_lead_doesnt_ask_right_after_an_update():
    case_id = make_case()
    t = start_incident(case_id)
    (config.LIBRARY_DIR / case_id / "cast.json").write_text(json.dumps(
        {**CAST, "evidence": [{"id": "ev1", "who": "Ade Okafor", "offer": "o", "output": "order 42 total: 50"}],
         "beats": CAST["beats"][:2]}))
    cast.tick(set_active(t["id"], 120), case_id)
    assert cast.messages(t["id"]) == []
    cast.tick(set_active(t["id"], 200), case_id)
    [beat] = cast.messages(t["id"])
    assert beat["author"] == "Ade Okafor" and beat["kind"] == "beat"
    assert "```\norder 42 total: 50\n```" in beat["body"]
    cast._add(t, "You", "Contractor", "Looking at pricing now, update soon.", "learner")
    cast.tick(set_active(t["id"], 400), case_id)
    kinds = [m["kind"] for m in cast.messages(t["id"])]
    assert kinds == ["beat", "learner"]  # the status check was skipped, and stays skipped
    cast.tick(set_active(t["id"], 500), case_id)
    assert len(cast.messages(t["id"])) == 2


async def test_a_question_gets_an_in_character_reply_with_real_output_attached():
    case_id = make_case()
    t = start_incident(case_id)
    (config.LIBRARY_DIR / case_id / "cast.json").write_text(json.dumps(
        {**CAST, "evidence": [{"id": "ev1", "who": "Ade Okafor", "offer": "o", "output": "order 42 total: 50"}]}))
    router = FakeRouter(**{"voicing the people in a live incident thread": {
        "replies": [{"from": "Ade Okafor", "body": "Ran it on staging:", "evidence": "ev1"}]}}).install()
    posted = cast.post(t["id"], "Does it happen for every order? Can you run order 42?")
    assert posted["author"] == "You"
    await finish(f"reply:{t['id']}")
    reply = cast.messages(t["id"])[-1]
    assert reply["author"] == "Ade Okafor" and reply["author_role"] == "Support lead"
    assert reply["body"].endswith("```\norder 42 total: 50\n```")
    prompt = router.seen[-1]
    assert "Can you run order 42?" in prompt and "NOBODY in the thread knows this" in prompt
    assert "messaged the team" in review._timeline(t["id"], t["started_at"])


async def test_a_failed_reply_is_reported_and_can_be_retried():
    case_id = make_case()
    t = start_incident(case_id)
    (config.LIBRARY_DIR / case_id / "cast.json").write_text(json.dumps({**CAST, "evidence": []}))
    FakeRouter(**{"voicing the people": [
        httpx.Response(402, json={"error": {"message": "in_flight_budget_exhausted"}}),
        {"replies": [{"from": "Priya Raman", "body": "Every order, as far as we can tell."}]},
    ]}).install()
    cast.post(t["id"], "Is it every order?")
    await finish(f"reply:{t['id']}")
    assert "out of credits" in cast.reply_error(t["id"])
    cast.retry(t["id"])
    await finish(f"reply:{t['id']}")
    assert cast.reply_error(t["id"]) is None
    assert cast.messages(t["id"])[-1]["body"] == "Every order, as far as we can tell."


def test_resolution_closes_the_loop_once():
    case_id = make_case()
    t = start_incident(case_id)
    (config.LIBRARY_DIR / case_id / "cast.json").write_text(json.dumps(CAST))
    db.run("UPDATE tasks SET status = 'passed' WHERE id = ?", t["id"])
    cast.resolve(t["id"])
    cast.resolve(t["id"])
    [msg] = cast.messages(t["id"])
    assert msg["kind"] == "resolution" and "two lines for the log" in msg["body"]


# --- the coach ---------------------------------------------------------------------------------

async def test_coach_checks_in_after_five_stuck_minutes_and_backs_off_on_progress():
    case_id = make_case()
    t = start_incident(case_id)
    router = FakeRouter(**{"COACH CHECK-IN": "What does the report say is *missing* from the total?"}).install()
    coach.tick(set_active(t["id"], 100), case_id)            # still reading the brief
    coach.tick(set_active(t["id"], 330), case_id)            # only 230s without progress
    assert not bg.running(f"nudge:{t['id']}") and not router.seen
    coach.tick(set_active(t["id"], 420), case_id)            # 320s stuck → check in
    await finish(f"nudge:{t['id']}")
    [nudge] = coach.nudges(t["id"])
    assert nudge["content"].startswith("What does the report say")
    assert "check-in #1" in router.seen[-1]
    history = [m["role"] for m in E.db.all_("SELECT role FROM chat WHERE task_id = ?", t["id"])]
    assert history == ["nudge"]
    E.log_event(t["engagement_id"], t["id"], "edit", {"path": "shop/pricing.py"})
    coach.tick(set_active(t["id"], 800), case_id)            # the edit reset the clock
    assert not bg.running(f"nudge:{t['id']}")
    coach.tick(set_active(t["id"], 1150), case_id)           # stuck again → second check-in
    await finish(f"nudge:{t['id']}")
    assert len(coach.nudges(t["id"])) == 2 and "check-in #2" in router.seen[-1]


async def test_coach_skips_when_the_learner_looks_on_track():
    case_id = make_case()
    t = start_incident(case_id)
    FakeRouter(**{"COACH CHECK-IN": "SKIP"}).install()
    coach.tick(set_active(t["id"], 10), case_id)
    coach.tick(set_active(t["id"], 400), case_id)
    await finish(f"nudge:{t['id']}")
    assert coach.nudges(t["id"]) == []
    assert coach._state[t["id"]]["skip_until"] >= 400 + coach.SKIP_BACKOFF


def test_coach_respects_the_setting():
    case_id = make_case()
    t = start_incident(case_id)
    db.update_settings({"coach_nudges": False})
    coach.tick(set_active(t["id"], 10), case_id)
    coach.tick(set_active(t["id"], 900), case_id)
    assert t["id"] not in coach._state


# --- the replay --------------------------------------------------------------------------------

REPLAY = {
    "takeaway": "Compare what's missing with what's sliced.",
    "steps": [
        {"kind": "think", "say": "One item is missing from every total. Something drops an element.", "at": 0},
        {"kind": "search", "query": "def total", "say": "Where are totals computed?", "at": 15},
        {"kind": "read", "path": "shop/pricing.py", "anchor": "subtotal = sum(prices[1:])", "lines": 2,
         "say": "The slice starts at 1.", "at": 30},
        {"kind": "run", "command": "python -c \"from shop.pricing import total; print(total([10, 20, 30]))\"",
         "say": "Reproduce with three prices.", "at": 50},
        {"kind": "run", "command": "python -m shop.nope", "say": "Run the checker.", "at": 70},
        {"kind": "fix", "say": "Sum the whole list.", "at": 90},
        {"kind": "verify", "command": "python -c \"from shop.pricing import total; print(total([10, 20, 30]))\"",
         "say": "Now it's 60.", "at": 110},
    ],
}


async def test_replay_runs_commands_for_real_and_repairs_broken_ones():
    case_id = make_case()
    t = start_incident(case_id)
    router = FakeRouter(**{
        "didn't run as intended": {"steps": [{"index": 4, "kind": "run", "command": "pytest -q tests/test_pricing.py"}]},
        "Script a screen recording": REPLAY,
    }).install()
    result = await replay.generate(case_id)
    steps = {i: s for i, s in enumerate(result["steps"])}
    assert steps[1]["hits"] == [{"path": "shop/pricing.py", "line": 1, "text": "def total(prices, discount=0):"}]
    assert (steps[2]["line"], steps[2]["end_line"]) == (2, 3)
    assert steps[3]["output"] == "50"
    assert "1 passed" in steps[4]["output"]                   # repaired with the real error in hand
    assert "No module named" in router.seen[-1]
    assert steps[5]["diff"] and "+    subtotal = sum(prices)" in steps[5]["diff"]
    assert steps[6]["output"] == "60"                         # verified against the fixed code

    with pytest.raises(E.EngagementError):
        replay.payload(t["id"])                               # not before the incident is done
    E.log_event(t["engagement_id"], t["id"], "open_file", {"path": "shop/pricing.py"}, ts=t["started_at"] + 200)
    db.run("UPDATE tasks SET status = 'passed', active_seconds = 600 WHERE id = ?", t["id"])
    view = replay.payload(t["id"])
    read = next(s for s in view["steps"] if s["kind"] == "read")
    assert read["you_at"] == pytest.approx(200, abs=1)
    assert view["files"]["shop/pricing.py"] == BUGGY and view["fixed"]["shop/pricing.py"] == CLEAN
    assert view["your_seconds"] == 600


def test_command_parsing_is_limited_to_python_and_pytest():
    assert runner._argv("pytest -q tests")[1:] == ["-m", "pytest", "-p", "no:cacheprovider", "--color=no", "-q", "tests"]
    assert runner._argv("python -m pytest -x")[1:4] == ["-m", "pytest", "-p"]
    assert runner._argv('python -c "print(1)"')[1:] == ["-c", "print(1)"]
    with pytest.raises(runner.CommandError):
        runner._argv("rm -rf /")
    assert runner.looks_broken("ModuleNotFoundError: No module named 'x'")
    assert not runner.looks_broken("order 42 total: 50")
