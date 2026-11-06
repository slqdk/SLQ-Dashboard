"""DK live's API, under /api/s/dklive: the section's page, and what the map reads."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Query, Response

from . import client, flow, forecast, photos, source, webcams

router = APIRouter(prefix="/api/s/dklive", tags=["dklive"])


@router.get("/state")
def state():
    return client.state()


@router.get("/map/flow/{z}/{x}/{y}.pbf")
def flow_tile(z: int, x: int, y: int):
    try:
        tile = flow.tile(z, x, y)
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"TomTom: {source.why(exc)}")
    if tile is None:
        raise HTTPException(404, "Ingen nøgle til TomTom.")
    return Response(tile, media_type="application/x-protobuf", headers={"Cache-Control": "private, max-age=60"})


@router.get("/map/forecast")
def point_forecast(lat: float = Query(...), lon: float = Query(...)):
    if not source.in_bbox(lat, lon):
        raise HTTPException(400, "Stedet er uden for kortet.")
    try:
        return forecast.at(lat, lon)
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Open-Meteo: {source.why(exc)}")


@router.get("/map/windy/{webcam}")
def windy_image(webcam: int):
    try:
        picture = webcams.image(str(webcam))
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Windy: {source.why(exc)}")
    if picture is None:
        raise HTTPException(404, "Ingen nøgle til Windy.")
    return picture


@router.get("/map/photo/aircraft/{hex_id}")
def aircraft_photo(hex_id: str, reg: str | None = None, type: str | None = None):
    return photos.aircraft(hex_id, reg, type) or {}


@router.get("/map/photo/ship/{mmsi}")
def ship_photo(mmsi: int, name: str | None = None):
    return photos.ship(mmsi, name) or {}


@router.get("/map/{feed}")
def map_feed(feed: str):
    data = client.map_feed(feed)
    if data is None:
        raise HTTPException(404, "Kortet har ikke det lag.")
    return data
