"""DK live's API, under /api/s/dklive."""
from __future__ import annotations

from fastapi import APIRouter

from . import client

router = APIRouter(prefix="/api/s/dklive", tags=["dklive"])


@router.get("/state")
def state():
    return client.state()
