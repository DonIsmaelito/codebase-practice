"""Reading, writing, rendering and patching generated repos.

Models emit code as XML-ish blocks (no JSON escaping of source code):

    <file path="pkg/models.py">...</file>
    <edit path="pkg/models.py"><search>...</search><replace>...</replace></edit>
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from .. import llm

TEXT_SUFFIXES = {".py", ".md", ".txt", ".toml", ".cfg", ".ini", ".json", ".jsonl",
                 ".csv", ".tsv", ".yaml", ".yml", ".sql", ".html", ".j2", ".jinja", ".srt", ".xml"}
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".coldstart", ".venv"}


@dataclass
class Edit:
    path: str
    search: str
    replace: str


class EditError(ValueError):
    pass


def safe_rel(path: str) -> str:
    """Normalize a model-supplied relative path and refuse traversal."""
    p = path.strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    if not p or p.startswith("/") or ".." in Path(p).parts:
        raise EditError(f"unsafe path: {path!r}")
    return p


def parse_files(text: str) -> dict[str, str]:
    files: dict[str, str] = {}
    for attrs, body in llm.extract_tags(text, "file"):
        if "path" not in attrs:
            continue
        body = _strip_fence(body)
        files[safe_rel(attrs["path"])] = body.rstrip() + "\n"
    return files


def parse_edits(text: str, tag: str = "edit") -> list[Edit]:
    edits: list[Edit] = []
    for attrs, body in llm.extract_tags(text, tag):
        if "path" not in attrs:
            continue
        search = llm.extract_tag(body, "search")
        replace = llm.extract_tag(body, "replace")
        if replace is None:
            continue
        edits.append(Edit(safe_rel(attrs["path"]), search or "", replace))
    return edits


def _strip_fence(body: str) -> str:
    """Models sometimes wrap file bodies in ``` fences; drop them."""
    s = body.strip("\n")
    m = re.match(r"^```[\w+-]*\n(.*)\n```\s*$", s, re.DOTALL)
    return m.group(1) if m else s


def write_repo(root: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        dest = root / safe_rel(rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content)


def read_repo(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in sorted(root.rglob("*")):
        if not p.is_file() or any(part in SKIP_DIRS for part in p.relative_to(root).parts):
            continue
        if p.suffix.lower() not in TEXT_SUFFIXES and p.name not in ("Makefile", "Dockerfile"):
            continue
        try:
            out[p.relative_to(root).as_posix()] = p.read_text()
        except UnicodeDecodeError:
            continue
    return out


def copy_repo(src: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns(*SKIP_DIRS, "*.pyc"))


def _find_unique(haystack: str, needle: str) -> int:
    idx = haystack.find(needle)
    if idx == -1:
        return -1
    if haystack.find(needle, idx + 1) != -1:
        return -2
    return idx


def _loose_find(content: str, search: str) -> tuple[int, int] | None:
    """Match ignoring trailing whitespace on each line; returns (start, end) offsets."""
    c_lines = content.split("\n")
    s_lines = [l.rstrip() for l in search.strip("\n").split("\n")]
    n = len(s_lines)
    hits = []
    for i in range(len(c_lines) - n + 1):
        if all(c_lines[i + k].rstrip() == s_lines[k] for k in range(n)):
            hits.append(i)
    if len(hits) != 1:
        return None
    i = hits[0]
    start = sum(len(l) + 1 for l in c_lines[:i])
    end = start + sum(len(l) + 1 for l in c_lines[i : i + n]) - 1
    return start, end


def apply_edits(root: Path, edits: list[Edit]) -> list[str]:
    """Apply search/replace edits in place. Returns the touched paths.

    An empty search on a missing file creates it. Raises EditError with a
    message suitable for feeding back to the model.
    """
    touched: list[str] = []
    for e in edits:
        path = root / e.path
        if not e.search.strip():
            if path.exists() and path.read_text().strip():
                raise EditError(f"{e.path}: empty <search> but file already exists — include the text to replace")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(e.replace.rstrip() + "\n")
            touched.append(e.path)
            continue
        if not path.exists():
            raise EditError(f"{e.path}: file does not exist")
        content = path.read_text()
        idx = _find_unique(content, e.search)
        if idx >= 0:
            content = content[:idx] + e.replace + content[idx + len(e.search):]
        elif idx == -2:
            raise EditError(f"{e.path}: <search> text appears more than once — include more surrounding lines")
        else:
            span = _loose_find(content, e.search)
            if span is None:
                raise EditError(f"{e.path}: <search> text not found verbatim:\n{e.search[:400]}")
            content = content[: span[0]] + e.replace.rstrip("\n") + content[span[1]:]
        path.write_text(content)
        touched.append(e.path)
    return touched


def render_repo(files: dict[str, str], *, include_tests: bool = True,
                exclude: set[str] | None = None) -> str:
    """Serialize a repo for a prompt, deterministically (stable for caching)."""
    parts = []
    for rel in sorted(files):
        if exclude and rel in exclude:
            continue
        if not include_tests and rel.startswith("tests/"):
            continue
        parts.append(f'<file path="{rel}">\n{files[rel].rstrip()}\n</file>')
    return "\n\n".join(parts)


def repo_stats(files: dict[str, str]) -> dict[str, int]:
    src_files = [p for p in files if p.endswith(".py") and not p.startswith("tests/")]
    test_files = [p for p in files if p.endswith(".py") and p.startswith("tests/")]

    def loc(paths: list[str]) -> int:
        return sum(1 for p in paths for line in files[p].splitlines() if line.strip())

    return {
        "files": len(files),
        "py_files": len(src_files),
        "test_files": len(test_files),
        "loc": loc(src_files),
        "test_loc": loc(test_files),
    }


def unified_diff(before: dict[str, str], after: dict[str, str]) -> str:
    import difflib

    out: list[str] = []
    for rel in sorted(set(before) | set(after)):
        a, b = before.get(rel), after.get(rel)
        if a == b:
            continue
        out.extend(difflib.unified_diff(
            (a or "").splitlines(keepends=True), (b or "").splitlines(keepends=True),
            fromfile=f"a/{rel}" if a is not None else "/dev/null",
            tofile=f"b/{rel}" if b is not None else "/dev/null",
        ))
    return "".join(out)


def line_of(content: str, anchor: str) -> int | None:
    """1-based line number of the first line containing `anchor` (whitespace-trimmed)."""
    needle = anchor.strip()
    if not needle:
        return None
    first = needle.splitlines()[0].strip()
    for i, line in enumerate(content.splitlines(), start=1):
        if first and first in line:
            return i
    return None


def added_lines(before: str, after: str) -> list[str]:
    import difflib

    return [l[1:] for l in difflib.ndiff(before.splitlines(), after.splitlines()) if l.startswith("+ ")]
