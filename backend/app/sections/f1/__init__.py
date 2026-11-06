"""Formel 1: the season's sessions and nothing else. Nothing live.

Reads Jolpica directly (the same source and the same parsing as
F1-Live-replay's F1Schedule.cs), so it does not need that container."""
from __future__ import annotations

from ...core.sections import Section
from . import schedule
from .routes import router

SECTION = Section(
    id="f1",
    title="Formel 1",
    router=router,
    overview=schedule.overview,
    jobs=[(6 * 3600.0, schedule.job)],
    setup=schedule.setup_status,
    reset=schedule.reset,
)
