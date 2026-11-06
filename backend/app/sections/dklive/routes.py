"""DK live's API, under /api/s/dklive, and dk-live's own map passed through."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response

from . import client

router = APIRouter(prefix="/api/s/dklive", tags=["dklive"])


@router.get("/state")
def state():
    return client.state()


@router.get("/map/{path:path}")
def map_file(path: str, request: Request):
    try:
        file = client.map_file(path, str(request.url.query))
    except client.NotOnTheMap:
        raise HTTPException(403, "Ikke en del af kortet.")
    except client.MapUnavailable as exc:
        raise HTTPException(502, str(exc))
    return Response(file.content, status_code=file.status_code,
                    media_type=file.headers.get("content-type", "application/octet-stream"),
                    headers={"Cache-Control": file.headers.get("cache-control", "no-store")})
