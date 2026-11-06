"""Kalender's API, under /api/s/calendar, and Google's way back."""
from __future__ import annotations

import threading

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from ...core import google, jobs, logs, settings
from . import sync

router = APIRouter(prefix="/api/s/calendar", tags=["calendar"])
callback_router = APIRouter(tags=["calendar"])

CALLBACK_PATH = "/api/google/callback"


def redirect_uri(request: Request) -> str:
    """What Google must have on its list. publicUrl wins; without it, what the
    browser used, also behind Nginx Proxy Manager."""
    base = settings.load().get("publicUrl")
    if not base:
        proto = request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip()
        host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
        base = f"{proto}://{host}"
    return base.rstrip("/") + CALLBACK_PATH


@router.get("/state")
def state(request: Request):
    me = request.state.user["id"]
    return {**sync.state_of(me), "events": sync.upcoming(me, days=31, limit=300)}


@router.post("/connect")
def connect(request: Request):
    """The address to send the browser to."""
    if not google.configured():
        raise HTTPException(400, "Google er ikke sat op endnu. Det gøres under Admin → Opsætning.")
    return {"url": google.authorize_url(redirect_uri(request),
                                        google.new_state(request.state.user["id"]))}


class Selected(BaseModel):
    calendarId: str
    selected: bool


@router.put("/selected")
def selected(body: Selected, request: Request):
    sync.select(request.state.user["id"], body.calendarId, body.selected)
    jobs.kick()
    return sync.state_of(request.state.user["id"])


class LogCalendar(BaseModel):
    calendarId: str


@router.put("/log-calendar")
def log_calendar(body: LogCalendar, request: Request):
    try:
        sync.set_log_calendar(request.state.user["id"], body.calendarId)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    jobs.kick()
    return sync.state_of(request.state.user["id"])


@router.post("/sync")
def sync_now(request: Request):
    me = request.state.user["id"]
    return {"counts": sync.sync_user(me), **sync.state_of(me)}


@router.post("/disconnect")
def disconnect(request: Request):
    sync.disconnect(request.state.user["id"])
    return sync.state_of(request.state.user["id"])


@callback_router.get(CALLBACK_PATH)
def callback(request: Request, code: str = "", state: str = "", error: str = ""):
    """Google sends the browser back here. Needs the same person's session."""
    uid = google.take_state(state)
    me = request.state.user
    if error or uid is None or uid != me["id"]:
        return RedirectResponse("/#/kalender?google=afvist", status_code=303)
    try:
        sync.connect(uid, code, redirect_uri(request))
    except google.GoogleError as exc:
        logs.record_problem("google connect", str(exc))
        return RedirectResponse("/#/kalender?google=fejl", status_code=303)

    def first_sync() -> None:
        try:
            sync.sync_user(uid)
        except Exception as exc:
            logs.record_exception(exc, "first calendar sync")

    threading.Thread(target=first_sync, name="first-sync", daemon=True).start()
    return RedirectResponse("/#/kalender?google=ok", status_code=303)
