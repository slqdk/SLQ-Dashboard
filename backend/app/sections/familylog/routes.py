"""FamilyLog's API, under /api/s/familylog."""
from __future__ import annotations

from fastapi import APIRouter, Request

from . import client

router = APIRouter(prefix="/api/s/familylog", tags=["familylog"])


@router.get("/state")
def state(request: Request):
    return client.state(request.state.user["id"])
