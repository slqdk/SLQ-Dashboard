"""LogMyLife's API, under /api/s/logmylife."""
from __future__ import annotations

from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, StreamingResponse

from . import export, files, store, strava

router = APIRouter(prefix="/api/s/logmylife", tags=["logmylife"])


@router.get("/events")
def events(request: Request, scope: str = "mine", before: str | None = None, q: str = "",
           source: str = "", year: str = "", limit: int = 100):
    return store.timeline(request.state.user["id"], scope=scope, before=before, q=q,
                          source=source, year=year, limit=limit)


@router.get("/timeline")
def timeline(request: Request, scope: str = "mine", q: str = "", source: str = ""):
    return store.index(request.state.user["id"], scope=scope, q=q, source=source)


@router.get("/meta")
def meta(request: Request):
    me = request.state.user["id"]
    return {"categories": store.CATEGORIES, "stats": store.stats(me), "files": files.usage(me),
            "onThisDay": store.on_this_day(me, limit=20)}


@router.get("/events/{event_id}")
def entry(event_id: int, request: Request):
    try:
        return store.entry(request.state.user["id"], event_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc))


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


# ---- pictures and files ----------------------------------------------------------

@router.post("/events/{event_id}/files")
async def upload(event_id: int, name: str, request: Request):
    """One file as the request body, so a big one needs no form parsing in memory."""
    me = request.state.user["id"]
    try:
        temporary = await files.receive(me, request.stream())
        return await run_in_threadpool(files.add, me, event_id, name, temporary)
    except files.Problem as exc:
        raise HTTPException(413, str(exc))
    except LookupError as exc:
        raise HTTPException(404, str(exc))


@router.get("/files/{file_id}/{size}")
def file(file_id: int, size: str, request: Request):
    me = request.state.user["id"]
    row = files.readable(me, file_id)
    if row is None or size not in files.SIZES or (size != "original" and row["kind"] != "image"):
        raise HTTPException(404, "Findes ikke.")
    if size == "original" and row["kind"] == "image" and row["user_id"] != me:
        raise HTTPException(404, "Findes ikke.")            # it can carry where it was taken
    path = files.path_of(row, size)
    if not path.exists():
        raise HTTPException(404, "Filen er væk fra disken.")
    headers = {"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"}
    if size != "original":
        return FileResponse(path, media_type="image/jpeg", headers=headers)
    playable = row["mime"] in files.PLAYABLE
    return FileResponse(path, media_type=row["mime"], headers=headers, filename=row["name"],
                        content_disposition_type="inline" if playable else "attachment")


@router.delete("/files/{file_id}")
def remove_file(file_id: int, request: Request):
    try:
        files.remove(request.state.user["id"], file_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    return {"ok": True}


# ---- export ------------------------------------------------------------------------

@router.get("/export")
def export_log(request: Request, format: str = "zip", since: str = "", until: str = "", q: str = "", source: str = ""):
    """Everything of the person's own in the range, as a file the browser saves."""
    rows = export.entries(request.state.user["id"], since=since, until=until, q=q, source=source)
    stem = f"logmylife-{date.today().isoformat()}"
    disposition = lambda name: {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"}
    if format == "zip":
        return StreamingResponse(export.as_zip(rows), media_type="application/zip", headers=disposition(f"{stem}.zip"))
    makers = {"json": (export.as_json, "application/json"), "csv": (export.as_csv, "text/csv; charset=utf-8"),
              "ics": (export.as_ics, "text/calendar; charset=utf-8")}
    if format not in makers:
        raise HTTPException(400, "Ukendt format.")
    make, media = makers[format]
    return Response(make(rows), media_type=media, headers=disposition(f"{stem}.{format}"))


@router.post("/import/strava")
async def import_strava(request: Request):
    """Strava's export as the request body: the zip as it came, or just activities.csv."""
    me = request.state.user["id"]
    temporary = None
    try:
        temporary = await files.receive(me, request.stream())
        return await run_in_threadpool(strava.import_file, me, temporary)
    except files.Problem as exc:
        raise HTTPException(413, str(exc))
    except strava.Problem as exc:
        raise HTTPException(400, str(exc))
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
