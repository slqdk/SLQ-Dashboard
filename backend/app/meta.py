"""The app's name and version - the ONE place to rename it."""
from __future__ import annotations

from pathlib import Path

APP_DISPLAY_NAME = "SLQ Dashboard"
APP_ID = "slqdashboard"

_VERSION_FILE = Path(__file__).resolve().parents[2] / "VERSION"


def _read_version() -> str:
    try:
        return _VERSION_FILE.read_text(encoding="utf-8").strip() or "0.0.0"
    except OSError:
        return "0.0.0"


APP_VERSION = _read_version()
