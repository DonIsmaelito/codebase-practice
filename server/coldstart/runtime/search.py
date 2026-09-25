"""Workspace-wide text search (Cmd+Shift+F). Repos are small, so plain Python is instant."""

from __future__ import annotations

import re
from typing import Any

from .workspace import Workspace

MAX_MATCHES = 600


def search(ws: Workspace, query: str, *, regex: bool = False, case: bool = False,
           word: bool = False, include: str | None = None) -> dict[str, Any]:
    if not query:
        return {"results": [], "total": 0, "truncated": False}
    pattern = query if regex else re.escape(query)
    if word:
        pattern = rf"\b{pattern}\b"
    try:
        rx = re.compile(pattern, 0 if case else re.IGNORECASE)
    except re.error as err:
        return {"results": [], "total": 0, "truncated": False, "error": f"invalid regex: {err}"}

    results, total = [], 0
    for rel, content in sorted(ws.files().items()):
        if include and include not in rel:
            continue
        matches = []
        for lineno, line in enumerate(content.splitlines(), start=1):
            for m in rx.finditer(line):
                matches.append({"line": lineno, "column": m.start() + 1, "length": max(1, m.end() - m.start()),
                                "text": line[:400]})
                total += 1
                if total >= MAX_MATCHES:
                    break
            if total >= MAX_MATCHES:
                break
        if matches:
            results.append({"path": rel, "matches": matches})
        if total >= MAX_MATCHES:
            break
    return {"results": results, "total": total, "truncated": total >= MAX_MATCHES}
