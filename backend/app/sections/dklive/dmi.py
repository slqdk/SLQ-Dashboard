"""DMI's open observations (no key): wind from the weather stations and sea level from the
tide gauges, in cm relative to DVR90. Station names are refreshed daily."""
from __future__ import annotations

import time

import httpx

from . import source

BASE = "https://opendataapi.dmi.dk/v2"
BBOX = f"{source.WEST},{source.SOUTH},{source.EAST},{source.NORTH}"
NAMES_FOR = 24 * 3600.0
QUIET_GAUGE_MS = 3 * 3_600_000      # a gauge not heard for this long has gone quiet

_wind: dict = {"updated": 0, "stations": []}
_sea: dict = {"updated": 0, "stations": []}
_names: dict[str, dict[str, str]] = {"metObs": {}, "oceanObs": {}}
_names_at: dict[str, float] = {"metObs": 0.0, "oceanObs": 0.0}


def reset() -> None:
    global _wind, _sea
    _wind = {"updated": 0, "stations": []}
    _sea = {"updated": 0, "stations": []}
    for api in _names:
        _names[api] = {}
        _names_at[api] = 0.0


def _items(api: str, collection: str, **params) -> list[dict]:
    data = source.fetch(f"{BASE}/{api}/collections/{collection}/items", params={"bbox": BBOX, "limit": 10000, **params}).json()
    return data.get("features") or []


def _load_names(api: str) -> None:
    if time.monotonic() - _names_at[api] < NAMES_FOR and _names_at[api]:
        return
    try:
        for f in _items(api, "station", status="Active"):
            p = f.get("properties") or {}
            if p.get("stationId"):
                _names[api][p["stationId"]] = p.get("name")
        _names_at[api] = time.monotonic()
    except (httpx.HTTPError, ValueError):
        pass        # the stations show by number until the next turn


def latest(features: list[dict]) -> dict[str, dict]:
    """The newest value per station."""
    out: dict[str, dict] = {}
    for f in features:
        p = f.get("properties") or {}
        at = source.iso_ms(p.get("observed"))
        held = out.get(p.get("stationId"))
        if at and (not held or at > held["time"]):
            out[p["stationId"]] = {"value": p.get("value"), "time": at, "coords": (f.get("geometry") or {}).get("coordinates")}
    return out


def wind_stations(speed: dict, direction: dict, gust: dict, temp: dict, names: dict) -> list[dict]:
    out = []
    for station, s in speed.items():
        if not s["coords"] or s["value"] is None:
            continue
        out.append({"id": station, "name": names.get(station) or station, "lon": s["coords"][0], "lat": s["coords"][1],
                    "time": s["time"],
                    "speed": s["value"],                                # m/s, 10-minute mean
                    "dir": (direction.get(station) or {}).get("value"),  # where the wind comes from
                    "gust": (gust.get(station) or {}).get("value"),      # m/s, strongest in 10 minutes
                    "temp": (temp.get(station) or {}).get("value")})
    return out


@source.watched("wind", "wind")
def wind_job() -> None:
    global _wind
    _load_names("metObs")
    speed, direction, gust, temp = (latest(_items("metObs", "observation", parameterId=p, period="latest-hour"))
                                    for p in ("wind_speed", "wind_dir", "wind_max", "temp_dry"))
    stations = wind_stations(speed, direction, gust, temp, _names["metObs"])
    _wind = {"updated": source.now_ms(), "stations": stations}
    source.done("wind", f"{len(stations)} stationer")


@source.watched("sealevel", "sealevel")
def sea_job() -> None:
    global _sea
    _load_names("oceanObs")
    now = source.now_ms()
    stations = []
    for station, s in latest(_items("oceanObs", "observation", parameterId="sealev_dvr", period="latest-day")).items():
        if s["coords"] and s["value"] is not None and s["time"] >= now - QUIET_GAUGE_MS:
            stations.append({"id": station, "name": _names["oceanObs"].get(station) or station, "lon": s["coords"][0],
                             "lat": s["coords"][1], "time": s["time"], "level": s["value"]})
    _sea = {"updated": now, "stations": stations}
    source.done("sealevel", f"{len(stations)} vandstandsmålere")


def wind() -> dict:
    return _wind


def sea() -> dict:
    return _sea
