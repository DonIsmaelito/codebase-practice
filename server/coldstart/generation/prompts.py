"""Prompt templates for the case-generation pipeline.

Every stage shares one principle: realistic, fair, instructive. The designer
stages (incident / feature / recon / QA) share an identical system prompt and
cached codebase block so the codebase is only paid for once per case.
"""

from __future__ import annotations

import json
from typing import Any

from .. import llm

RUNTIME_LIBS = [
    "pydantic", "fastapi", "httpx", "sqlalchemy", "numpy", "pandas", "click", "attrs",
    "python-dateutil", "freezegun", "jinja2", "pyyaml", "networkx", "hypothesis", "pytest-asyncio",
]

FIDELITY = {
    "failing_test": (
        "CI is red. A teammate wrote a regression test that reproduces a customer-reported "
        "problem, and it fails. The report links the failing test and pastes its pytest output."
    ),
    "traceback": (
        "An exception in production. The report includes the real traceback and what the user "
        "was doing when it happened."
    ),
    "repro_steps": (
        "QA filed a ticket with precise reproduction steps and expected vs. actual results. "
        "Nothing crashes; the system produces a wrong result."
    ),
    "user_report": (
        "A customer complaint forwarded by support, with concrete but non-technical details "
        "(amounts, names, times). The learner has to translate it into a code path."
    ),
    "logs": (
        "An on-call engineer's message with log excerpts and a metric or two. The symptom is "
        "visible in the logs; the cause is not."
    ),
    "vague": (
        "A vague thread ('some customers see wrong totals, sometimes') with one or two concrete "
        "data points buried in it."
    ),
    "misleading": (
        "A thread where a well-meaning teammate confidently proposes a wrong theory (e.g. 'it "
        "must be the cache'), alongside real data points that point elsewhere."
    ),
    "metrics": (
        "A performance/resource regression reported via metrics (latency, memory, query counts) "
        "with a timeline. The root cause is an efficiency problem."
    ),
}

RECON_MODES = {
    "guided": (
        "GUIDED — the learner is new to unfamiliar codebases. They get the guided tour up front, "
        "then answer questions with the code open. The briefing should include a short, friendly "
        "checklist of where to start."
    ),
    "open": (
        "OPEN-BOOK — the learner explores on their own (the tour is available only as a hint), "
        "then answers questions with the code open, against a timer."
    ),
    "closed": (
        "CLOSED-BOOK SCOUTING — the learner gets a few minutes to explore, then the code is hidden "
        "and they answer from memory. Questions should reward building a real mental model "
        "(structure, flows, responsibilities), not memorizing trivia."
    ),
}


def learner_description(level: int) -> str:
    if level <= 2:
        return (
            "Knows Python syntax and basic data structures but has little experience in unfamiliar "
            "multi-file codebases, which feel intimidating. Keep the architecture clean and "
            "navigable with meaningful names; the challenge must come from realism and the "
            "concept, never from obfuscation. Early wins matter."
        )
    if level <= 4:
        return (
            "Comfortable reading small codebases; building speed at tracing a flow across several "
            "modules and at forming good hypotheses from bug reports."
        )
    if level <= 6:
        return (
            "Navigates mid-sized codebases confidently; ready for bugs whose symptoms surface far "
            "from their cause and for features that require understanding existing abstractions."
        )
    return (
        "Experienced and fast. Wants subtle, realistic bugs in larger systems, red herrings, "
        "imperfect information, and features that demand good design judgment."
    )


def concept_block(c: dict[str, Any], label: str) -> str:
    lines = [f"{label}: {c['name']} (id: {c['id']}) — {c['summary']}"]
    if c.get("bug_patterns"):
        lines.append("  Typical real-world manifestations:")
        lines += [f"  - {p}" for p in c["bug_patterns"]]
    if c.get("feature_patterns"):
        lines.append("  Feature ideas that exercise it:")
        lines += [f"  - {p}" for p in c["feature_patterns"]]
    if c.get("beacons"):
        lines.append("  Beacons experts notice when skimming: " + "; ".join(c["beacons"]))
    return "\n".join(lines)


# --- 1. architect --------------------------------------------------------------

ARCHITECT_SYSTEM = """You are a principal engineer who designs realistic codebases for Cold Start, a practice gym where a developer is dropped into an unfamiliar Python codebase — as a contractor hired by the company — to get fast at understanding code, debugging production incidents, and shipping features.

Your designs feel like real software built by a real team at a real company: specific business rules, domain vocabulary, sensible architecture, and a little real-world texture. Never tutorial-like, never generic "Foo/Bar" code."""


def architect_messages(spec: dict[str, Any]) -> list[llm.Message]:
    d = spec["domain"]
    flavor = "\n".join(f"- {c['name']}: {c['summary']}" for c in spec["flavor_concepts"]) or "- (none)"
    user = f"""Design the codebase for a new engagement.

DOMAIN: {d['name']} — {d['flavor']}
SHAPE: choose one of {', '.join(d['shapes'])} (whichever makes the most natural codebase here)
LEARNER: {learner_description(spec['level'])}
SIZE: {spec['files'][0]}–{spec['files'][1]} Python modules (excluding tests and __init__.py), about {spec['loc'][0]}–{spec['loc'][1]} non-blank lines of non-test code, plus a pytest suite.
LIBRARIES: Python 3.12+ standard library plus only these third-party packages: {', '.join(RUNTIME_LIBS)}. {spec['library_hint']}
STYLE / VINTAGE: {spec['vintage']}

{concept_block(spec['incident_concept'], 'INCIDENT CONCEPT (a separate step will later inject a realistic bug of this kind — you only plan where it will live)')}

{concept_block(spec['feature_concept'], 'FEATURE CONCEPT (a later feature ticket will exercise this)')}

FLAVOR CONCEPTS (should appear naturally somewhere, used correctly):
{flavor}

INCIDENT REPORT STYLE: {spec['fidelity']} — {FIDELITY[spec['fidelity']]}
DISTANCE: the root cause should sit about {spec['hops']} call(s) away from where the symptom becomes visible.

Hard constraints for the codebase:
- Runs fully offline: no real network, no external services. Use in-memory repositories/fakes, sqlite3 (in-memory or temp files), or local files instead. No subprocess/shelling out.
- Deterministic and testable: inject clocks/ID generators/random seeds where time or randomness matters. The whole test suite runs in under 10 seconds.
- The planned incident location must be on the code path that produces the planned symptom, with enough surrounding code for a real investigation.

Reply with ONLY a JSON object:
{{
  "company": {{
    "name": "...", "tagline": "...", "industry": "...",
    "blurb": "2-3 sentences: who they are, their scale, why this software matters to them",
    "team": [{{"name": "...", "role": "...", "voice": "how they write (e.g. terse, emoji-heavy, over-explains, formal)"}}]
  }},
  "repo": {{
    "name": "kebab-case-repo-name",
    "package": "python_package_name",
    "shape": "service|cli|library|pipeline|worker|simulation|interpreter",
    "summary": "what the codebase does, 2-3 sentences",
    "architecture": "markdown: the modules and how data flows between them — precise enough for another engineer to implement",
    "entry_points": ["how it is run or used"],
    "files": [{{"path": "pkg/module.py", "purpose": "...", "key_symbols": ["ClassName", "function_name(args) -> ret"], "approx_lines": 120}}],
    "test_files": [{{"path": "tests/test_x.py", "covers": "..."}}],
    "libraries": ["only third-party packages actually used"],
    "conventions": "style rules the team follows (e.g. 'money is Decimal', 'services take a Clock', 'errors subclass LedgerError')",
    "texture": "1-3 realistic touches of age/team history (an older module in a different style, a TODO referencing a ticket, a README section slightly out of date)"
  }},
  "incident_plan": {{
    "location": "file + function where the bug will later be injected",
    "substrate": "the correct behavior/code that must exist there (the implementer writes it correctly; the bug is injected later)",
    "symptom": "what goes wrong, observed from outside, once the bug is injected",
    "why_tests_miss_it": "why the existing tests would not catch it",
    "reporter": "name of the team member who reports it"
  }},
  "feature_plan": {{
    "title": "...", "summary": "...", "touches": ["files that would change"], "reporter": "name (usually a PM or lead)"
  }},
  "recon_focus": ["3-5 things a newcomer must understand to be effective in this codebase"]
}}

The team: 3-4 people with diverse, realistic names; include an engineering lead and at least one non-engineer (support, ops, or product)."""
    return [{"role": "system", "content": ARCHITECT_SYSTEM}, {"role": "user", "content": user}]


# --- 2. implementer ------------------------------------------------------------

IMPLEMENTER_SYSTEM = """You are a senior Python engineer. You write clean, working, production-quality Python that reads as if a real team wrote it over a couple of years. You implement the design you're given precisely, and every test you write passes."""

REALISM_RULES = """REALISM RULES — this code will be read by someone learning to navigate real codebases:
- Write like 3-4 engineers built this over ~2 years. Each module is internally consistent; modules may differ slightly in style where the design's "texture" calls for it.
- Comments explain WHY, not WHAT. Docstrings on public classes/functions where a teammate would want one — not on every trivial helper. At most about one TODO/NOTE/FIXME per 150 lines, referencing a plausible ticket id (e.g. "# TODO(PAY-212): ..."). Never narrate ("# Step 1: loop over items"), never mention exercises/training/learners, and never allude to bugs.
- Real domain logic: business rules, validation, statuses, edge cases, meaningful errors (a small exceptions module is typical). Use `logging.getLogger(__name__)` where a real service would log.
- Tests: pytest, shared fixtures in tests/conftest.py, descriptive test names. Cover the main flows well but NOT exhaustively — real suites have gaps. Deterministic (no sleeps, no wall-clock time, no network), whole suite < 10s.
- Everything must actually run and every test must pass.
- README.md: what it is, how to run it, a layout overview, a couple of dev notes. Realistic, not exhaustive.
- Do NOT write pyproject.toml, setup.py, requirements files, CI configs, or Dockerfiles — the harness adds packaging. Tests import the package from the repo root: `from {package}.module import Thing`.
- Only the standard library plus: {libs}."""


def implementer_messages(spec: dict[str, Any], design: dict[str, Any]) -> list[llm.Message]:
    public_design = {
        "company": design["company"],
        "repo": design["repo"],
        "must_exist_and_work_correctly": design["incident_plan"]["substrate"],
        "feature_to_leave_room_for": design["feature_plan"]["summary"],
    }
    package = design["repo"]["package"]
    rules = REALISM_RULES.format(package=package, libs=", ".join(design["repo"].get("libraries") or []) or "(no third-party packages)")
    user = f"""Implement this codebase completely.

<design>
{json.dumps(public_design, indent=2)}
</design>

LEARNER CONTEXT (why this matters): {learner_description(spec['level'])}
SIZE TARGET: {spec['files'][0]}–{spec['files'][1]} modules, ~{spec['loc'][0]}–{spec['loc'][1]} non-blank lines of non-test code. Hitting the size matters less than realism and correctness.

{rules}

Do not implement the future feature ("feature_to_leave_room_for") — it just shouldn't be architecturally impossible.

Output every file as:
<file path="relative/path.py">
...complete file content...
</file>

Include every package `__init__.py`, tests/conftest.py, the test modules, README.md, and any small data fixtures. Output nothing but the file blocks."""
    return [{"role": "system", "content": IMPLEMENTER_SYSTEM}, {"role": "user", "content": user}]


def repair_message(report_summary: str, extra: str = "") -> llm.Message:
    return {
        "role": "user",
        "content": f"""The code doesn't pass verification yet.

<verification>
{report_summary}
</verification>
{extra}
Fix it. Prefer fixing the code to match the design's intent; fix a test only if the test itself is wrong. Keep all realism rules.

Reply with <edit path="..."><search>exact existing lines</search><replace>new lines</replace></edit> blocks (the search text must match the current file exactly and be unique), or a complete <file path="..."> block when a file needs many changes. Output only edit/file blocks.""",
    }


# --- shared designer prefix (cached) ---------------------------------------------

DESIGNER_SYSTEM = """You are the exercise designer for Cold Start, a practice gym where a developer is dropped into an unfamiliar Python codebase — as a contractor hired by the company — to get fast at understanding code, debugging, and shipping features. You are both a superb Python engineer and a superb teacher.

Your exercises must be:
- Realistic: everything feels like real work at a real company. Bugs are plausible mistakes by competent engineers, not sabotage.
- Fair: everything needed to succeed is discoverable from the codebase and the materials the learner gets. Tests only check behavior that is specified or clearly implied.
- Instructive: each exercise teaches a transferable principle, and your explanations make it click.

Follow the requested output format exactly."""


def designer_prefix(case_context: str, repo_block: str) -> list[llm.Message]:
    """System + the cached codebase. Task instructions are appended as a 2nd content part."""
    return [
        {"role": "system", "content": DESIGNER_SYSTEM},
        {"role": "user", "content": [llm.cached(f"{case_context}\n\n<codebase>\n{repo_block}\n</codebase>")]},
    ]


def with_task(prefix: list[llm.Message], task: str) -> list[llm.Message]:
    msgs = [dict(m) for m in prefix]
    msgs[-1] = {"role": "user", "content": [*prefix[-1]["content"], llm.text_part(task)]}
    return msgs


def case_context(spec: dict[str, Any], design: dict[str, Any]) -> str:
    return f"""<engagement>
<company>{json.dumps(design['company'], indent=1)}</company>
<repo_summary>{design['repo']['summary']}</repo_summary>
<architecture>
{design['repo']['architecture']}
</architecture>
<learner level="{spec['level']}">{learner_description(spec['level'])}</learner>
</engagement>"""


# --- 3. incident -----------------------------------------------------------------

def incident_task(spec: dict[str, Any], design: dict[str, Any]) -> str:
    failing = spec["fidelity"] == "failing_test"
    package = design["repo"]["package"]
    reg_block = (
        f"""
REGRESSION TEST (report style is failing_test):
Also output <regression_test path="tests/test_regression_<short_slug>.py">...</regression_test>: a SHORT test module (1-2 tests) that a teammate wrote to reproduce the customer's problem. It must FAIL with your bug and PASS on the original code. It gets added to the learner's repo and its failing output is quoted in the report. It should test the symptom, not point at the cause.
"""
        if failing else ""
    )
    return f"""TASK: Design the production incident for this engagement.

{concept_block(spec['incident_concept'], 'INCIDENT CONCEPT')}

ARCHITECT'S PLAN: {json.dumps(design['incident_plan'])}
REPORT STYLE: {spec['fidelity']} — {FIDELITY[spec['fidelity']]}
DISTANCE: the symptom should surface about {spec['hops']} call(s) away from the root cause.

THE BUG
1. A realistic mistake a competent engineer could make here — the kind that passes code review — and a genuine instance of the INCIDENT CONCEPT. If the planned location isn't the best fit, choose a better one.
2. Introduce it with 1-3 small search/replace edits (typically 1-12 changed lines) against the CURRENT code. The result must look like it was always written that way: same style and naming, no comments or names that hint at the problem. Rewriting a small region is fine if that's what makes the mistake natural (e.g. a "cleanup" that introduced it).
3. Every existing test in tests/ must still PASS with the bug present{' (your new regression test is the exception)' if failing else ''} — real bugs escape test suites. If an existing test would catch your bug, choose a different variant.
4. The symptom must be observable through public behavior (return values, raised errors, persisted state, output) and consistent with the report style.

HIDDEN TESTS (verify the learner's fix)
- A pytest module that PASSES on the original code and FAILS with your bug.
- Test behavior through public APIs, the way the report describes it — not private helpers and not the specific shape of your fix. ANY correct fix must pass. Don't assert on log text or exact exception messages unless the report quotes them.
- 2-5 tests: the reported scenario, plus 1-3 closely related cases of the same root cause so that symptom-only patches (special-casing the reported input) fail.
- Deterministic, fast, `from {package}... import ...`; you may use fixtures from tests/conftest.py.

REPRO SCRIPT
- A standalone script run from the repo root that exercises the reported scenario and prints the observable symptom (or lets the exception propagate). Its REAL output is quoted in the incident report, so print things the way the app/logs/a REPL session would show them. No asserts, under 60 lines.
{reg_block}
OUTPUT FORMAT (exactly these blocks):

<bug_edit path="relative/path.py">
<search>
exact existing lines (unique in the file)
</search>
<replace>
the buggy version
</replace>
</bug_edit>
(repeat bug_edit if needed)

<hidden_tests>
...pytest module...
</hidden_tests>

<repro>
...python script...
</repro>
{'<regression_test path="tests/test_regression_....py">...</regression_test>' if failing else ''}
<meta>
{{
  "title": "internal name for this incident",
  "inbox_subject": "subject line the way the client would write it — symptom only, never the cause (<= 70 chars)",
  "symptom": "what is observed, 1-2 sentences",
  "root_cause": "1-2 precise sentences",
  "root_cause_file": "path",
  "root_cause_symbol": "function or Class.method",
  "files_involved": ["files on the path from symptom to cause, in order"],
  "mechanism": "markdown, 120-250 words: the general Python/engineering principle first, then how it plays out here. Include a minimal standalone ```python snippet demonstrating the trap.",
  "fix": "markdown: what a correct fix looks like, one alternative that also works, and what a symptom-only patch would look like and why it's worse",
  "expert_path": [{{"step": "concrete action (file, search, command)", "why": "the reasoning behind it"}}],
  "hints": [
    "1 NUDGE: a question that redirects attention to the most telling evidence in the report",
    "2 AREA: which part of the system to investigate and why",
    "3 LOCATION: the file and function",
    "4 MECHANISM: what exactly goes wrong there — stop short of writing the fix"
  ],
  "concept_card": {{
    "headline": "memorable one-line principle (<= 90 chars)",
    "explanation": "markdown, 80-150 words, general (not about this codebase)",
    "example": "minimal python snippet: the trap, then the fix",
    "spot_it": ["2-3 beacons for recognizing this in any codebase"],
    "elsewhere": ["2-3 other real-world places this same mistake shows up"]
  }},
  "recall": {{"q": "a retrieval-practice question about the general principle", "a": "concise answer"}},
  "par_minutes": 15
}}
</meta>

expert_path should have 4-7 steps from reading the report to confirming the root cause."""


# --- 4. incident report -----------------------------------------------------------

WRITER_SYSTEM = """You write realistic workplace communication for Cold Start exercises: Slack threads, emails, Jira tickets, pager alerts. People sound like real people with distinct voices. Details are concrete (names, IDs, timestamps, amounts). You never reveal information the characters wouldn't know."""


def report_messages(spec: dict[str, Any], design: dict[str, Any], meta: dict[str, Any],
                    repro_output: str, failing_test_output: str | None) -> list[llm.Message]:
    misleading = spec["fidelity"] == "misleading"
    reporter = design["incident_plan"].get("reporter") or design["company"]["team"][0]["name"]
    evidence = f"<repro_output>\n{repro_output.strip()[:5000]}\n</repro_output>"
    if failing_test_output:
        evidence += f"\n<failing_ci_output>\n{failing_test_output.strip()[:5000]}\n</failing_ci_output>"
    user = f"""Write the incident report the contractor (the learner) receives from {design['company']['name']}.

COMPANY: {json.dumps({k: design['company'][k] for k in ('name', 'tagline', 'industry', 'blurb')})}
TEAM (use their voices): {json.dumps(design['company']['team'])}
REPORTER: {reporter}
REPORT STYLE: {spec['fidelity']} — {FIDELITY[spec['fidelity']]}

WHAT'S ACTUALLY HAPPENING (for you only — the characters do NOT know the cause):
symptom: {meta.get('symptom')}
root cause: {meta.get('root_cause')}

REAL EVIDENCE captured by actually running the scenario — quote from it where a person would paste output; don't invent different numbers, IDs, or tracebacks than what's shown:
{evidence}

Write 2-5 messages in ONE channel that fits the style (Slack thread, email chain, Jira ticket + comments, or pager alert + Slack follow-up). Keep it tight — like a real thread, not an essay. The last message hands the problem to the contractor with a clear ask.
Never state or hint at the root cause.{' Include one teammate who confidently proposes a plausible but WRONG theory; real data points elsewhere in the thread should point in the right direction.' if misleading else ''}

Reply with ONLY a JSON object:
{{"channel": "slack|email|jira|pager", "title": "thread or ticket title", "messages": [{{"from": "Name", "role": "Role", "time": "e.g. 09:42 or Tue 14:05", "body": "markdown"}}], "ask": "one-line summary of what they need from you"}}"""
    return [{"role": "system", "content": WRITER_SYSTEM}, {"role": "user", "content": user}]


# --- 5. feature ---------------------------------------------------------------------

FEATURE_SCOPE = {1: "15-40", 2: "20-50", 3: "30-70", 4: "40-90", 5: "50-110", 6: "60-130"}


def feature_task(spec: dict[str, Any], design: dict[str, Any]) -> str:
    package = design["repo"]["package"]
    scope = FEATURE_SCOPE.get(spec["level"], "80-160")
    return f"""TASK: Write this engagement's feature ticket, a reference implementation, and its tests.

{concept_block(spec['feature_concept'], 'FEATURE CONCEPT')}

ARCHITECT'S PLAN: {json.dumps(design['feature_plan'])}

REQUIREMENTS
1. A realistic, useful feature this company would actually want that naturally exercises the FEATURE CONCEPT. Scope: about {scope} lines of new/changed code for a strong engineer. Adjust the architect's idea if a better one fits.
2. The ticket must fully specify every behavior the tests check. Its "interface" section gives exact names, signatures, return types, and error behavior for everything tests call. The learner must never have to guess something a test asserts.
3. Reference implementation as <ref_edit> search/replace blocks against the CURRENT code (plus <ref_file path="..."> for new files). Follow the codebase's conventions. Existing tests must keep passing.
4. <acceptance_tests path="tests/test_<feature_slug>.py">: 2-4 straightforward tests of the main behavior, given to the learner up front like QA's acceptance checks.
5. <hidden_tests>: 3-7 more tests of the ticket's edge cases and acceptance criteria. Every assertion must follow from the ticket text. No private helpers, internal structure, or log text.
6. All tests deterministic and fast, importing `from {package}... import ...` (fixtures from tests/conftest.py are available).

OUTPUT FORMAT (exactly these blocks):

<ref_edit path="relative/path.py">
<search>
exact existing lines
</search>
<replace>
new lines
</replace>
</ref_edit>
<ref_file path="relative/new_module.py">
...only for brand-new files...
</ref_file>

<acceptance_tests path="tests/test_<feature_slug>.py">
...
</acceptance_tests>

<hidden_tests>
...
</hidden_tests>

<meta>
{{
  "title": "FEAT-###: short title",
  "inbox_subject": "subject line as the author would write it (<= 70 chars)",
  "author": "team member name",
  "ticket": {{
    "background": "markdown in the author's voice: the business context — why now, who asked (2-4 sentences)",
    "requirements": ["..."],
    "acceptance": ["precise, testable criteria"],
    "interface": "markdown: the exact public API to add or change",
    "examples": "markdown: concrete input -> output examples",
    "out_of_scope": ["..."],
    "notes": "a teammate-style pointer or two (e.g. 'X already does something similar')"
  }},
  "expert_path": [{{"step": "...", "why": "..."}}],
  "hints": [
    "1 ORIENT: where in the codebase this belongs / what existing code to mirror",
    "2 APPROACH: the overall approach",
    "3 CORE: the key data structure or algorithm and why it fits",
    "4 SKETCH: a near-solution sketch in words (no full code)"
  ],
  "review_focus": ["what a reviewer should check in the learner's implementation: edge cases, idioms, complexity, conventions"],
  "concept_card": {{
    "headline": "...", "explanation": "markdown 80-150 words, general", "example": "python snippet",
    "spot_it": ["..."], "elsewhere": ["..."]
  }},
  "recall": {{"q": "...", "a": "..."}},
  "par_minutes": 25
}}
</meta>"""


# --- 6. recon ----------------------------------------------------------------------

def recon_task(spec: dict[str, Any], design: dict[str, Any], incident_meta: dict[str, Any]) -> str:
    return f"""TASK: Design the onboarding ("recon") for this engagement. The learner explores the codebase BEFORE the incident is revealed.

RECON MODE: {RECON_MODES[spec['recon_mode']]}
FOCUS (from the architect): {json.dumps(design.get('recon_focus', []))}
LEARNER: {learner_description(spec['level'])}

DO NOT SPOIL THE INCIDENT. Root cause (for you only): {incident_meta.get('root_cause')} in {incident_meta.get('root_cause_file')}.
No question may reveal or hint at it, and tour notes about that code must stay neutral. (The tour may pass through those files — that's realistic.)

Reply with ONLY a JSON object:
{{
  "briefing": {{"from": "team member name", "role": "...", "body": "markdown: a warm, realistic welcome message from the team — what the system does, what matters, where to start{' — include a short checklist of 3-5 things to find' if spec['recon_mode'] == 'guided' else ''}"}},
  "tour": [
    {{"path": "file path", "anchor": "one exact line of code copied from that file, unique within it, where the stop begins", "title": "short title", "note": "1-3 sentences, like a senior engineer showing you around: what this is and why it matters"}}
  ],
  "map": {{
    "summary": "one paragraph: the mental model an expert has of this system",
    "components": [{{"name": "...", "paths": ["..."], "role": "one sentence"}}],
    "flows": [{{"name": "e.g. Booking a seat", "steps": ["cli.book", "BookingService.create", "SeatMap.allocate", "Repo.save"]}}]
  }},
  "questions": [
    {{"id": "q1", "kind": "locate|trace|explain|impact|predict", "prompt": "...", "answer": "reference answer", "key_points": ["what a correct answer must mention"]}}
  ]
}}

TOUR: 5-8 stops in a sensible reading order (entry point → core model → the main flow → supporting pieces → the tests). Anchors must be copied exactly from the file.

QUESTIONS: exactly 4 — one "locate" (where does X happen? answer = file + function), one "trace" (sequence of calls/modules when Y happens), one "explain" or "impact" (responsibility/invariant, or what else a change would affect), and one "predict".
A "predict" question also has "setup" (Python statements run from the repo root: imports and object construction) and "expr" (one expression). The harness executes it and uses the REAL repr as the answer — choose something deterministic with a short repr (< 80 chars) that rewards reading the code carefully (a rounding rule, a default, a normalization, an ordering). Avoid code involved in the incident. The prompt should show the call so the learner knows exactly what's evaluated."""


# --- 7. QA -----------------------------------------------------------------------------

def qa_task(materials: str) -> str:
    return f"""TASK: You are the final QA reviewer for this exercise. Review the materials against the codebase and decide whether it ships.

HOW THE EXERCISE WORKS (read carefully): the <codebase> above is the ORIGINAL, CORRECT code. The exercise deliberately INJECTS a bug by applying <bug_diff> to it; the learner receives the original code WITH the bug_diff applied (plus the report), and must find and undo the bug. So the bug_diff is SUPPOSED to turn correct code into buggy code — that is not a problem. Hidden tests are supposed to pass on the original and fail on the buggy version (this was verified by running them).

{materials}

Check:
1. LEAKAGE — Does the report, ticket, briefing, tour, any code comment, identifier, docstring, or README give away the incident's root cause?
2. FAIRNESS — Can a careful learner get from the report to the root cause using the codebase? Would any correct fix pass the hidden incident tests (no over-specific assertions)? Does every feature-test assertion follow from the ticket text?
3. REALISM — Is the bug a plausible human mistake? Do the messages read like real people at this company?
4. ACCURACY — Are the explanations, hints, concept cards, and recon answers technically correct?

Reply with ONLY a JSON object:
{{
  "verdict": "ship" | "patch" | "reject",
  "issues": [{{"severity": "high|medium|low", "area": "report|bug|hidden_tests|feature|recon|explanations", "problem": "...", "fix": "..."}}],
  "patches": {{
    "report_messages": null,
    "feature_ticket": null,
    "recon_questions": null,
    "incident_meta": null
  }}
}}
"patches" fields: null, or a full replacement in the same schema as the materials (report_messages = list of messages; feature_ticket = ticket object; recon_questions = questions list; incident_meta = an object containing only the meta fields to replace, e.g. hints or mechanism).
Use "patch" when text changes fix the issues; "reject" only for problems text can't fix (implausible bug, hidden tests that reject valid fixes, code that leaks the answer). Minor nitpicks → "ship"."""
