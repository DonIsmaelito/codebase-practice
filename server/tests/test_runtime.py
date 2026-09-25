import asyncio
from pathlib import Path

import pytest

from coldstart import config
from coldstart.runtime import intel, search
from coldstart.runtime.terminal import TerminalSession
from coldstart.runtime.workspace import Workspace, WorkspaceError


@pytest.fixture
def ws(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    case = tmp_path / "case"
    (case / "repo" / "shop").mkdir(parents=True)
    (case / "repo" / "shop" / "__init__.py").write_text("")
    (case / "repo" / "shop" / "cart.py").write_text(
        "from collections import Counter\n\n\n"
        "def total(prices):\n"
        "    \"\"\"Sum item prices.\"\"\"\n"
        "    return sum(prices)\n\n\n"
        "def summary(items):\n"
        "    counts = Counter(items)\n"
        "    return total([1, 2]), counts\n"
    )
    return Workspace.provision("e1", case, ("Dana Lee", "dana@example.com"))


def test_workspace_tree_read_write_and_diff(ws):
    paths = {e["path"] for e in ws.tree()}
    assert {"shop", "shop/cart.py"} <= paths
    assert ".git" not in paths
    ws.snapshot("t1")
    ws.write("shop/cart.py", ws.read("shop/cart.py").replace("sum(prices)", "sum(prices) or 0"))
    ws.create("shop/new.py")
    changes = {c["path"]: c["status"] for c in ws.changes("t1")}
    assert changes == {"shop/cart.py": "modified", "shop/new.py": "added"}
    assert "+    return sum(prices) or 0" in ws.diff("t1")
    ws.revert("t1")
    assert ws.changes("t1") == []


def test_workspace_refuses_escape(ws):
    with pytest.raises(WorkspaceError):
        ws.read("../../etc/passwd")
    with pytest.raises(WorkspaceError):
        ws.read(".git/config")


def test_git_history_has_client_author(ws):
    log = ws.git("log", "--format=%an|%s")
    assert log.strip() == "Dana Lee|Snapshot of main for contractor access"


def test_search(ws):
    res = search.search(ws, "total")
    assert res["results"][0]["path"] == "shop/cart.py"
    assert [m["line"] for m in res["results"][0]["matches"]] == [4, 11]
    assert search.search(ws, "(", regex=True).get("error")


def test_jedi_definition_references_hover_symbols(ws):
    # `total` call on line 11, col 12 (1-based)
    defs = intel.definition(ws, "shop/cart.py", 11, 12)
    assert defs and defs[0]["path"] == "shop/cart.py" and defs[0]["line"] == 4
    refs = intel.references(ws, "shop/cart.py", 4, 5)
    assert sorted(r["line"] for r in refs) == [4, 11]
    # Counter goes into the stdlib, opened read-only
    ext = intel.definition(ws, "shop/cart.py", 10, 15)
    assert ext and ext[0]["external"] and ext[0]["path"].endswith("collections/__init__.py")
    assert "class Counter" in intel.read_external(ext[0]["path"])
    h = intel.hover(ws, "shop/cart.py", 11, 12)
    assert h and "Sum item prices" in h["doc"]
    names = {s["name"] for s in intel.symbols(ws, "shop/cart.py")}
    assert names == {"total", "summary"}
    with pytest.raises(PermissionError):
        intel.read_external("/etc/hosts")


async def test_terminal_runs_python_in_workspace(ws):
    commands = []
    term = TerminalSession(ws.root, ws.repo, on_command=commands.append)
    out = []

    async def send(text):
        out.append(text)

    pump = asyncio.create_task(term.pump(send))
    await asyncio.sleep(0.8)
    term.write("python -c 'print(6*7)'\r")
    for _ in range(40):
        await asyncio.sleep(0.1)
        if "42" in "".join(out):
            break
    term.close()
    await asyncio.wait_for(pump, 3)
    assert "42" in "".join(out)
    assert commands == ["python -c 'print(6*7)'"]
