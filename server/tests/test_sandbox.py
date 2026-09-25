import sys
import textwrap
from pathlib import Path

import pytest

from coldstart import sandbox


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "pkg").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "pkg" / "__init__.py").write_text("")
    (repo / "pkg" / "mathy.py").write_text("def add(a, b):\n    return a + b\n")
    (repo / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\npythonpath = ["."]\ntestpaths = ["tests"]\n'
    )
    (repo / "tests" / "test_mathy.py").write_text(textwrap.dedent("""
        from pkg.mathy import add

        def test_add():
            assert add(2, 2) == 4

        def test_add_wrong():
            assert add(2, 2) == 5

        class TestGroup:
            def test_inside_class(self):
                assert add(1, 1) == 2
    """))
    return repo


async def test_run_pytest_counts_and_nodeids(tmp_path):
    repo = make_repo(tmp_path)
    rep = await sandbox.run_pytest(repo)
    assert (rep.passed, rep.failed, rep.errors) == (2, 1, 0)
    assert not rep.ok
    ids = {c.nodeid for c in rep.cases}
    assert "tests/test_mathy.py::test_add_wrong" in ids
    assert "tests/test_mathy.py::TestGroup::test_inside_class" in ids
    failing = rep.failing()[0]
    assert "assert 4 == 5" in failing.details or "assert 4 == 5" in failing.message


async def test_collection_error_is_reported(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "tests" / "test_broken.py").write_text("import nope_not_a_module\n")
    rep = await sandbox.run_pytest(repo)
    assert rep.errors >= 1
    assert not rep.ok


async def test_timeout_kills_process(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "tests" / "test_slow.py").write_text("import time\n\ndef test_slow():\n    time.sleep(30)\n")
    rep = await sandbox.run_pytest(repo, ["tests/test_slow.py"], timeout=3)
    assert rep.timed_out
    assert not rep.ok


@pytest.mark.skipif(sys.platform != "darwin", reason="sandbox-exec is macOS-only")
async def test_sandbox_blocks_network_and_outside_writes(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    outside = Path.home() / ".coldstart_sandbox_probe"
    code = textwrap.dedent(f"""
        import socket, pathlib
        pathlib.Path("inside.txt").write_text("ok")
        try:
            pathlib.Path({str(outside)!r}).write_text("x")
            print("OUTSIDE_WRITE_ALLOWED")
        except PermissionError:
            print("outside write blocked")
        try:
            socket.create_connection(("1.1.1.1", 80), timeout=3)
            print("NETWORK_ALLOWED")
        except OSError:
            print("network blocked")
    """)
    res = await sandbox.run_python(code, work)
    assert "outside write blocked" in res.stdout, res.stderr
    assert "network blocked" in res.stdout, res.stderr
    assert (work / "inside.txt").exists()
    assert not outside.exists()
