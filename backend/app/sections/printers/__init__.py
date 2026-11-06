"""Printere: status from Bambu Lab printers on the LAN. Read only.

Each printer runs a small MQTT broker and reports its state there. The dashboard
listens directly, without Bambu's cloud, and never controls a printer: the one
message it sends asks the printer to report everything.
"""
from __future__ import annotations

from ...core.sections import Section
from . import store, watcher
from .routes import router

SECTION = Section(
    id="printers",
    title="Printere",
    router=router,
    migrations=[(1, "printers", store.migrate_1)],
    overview=watcher.overview,
    jobs=[(30.0, watcher.job)],
    setup=watcher.setup_status,
    reset=watcher.reset,
)
