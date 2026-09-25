"""Paths, environment, and defaults. Everything configurable lives here."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

DATA_DIR = Path(os.environ.get("COLDSTART_DATA", ROOT / "data")).resolve()
LIBRARY_DIR = DATA_DIR / "library"
WORKSPACES_DIR = DATA_DIR / "workspaces"
SCRATCH_DIR = DATA_DIR / "scratch"
DB_PATH = DATA_DIR / "coldstart.db"

CONTENT_DIR = ROOT / "content"
WEB_DIST = ROOT / "web" / "dist"

RUNTIME_VENV = Path(os.environ.get("COLDSTART_RUNTIME", ROOT / ".runtime")).resolve()
RUNTIME_PYTHON = RUNTIME_VENV / "bin" / "python"
RUNTIME_REQUIREMENTS = ROOT / "runtime" / "requirements.txt"

HOST = os.environ.get("COLDSTART_HOST", "127.0.0.1")
PORT = int(os.environ.get("COLDSTART_PORT", "8321"))

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE = "https://openrouter.ai/api/v1"

# Every model role can be re-pointed from the Settings page; these are the
# defaults. The user asked for max quality, so everything starts on Opus.
DEFAULT_MODELS: dict[str, str] = {
    "architect": "anthropic/claude-opus-5.5",
    "implementer": "anthropic/claude-opus-5.5",
    "designer": "anthropic/claude-opus-5.5",
    "writer": "anthropic/claude-opus-5.5",
    "reviewer": "anthropic/claude-opus-5.5",
    "mentor": "anthropic/claude-opus-5.5",
    "grader": "anthropic/claude-opus-5.5",
}

MODEL_PRESETS: dict[str, dict[str, str]] = {
    "max": dict(DEFAULT_MODELS),
    "balanced": {
        **DEFAULT_MODELS,
        "implementer": "anthropic/claude-sonnet-5",
        "writer": "anthropic/claude-sonnet-5",
        "mentor": "anthropic/claude-sonnet-5",
        "grader": "anthropic/claude-sonnet-5",
    },
    "economy": {
        "architect": "anthropic/claude-sonnet-5",
        "implementer": "anthropic/claude-sonnet-5",
        "designer": "anthropic/claude-sonnet-5",
        "writer": "openai/gpt-6-luna",
        "reviewer": "anthropic/claude-sonnet-5",
        "mentor": "anthropic/claude-haiku-4.5",
        "grader": "openai/gpt-6-luna",
    },
}

DEFAULT_SETTINGS: dict[str, object] = {
    "models": DEFAULT_MODELS,
    "buffer_size": 2,            # ready cases to keep in the inbox
    "auto_generate": True,
    "budget_floor_usd": 1.0,     # stop background generation below this remaining credit
    "default_plan": ["recon", "incident"],
    "timer_mode": "stopwatch",   # stopwatch | countdown
    "mentor_name": "Sam",
    "sound": False,
}

SANDBOX_TEST_TIMEOUT = 90  # seconds per pytest run


def ensure_dirs() -> None:
    for d in (DATA_DIR, LIBRARY_DIR, WORKSPACES_DIR, SCRATCH_DIR):
        d.mkdir(parents=True, exist_ok=True)
