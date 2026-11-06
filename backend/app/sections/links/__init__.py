"""Links: each person's bookmarks in a folder tree. The pinned ones are on the
overview."""
from __future__ import annotations

from ...core.sections import Section
from . import store
from .routes import router

SECTION = Section(
    id="links",
    title="Links",
    router=router,
    migrations=[(1, "folders and links", store.migrate_1)],
    overview=store.overview,
)
