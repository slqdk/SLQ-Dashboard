"""Aktier: each person's Nordnet holdings, from an export they upload.

Nordnet's API is closed to new customers, so the way in is the transactions file
from Nordnet's own site. Off for family accounts unless the admin says so, and a
person only ever sees their own rows."""
from __future__ import annotations

from ...core.sections import Section
from . import store
from .routes import router

SECTION = Section(
    id="aktier",
    title="Aktier",
    router=router,
    migrations=[(1, "nordnet_rows", store.migrate_1)],
    family_default=False,
    overview=store.overview,
    setup=store.setup_status,
)
