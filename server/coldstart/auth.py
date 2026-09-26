"""The login gate for the hosted app.

The browser signs in with InsForge Auth (Google, GitHub, or an emailed code)
and sends its short-lived access token with every request. We ask InsForge
who the token belongs to and only let allow-listed emails through — this
server can run a shell and spend the OpenRouter budget, so it is never open.

Locally (no allow-list configured) the gate is off.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

import httpx

from . import config

CACHE_SECONDS = 300


class AuthError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class User:
    id: str
    email: str


_cache: dict[str, tuple[float, User]] = {}
_client: httpx.AsyncClient | None = None


def required() -> bool:
    return config.AUTH_REQUIRED


def _http() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(base_url=config.INSFORGE_URL, timeout=httpx.Timeout(15, connect=10))
    return _client


def bearer(header: str | None) -> str | None:
    if not header or not header.lower().startswith("bearer "):
        return None
    token = header[7:].strip()
    return token or None


async def verify(token: str | None) -> User:
    """Resolve an InsForge access token to an allowed user, or raise AuthError."""
    if not token:
        raise AuthError(401, "sign in required")
    key = hashlib.sha256(token.encode()).hexdigest()
    now = time.time()
    hit = _cache.get(key)
    if hit and hit[0] > now:
        return hit[1]
    try:
        r = await _http().get("/api/auth/sessions/current", headers={"Authorization": f"Bearer {token}"})
    except httpx.HTTPError as err:
        raise AuthError(503, f"couldn't reach the auth service: {err}") from err
    if r.status_code in (401, 403):
        raise AuthError(401, "session expired — sign in again")
    if r.status_code >= 400:
        raise AuthError(503, f"auth service error {r.status_code}")
    data = (r.json() or {}).get("user") or {}
    email = str(data.get("email") or "").lower()
    user = User(id=str(data.get("id") or ""), email=email)
    if not user.id or email not in config.ALLOWED_EMAILS:
        raise AuthError(403, f"{email or 'this account'} doesn't have access to this Cold Start")
    if len(_cache) > 500:
        _cache.clear()
    _cache[key] = (now + CACHE_SECONDS, user)
    return user
