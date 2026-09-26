import json

import httpx
import pytest

from coldstart import config, db, llm


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
    yield
    llm._client = None
    if hasattr(db._local, "conn"):
        db._local.conn.close()
        del db._local.conn


def sse(*chunks: dict) -> bytes:
    return b"".join(f"data: {json.dumps(c)}\n\n".encode() for c in chunks) + b"data: [DONE]\n\n"


def mock_openrouter(handler):
    llm._client = httpx.AsyncClient(base_url=config.OPENROUTER_BASE, transport=httpx.MockTransport(handler))


def test_reasoning_budget_forms():
    body = lambda r: llm._body("m", [], max_tokens=10000, temperature=None, reasoning=r, stream=True, json_mode=False)
    assert body(4000)["reasoning"] == {"max_tokens": 4000}
    assert body("low")["reasoning"] == {"effort": "low"}
    assert body("off")["reasoning"] == {"enabled": False}
    assert "reasoning" not in body(None)
    big = lambda r, n: llm._body("m", [], max_tokens=n, temperature=None, reasoning=r, stream=True, json_mode=False)
    assert big(1500, 1200).get("reasoning") is None                  # no room left to answer: don't think
    assert big(8000, 6000)["reasoning"] == {"max_tokens": 5488}      # leave room for the answer


async def test_all_thinking_no_answer_retries_without_reasoning():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        if len(seen) == 1:  # the model thought until the limit and said nothing
            content = sse({"choices": [{"delta": {}, "finish_reason": "length"}],
                           "usage": {"prompt_tokens": 5, "completion_tokens": 100, "cost": 0.01}})
        else:
            content = sse({"choices": [{"delta": {"content": "the answer"}}]},
                          {"choices": [{"delta": {}, "finish_reason": "stop"}],
                           "usage": {"prompt_tokens": 5, "completion_tokens": 3, "cost": 0.001}})
        return httpx.Response(200, content=content, headers={"content-type": "text/event-stream"})

    mock_openrouter(handler)
    c = await llm.complete([{"role": "user", "content": "q"}], role="designer", max_tokens=4000, reasoning=2000)
    assert c.text == "the answer"
    assert seen[0]["reasoning"] == {"max_tokens": 2000}
    assert seen[1]["reasoning"] == {"enabled": False} and seen[1]["max_tokens"] == 6000
    # both calls are on the spend ledger, including the wasted one
    assert db.one("SELECT COUNT(*) AS n, SUM(cost_usd) AS s FROM llm_calls")["n"] == 2


async def test_out_of_credits_is_a_clear_error_and_not_retried():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(402, json={"error": {"code": 402, "message": "in_flight_budget_exhausted"}})

    mock_openrouter(handler)
    with pytest.raises(llm.CreditError, match="out of credits"):
        await llm.complete([{"role": "user", "content": "q"}], role="grader")
    assert len(calls) == 1
