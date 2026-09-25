from pathlib import Path

import pytest

from coldstart.generation import files as F
from coldstart.generation import safety


def test_parse_files_strips_fences_and_normalizes_paths():
    text = '''
<file path="./shop/cart.py">
```python
def total(xs):
    return sum(xs)
```
</file>
<file path="README.md">
# Shop
</file>
'''
    files = F.parse_files(text)
    assert files == {"shop/cart.py": "def total(xs):\n    return sum(xs)\n", "README.md": "# Shop\n"}


def test_safe_rel_refuses_traversal_and_absolute_paths():
    for bad in ("../etc/passwd", "/etc/passwd", "a/../../b", ""):
        with pytest.raises(F.EditError):
            F.safe_rel(bad)
    assert F.safe_rel("./pkg/mod.py") == "pkg/mod.py"


def test_parse_edits_and_apply(tmp_path: Path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "m.py").write_text("def f(items=None):\n    items = items or []\n    return items\n")
    text = '''<bug_edit path="pkg/m.py">
<search>
def f(items=None):
    items = items or []
</search>
<replace>
def f(items=[]):
</replace>
</bug_edit>'''
    edits = F.parse_edits(text, "bug_edit")
    assert len(edits) == 1
    F.apply_edits(tmp_path, edits)
    assert (tmp_path / "pkg" / "m.py").read_text() == "def f(items=[]):\n    return items\n"


def test_apply_edits_tolerates_trailing_whitespace_but_not_ambiguity(tmp_path: Path):
    (tmp_path / "m.py").write_text("x = 1   \ny = 2\nx = 1\n")
    F.apply_edits(tmp_path, [F.Edit("m.py", "x = 1\ny = 2", "x = 10\ny = 20")])
    assert (tmp_path / "m.py").read_text() == "x = 10\ny = 20\nx = 1\n"
    (tmp_path / "d.py").write_text("a = 1\na = 1\n")
    with pytest.raises(F.EditError, match="more than once"):
        F.apply_edits(tmp_path, [F.Edit("d.py", "a = 1", "a = 2")])
    with pytest.raises(F.EditError, match="not found"):
        F.apply_edits(tmp_path, [F.Edit("d.py", "zzz", "a = 2")])


def test_apply_edits_creates_new_files_but_not_over_existing(tmp_path: Path):
    F.apply_edits(tmp_path, [F.Edit("pkg/new.py", "", "VALUE = 1")])
    assert (tmp_path / "pkg" / "new.py").read_text() == "VALUE = 1\n"
    with pytest.raises(F.EditError):
        F.apply_edits(tmp_path, [F.Edit("pkg/new.py", "", "VALUE = 2")])


def test_read_repo_keeps_dotfiles_and_skips_caches(tmp_path: Path):
    F.write_repo(tmp_path, {"a.py": "x = 1\n", ".gitignore": "__pycache__/\n", "__pycache__/a.cpython.pyc": "junk"})
    assert set(F.read_repo(tmp_path)) == {"a.py", ".gitignore"}


def test_repo_stats_and_line_of():
    files = {"pkg/a.py": "import os\n\n\ndef f():\n    return 1\n", "tests/test_a.py": "def test():\n    pass\n"}
    stats = F.repo_stats(files)
    assert stats["py_files"] == 1 and stats["test_files"] == 1 and stats["loc"] == 3
    assert F.line_of(files["pkg/a.py"], "    def f():") == 4
    assert F.line_of(files["pkg/a.py"], "nope") is None


def test_unified_diff_marks_added_files():
    diff = F.unified_diff({"a.py": "x = 1\n"}, {"a.py": "x = 2\n", "b.py": "y = 1\n"})
    assert "-x = 1" in diff and "+x = 2" in diff and "/dev/null" in diff


def test_safety_scan_flags_network_and_shelling_out():
    src = "import socket\nimport subprocess\nsubprocess.run(['ls'])\nimport httpx\nhttpx.get('https://api.stripe.com/v1')\n"
    problems = safety.scan_python("m.py", src)
    assert any("socket" in p for p in problems)
    assert any("subprocess.run" in p for p in problems)
    assert any("real network URL" in p for p in problems)
    assert safety.scan_python("ok.py", "import httpx\nclient = httpx.Client(base_url='http://testserver')\n") == []


def test_leaky_comment_detection():
    assert safety.leaky_comment_lines(["x = items  # BUG: shared list", "y = 2  # cache for speed"]) == ["x = items  # BUG: shared list"]
