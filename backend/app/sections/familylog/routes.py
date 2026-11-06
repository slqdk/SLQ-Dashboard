"""FamilyLog's API, under /api/s/familylog."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from . import client

router = APIRouter(prefix="/api/s/familylog", tags=["familylog"])


@router.get("/state")
def state(request: Request):
    return client.state(request.state.user["id"])


@router.get("/search")
def search(request: Request, q: str = ""):
    try:
        return client.search(request.state.user["id"], q)
    except client.Unavailable as exc:
        raise HTTPException(502, str(exc))


@router.post("/sync")
def sync(request: Request):
    """Fetch now, for the button on the page."""
    client.sync_user(request.state.user["id"])
    return client.state(request.state.user["id"])
