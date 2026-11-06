"""Kameraer's API, under /api/s/cameras. Everyone with the section sees the
pictures; only an admin changes which cameras there are."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from ...core import jobs
from . import client, store

router = APIRouter(prefix="/api/s/cameras", tags=["cameras"])


def _admin(request: Request) -> None:
    if request.state.user["role"] != "admin":
        raise HTTPException(403, "Kun for administrator.")


@router.get("/list")
def cameras():
    return client.overview({})


@router.get("/{camera_id}/frame.jpg")
def frame(camera_id: int, size: str = "lo"):
    try:
        picture = client.frame(camera_id, size)
    except client.NoPicture as exc:
        raise HTTPException(503, str(exc))
    return Response(picture, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.get("/{camera_id}/live.mp4")
async def live(camera_id: int):
    try:
        media_type, body = await client.live(camera_id)
    except client.NoPicture as exc:
        raise HTTPException(503, str(exc))
    return StreamingResponse(body, media_type=media_type, headers={"Cache-Control": "no-store"})


@router.get("/config")
def config(request: Request):
    _admin(request)
    return {"items": store.all_cameras(), "status": client.setup_status()}


@router.post("/config")
def add(body: dict, request: Request):
    _admin(request)
    try:
        out = store.add(body)
    except store.Problem as exc:
        raise HTTPException(400, str(exc))
    jobs.kick()
    return out


@router.put("/config/{camera_id}")
def update(camera_id: int, body: dict, request: Request):
    _admin(request)
    try:
        out = store.update(camera_id, body)
    except store.Problem as exc:
        raise HTTPException(400, str(exc))
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    jobs.kick()
    return out


@router.delete("/config/{camera_id}")
def delete(camera_id: int, request: Request):
    _admin(request)
    store.delete(camera_id)
    jobs.kick()
    return {"ok": True}
