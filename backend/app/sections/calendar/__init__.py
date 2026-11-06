"""Kalender: each person's Google calendars, read only.

Connecting is per person; the Google client is set up once in Admin. The sync
job keeps a copy of each ticked calendar, and sends one calendar on to LogMyLife
(sections/logmylife/store.ingest): the calendar is what is coming, and the log is
what remembers.
"""
from __future__ import annotations

from ...core.sections import Section
from . import sync
from .routes import callback_router, router

SECTION = Section(
    id="calendar",
    title="Kalender",
    router=router,
    migrations=[(1, "google accounts and calendars", sync.migrate_1),
                (2, "each calendar's events, one calendar to the log", sync.migrate_2)],
    overview=sync.overview,
    jobs=[(900.0, sync.job)],
    setup=sync.setup_status,
)

__all__ = ["SECTION", "callback_router"]
