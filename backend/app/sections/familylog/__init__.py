"""FamilyLog: read-only access to the signed-in person's own data there.

Each person has their own read key, made in FamilyLog (Settings → Accounts), so
FamilyLog's rules decide what they see. The job keeps this month's spending
ready for the overview and copies the person's Dagbog days and FamilyMap
reviews to their LogMyLife.
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
    jobs=[(1800.0, client.job)],
    setup=client.setup_status,
    reset=client.reset,
)
