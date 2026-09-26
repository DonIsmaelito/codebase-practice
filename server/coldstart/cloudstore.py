"""InsForge Storage client (server-side, admin key) for blobs the container
can't keep: generated case bundles and workspace snapshots.

Uploads follow InsForge's upload strategy (presigned S3 POST + confirm, or a
direct PUT); downloads follow the download strategy (presigned or direct URL).
"""

from __future__ import annotations

import logging
from urllib.parse import quote

import httpx

from . import config

log = logging.getLogger("coldstart.cloudstore")


class StorageError(RuntimeError):
    pass


def enabled() -> bool:
    return config.CLOUD_STORAGE


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {config.INSFORGE_API_KEY}"}


def _client() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(60, connect=15), follow_redirects=True)


def _object_path(key: str) -> str:
    return "/".join(quote(part, safe="") for part in key.split("/"))


def put(key: str, data: bytes, content_type: str = "application/gzip") -> None:
    base, bucket = config.INSFORGE_URL, config.STORAGE_BUCKET
    with _client() as http:
        r = http.post(f"{base}/api/storage/buckets/{bucket}/upload-strategy", headers=_headers(),
                      json={"filename": key, "contentType": content_type, "size": len(data)})
        if r.status_code >= 400:
            raise StorageError(f"upload-strategy {r.status_code}: {r.text[:300]}")
        strategy = r.json()
        files = {"file": (key.rsplit("/", 1)[-1], data, content_type)}
        if strategy.get("method") == "presigned":
            up = http.post(strategy["uploadUrl"], data=strategy.get("fields") or {}, files=files)
            if up.status_code >= 400:
                raise StorageError(f"presigned upload {up.status_code}: {up.text[:300]}")
            if strategy.get("confirmRequired"):
                confirm_url = strategy.get("confirmUrl") or f"/api/storage/buckets/{bucket}/objects/{_object_path(key)}/confirm-upload"
                c = http.post(f"{base}{confirm_url}", headers=_headers(),
                              json={"size": len(data), "contentType": content_type,
                                    **({"etag": up.headers["etag"].strip('"')} if up.headers.get("etag") else {})})
                if c.status_code >= 400:
                    raise StorageError(f"confirm-upload {c.status_code}: {c.text[:300]}")
        else:
            url = strategy.get("uploadUrl") or f"/api/storage/buckets/{bucket}/objects/{_object_path(key)}"
            up = http.put(url if url.startswith("http") else f"{base}{url}", headers=_headers(), files=files)
            if up.status_code >= 400:
                raise StorageError(f"direct upload {up.status_code}: {up.text[:300]}")


def get(key: str) -> bytes | None:
    """The object's bytes, or None if it doesn't exist."""
    base, bucket = config.INSFORGE_URL, config.STORAGE_BUCKET
    with _client() as http:
        r = http.get(f"{base}/api/storage/buckets/{bucket}/download-strategy/objects/{_object_path(key)}",
                     headers=_headers())
        if r.status_code == 404:
            return None
        if r.status_code >= 400:
            raise StorageError(f"download-strategy {r.status_code}: {r.text[:300]}")
        url = r.json().get("url") or ""
        if url.startswith("http"):
            d = http.get(url)  # presigned URLs carry their own auth
        else:
            d = http.get(f"{base}{url}", headers=_headers())
        if d.status_code == 404:
            return None
        if d.status_code >= 400:
            raise StorageError(f"download {d.status_code}: {d.text[:200]}")
        return d.content


def delete(key: str) -> None:
    base, bucket = config.INSFORGE_URL, config.STORAGE_BUCKET
    with _client() as http:
        r = http.delete(f"{base}/api/storage/buckets/{bucket}/objects/{_object_path(key)}", headers=_headers())
        if r.status_code >= 400 and r.status_code != 404:
            raise StorageError(f"delete {r.status_code}: {r.text[:300]}")
