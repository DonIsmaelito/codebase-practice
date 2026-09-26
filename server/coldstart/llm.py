"""OpenRouter client: streaming chat completions with cost tracking and caching.

All model traffic goes through `complete()` / `stream()`. Every call is logged
to the llm_calls table with tokens and USD cost so the Settings page can show
exactly where the budget went.
"""

from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable

import httpx

from . import config, db

log = logging.getLogger("coldstart.llm")

Message = dict[str, Any]


class LLMError(RuntimeError):
    pass


class CreditError(LLMError):
    """OpenRouter refused for lack of credit — retrying won't help until someone tops up."""


@dataclass
class Completion:
    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    cost_usd: float = 0.0
    duration_s: float = 0.0
    finish_reason: str | None = None
    raw_usage: dict[str, Any] = field(default_factory=dict)


def cached(text: str) -> dict[str, Any]:
    """A content part marked as a prompt-cache breakpoint (Anthropic/Gemini)."""
    return {"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}


def text_part(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


# Lets the CLI force one model for every role (e.g. a cheap model while testing).
MODEL_OVERRIDE: contextvars.ContextVar[str | None] = contextvars.ContextVar("model_override", default=None)


def model_for(role: str) -> str:
    return MODEL_OVERRIDE.get() or db.settings()["models"].get(role) or config.DEFAULT_MODELS[role]


_client: httpx.AsyncClient | None = None


def _http() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            base_url=config.OPENROUTER_BASE,
            timeout=httpx.Timeout(connect=20, read=300, write=60, pool=60),
            headers={
                "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
                "HTTP-Referer": "http://localhost/coldstart",
                "X-Title": "Cold Start",
            },
        )
    return _client


def _record(role: str, model: str, case_id: str | None, c: Completion | None,
            duration: float, error: str | None = None) -> None:
    db.run(
        "INSERT INTO llm_calls(ts, role, model, case_id, prompt_tokens, completion_tokens,"
        " cached_tokens, cost_usd, duration_s, ok, error) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        time.time(), role, model, case_id,
        c.prompt_tokens if c else None,
        c.completion_tokens if c else None,
        c.cached_tokens if c else None,
        c.cost_usd if c else 0.0,
        duration,
        1 if error is None else 0,
        error,
    )
    if case_id and c:
        db.run("UPDATE cases SET cost_usd = cost_usd + ? WHERE id = ?", c.cost_usd, case_id)


def _body(model: str, messages: list[Message], *, max_tokens: int,
          temperature: float | None, reasoning: str | int | None, stream: bool,
          json_mode: bool) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": stream,
        "usage": {"include": True},
    }
    if temperature is not None:
        body["temperature"] = temperature
    # An int is an explicit thinking budget (tokens). Prefer it: reasoning counts
    # against max_tokens, and an effort level alone once let a model think until
    # the limit and return nothing.
    if isinstance(reasoning, int):
        body["reasoning"] = {"max_tokens": reasoning}
    elif reasoning == "off":
        body["reasoning"] = {"enabled": False}
    elif reasoning:
        body["reasoning"] = {"effort": reasoning}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    return body


_spend_cache: tuple[float, float] | None = None


def _spent_last_24h() -> float:
    global _spend_cache
    now = time.time()
    if _spend_cache and now - _spend_cache[0] < 20:
        return _spend_cache[1]
    row = db.one("SELECT COALESCE(SUM(cost_usd), 0) AS s FROM llm_calls WHERE ts > ?", now - 86_400)
    _spend_cache = (now, float(row["s"] or 0))
    return _spend_cache[1]


def check_budget() -> None:
    """Refuse new AI calls once the rolling 24h spend hits the cap (Settings → daily budget).

    The app has no login, so this is what stops anyone — or a runaway bug —
    from draining the OpenRouter credit in one go.
    """
    cap = float(db.settings().get("daily_budget_usd") or 0)
    if cap > 0 and _spent_last_24h() >= cap:
        raise LLMError(f"Today's AI budget (${cap:.0f}) is used up. It frees up over the next 24 hours, "
                       "or raise it in Settings.")


async def _stream_raw(body: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
    async with _http().stream("POST", "/chat/completions", json=body) as resp:
        if resp.status_code >= 400:
            detail = (await resp.aread()).decode("utf-8", "replace")[:800]
            if resp.status_code == 402:
                raise CreditError("Your OpenRouter account is out of credits — add some at "
                                  "openrouter.ai/settings/credits, then try again.")
            raise LLMError(f"HTTP {resp.status_code}: {detail}")
        async for line in resp.aiter_lines():
            if not line or line.startswith(":"):
                continue  # keep-alive comments
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                return
            try:
                chunk = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if "error" in chunk:
                raise LLMError(f"stream error: {chunk['error']}")
            yield chunk


def _is_retryable(err: Exception) -> bool:
    if isinstance(err, (httpx.TransportError, httpx.TimeoutException)):
        return True
    msg = str(err)
    return any(code in msg for code in ("HTTP 429", "HTTP 500", "HTTP 502", "HTTP 503", "HTTP 504",
                                          "overloaded", "stream error"))


async def complete(
    messages: list[Message],
    *,
    role: str,
    model: str | None = None,
    max_tokens: int = 8000,
    temperature: float | None = None,
    reasoning: str | int | None = None,
    json_mode: bool = False,
    case_id: str | None = None,
    on_progress: Callable[[int], None] | None = None,
    retries: int = 3,
) -> Completion:
    """Run a completion (streamed under the hood so long generations never idle out)."""
    model = model or model_for(role)
    if not config.OPENROUTER_API_KEY:
        raise LLMError("OPENROUTER_API_KEY is not set (add it to .env)")
    check_budget()

    last_err: Exception | None = None
    for attempt in range(retries + 1):
        started = time.monotonic()
        parts: list[str] = []
        usage: dict[str, Any] = {}
        finish: str | None = None
        chars = 0
        try:
            body = _body(model, messages, max_tokens=max_tokens, temperature=temperature,
                         reasoning=reasoning, stream=True, json_mode=json_mode)
            async for chunk in _stream_raw(body):
                if chunk.get("usage"):
                    usage = chunk["usage"]
                for choice in chunk.get("choices") or []:
                    delta = choice.get("delta") or {}
                    piece = delta.get("content")
                    if piece:
                        parts.append(piece)
                        chars += len(piece)
                        if on_progress:
                            on_progress(chars)
                    if choice.get("finish_reason"):
                        finish = choice["finish_reason"]
            text = "".join(parts)
            c = Completion(
                text=text,
                model=model,
                prompt_tokens=int(usage.get("prompt_tokens") or 0),
                completion_tokens=int(usage.get("completion_tokens") or 0),
                cached_tokens=int((usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0),
                cost_usd=float(usage.get("cost") or 0.0),
                duration_s=time.monotonic() - started,
                finish_reason=finish,
                raw_usage=usage,
            )
            _record(role, model, case_id, c, c.duration_s)
            if not text.strip() and finish == "length" and reasoning != "off":
                # All tokens went to thinking. Try once more without it, with more room.
                log.warning("%s: thinking used the whole budget; retrying without reasoning", role)
                reasoning, max_tokens = "off", min(64000, int(max_tokens * 1.5))
                continue
            if not text.strip():
                raise LLMError(f"empty completion (finish_reason={finish})")
            return c
        except Exception as err:  # noqa: BLE001 — we classify below
            last_err = err
            _record(role, model, case_id, None, time.monotonic() - started, error=str(err)[:500])
            if attempt < retries and _is_retryable(err) and not isinstance(err, CreditError):
                delay = min(60, 4 * 2**attempt)
                log.warning("LLM call failed (%s); retrying in %ss", err, delay)
                await asyncio.sleep(delay)
                continue
            break
    if isinstance(last_err, LLMError):
        raise last_err
    raise LLMError(str(last_err)) from last_err


async def stream(
    messages: list[Message],
    *,
    role: str,
    model: str | None = None,
    max_tokens: int = 2000,
    temperature: float | None = None,
    reasoning: str | int | None = None,
    case_id: str | None = None,
) -> AsyncIterator[str]:
    """Yield text deltas as they arrive (used for the mentor chat)."""
    model = model or model_for(role)
    check_budget()
    started = time.monotonic()
    usage: dict[str, Any] = {}
    body = _body(model, messages, max_tokens=max_tokens, temperature=temperature,
                 reasoning=reasoning, stream=True, json_mode=False)
    try:
        async for chunk in _stream_raw(body):
            if chunk.get("usage"):
                usage = chunk["usage"]
            for choice in chunk.get("choices") or []:
                piece = (choice.get("delta") or {}).get("content")
                if piece:
                    yield piece
    except Exception as err:
        _record(role, model, case_id, None, time.monotonic() - started, error=str(err)[:500])
        raise
    c = Completion(
        text="",
        model=model,
        prompt_tokens=int(usage.get("prompt_tokens") or 0),
        completion_tokens=int(usage.get("completion_tokens") or 0),
        cached_tokens=int((usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0),
        cost_usd=float(usage.get("cost") or 0.0),
    )
    _record(role, model, case_id, c, time.monotonic() - started)


# --- structured output helpers ------------------------------------------------

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_json(text: str) -> Any:
    """Parse a JSON object from model output, tolerating fences and preamble."""
    s = text.strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    s = _FENCE.sub("", s).strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end > start:
        return json.loads(s[start : end + 1])
    raise ValueError("no JSON object found in model output")


def extract_tag(text: str, tag: str) -> str | None:
    """Return the body of the first <tag>...</tag> block (XML-ish, code-safe)."""
    m = re.search(rf"<{tag}(?:\s[^>]*)?>\n?(.*?)\n?</{tag}>", text, re.DOTALL)
    return m.group(1) if m else None


def extract_tags(text: str, tag: str) -> list[tuple[dict[str, str], str]]:
    """All <tag attr="...">body</tag> blocks as (attrs, body) pairs."""
    out = []
    for m in re.finditer(rf"<{tag}((?:\s+\w+=\"[^\"]*\")*)\s*>\n?(.*?)\n?</{tag}>", text, re.DOTALL):
        attrs = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
        out.append((attrs, m.group(2)))
    return out


async def complete_json(messages: list[Message], *, role: str, retries: int = 2, **kw: Any) -> tuple[Any, Completion]:
    """complete() + parse_json(), re-asking the model if the JSON is malformed."""
    msgs = list(messages)
    last: Exception | None = None
    for _ in range(retries + 1):
        c = await complete(msgs, role=role, **kw)
        try:
            return parse_json(c.text), c
        except (ValueError, json.JSONDecodeError) as err:
            last = err
            msgs = msgs + [
                {"role": "assistant", "content": c.text},
                {"role": "user", "content": f"That was not valid JSON ({err}). Reply with only the corrected JSON object."},
            ]
    raise LLMError(f"model never produced valid JSON: {last}")


# --- budget -------------------------------------------------------------------

_key_cache: tuple[float, dict[str, Any]] | None = None


async def key_status(force: bool = False) -> dict[str, Any]:
    """Remaining credit on the OpenRouter key (cached for a minute)."""
    global _key_cache
    now = time.time()
    if not force and _key_cache and now - _key_cache[0] < 60:
        return _key_cache[1]
    try:
        r = await _http().get("/key")
        r.raise_for_status()
        data = r.json().get("data", {})
        # A key's limit is only a cap; what can actually be spent is the account
        # balance (shared with every other key on the account).
        account = None
        try:
            c = await _http().get("/credits")
            if c.status_code == 200:
                cd = c.json().get("data", {})
                account = float(cd.get("total_credits") or 0) - float(cd.get("total_usage") or 0)
        except httpx.HTTPError:
            pass
        key_left = data.get("limit_remaining")
        options = [v for v in (key_left, account) if v is not None]
        status = {
            "ok": True,
            "limit": data.get("limit"),
            "key_remaining": key_left,
            "account_remaining": account,
            "remaining": min(options) if options else None,
            "usage": data.get("usage"),
        }
    except Exception as err:  # noqa: BLE001
        status = {"ok": False, "error": str(err)}
    _key_cache = (now, status)
    return status


def spend_summary() -> dict[str, Any]:
    rows = db.all_(
        "SELECT role, model, COUNT(*) AS calls, SUM(cost_usd) AS cost,"
        " SUM(prompt_tokens) AS prompt_tokens, SUM(completion_tokens) AS completion_tokens,"
        " SUM(cached_tokens) AS cached_tokens"
        " FROM llm_calls GROUP BY role, model ORDER BY cost DESC"
    )
    total = sum((r["cost"] or 0) for r in rows)
    return {"total_usd": total, "by_role": rows}
