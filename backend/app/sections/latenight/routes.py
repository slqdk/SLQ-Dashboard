"""SLQ DL's API, under /api/s/latenight. Everyone with the section reads; only
an admin adds or changes facts."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Request

from . import store

router = APIRouter(prefix="/api/s/latenight", tags=["latenight"])


def _admin(request: Request) -> None:
    if request.state.user["role"] != "admin":
        raise HTTPException(403, "Kun for administrator.")


@router.get("/today")
def on_date(day: str | None = None):
    try:
        return store.on_date(date.fromisoformat(day) if day else None)
    except ValueError:
        raise HTTPException(400, "Ugyldig dato.")


@router.get("/facts")
def facts(q: str = "", host: str = "", story: str = "", kind: str = "", decade: str = ""):
    return {"facts": store.facts(q, host, story, kind, decade), **store.meta()}


@router.post("/facts")
def add(body: dict, request: Request):
    _admin(request)
    try:
        return store.add(body)
    except store.Problem as exc:
        raise HTTPException(400, str(exc))


@router.put("/facts/{fact_id}")
def update(fact_id: int, body: dict, request: Request):
    _admin(request)
    try:
        return store.update(fact_id, body)
    except store.Problem as exc:
        raise HTTPException(400, str(exc))
    except LookupError as exc:
        raise HTTPException(404, str(exc))


@router.delete("/facts/{fact_id}")
def delete(fact_id: int, request: Request):
    _admin(request)
    store.delete(fact_id)
    return {"ok": True}
