"""Nyheder's API, under /api/s/news."""
from __future__ import annotations

from fastapi import APIRouter

from . import feed

router = APIRouter(prefix="/api/s/news", tags=["news"])


@router.get("/items")
def items():
    return {"items": feed.merged()[:80], "feeds": feed.feeds_state()}
