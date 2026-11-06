"""Aktier's API, under /api/s/aktier. Everything is the signed-in person's own."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from . import nordnet, store

router = APIRouter(prefix="/api/s/aktier", tags=["aktier"])


@router.get("/state")
def state(request: Request):
    return store.state(request.state.user["id"])


@router.post("/import")
async def import_export(request: Request):
    """The CSV from Nordnet, sent as the request body."""
    body = await request.body()
    if len(body) > nordnet.MAX_BYTES:
        raise HTTPException(413, "Filen er for stor til at være et udtræk fra Nordnet.")
    try:
        rows, skipped = nordnet.parse(body)
    except nordnet.Problem as exc:
        raise HTTPException(400, str(exc))
    return {**store.ingest(request.state.user["id"], rows), "skipped": skipped}


@router.delete("/rows")
def clear(request: Request):
    store.clear(request.state.user["id"])
    return {"ok": True}
