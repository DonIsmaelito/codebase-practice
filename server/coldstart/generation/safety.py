"""Static checks on generated code, on top of the runtime sandbox.

The sandbox is the real protection; this catches code that would be
unrealistic or unsafe to hand to a learner (real network calls, shelling out,
destructive filesystem calls) and bug edits that leak the answer.
"""

from __future__ import annotations

import ast
import re

BLOCKED_CALLS = {
    ("os", "system"), ("os", "popen"), ("os", "execv"), ("os", "execvp"), ("os", "fork"),
    ("subprocess", "run"), ("subprocess", "Popen"), ("subprocess", "call"),
    ("subprocess", "check_output"), ("subprocess", "check_call"),
}
BLOCKED_IMPORTS = {"socket", "ctypes", "requests", "urllib3", "paramiko", "smtplib", "ftplib", "telnetlib"}
REAL_URL = re.compile(r"https?://(?!(?:example\.(?:com|org|net)|localhost|127\.0\.0\.1|test|testserver)\b)[\w.-]+\.\w+")

LEAKY_WORDS = re.compile(
    r"\b(bug|buggy|wrong|incorrect|should be|oops|mistake|broken|fixme|hack|intentional|injected)\b",
    re.IGNORECASE,
)


def scan_python(path: str, source: str) -> list[str]:
    problems: list[str] = []
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as err:
        return [f"{path}: syntax error line {err.lineno}: {err.msg}"]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in BLOCKED_IMPORTS:
                    problems.append(f"{path}:{node.lineno}: imports {alias.name}")
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in BLOCKED_IMPORTS:
                problems.append(f"{path}:{node.lineno}: imports from {node.module}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            base = node.func.value
            if isinstance(base, ast.Name) and (base.id, node.func.attr) in BLOCKED_CALLS:
                problems.append(f"{path}:{node.lineno}: calls {base.id}.{node.func.attr}")
    for m in REAL_URL.finditer(source):
        line = source.count("\n", 0, m.start()) + 1
        # URLs inside comments/docstrings are fine; flag only ones used in code calls.
        text_line = source.splitlines()[line - 1]
        if re.search(r"\b(get|post|put|delete|request|urlopen|stream)\s*\(", text_line):
            problems.append(f"{path}:{line}: real network URL in a call: {m.group(0)}")
    return problems


def scan_repo(files: dict[str, str]) -> list[str]:
    problems: list[str] = []
    for path, src in files.items():
        if path.endswith(".py"):
            problems.extend(scan_python(path, src))
    return problems


def leaky_comment_lines(added: list[str]) -> list[str]:
    """Added lines whose comments/strings hint at the injected bug."""
    hits = []
    for line in added:
        stripped = line.strip()
        comment = stripped.split("#", 1)[1] if "#" in stripped else ""
        if comment and LEAKY_WORDS.search(comment):
            hits.append(line)
    return hits
