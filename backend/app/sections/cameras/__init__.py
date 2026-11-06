"""Kameraer: pictures and live video from Tapo C200 cameras, behind the login.

A browser cannot play RTSP, so go2rtc sits next to the dashboard and turns the
cameras' streams into something it can. go2rtc has no published port: only this
section talks to it, and every picture passes the same access check as the rest
of the dashboard. Family accounts get the section only if the admin says so.
"""
from __future__ import annotations

from ...core.sections import Section
from . import client, store
from .routes import router

SECTION = Section(
    id="cameras",
    title="Kameraer",
    router=router,
    migrations=[(1, "cameras", store.migrate_1)],
    family_default=False,
    overview=client.overview,
    jobs=[(60.0, client.job)],
    setup=client.setup_status,
    reset=client.reset,
)
