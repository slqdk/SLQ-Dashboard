"""LogMyLife's API, under /api/s/logmylife."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from . import store, strava

router = APIRouter(prefix="/api/s/logmylife", tags=["logmylife"])


@router.get("/events")
def events(request: Request, scope: str = "mine", before: str | None = None, q: str = "",
           source: str = "", year: str = "", limit: int = 100):
    return store.timeline(request.state.user["id"], scope=scope, before=before, q=q,
                          source=source, year=year, limit=limit)


@router.get("/meta")
def meta(request: Request):
    me = request.state.user["id"]
    return {"categories": store.CATEGORIES, "stats": store.stats(me),
            "onThisDay": store.on_this_day(me, limit=20)}


@router.post("/events")
def add(body: dict, request: Request):
    try:
        return store.add(request.state.user["id"], body)
    except store.Problem as exc:
        raise HTTPException(400, str(exc))


@router.put("/events/{event_id}")
def update(event_id: int, body: dict, request: Request):
    try:
        return store.update(request.state.user["id"], event_id, body)
    except store.Problem as exc:
        raise HTTPException(400, str(exc))
    except LookupError as exc:
        raise HTTPException(404, str(exc))


@router.delete("/events/{event_id}")
def remove(event_id: int, request: Request):
    try:
        store.remove(request.state.user["id"], event_id)
    except store.Problem as exc:
        raise HTTPException(400, str(exc))
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    return {"ok": True}


@router.post("/import/strava")
async def import_strava(request: Request):
    """activities.csv from Strava's own export, sent as the request body."""
    body = await request.body()
    if len(body) > strava.MAX_BYTES:
        raise HTTPException(413, "Filen er for stor. Brug activities.csv, ikke hele zip-filen.")
    try:
        return strava.import_csv(request.state.user["id"], body)
    except strava.Problem as exc:
        raise HTTPException(400, str(exc))
