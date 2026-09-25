---
slug: terminal
title: Terminal moves
summary: A dozen pytest flags, the pdb basics and a few git commands cover almost everything you'll do in the terminal while debugging.
order: 8
---

# Terminal moves

You don't need to be a shell wizard. A small set of commands, used fluently, covers nearly all of the terminal work in debugging and feature development.

## pytest

```bash
pytest -q                          # quiet: one character per test
pytest -x                          # stop at the first failure
pytest -k refund                   # only tests whose names match "refund"
pytest -k "refund and not partial" # boolean expressions work
pytest tests/test_pricing.py       # one file
pytest tests/test_pricing.py::test_child_fare   # one test
pytest --lf                        # re-run only the tests that failed last time
pytest --ff                        # run last failures first, then the rest
pytest -vv                         # verbose: full test names and full assertion diffs
pytest -s                          # show print() output (don't capture stdout)
pytest -l                          # show local variables in tracebacks
pytest --tb=short                  # compact tracebacks
pytest --pdb                       # drop into the debugger at the first failure
pytest --collect-only -q           # list tests without running them
```

The everyday loop is `pytest -x -q` to find the first failure, then `pytest -k that_test -vv -s` to focus on it.

## Running Python directly

```bash
python -c "from shop.pricing import quote; print(quote('A1', 3))"   # one-off experiment
python -i repro.py          # run a script, then stay in the REPL with its variables
python -m shop.cli --help   # run a module as a script (keeps imports working)
```

`python -i` is underrated: run your reproduction script, and when it finishes you're in an interactive prompt with every variable still alive to poke at.

Prefer `python -m package.module` over `python package/module.py` — running a file by path changes how imports resolve and can produce confusing `ImportError`s that have nothing to do with your bug.

## The debugger: breakpoint() and pdb

Put this line where you want to stop:

```python
breakpoint()
```

Run the code (or the test with `-s`), and you'll land in `pdb`. The commands you'll actually use:

| Command | Does |
|---|---|
| `p expr` / `pp expr` | print / pretty-print an expression |
| `n` | next line (step *over* calls) |
| `s` | step *into* the call on this line |
| `c` | continue until the next breakpoint |
| `l` / `ll` | list code around here / the whole current function |
| `w` | where: show the call stack |
| `u` / `d` | move up / down the stack to inspect callers |
| `b file.py:42` | set a breakpoint at a line |
| `interact` | open a full Python REPL in the current scope |
| `q` | quit |

`u` is the secret weapon: when a bad value reaches a function, go **up** to the caller and inspect how it was built.

Remove your `breakpoint()` calls before you submit.

## git: your safety net

Your workspace is a git repository, so you can always see exactly what you've changed:

```bash
git status                  # which files you've touched
git diff                    # your changes, line by line
git diff --stat             # just the summary
git diff -- shop/pricing.py # changes to one file
git checkout -- shop/pricing.py   # throw away your changes to one file
git log --oneline -10       # recent history
git log -p -- shop/pricing.py     # history of one file, with diffs
git stash / git stash pop   # set your changes aside and bring them back
```

Checking `git diff` before submitting is a great habit: it catches leftover debug prints and accidental edits.

## Searching from the terminal

```bash
grep -rn "could not allocate" --include="*.py" .    # recursive, with line numbers
grep -rn "def quote" .                               # find a definition
grep -rln "DEFAULT_CURRENCY" .                       # just the file names
grep -rn "status\s*=" --include="*.py" shop/         # regex: writes to .status
find . -name "*.py" -path "*pricing*"                # files by name/path
```

## A typical session

```bash
pytest -x -q                               # what's failing?
pytest -k test_cancel_refund -vv           # focus on it, see the full diff
grep -rn "def cancel" --include="*.py" .   # where does cancel live?
python -i repro.py                         # poke at the objects
# ...edit, add a breakpoint() if needed...
pytest -k test_cancel_refund               # fixed?
pytest -q                                  # did I break anything else?
git diff                                   # anything left over?
```

That's the whole toolkit. Fluency with these beats knowledge of a hundred others.
