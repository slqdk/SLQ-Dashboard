"""Formel 1's API, under /api/s/f1."""
from __future__ import annotations

from fastapi import APIRouter

from . import schedule

router = APIRouter(prefix="/api/s/f1", tags=["f1"])


@router.get("/season")
def season():
    return {"weekends": schedule.season(), "status": schedule.setup_status()}
