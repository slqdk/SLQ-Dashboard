"""Aktier: each person's Nordnet holdings, from an export they upload.

Nordnet's API is closed to new customers, so the way in is the transactions file
from Nordnet's own site, and a job fetches the prices for what is held. Off for
family accounts unless the admin says so, and a person only ever sees their own
rows."""
from __future__ import annotations

from ...core.sections import Section
from . import prices, store
from .routes import router

SECTION = Section(
    id="aktier",
    title="Aktier",
    router=router,
    migrations=[(1, "nordnet_rows", store.migrate_1), (2, "stock prices", prices.migrate_2)],
    family_default=False,
    overview=store.overview,
    jobs=[(1800.0, prices.job)],
    setup=store.setup_status,
    reset=prices.reset,
)
