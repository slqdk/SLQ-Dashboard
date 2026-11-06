"""What a section is. Every section package exports one `SECTION`.

From FamilyLog's Section, with what a dashboard adds:

* id           - short, stable; its API lives under /api/s/<id>/ and access
                 to that prefix is checked once, in the auth middleware
* title        - shown in the navigation (the frontend has its own registry)
* router       - its FastAPI routes, with prefix /api/s/<id>
* migrations   - its own numbered list [(version, name, fn(con))]
* family_default - whether a new family account gets the section
* overview     - fn(me) -> dict: what the overview page shows. Reads only what
                 is already here (database, the job's cache), never a slow
                 upstream, so the overview always answers at once
* jobs         - [(seconds, fn)]: background work; each runs in its own
                 daemon thread, first time right after start
* setup        - fn() -> {"ok": bool, "text": str}: one line for Admin → Opsætning
* sources      - optional: fn() -> [{"name", "ok", "text", "at", "lastOk"}], for a section
                 with several, on Admin → Log. The others have their one line there
* reset        - optional: clears in-memory state (tests)
* on_user_deleted - optional: called with the user id after an account is
                 deleted (rows go by ON DELETE CASCADE)

Adding a section: a package under app/sections/, one line in
app/sections/__init__.py, a file under frontend/src/sections/ plus one line
in its registry.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from fastapi import APIRouter


@dataclass(frozen=True)
class Section:
    id: str
    title: str
    router: APIRouter
    migrations: list[tuple[int, str, Callable]] = field(default_factory=list)
    family_default: bool = True
    overview: Callable[[dict], dict] | None = None
    jobs: list[tuple[float, Callable[[], None]]] = field(default_factory=list)
    setup: Callable[[], dict] | None = None
    sources: Callable[[], list[dict]] | None = None
    reset: Callable[[], None] | None = None
    on_user_deleted: Callable[[int], None] | None = None
