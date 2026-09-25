"""Command line: `coldstart serve | generate | spend | doctor`."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import shutil
import sys

from . import config, db, llm, sandbox


def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    uvicorn.run("coldstart.app:app", host=config.HOST, port=args.port, reload=args.reload,
                log_level="info", reload_dirs=[str(config.ROOT / "server" / "coldstart")] if args.reload else None)


def cmd_generate(args: argparse.Namespace) -> None:
    from .generation import manager, pipeline
    from .learning import scheduler

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s", datefmt="%H:%M:%S")
    if args.model:
        llm.MODEL_OVERRIDE.set(args.model)

    async def main() -> None:
        for i in range(args.count):
            spec = scheduler.build_spec(focus=args.focus, level_override=args.level)
            case_id = manager.enqueue(spec)
            print(f"[{i + 1}/{args.count}] {case_id}: level {spec['level']} · {spec['domain']['name']} · "
                  f"incident={spec['incident_concept']['id']} · feature={spec['feature_concept']['id']} · "
                  f"{spec['fidelity']}")
            try:
                case = await pipeline.generate(case_id, spec)
                cost = db.one("SELECT cost_usd FROM cases WHERE id = ?", case_id)["cost_usd"]
                print(f"  ✓ {case['company']['name']} — {case['card']['subject']}  "
                      f"({case['repo']['stats']['loc']} LOC, ${cost:.2f}, {case['generation']['seconds']}s)")
            except Exception as err:  # noqa: BLE001
                cost = db.one("SELECT cost_usd FROM cases WHERE id = ?", case_id)["cost_usd"]
                print(f"  ✗ failed (${cost:.2f}): {err}")
                print(f"    log: {config.LIBRARY_DIR / case_id / 'gen.log'}")

    asyncio.run(main())


def cmd_spend(args: argparse.Namespace) -> None:
    s = llm.spend_summary()
    print(f"Total recorded spend: ${s['total_usd']:.2f}")
    for r in s["by_role"]:
        print(f"  {r['role']:<12} {r['model']:<34} {r['calls']:>4} calls  ${r['cost'] or 0:.3f}")
    print(json.dumps(asyncio.run(llm.key_status(force=True)), indent=2))


def cmd_doctor(args: argparse.Namespace) -> None:
    ok = True

    def check(label: str, passed: bool, hint: str = "") -> None:
        nonlocal ok
        ok &= passed
        print(f"  {'✓' if passed else '✗'} {label}" + (f"  — {hint}" if not passed and hint else ""))

    print("Cold Start doctor")
    check("OPENROUTER_API_KEY set", bool(config.OPENROUTER_API_KEY), "add it to .env")
    check("runtime venv", config.RUNTIME_PYTHON.exists(), "run ./coldstart setup")
    check("sandbox-exec available", sandbox.SANDBOX_EXEC is not None, "non-macOS: code runs unsandboxed")
    check("git available", shutil.which("git") is not None)
    check("web build present", (config.WEB_DIST / "index.html").exists(), "run ./coldstart setup")
    check("content present", (config.CONTENT_DIR / "concepts.yaml").exists())
    status = asyncio.run(llm.key_status(force=True))
    check("OpenRouter key works", bool(status.get("ok")), status.get("error", ""))
    if status.get("ok"):
        print(f"    credit remaining: ${status.get('remaining')} of ${status.get('limit')}")
    sys.exit(0 if ok else 1)


def main() -> None:
    parser = argparse.ArgumentParser(prog="coldstart")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("serve", help="run the app")
    p.add_argument("--port", type=int, default=config.PORT)
    p.add_argument("--reload", action="store_true")
    p.set_defaults(func=cmd_serve)
    p = sub.add_parser("generate", help="generate cases in the foreground")
    p.add_argument("--count", type=int, default=1)
    p.add_argument("--focus", help="concept id to target")
    p.add_argument("--level", type=int, help="override the learner level")
    p.add_argument("--model", help="force one OpenRouter model for every role (testing)")
    p.set_defaults(func=cmd_generate)
    sub.add_parser("spend", help="show LLM spend").set_defaults(func=cmd_spend)
    sub.add_parser("doctor", help="check the environment").set_defaults(func=cmd_doctor)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
