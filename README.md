# Cold Start

**A practice gym for getting fast in unfamiliar Python codebases.**

Every session you're a contractor dropped into a new company's codebase — a ferry
booking backend, a lab-sample tracker, a tournament bracket engine, a rate-limiting
gateway. You get your bearings, a production incident lands in Slack, you find the
root cause, fix it, and prove it. If you stay late, product has a feature ticket for
you. Then a senior engineer walks you through how an expert would have done it.

Every codebase is generated fresh by an LLM and **verified by execution** before you
ever see it: the suite passes, the injected bug is caught by hidden tests (and only
by a real fix), feature tests fail before and pass after the reference
implementation, and reports quote *real* tracebacks from actually running the bug.

No points, no XP, no leaderboards. What you get instead: new territory every time, a
fog-of-war atlas of Python/engineering concepts that only lifts when you've
genuinely dealt with something, your own real speed over time, and a journal that
turns into your personal Python handbook.

→ Why it's designed this way, and how to practice for maximum learning:
[`docs/PEDAGOGY.md`](docs/PEDAGOGY.md)

## Quick start

Requirements: macOS (for the `sandbox-exec` jail; Linux works without the jail),
[uv](https://docs.astral.sh/uv/), Node 20+, git, and an
[OpenRouter](https://openrouter.ai/keys) key.

```bash
./coldstart setup        # Python envs, runtime libraries, web build
# put your key in .env:   OPENROUTER_API_KEY=sk-or-...
./coldstart              # → http://127.0.0.1:8321
```

The first client takes a few minutes to generate; after that the inbox is kept
stocked in the background.

Other commands:

```bash
./coldstart doctor                    # check the environment and key
./coldstart spend                     # what the AI has cost so far, by role
./coldstart generate --count 2        # generate clients in the foreground
./coldstart generate --focus dict-semantics --level 3
./coldstart dev                       # hot-reload backend + Vite (to hack on Cold Start)
```

## A session

1. **Desk** — your inbox of client requests. Pick one; skim the client file.
2. **Recon** (~7 min) — explore with a real editor, terminal, search, go-to-definition
   (into stdlib/library source too). Early on a teammate gives you a guided tour; later
   it's open-book, then closed-book scouting (the code hides while you answer).
3. **Incident** (~15 min) — the report arrives message by message. Write a first
   hypothesis, investigate, fix, run tests, submit. Hidden client checks grade you;
   they're never shown before you finish.
4. **Debrief** — explain the root cause in one sentence *before* the reveal. Then:
   your diff vs. the canonical fix with a code review, your investigation timeline vs.
   an expert's path, a field-guide card for the concept, links to the last time you
   met the same idea in a different codebase, and one habit to try next time.
5. **Feature ticket** (optional, ~25 min) — a Jira-style spec with acceptance tests;
   you get a line-by-line PR review focused on writing better Python.

Keyboard: `⌘P` go to file (`name:42` jumps to a line) · `⌘⇧F` search · `F12` definition ·
`⇧F12` references · `⌘⇧O` symbols · `⌘J` terminal · `⌘B` sidebar · `⌘S` save.
Click any `file.py:42` in a traceback to jump there.

## How it works

```
server/            FastAPI app (Python 3.12+)
  coldstart/
    generation/    the case pipeline: architect → implement → verify/repair →
                   incident (+verify) → report → feature ∥ recon → QA → assemble
    learning/      scheduler (spaced repetition, interleaving, adaptive level),
                   engagements, grading, AI debriefs, mentor
    runtime/       git-backed workspaces, jedi code intelligence, search, PTY terminal
    sandbox.py     sandbox-exec jail + pytest runner (JUnit parsing)
    llm.py         OpenRouter client: streaming, prompt caching, per-call cost ledger
web/               React + TypeScript + Monaco + xterm.js + Tailwind
content/           157-concept atlas, 153 client domains, 10 playbook articles
runtime/           libraries available to generated codebases (.runtime venv)
data/              (git-ignored) generated cases, workspaces, your progress DB
```

**Models.** Every role (architect, implementer, designer, writer, reviewer, mentor,
grader) can point at any OpenRouter model from Settings. Default is max quality
(`anthropic/claude-opus-5.5` everywhere, ≈ $1–2 per client); *Balanced* and
*Economy* presets trade quality for cost. The codebase is prompt-cached, so a mentor
conversation pays for it once. Background generation pauses when the key's remaining
credit drops below a floor you choose.

**Safety.** Generated code only ever runs inside `sandbox-exec` (macOS): no outbound
network, file writes limited to the case's scratch copy or your workspace — that
includes the in-app terminal. The server binds to localhost and rejects requests
with a foreign `Host`, mutations without the app's custom header, and terminal
WebSockets from other origins. Your API key never leaves the server.

## Development

```bash
cd server && uv run --extra dev pytest        # server tests
cd web && npm run typecheck && npm run build  # frontend
```

Generated cases contain their own solutions, so `data/` is git-ignored — don't
browse `data/library/` unless you want spoilers.
