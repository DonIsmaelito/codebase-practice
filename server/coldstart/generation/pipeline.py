"""The case-generation pipeline.

    architect → implement → verify/repair → incident (+verify) → report
              → feature (+verify) ∥ recon (+verify) → QA → assemble

Nothing reaches the learner unless it was executed: the clean codebase passes
its own suite, hidden incident tests pass on clean code and fail on the buggy
code, feature tests fail before and pass after the reference implementation,
and "predict" recon answers are the real repr() of running the code.
"""

from __future__ import annotations

import asyncio
import json
import keyword
import logging
import random
import re
import shutil
import sys
import textwrap
import time
from pathlib import Path
from typing import Any

from .. import config, db, llm, sandbox
from . import files as F
from . import prompts as P
from . import safety

log = logging.getLogger("coldstart.pipeline")

HIDDEN_INCIDENT = "tests/test_zz_hidden_incident.py"
HIDDEN_FEATURE = "tests/test_zz_hidden_feature.py"

STAGES = {
    "architect": "Meeting the client",
    "implement": "Their engineers are writing the code",
    "verify": "Running their test suite",
    "incident": "Something breaks in production",
    "report": "The pager goes off",
    "feature": "Product is writing a ticket",
    "recon": "Preparing your onboarding",
    "qa": "Final QA pass",
    "assemble": "Packing the case file",
}


class PipelineError(RuntimeError):
    pass


class Pipeline:
    def __init__(self, case_id: str, spec: dict[str, Any]):
        self.case_id = case_id
        self.spec = spec
        self.dir = config.LIBRARY_DIR / case_id
        self.work = self.dir / "work"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.work.mkdir(exist_ok=True)
        self.timings: dict[str, float] = {}
        self._repo_name: str | None = None
        self._log = (self.dir / "gen.log").open("a")

    # --- bookkeeping ------------------------------------------------------------

    def note(self, msg: str) -> None:
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        self._log.write(line + "\n")
        self._log.flush()
        log.info("%s %s", self.case_id, msg)

    def stage(self, key: str, detail: str = "", progress: float | None = None) -> None:
        db.run(
            "UPDATE cases SET stage = ? WHERE id = ?",
            db.dumps({"key": key, "label": STAGES.get(key, key), "detail": detail,
                      "progress": progress, "ts": time.time()}),
            self.case_id,
        )

    def transcript(self, stage: str, messages: list[llm.Message], output: str) -> None:
        last = messages[-1]["content"]
        if isinstance(last, list):
            last = last[-1].get("text", "")
        with (self.dir / "transcript.jsonl").open("a") as fh:
            fh.write(json.dumps({"stage": stage, "ts": time.time(), "prompt_tail": last[-6000:],
                                 "output": output}) + "\n")

    async def call(self, stage: str, messages: list[llm.Message], *, role: str, max_tokens: int,
                   reasoning: str | None = None, expected_chars: int | None = None) -> llm.Completion:
        last = [0.0]

        def progress(chars: int) -> None:
            now = time.monotonic()
            if expected_chars and now - last[0] >= 1.0:  # at most one DB write per second
                last[0] = now
                self.stage(stage, f"{chars // 1000}k chars", min(0.97, chars / expected_chars))

        started = time.monotonic()
        c = await llm.complete(messages, role=role, max_tokens=max_tokens, reasoning=reasoning,
                               case_id=self.case_id, on_progress=progress if expected_chars else None)
        self.timings[stage] = self.timings.get(stage, 0) + time.monotonic() - started
        self.note(f"{stage}: {c.model} in={c.prompt_tokens} (cached {c.cached_tokens}) "
                  f"out={c.completion_tokens} ${c.cost_usd:.3f} {c.duration_s:.0f}s finish={c.finish_reason}")
        self.transcript(stage, messages, c.text)
        return c

    # --- stages -----------------------------------------------------------------

    async def architect(self) -> dict[str, Any]:
        self.stage("architect")
        msgs = P.architect_messages(self.spec)
        for attempt in range(3):
            c = await self.call("architect", msgs, role="architect", max_tokens=16000, reasoning="medium")
            try:
                design = llm.parse_json(c.text)
                self._validate_design(design)
                return design
            except (ValueError, KeyError, TypeError) as err:
                self.note(f"architect output rejected: {err}")
                msgs = msgs + [
                    {"role": "assistant", "content": c.text},
                    {"role": "user", "content": f"That design is invalid: {err}. Reply with the corrected JSON only."},
                ]
        raise PipelineError("architect never produced a valid design")

    def _validate_design(self, d: dict[str, Any]) -> None:
        repo = d["repo"]
        pkg = re.sub(r"[^a-z0-9_]", "_", str(repo["package"]).lower()).strip("_")
        if not pkg or pkg[0].isdigit() or keyword.iskeyword(pkg):
            raise ValueError(f"bad package name {repo['package']!r}")
        taken = set(sys.stdlib_module_names) | {"tests", "test", "app", "pydantic", "fastapi", "httpx",
                                                "sqlalchemy", "numpy", "pandas", "click", "attrs",
                                                "dateutil", "jinja2", "yaml", "networkx", "hypothesis"}
        if pkg in taken:
            raise ValueError(f"package name {pkg!r} shadows an existing module; choose a product-specific name")
        original = str(repo["package"])
        if original != pkg:
            for f in repo.get("files") or []:
                if str(f.get("path", "")).startswith(original + "/"):
                    f["path"] = pkg + f["path"][len(original):]
        repo["package"] = pkg
        repo["libraries"] = [l for l in (repo.get("libraries") or []) if l in P.RUNTIME_LIBS]
        if not d["company"]["name"] or len(d["company"].get("team") or []) < 2:
            raise ValueError("company needs a name and a team of 3-4 people")
        if not repo.get("files"):
            raise ValueError("repo.files is empty")
        for key in ("incident_plan", "feature_plan"):
            if not isinstance(d.get(key), dict):
                raise ValueError(f"missing {key}")

    async def implement(self, design: dict[str, Any]) -> tuple[dict[str, str], list[llm.Message]]:
        self.stage("implement", progress=0.0)
        msgs = P.implementer_messages(self.spec, design)
        expected = max(40_000, self.spec["loc"][1] * 2 * 45)  # rough chars for code + tests + README
        c = await self.call("implement", msgs, role="implementer", max_tokens=64000,
                            reasoning="low", expected_chars=expected)
        repo_files = F.parse_files(c.text)
        if not repo_files:
            raise PipelineError("implementer produced no files")
        repo_files.update(self._harness_files(design))
        convo = msgs + [{"role": "assistant", "content": [llm.cached(c.text)]}]
        return repo_files, convo

    def _harness_files(self, design: dict[str, Any]) -> dict[str, str]:
        repo = design["repo"]
        deps = ", ".join(json.dumps(l) for l in repo.get("libraries") or [])
        version = random.choice(["0.9.3", "1.4.0", "1.12.2", "2.1.7", "0.18.1", "3.0.2"])
        summary = " ".join(str(repo.get("summary", "")).split())[:200]
        return {
            "pyproject.toml": textwrap.dedent(f"""\
                [project]
                name = {json.dumps(repo['name'])}
                version = "{version}"
                description = {json.dumps(summary)}
                requires-python = ">=3.12"
                dependencies = [{deps}]

                [tool.pytest.ini_options]
                pythonpath = ["."]
                testpaths = ["tests"]
                asyncio_mode = "auto"
                asyncio_default_fixture_loop_scope = "function"
                """),
            ".gitignore": "__pycache__/\n*.pyc\n.pytest_cache/\n.venv/\n*.egg-info/\n",
        }

    async def verify_and_repair(self, design: dict[str, Any], repo_files: dict[str, str],
                                convo: list[llm.Message]) -> dict[str, str]:
        clean = self.work / "clean"
        for round_no in range(4):
            self.stage("verify", f"round {round_no + 1}")
            if clean.exists():
                shutil.rmtree(clean)
            F.write_repo(clean, repo_files)
            problems = safety.scan_repo(repo_files)
            pkg = design["repo"]["package"]
            if not (clean / pkg / "__init__.py").exists():
                problems.append(f"missing package {pkg}/__init__.py")
            report = await sandbox.run_pytest(clean)
            stats = F.repo_stats(repo_files)
            self.note(f"verify round {round_no + 1}: {report.passed} passed, {report.failed} failed, "
                      f"{report.errors} errors; {stats}; problems={problems}")
            if report.ok and report.total >= 3 and not problems:
                return repo_files
            if round_no == 3:
                break
            summary = report.summary()
            if report.ok and report.total < 3:
                summary += "\nThe suite has fewer than 3 tests — add realistic tests for the main flows."
            extra = ("\nStatic checks also found problems to fix:\n" + "\n".join(f"- {p}" for p in problems)) if problems else ""
            convo = convo + [P.repair_message(summary, extra)]
            c = await self.call("verify", convo, role="implementer", max_tokens=32000, reasoning="low")
            convo = convo + [{"role": "assistant", "content": c.text}]
            for rel, body in F.parse_files(c.text).items():
                repo_files[rel] = body
            edits = F.parse_edits(c.text)
            if edits:
                F.write_repo(clean, repo_files)
                try:
                    F.apply_edits(clean, edits)
                except F.EditError as err:
                    self.note(f"repair edit failed: {err}")
                repo_files = F.read_repo(clean)
        raise PipelineError("codebase never passed its own test suite")

    async def design_incident(self, prefix: list[llm.Message], design: dict[str, Any],
                              clean_files: dict[str, str]) -> dict[str, Any]:
        self.stage("incident")
        msgs = P.with_task(prefix, P.incident_task(self.spec, design))
        failing_mode = self.spec["fidelity"] == "failing_test"
        clean = self.work / "clean"
        for attempt in range(3):
            c = await self.call("incident", msgs, role="designer", max_tokens=24000, reasoning="medium")
            try:
                result = await self._verify_incident(c.text, clean, clean_files, failing_mode)
                return result
            except (PipelineError, F.EditError, ValueError, KeyError) as err:
                self.note(f"incident attempt {attempt + 1} rejected: {err}")
                msgs = msgs + [
                    {"role": "assistant", "content": c.text},
                    {"role": "user", "content": f"Verification failed:\n{err}\n\nRevise and output the COMPLETE response again in the same format (all blocks)."},
                ]
        raise PipelineError("could not produce a verifiable incident")

    async def _verify_incident(self, text: str, clean: Path, clean_files: dict[str, str],
                               failing_mode: bool) -> dict[str, Any]:
        edits = F.parse_edits(text, "bug_edit")
        hidden = llm.extract_tag(text, "hidden_tests")
        repro = llm.extract_tag(text, "repro")
        meta_raw = llm.extract_tag(text, "meta")
        if not edits or not hidden or not repro or not meta_raw:
            raise ValueError("missing one of: bug_edit, hidden_tests, repro, meta")
        meta = llm.parse_json(meta_raw)
        for key in ("root_cause", "hints", "mechanism", "concept_card", "inbox_subject"):
            if key not in meta:
                raise ValueError(f"meta missing {key}")
        if len(meta["hints"]) < 4:
            raise ValueError("need 4 hints")
        hidden = F._strip_fence(hidden) + "\n"
        repro = F._strip_fence(repro) + "\n"
        regression: tuple[str, str] | None = None
        if failing_mode:
            regs = llm.extract_tags(text, "regression_test")
            if not regs or "path" not in regs[0][0]:
                raise ValueError("failing_test style requires a <regression_test path=...> block")
            regression = (F.safe_rel(regs[0][0]["path"]), F._strip_fence(regs[0][1]) + "\n")
            if not regression[0].startswith("tests/"):
                raise ValueError("regression test must live under tests/")

        buggy = self.work / "buggy"
        F.copy_repo(clean, buggy)
        touched = F.apply_edits(buggy, edits)
        leaks = []
        for rel in touched:
            leaks += safety.leaky_comment_lines(F.added_lines(clean_files.get(rel, ""), (buggy / rel).read_text()))
        if leaks:
            raise PipelineError("the bug edit adds comments that hint at the problem:\n" + "\n".join(leaks))
        if F.read_repo(buggy) == clean_files:
            raise PipelineError("the bug edits didn't change anything")

        problems = []
        # 1. hidden tests pass on clean, fail on buggy (with real failures, not import errors)
        on_clean = await self._run_extra(clean, {HIDDEN_INCIDENT: hidden}, [HIDDEN_INCIDENT])
        if not on_clean.ok:
            problems.append("Hidden tests must PASS on the original code, but:\n" + on_clean.summary())
        on_buggy = await self._run_extra(buggy, {HIDDEN_INCIDENT: hidden}, [HIDDEN_INCIDENT])
        real_failures = [c for c in on_buggy.failing() if c.outcome == "failed"]
        if on_buggy.ok:
            problems.append("Hidden tests must FAIL with the bug, but they all passed.")
        elif not real_failures:
            problems.append("Hidden tests error out (collection/fixture errors) on the buggy code instead of "
                            "failing their assertions:\n" + on_buggy.summary())
        # 2. the existing suite still passes with the bug (bugs escape test suites)
        visible = await sandbox.run_pytest(buggy)
        if not visible.ok:
            problems.append("Existing tests must still PASS with the bug present, but:\n" + visible.summary())
        # 3. regression test (failing_test style): fails on buggy, passes on clean
        failing_output = None
        if regression:
            reg_clean = await self._run_extra(clean, {regression[0]: regression[1]}, [regression[0]])
            reg_buggy = await self._run_extra(buggy, {regression[0]: regression[1]}, [regression[0]])
            if not reg_clean.ok:
                problems.append("Regression test must pass on the original code:\n" + reg_clean.summary())
            if reg_buggy.ok:
                problems.append("Regression test must FAIL with the bug, but it passed.")
            failing_output = reg_buggy.output
        if problems:
            raise PipelineError("\n\n".join(problems))

        # 4. capture real repro output for the report
        repro_buggy = await self._run_script(buggy, repro)
        repro_clean = await self._run_script(clean, repro)
        if (repro_buggy.stdout + repro_buggy.stderr).strip() == (repro_clean.stdout + repro_clean.stderr).strip():
            raise PipelineError("The repro script prints the same output with and without the bug; it must show the symptom.")
        if regression:
            (buggy / regression[0]).write_text(regression[1])

        return {
            "edits": [e.__dict__ for e in edits],
            "hidden_tests": hidden,
            "repro": repro,
            "repro_output": (repro_buggy.stdout + ("\n" + repro_buggy.stderr if repro_buggy.stderr.strip() else "")).strip(),
            "repro_output_clean": (repro_clean.stdout + repro_clean.stderr).strip(),
            "regression_test": {"path": regression[0], "content": regression[1]} if regression else None,
            "failing_output": failing_output,
            "meta": meta,
            "hidden_counts": {"total": on_buggy.total, "failing_on_buggy": len(on_buggy.failing())},
        }

    async def _run_extra(self, base: Path, extra: dict[str, str], targets: list[str]) -> sandbox.TestReport:
        tmp = sandbox.scratch_copy(base, "verify")
        try:
            F.write_repo(tmp, extra)
            return await sandbox.run_pytest(tmp, targets)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    async def _run_script(self, base: Path, code: str) -> sandbox.ProcResult:
        tmp = sandbox.scratch_copy(base, "repro")
        try:
            res = await sandbox.run_python(code, tmp, timeout=30, filename="repro.py")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        # Real tracebacks come from a server, not our scratch dir or this machine's venv.
        deploy = f"/srv/{self._repo_name or 'app'}"
        venv, base = sandbox.runtime_prefixes()
        mapping = {p: deploy for p in (str(tmp), str(tmp.resolve()), str(tmp).replace("/private/", "/", 1))}
        mapping[venv] = f"{deploy}/.venv"
        mapping[str(Path(venv).resolve())] = f"{deploy}/.venv"
        mapping[base] = "/usr/local"
        mapping[str(Path(base).resolve())] = "/usr/local"
        res.stdout = sandbox.scrub_paths(res.stdout, mapping)
        res.stderr = sandbox.scrub_paths(res.stderr, mapping)
        return res

    async def write_report(self, design: dict[str, Any], incident: dict[str, Any]) -> dict[str, Any]:
        self.stage("report")
        msgs = P.report_messages(self.spec, design, incident["meta"], incident["repro_output"],
                                 incident.get("failing_output"))
        for _ in range(3):
            c = await self.call("report", msgs, role="writer", max_tokens=6000)
            try:
                report = llm.parse_json(c.text)
                if not report.get("messages"):
                    raise ValueError("no messages")
                return report
            except (ValueError, json.JSONDecodeError) as err:
                msgs = msgs + [{"role": "assistant", "content": c.text},
                               {"role": "user", "content": f"Invalid ({err}). Reply with only the JSON object."}]
        raise PipelineError("report writer failed")

    async def design_feature(self, prefix: list[llm.Message], design: dict[str, Any]) -> dict[str, Any]:
        self.stage("feature")
        msgs = P.with_task(prefix, P.feature_task(self.spec, design))
        for attempt in range(3):
            c = await self.call("feature", msgs, role="designer", max_tokens=28000, reasoning="medium")
            try:
                return await self._verify_feature(c.text)
            except (PipelineError, F.EditError, ValueError, KeyError) as err:
                self.note(f"feature attempt {attempt + 1} rejected: {err}")
                msgs = msgs + [
                    {"role": "assistant", "content": c.text},
                    {"role": "user", "content": f"Verification failed:\n{err}\n\nRevise and output the COMPLETE response again in the same format (all blocks)."},
                ]
        raise PipelineError("could not produce a verifiable feature")

    async def _verify_feature(self, text: str) -> dict[str, Any]:
        edits = F.parse_edits(text, "ref_edit")
        for attrs, body in llm.extract_tags(text, "ref_file"):
            if "path" in attrs:
                edits.append(F.Edit(F.safe_rel(attrs["path"]), "", F._strip_fence(body)))
        acc = llm.extract_tags(text, "acceptance_tests")
        hidden = llm.extract_tag(text, "hidden_tests")
        meta_raw = llm.extract_tag(text, "meta")
        if not edits or not acc or "path" not in acc[0][0] or not hidden or not meta_raw:
            raise ValueError("missing one of: ref_edit/ref_file, acceptance_tests(path), hidden_tests, meta")
        meta = llm.parse_json(meta_raw)
        for key in ("title", "ticket", "hints", "concept_card"):
            if key not in meta:
                raise ValueError(f"meta missing {key}")
        acc_path = F.safe_rel(acc[0][0]["path"])
        if not acc_path.startswith("tests/"):
            raise ValueError("acceptance tests must live under tests/")
        acc_body = F._strip_fence(acc[0][1]) + "\n"
        hidden = F._strip_fence(hidden) + "\n"

        clean = self.work / "clean"
        featured = self.work / "featured"
        F.copy_repo(clean, featured)
        F.apply_edits(featured, edits)
        extra = {acc_path: acc_body, HIDDEN_FEATURE: hidden}
        problems = []
        full = await self._run_extra(featured, extra, [])
        if not full.ok:
            problems.append("With the reference implementation, the whole suite (existing + acceptance + hidden) must pass:\n" + full.summary())
        before = await self._run_extra(clean, extra, [acc_path, HIDDEN_FEATURE])
        failing_ids = {c.nodeid for c in before.failing()}
        acc_fail = any(i.startswith(acc_path) for i in failing_ids)
        hid_fail = any(i.startswith(HIDDEN_FEATURE) for i in failing_ids)
        if before.total and (not acc_fail or not hid_fail) and before.exit_code in (0, 1):
            problems.append("Before the feature exists, the acceptance tests and the hidden tests should each have failures "
                            f"(acceptance failing: {acc_fail}, hidden failing: {hid_fail}). Make sure they test the new behavior.")
        if problems:
            raise PipelineError("\n\n".join(problems))
        return {
            "edits": [e.__dict__ for e in edits],
            "acceptance": {"path": acc_path, "content": acc_body},
            "hidden_tests": hidden,
            "meta": meta,
            "reference_diff": F.unified_diff(F.read_repo(clean), F.read_repo(featured)),
        }

    async def design_recon(self, prefix: list[llm.Message], design: dict[str, Any],
                           incident: dict[str, Any]) -> dict[str, Any]:
        self.stage("recon")
        msgs = P.with_task(prefix, P.recon_task(self.spec, design, incident["meta"]))
        buggy_files = F.read_repo(self.work / "buggy")
        for attempt in range(3):
            c = await self.call("recon", msgs, role="designer", max_tokens=12000, reasoning="low")
            try:
                recon = llm.parse_json(c.text)
                return await self._verify_recon(recon, buggy_files)
            except (PipelineError, ValueError, KeyError, TypeError) as err:
                self.note(f"recon attempt {attempt + 1} rejected: {err}")
                msgs = msgs + [
                    {"role": "assistant", "content": c.text},
                    {"role": "user", "content": f"Problem: {err}\nReply with the corrected complete JSON only."},
                ]
        raise PipelineError("could not produce recon materials")

    async def _verify_recon(self, recon: dict[str, Any], buggy_files: dict[str, str]) -> dict[str, Any]:
        stops = []
        for stop in recon.get("tour") or []:
            path = stop.get("path", "")
            content = buggy_files.get(path)
            line = F.line_of(content, stop.get("anchor", "")) if content else None
            if line:
                stops.append({**stop, "line": line})
        if len(stops) < 3:
            raise PipelineError("fewer than 3 tour stops have anchors that exist verbatim in their files")
        recon["tour"] = stops
        questions = recon.get("questions") or []
        if len(questions) < 3:
            raise PipelineError("need 4 questions")
        kept = []
        for q in questions:
            if q.get("kind") == "predict":
                value = await self._evaluate_predict(q)
                if value is None:
                    self.note(f"dropping predict question {q.get('id')}: not deterministic or failed")
                    continue
                q["answer"] = value
                q["verified"] = True
            kept.append(q)
        recon["questions"] = kept
        return recon

    async def _evaluate_predict(self, q: dict[str, Any]) -> str | None:
        setup, expr = q.get("setup") or "", q.get("expr") or ""
        if not expr:
            return None
        code = f"{setup}\n__v = ({expr})\nprint('<<<' + repr(__v) + '>>>')\n"
        outs = []
        for base in (self.work / "buggy", self.work / "clean"):
            res = await self._run_script(base, code)
            m = re.search(r"<<<(.*)>>>", res.stdout, re.DOTALL)
            if not m or res.returncode != 0:
                return None
            outs.append(m.group(1))
        if outs[0] != outs[1] or len(outs[0]) > 120:
            return None
        return outs[0]

    async def qa(self, prefix: list[llm.Message], materials: str) -> dict[str, Any]:
        self.stage("qa")
        msgs = P.with_task(prefix, P.qa_task(materials))
        c = await self.call("qa", msgs, role="reviewer", max_tokens=16000, reasoning="medium")
        try:
            return llm.parse_json(c.text)
        except (ValueError, json.JSONDecodeError):
            self.note("QA output unparseable; shipping without QA patches")
            return {"verdict": "ship", "issues": [], "patches": {}}

    # --- orchestration -------------------------------------------------------------

    async def run(self, eager_feature: bool = False) -> dict[str, Any]:
        """Generate a case. The feature ticket is generated lazily (on demand) unless eager."""
        t0 = time.monotonic()
        self.note(f"spec: {json.dumps(self._spec_summary())}")
        design = await self.architect()
        (self.dir / "design.json").write_text(json.dumps(design, indent=2))
        self._repo_name = design["repo"]["name"]
        self.note(f"design: {design['company']['name']} / {design['repo']['name']} ({design['repo']['shape']})")

        repo_files, convo = await self.implement(design)
        clean_files = await self.verify_and_repair(design, repo_files, convo)

        prefix = P.designer_prefix(P.case_context(self.spec, design), F.render_repo(clean_files))
        incident = await self.design_incident(prefix, design, clean_files)
        # The designer prefix is now cached; these three are independent.
        try:
            async with asyncio.TaskGroup() as tg:
                report_t = tg.create_task(self.write_report(design, incident))
                feature_t = tg.create_task(self.design_feature(prefix, design)) if eager_feature else None
                recon_t = tg.create_task(self.design_recon(prefix, design, incident))
        except* Exception as group:
            raise group.exceptions[0] from None
        report, recon = report_t.result(), recon_t.result()
        feature = feature_t.result() if feature_t else None

        materials = self._qa_materials(design, incident, report, feature, recon)
        qa = await self.qa(prefix, materials)
        self.note(f"QA verdict: {qa.get('verdict')} issues={len(qa.get('issues') or [])}")
        high = [i for i in qa.get("issues") or [] if i.get("severity") == "high"]
        if qa.get("verdict") == "reject" and not high:
            qa["verdict"] = "patch"  # rejects need a high-severity reason; otherwise keep the patches
        if qa.get("verdict") == "reject":
            raise PipelineError("QA rejected the case: " + "; ".join(i.get("problem", "") for i in qa.get("issues", [])[:3]))
        report, feature, recon, incident = self._apply_patches(qa, report, feature, recon, incident)

        self.stage("assemble")
        case = self._assemble(design, clean_files, incident, report, feature, recon, qa)
        case["generation"]["seconds"] = round(time.monotonic() - t0)
        (self.dir / "case.json").write_text(json.dumps(case, indent=2))
        shutil.rmtree(self.work, ignore_errors=True)
        self.note(f"done in {case['generation']['seconds']}s")
        return case

    def _spec_summary(self) -> dict[str, Any]:
        s = self.spec
        return {"level": s["level"], "domain": s["domain"]["id"], "incident": s["incident_concept"]["id"],
                "feature": s["feature_concept"]["id"], "fidelity": s["fidelity"], "recon": s["recon_mode"]}

    def _qa_materials(self, design, incident, report, feature, recon) -> str:
        bug_diff = F.unified_diff(F.read_repo(self.work / "clean"), F.read_repo(self.work / "buggy"))
        meta = {k: incident["meta"].get(k) for k in ("root_cause", "mechanism", "fix", "hints", "concept_card", "expert_path")}
        return f"""<materials>
<incident_report>{json.dumps(report, indent=1)}</incident_report>
<bug_diff>
{bug_diff}
</bug_diff>
<hidden_incident_tests>
{incident['hidden_tests']}
</hidden_incident_tests>
<incident_meta>{json.dumps(meta, indent=1)}</incident_meta>
{self._feature_materials(feature) if feature else ""}
<recon>{json.dumps({k: recon.get(k) for k in ('briefing', 'tour', 'questions')}, indent=1)}</recon>
<verification>All automated checks passed: clean suite green; hidden incident tests pass on clean code and fail with the bug; existing tests still pass with the bug; feature tests fail before and pass after the reference implementation; predict answers were computed by executing the code.</verification>
</materials>"""

    @staticmethod
    def _feature_materials(feature: dict[str, Any]) -> str:
        return f"""<feature_ticket>{json.dumps(feature['meta']['ticket'], indent=1)}</feature_ticket>
<feature_acceptance_tests path="{feature['acceptance']['path']}">
{feature['acceptance']['content']}
</feature_acceptance_tests>
<feature_hidden_tests>
{feature['hidden_tests']}
</feature_hidden_tests>"""

    def _apply_patches(self, qa, report, feature, recon, incident):
        patches = qa.get("patches") or {}
        if qa.get("verdict") != "patch" and not any(patches.values()):
            return report, feature, recon, incident
        if isinstance(patches.get("report_messages"), list) and patches["report_messages"]:
            report = {**report, "messages": patches["report_messages"]}
            self.note("QA patched report messages")
        if feature and isinstance(patches.get("feature_ticket"), dict):
            feature["meta"]["ticket"] = {**feature["meta"]["ticket"], **patches["feature_ticket"]}
            self.note("QA patched feature ticket")
        if isinstance(patches.get("recon_questions"), list) and patches["recon_questions"]:
            verified = {q["id"]: q for q in recon["questions"] if q.get("verified")}
            merged = []
            for q in patches["recon_questions"]:
                if q.get("kind") == "predict":
                    if q.get("id") in verified:
                        merged.append(verified[q["id"]])  # keep the executed answer
                    continue
                merged.append(q)
            recon["questions"] = merged
            self.note("QA patched recon questions")
        if isinstance(patches.get("incident_meta"), dict):
            incident["meta"].update({k: v for k, v in patches["incident_meta"].items() if v})
            self.note(f"QA patched incident meta: {list(patches['incident_meta'])}")
        return report, feature, recon, incident

    def _assemble(self, design, clean_files, incident, report, feature, recon, qa) -> dict[str, Any]:
        # On-disk layout: repo/ (what the learner starts with), clean/ (post-fix), hidden/, feature/
        F.copy_repo(self.work / "buggy", self.dir / "repo")
        F.copy_repo(self.work / "clean", self.dir / "clean")
        hidden_dir = self.dir / "hidden"
        hidden_dir.mkdir(exist_ok=True)
        (hidden_dir / "incident_test.py").write_text(incident["hidden_tests"])
        if feature:
            self._write_feature_files(feature)

        repo_files = F.read_repo(self.dir / "repo")
        stats = F.repo_stats(repo_files)
        regression_path = (incident.get("regression_test") or {}).get("path")
        bug_diff = F.unified_diff(clean_files, {k: v for k, v in repo_files.items() if k != regression_path})
        imeta = incident["meta"]
        fmeta = feature["meta"] if feature else {}
        spec = self.spec
        par_incident = int(imeta.get("par_minutes") or spec["par_incident"])
        par_recon = spec["par_recon"]
        return {
            "id": self.case_id,
            "version": 1,
            "created_at": time.time(),
            "spec": self._spec_summary() | {"hops": spec["hops"], "files": spec["files"], "loc": spec["loc"]},
            "company": design["company"],
            "repo": {
                "name": design["repo"]["name"], "package": design["repo"]["package"],
                "shape": design["repo"]["shape"], "summary": design["repo"]["summary"],
                "entry_points": design["repo"].get("entry_points", []),
                "libraries": design["repo"].get("libraries", []),
                "stats": stats,
            },
            "concepts": {
                "incident": spec["incident_concept"]["id"],
                "feature": spec["feature_concept"]["id"],
                "flavor": [c["id"] for c in spec["flavor_concepts"]],
            },
            "card": {
                "company": design["company"]["name"],
                "tagline": design["company"].get("tagline", ""),
                "industry": design["company"].get("industry", ""),
                "blurb": design["company"].get("blurb", ""),
                "subject": imeta.get("inbox_subject") or report.get("title"),
                "channel": report.get("channel", "slack"),
                "from": (report.get("messages") or [{}])[0].get("from", ""),
                "shape": design["repo"]["shape"],
                "libraries": design["repo"].get("libraries", []),
                "stats": stats,
                "level": spec["level"],
                "fidelity": spec["fidelity"],
                "minutes": {"recon": par_recon, "incident": par_incident, "feature": int(fmeta.get("par_minutes") or 25)},
                "domain": spec["domain"]["name"],
                "sector": spec["domain"].get("sector", ""),
            },
            "recon": {
                "mode": spec["recon_mode"],
                "par_minutes": par_recon,
                "briefing": recon.get("briefing"),
                "tour": recon.get("tour", []),
                "map": recon.get("map"),
                "questions": recon.get("questions", []),
            },
            "incident": {
                "report": report,
                "fidelity": spec["fidelity"],
                "par_minutes": par_incident,
                "meta": imeta,
                "bug_edits": incident["edits"],
                "bug_diff": bug_diff,
                "repro": incident["repro"],
                "repro_output": incident["repro_output"],
                "regression_test": incident.get("regression_test"),
                "hidden_tests_path": "hidden/incident_test.py",
            },
            "feature": self._feature_section(feature) if feature else None,
            "feature_plan": design.get("feature_plan"),
            "qa": {"verdict": qa.get("verdict"), "issues": qa.get("issues", [])},
            "generation": {"timings": {k: round(v) for k, v in self.timings.items()}},
        }

    def _write_feature_files(self, feature: dict[str, Any]) -> None:
        (self.dir / "hidden").mkdir(exist_ok=True)
        (self.dir / "hidden" / "feature_test.py").write_text(feature["hidden_tests"])
        (self.dir / "feature").mkdir(exist_ok=True)
        (self.dir / "feature" / "reference.diff").write_text(feature["reference_diff"])

    @staticmethod
    def _feature_section(feature: dict[str, Any]) -> dict[str, Any]:
        fmeta = feature["meta"]
        return {
            "title": fmeta.get("title"),
            "inbox_subject": fmeta.get("inbox_subject"),
            "author": fmeta.get("author"),
            "ticket": fmeta.get("ticket"),
            "par_minutes": int(fmeta.get("par_minutes") or 25),
            "meta": {k: v for k, v in fmeta.items() if k not in ("ticket",)},
            "acceptance": feature["acceptance"],
            "reference_edits": feature["edits"],
            "hidden_tests_path": "hidden/feature_test.py",
        }

    def close(self) -> None:
        self._log.close()


async def generate(case_id: str, spec: dict[str, Any]) -> dict[str, Any]:
    """Run the pipeline for a queued case row and update its status."""
    db.run("UPDATE cases SET status = 'generating', error = NULL WHERE id = ?", case_id)
    pipe = Pipeline(case_id, spec)
    try:
        case = await pipe.run()
    except Exception as err:
        pipe.note(f"FAILED: {type(err).__name__}: {err}")
        db.run("UPDATE cases SET status = 'failed', error = ?, finished_at = ? WHERE id = ?",
               f"{type(err).__name__}: {err}"[:2000], time.time(), case_id)
        raise
    finally:
        pipe.close()
    db.run("UPDATE cases SET status = 'ready', card = ?, finished_at = ?, stage = NULL WHERE id = ?",
           db.dumps(case["card"]), time.time(), case_id)
    return case


async def generate_feature(case_id: str) -> dict[str, Any]:
    """Write + verify the feature ticket for an existing case (on demand)."""
    from .. import curriculum

    d = config.LIBRARY_DIR / case_id
    case = json.loads((d / "case.json").read_text())
    if case.get("feature"):
        return case["feature"]
    design = json.loads((d / "design.json").read_text())
    concept = curriculum.load().concepts[case["concepts"]["feature"]]
    spec = {"level": case["spec"]["level"], "feature_concept": concept.to_dict()}
    pipe = Pipeline(case_id, spec)
    pipe._repo_name = design["repo"]["name"]
    try:
        F.copy_repo(d / "clean", pipe.work / "clean")
        clean_files = F.read_repo(pipe.work / "clean")
        prefix = P.designer_prefix(P.case_context(spec, design), F.render_repo(clean_files))
        feature = await pipe.design_feature(prefix, design)
        qa = await pipe.qa(prefix, f"<materials>\n{pipe._feature_materials(feature)}\n"
                                   "<verification>Feature tests fail before and pass after the reference implementation.</verification>\n</materials>")
        patch = (qa.get("patches") or {}).get("feature_ticket")
        if isinstance(patch, dict):
            feature["meta"]["ticket"] = {**feature["meta"]["ticket"], **patch}
            pipe.note("QA patched feature ticket")
        pipe._write_feature_files(feature)
        case = json.loads((d / "case.json").read_text())
        case["feature"] = pipe._feature_section(feature)
        case["card"]["minutes"]["feature"] = case["feature"]["par_minutes"]
        (d / "case.json").write_text(json.dumps(case, indent=2))
        pipe.note("feature ready")
        return case["feature"]
    except Exception as err:
        pipe.note(f"feature FAILED: {type(err).__name__}: {err}")
        raise
    finally:
        pipe.close()
        shutil.rmtree(pipe.work, ignore_errors=True)
