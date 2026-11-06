"""SLQ DL: the history of US late-night television, by date.

"On this date": what happened in late night on today's date in earlier years,
the long stories behind it (the Carson succession, the 2010 conflict), and the
newest monologues from the shows still on air."""
from __future__ import annotations

from ...core.sections import Section
from . import monologues, store
from .routes import router

SECTION = Section(
    id="latenight",
    title="SLQ DL",
    router=router,
    migrations=[(1, "dl_facts", store.migrate_1)],
    overview=store.overview,
    jobs=[(1800.0, monologues.job)],
    setup=monologues.status,
    reset=monologues.reset,
)
