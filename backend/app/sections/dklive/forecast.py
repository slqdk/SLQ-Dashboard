"""Point forecasts from Open-Meteo (no key): now, 15-minute rain for six hours, hourly for
three days. Home is kept fresh by a job; a place on the map is fetched when someone clicks
it and kept ten minutes. Place names come from Nominatim, at most one every 1.2 seconds.
Kilde: Open-Meteo.com"""
from __future__ import annotations

import threading
import time

import httpx

from ...core import logs, settings
from . import source

URL = "https://api.open-meteo.com/v1/forecast"
NOMINATIM = "https://nominatim.openstreetmap.org/reverse"
TTL = 600.0
GAP = 1.2
MOST_KEPT = 200
CURRENT = ("temperature_2m", "apparent_temperature", "relative_humidity_2m", "precipitation", "weather_code",
           "cloud_cover", "pressure_msl", "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m", "is_day")
MIN15 = ("precipitation", "weather_code")
HOURLY = ("temperature_2m", "precipitation", "precipitation_probability", "weather_code", "wind_speed_10m",
          "wind_gusts_10m", "wind_direction_10m", "cloud_cover")
DAILY = ("weather_code", "temperature_2m_max", "temperature_2m_min", "precipitation_sum",
         "precipitation_probability_max", "wind_speed_10m_max", "sunrise", "sunset")

_cache: dict[str, tuple[float, dict]] = {}
_places: dict[str, str | None] = {}
_home: dict = {}
_lock = threading.Lock()
_next_slot = 0.0


def reset() -> None:
    global _home, _next_slot
    _cache.clear()
    _places.clear()
    _home = {}
    _next_slot = 0.0


def _wait_turn() -> None:
    global _next_slot
    with _lock:
        now = time.monotonic()
        wait = max(0.0, _next_slot - now)
        _next_slot = max(now, _next_slot) + GAP
    if wait:
        time.sleep(wait)


def place_name(address: dict, name: str | None) -> str | None:
    local = next((address[k] for k in ("city", "town", "village", "hamlet", "suburb", "municipality", "county") if address.get(k)), None)
    wider = next((address[k] for k in ("municipality", "county") if address.get(k) and address[k] != local), None)
    water = address.get("water") or address.get("sea") or address.get("bay")
    return ", ".join(p for p in (local, wider) if p) if local else water or name


def _place(lat: float, lon: float) -> str | None:
    key = f"{lat:.2f},{lon:.2f}"
    if key in _places:
        return _places[key]
    _wait_turn()
    try:
        data = source.fetch(NOMINATIM, params={"format": "jsonv2", "zoom": 13, "lat": f"{lat:.4f}", "lon": f"{lon:.4f}",
                                               "accept-language": "da"}).json()
    except (httpx.HTTPError, ValueError) as exc:
        logs.record_problem("dklive", f"place name: {source.why(exc)}")
        return None             # not kept, so the next time tries again
    _places[key] = place_name(data.get("address") or {}, data.get("name"))
    return _places[key]


def _series(block: dict | None, fields: tuple[str, ...]) -> list[dict]:
    block = block or {}
    rows = []
    for i, at in enumerate(block.get("time") or []):
        row = {"time": at}
        for field in fields:
            values = block.get(field) or []
            row[field] = values[i] if i < len(values) else None
        rows.append(row)
    return rows


def shape(data: dict, place: str | None, now: int) -> dict:
    return {"lat": data.get("latitude"), "lon": data.get("longitude"), "place": place, "elevation": data.get("elevation"),
            "updated": now, "current": data.get("current"), "minutely": _series(data.get("minutely_15"), MIN15),
            "hourly": _series(data.get("hourly"), HOURLY), "daily": _series(data.get("daily"), DAILY)}


def at(lat: float, lon: float) -> dict:
    """The forecast for a point. Raises httpx errors."""
    key = f"{lat:.2f},{lon:.2f}"
    held = _cache.get(key)
    if held and time.monotonic() - held[0] < TTL:
        return held[1]
    params = {"latitude": f"{lat:.4f}", "longitude": f"{lon:.4f}", "current": ",".join(CURRENT),
              "minutely_15": ",".join(MIN15), "hourly": ",".join(HOURLY), "daily": ",".join(DAILY), "forecast_days": 3,
              "forecast_minutely_15": 24, "timezone": settings.load().get("timezone") or "Europe/Copenhagen",
              "wind_speed_unit": "ms"}
    data = shape(source.fetch(URL, params=params).json(), _place(lat, lon), source.now_ms())
    _cache[key] = (time.monotonic(), data)
    while len(_cache) > MOST_KEPT:
        del _cache[next(iter(_cache))]
    return data


@source.watched("forecast")
def job() -> None:
    global _home
    s = settings.load()
    _home = at(float(s["homeLat"]), float(s["homeLon"]))
    source.done("forecast", _home.get("place") or "hjemme")


def home() -> dict:
    return _home
