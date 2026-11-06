"""Aktier: the Nordnet account. Admin only by default.

Not connected yet. Nordnet's official API is closed to new customers, so the
way in is still to be chosen (see docs/PLAN.md)."""
from __future__ import annotations

from fastapi import APIRouter

from ...core import settings
from ...core.sections import Section

router = APIRouter(prefix="/api/s/aktier", tags=["aktier"])


def state(_me: dict | None = None) -> dict:
    return {"mode": settings.load().get("nordnetMode") or "off", "positions": []}


@router.get("/state")
def get_state():
    return state()


def setup_status() -> dict:
    mode = settings.load().get("nordnetMode")
    if mode == "off":
        return {"ok": False, "text": "Ikke forbundet."}
    return {"ok": False, "text": f"{mode}: ikke bygget endnu."}


SECTION = Section(
    id="aktier",
    title="Aktier",
    router=router,
    family_default=False,
    overview=state,
    setup=setup_status,
)
