"""LogMyLife: each person's own timeline, which remembers everything.

Three ways in, one table:

* entries the person writes by hand
* every Google Calendar event (sections/calendar/ calls `store.ingest`), kept
  also when it is later changed or deleted in Google
* other sections through the same `store.ingest` (Dagbog and FamilyMap when
  FamilyLog's read-only API exists)

Nothing is ever written back to Google.
"""
from __future__ import annotations

from ...core.sections import Section
from . import files, store
from .routes import router

SECTION = Section(
    id="logmylife",
    title="LogMyLife",
    router=router,
    migrations=[(1, "life_events", store.migrate_1), (2, "life_files", files.migrate_2)],
    overview=store.overview,
    on_user_deleted=files.on_user_deleted,
)
