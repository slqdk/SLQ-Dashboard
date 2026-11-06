"""Live aircraft from adsb.lol (community ADS-B, no key): one 250 nm circle around the
map's centre, kept to the map's area. Routes come from adsbdb, one call at a time."""
from __future__ import annotations

import re
import time
from collections import deque

import httpx

from . import source

URL = f"https://api.adsb.lol/v2/lat/{source.CENTER_LAT:.3f}/lon/{source.CENTER_LON:.3f}/dist/250"
ROUTE_URL = "https://api.adsbdb.com/v0/callsign/"
SKIP_TYPES = {"TWR", "GND"}         # ground stations and vehicles reported as aircraft
CALLSIGN = re.compile(r"^[A-Z0-9]{3,8}$")      # anything else is a misconfigured transponder
MAX_ROUTES = 20000
BACKOFF_FIRST, BACKOFF_MOST = 30.0, 300.0
ROUTE_PAUSE = 30.0

_cache: dict = {"updated": 0, "aircraft": []}
_routes: dict[str, dict | None] = {}
_queue: deque[str] = deque()
_backoff = 0.0
_wait_until = 0.0
_routes_wait_until = 0.0


def reset() -> None:
    global _cache, _backoff, _wait_until, _routes_wait_until
    _cache = {"updated": 0, "aircraft": []}
    _routes.clear()
    _queue.clear()
    _backoff = _wait_until = _routes_wait_until = 0.0


def parse(data: dict, now: int) -> list[dict]:
    out = []
    for a in data.get("ac") or []:
        lat, lon = a.get("lat"), a.get("lon")
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)) or not source.in_bbox(lat, lon):
            continue
        if a.get("t") in SKIP_TYPES:
            continue
        ground = a.get("alt_baro") == "ground"
        emergency = a.get("emergency")
        out.append({
            "id": a.get("hex"),
            "callsign": (a.get("flight") or "").strip() or None,
            "reg": a.get("r"),
            "type": a.get("t"),
            "desc": a.get("desc"),                  # "BOEING 737-800"
            "operator": a.get("ownOp"),
            "category": a.get("category"),          # A1 light ... A5 heavy, A7 rotorcraft
            "lat": lat,
            "lon": lon,
            "alt": 0 if ground else a.get("alt_baro"),      # feet
            "onGround": ground,
            "gs": a.get("gs"),                      # knots
            "track": a.get("track"),
            "vr": a.get("baro_rate"),               # ft/min
            "squawk": a.get("squawk"),
            "emergency": emergency if emergency and emergency != "none" else None,
            "military": bool((a.get("dbFlags") or 0) & 1),
            "seen": now - round((a.get("seen_pos") or 0) * 1000),
        })
    return out


def _queue_routes(aircraft: list[dict]) -> None:
    for a in aircraft:
        sign = a["callsign"]
        if not sign or sign in _routes or sign in _queue:
            continue
        if CALLSIGN.match(sign):
            _queue.append(sign)
        else:
            _routes[sign] = None


def _hold(retry_after: float = 0.0) -> None:
    """Back off: 30 s, doubling to 5 min, or what the server asks for if that is longer."""
    global _backoff, _wait_until
    _backoff = min(_backoff * 2 if _backoff else BACKOFF_FIRST, BACKOFF_MOST)
    _wait_until = time.monotonic() + max(_backoff, retry_after)


@source.watched("flights", "flights", "military")
def job() -> None:
    global _cache, _backoff, _wait_until
    if time.monotonic() < _wait_until:
        return
    try:
        data = source.fetch(URL, headers={"Accept": "application/json"}).json()
    except httpx.HTTPStatusError as exc:
        try:
            _hold(float(exc.response.headers.get("retry-after") or 0))
        except ValueError:
            _hold()
        raise
    except httpx.HTTPError:
        _hold()
        raise
    _backoff = _wait_until = 0.0
    now = source.now_ms()
    aircraft = parse(data, now)
    _queue_routes(aircraft)
    for a in aircraft:
        a["route"] = _routes.get(a["callsign"]) if a["callsign"] else None
    _cache = {"updated": now, "aircraft": aircraft}
    source.done("flights", f"{len(aircraft)} fly")


def _route_of(data: dict) -> dict | None:
    route = (data.get("response") or {}).get("flightroute") if isinstance(data.get("response"), dict) else None
    origin, destination = (route or {}).get("origin"), (route or {}).get("destination")
    if not origin or not destination:
        return None
    return {"from": origin.get("iata_code") or origin.get("icao_code"),
            "to": destination.get("iata_code") or destination.get("icao_code"),
            "fromName": origin.get("municipality") or origin.get("name"),
            "toName": destination.get("municipality") or destination.get("name")}


@source.watched("flights-routes", "flights", "military")
def route_job() -> None:
    """One lookup per turn. A hiccup goes to the back of the queue; a callsign adsbdb
    does not know is remembered as unknown."""
    global _routes_wait_until
    if not _queue or time.monotonic() < _routes_wait_until:
        return
    sign = _queue.popleft()
    if sign in _routes:
        return
    try:
        _routes[sign] = _route_of(source.fetch(ROUTE_URL + sign).json())
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (400, 404):
            _routes[sign] = None
        else:
            _queue.append(sign)
            _routes_wait_until = time.monotonic() + ROUTE_PAUSE
    except httpx.HTTPError:
        _queue.append(sign)
        _routes_wait_until = time.monotonic() + ROUTE_PAUSE
    while len(_routes) > MAX_ROUTES:
        del _routes[next(iter(_routes))]


def get() -> dict:
    return _cache
