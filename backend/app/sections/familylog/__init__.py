"""FamilyLog: read-only access to the signed-in person's own data there.

Each person has their own read key, so FamilyLog's rules decide what they see.
"""
from __future__ import annotations

from ...core.sections import Section
from . import client
from .routes import router

SECTION = Section(
    id="familylog",
    title="FamilyLog",
    router=router,
    migrations=[(1, "read keys", client.migrate_1)],
    overview=client.overview,
    setup=client.setup_status,
)
