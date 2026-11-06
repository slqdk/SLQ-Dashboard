"""Printere's API, under /api/s/printers. Everyone with the section reads; only
an admin changes which printers there are."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ...core import jobs
from . import store, watcher

router = APIRouter(prefix="/api/s/printers", tags=["printers"])


def _admin(request: Request) -> None:
    if request.state.user["role"] != "admin":
        raise HTTPException(403, "Kun for administrator.")


@router.get("/state")
def state():
    return {"printers": watcher.state()}


@router.get("/config")
def config(request: Request):
    _admin(request)
    return {"items": store.all_printers(), "status": watcher.setup_status()}


@router.post("/config")
def add(body: dict, request: Request):
    _admin(request)
    try:
        out = store.add(body)
    except store.Problem as exc:
        raise HTTPException(400, str(exc))
    jobs.kick()
    return out


@router.put("/config/{printer_id}")
def update(printer_id: int, body: dict, request: Request):
    _admin(request)
    try:
        out = store.update(printer_id, body)
    except store.Problem as exc:
        raise HTTPException(400, str(exc))
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    jobs.kick()
    return out


@router.delete("/config/{printer_id}")
def delete(printer_id: int, request: Request):
    _admin(request)
    store.delete(printer_id)
    jobs.kick()
    return {"ok": True}
