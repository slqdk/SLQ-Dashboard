"""Nyheder: RSS feeds, fetched by the server. Headlines and short text only,
with no images, scripts or trackers, and paid content filtered out."""
from __future__ import annotations

from ...core.sections import Section
from . import feed
from .routes import router

SECTION = Section(
    id="news",
    title="Nyheder",
    router=router,
    overview=feed.overview,
    jobs=[(600.0, feed.job)],
    setup=feed.setup_status,
    reset=feed.reset,
)
