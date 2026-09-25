"""Code intelligence for the in-browser editor, powered by jedi.

Go-to-definition, find-references, hover docs and a symbol outline — resolved
against the runtime venv, so definitions can jump into the standard library
or third-party packages (opened read-only in the editor).
"""

from __future__ import annotations

import ast
import json
import subprocess
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any

import jedi

from .. import config
from .workspace import Workspace

_lock = threading.Lock()  # jedi is not thread-safe


@lru_cache(maxsize=1)
def environment() -> Any:
    return jedi.create_environment(str(config.RUNTIME_PYTHON), safe=False)


@lru_cache(maxsize=1)
def external_roots() -> tuple[Path, ...]:
    """Directories outside a workspace that may be opened read-only (stdlib + site-packages)."""
    out = subprocess.run(
        [str(config.RUNTIME_PYTHON), "-c",
         "import json, sysconfig; p = sysconfig.get_paths(); print(json.dumps([p['stdlib'], p['purelib'], p['platlib']]))"],
        capture_output=True, text=True, check=True,
    ).stdout
    return tuple(Path(p).resolve() for p in json.loads(out))


def is_external_allowed(path: Path) -> bool:
    path = path.resolve()
    return path.suffix in (".py", ".pyi") and any(root == path or root in path.parents for root in external_roots())


def _script(ws: Workspace, rel: str, content: str | None) -> jedi.Script:
    project = jedi.Project(path=str(ws.repo), environment_path=str(config.RUNTIME_PYTHON))
    code = content if content is not None else ws.read(rel)
    return jedi.Script(code=code, path=str(ws.repo / rel), project=project, environment=environment())


def _location(ws: Workspace, d: Any) -> dict[str, Any] | None:
    if d.module_path is None or d.line is None:
        return None
    path = Path(d.module_path).resolve()
    repo = ws.repo.resolve()
    if repo in path.parents:
        return {"path": path.relative_to(repo).as_posix(), "external": False,
                "line": d.line, "column": d.column + 1, "name": d.name, "type": d.type}
    if is_external_allowed(path):
        return {"path": str(path), "external": True,
                "line": d.line, "column": d.column + 1, "name": d.name, "type": d.type}
    return None


def definition(ws: Workspace, rel: str, line: int, column: int, content: str | None = None) -> list[dict[str, Any]]:
    with _lock:
        s = _script(ws, rel, content)
        col = max(0, column - 1)
        defs = s.goto(line, col, follow_imports=True, follow_builtin_imports=True)
        if not defs:
            defs = s.infer(line, col)
        return [loc for d in defs if (loc := _location(ws, d))]


def references(ws: Workspace, rel: str, line: int, column: int, content: str | None = None) -> list[dict[str, Any]]:
    with _lock:
        s = _script(ws, rel, content)
        refs = s.get_references(line, max(0, column - 1), include_builtins=False)
        out = [loc for r in refs if (loc := _location(ws, r)) and not loc["external"]]
        return out[:300]


def hover(ws: Workspace, rel: str, line: int, column: int, content: str | None = None) -> dict[str, Any] | None:
    with _lock:
        s = _script(ws, rel, content)
        col = max(0, column - 1)
        names = s.help(line, col) or s.infer(line, col)
        if not names:
            return None
        n = names[0]
        sigs = []
        try:
            sigs = [sig.to_string() for sig in n.get_signatures()]
        except Exception:  # noqa: BLE001 — jedi can be flaky on odd objects
            pass
        doc = n.docstring(raw=True) or ""
        return {
            "name": n.name,
            "type": n.type,
            "module": n.module_name,
            "signatures": sigs[:3],
            "doc": doc[:3000],
        }


def symbols(ws: Workspace, rel: str, content: str | None = None) -> list[dict[str, Any]]:
    """Classes and functions defined in the file (outline / Cmd+Shift+O)."""
    code = content if content is not None else ws.read(rel)
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    out: list[dict[str, Any]] = []

    def visit(node: ast.AST, parent: str | None) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                kind = "class" if isinstance(child, ast.ClassDef) else "function"
                out.append({"name": child.name, "type": kind, "line": child.lineno,
                            "column": child.col_offset + 1, "parent": parent})
                visit(child, child.name)

    visit(tree, None)
    return out


def read_external(path: str) -> str:
    p = Path(path)
    if not is_external_allowed(p):
        raise PermissionError("only standard-library and installed-package sources can be opened")
    return p.read_text(errors="replace")
