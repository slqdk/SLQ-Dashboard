"""DK live: power prices, traffic and live updates from the dk-live container.

The dashboard only reads dk-live's API, so everything dk-live collects stays
in one place. The overview shows dk-live's own map, passed through the dashboard:
that keeps it behind the login and on the dashboard's https."""
from __future__ import annotations

from ...core.sections import Section
from . import client
from .routes import router

SECTION = Section(
    id="dklive",
    title="DK live",
    router=router,
    overview=client.overview,
    jobs=[(30.0, client.job)],
    setup=client.setup_status,
    reset=client.reset,
)
