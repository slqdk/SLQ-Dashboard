"""Airports from OurAirports (public domain): airports, runways and frequencies, fetched
monthly and kept. METAR for the fields that report one, from aviationweather.gov (no key)."""
from __future__ import annotations

import csv
import io
import re
import time

from . import source, store

OURAIRPORTS = "https://davidmegginson.github.io/ourairports-data"
METAR = "https://aviationweather.gov/api/data/metar"
TYPES = {"large_airport", "medium_airport", "small_airport"}
FRESH_DAYS = 30
ICAO = re.compile(r"^[A-Z]{4}$")
METRES_PER_FOOT = 0.3048
METRES_PER_MILE = 1609

_airports: list[dict] | None = None
_metars: dict[str, dict] = {}


def reset() -> None:
    global _airports
    _airports = None
    _metars.clear()


def _rows(name: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(source.fetch(f"{OURAIRPORTS}/{name}", timeout=60.0).text)))


def _metres(feet: str) -> int | None:
    return round(float(feet) * METRES_PER_FOOT) if feet else None


def build(airports: list[dict], runways: list[dict], frequencies: list[dict]) -> list[dict]:
    by_id: dict[str, dict] = {}
    for a in airports:
        lat, lon = float(a["latitude_deg"]), float(a["longitude_deg"])
        if a["type"] not in TYPES or not source.in_bbox(lat, lon):
            continue
        by_id[a["id"]] = {"id": a["id"], "icao": a.get("gps_code") or a["ident"], "iata": a.get("iata_code") or None,
                          "name": a["name"], "type": a["type"].replace("_airport", ""), "lat": lat, "lon": lon,
                          "elevationFt": float(a["elevation_ft"]) if a.get("elevation_ft") else None,
                          "municipality": a.get("municipality") or None, "country": a.get("iso_country"),
                          "scheduled": a.get("scheduled_service") == "yes", "website": a.get("home_link") or None,
                          "wikipedia": a.get("wikipedia_link") or None, "runways": [], "frequencies": []}
    for r in runways:
        airport = by_id.get(r["airport_ref"])
        if airport and r.get("closed") != "1":
            airport["runways"].append({"ident": "/".join(x for x in (r.get("le_ident"), r.get("he_ident")) if x),
                                       "lengthM": _metres(r.get("length_ft")), "widthM": _metres(r.get("width_ft")),
                                       "surface": r.get("surface") or None, "lighted": r.get("lighted") == "1"})
    for f in frequencies:
        airport = by_id.get(f["airport_ref"])
        if airport:
            airport["frequencies"].append({"type": f["type"], "desc": f.get("description") or None, "mhz": f.get("frequency_mhz")})
    return sorted(by_id.values(), key=lambda a: a["name"])


def _load() -> list[dict]:
    """From what is kept while it is fresh, from OurAirports otherwise. If that fails,
    what is kept is better than nothing, and the next turn tries again."""
    global _airports
    held = store.load("airports")
    if held and time.time() - held["at"] < FRESH_DAYS * 86400:
        _airports = held["airports"]
        return _airports
    try:
        built = build(_rows("airports.csv"), _rows("runways.csv"), _rows("airport-frequencies.csv"))
    except Exception:
        if not held:
            raise
        _airports = held["airports"]
        return _airports
    store.save("airports", {"at": time.time(), "airports": built})
    _airports = built
    return built


def metar(m: dict) -> dict:
    report = m.get("reportTime")
    seen = m.get("visib")
    return {"raw": m.get("rawOb"), "time": source.iso_ms(report), "tempC": m.get("temp"), "dewC": m.get("dewp"),
            "windDir": m.get("wdir"), "windKt": m.get("wspd"), "gustKt": m.get("wgst"),
            "visM": seen if isinstance(seen, str) or seen is None else round(seen * METRES_PER_MILE),
            "qnh": round(m["altim"]) if m.get("altim") is not None else None, "wx": m.get("wxString"),
            "clouds": ", ".join(f"{c.get('cover')}{'' if c.get('base') is None else ' %s ft' % c['base']}" for c in m.get("clouds") or []) or None,
            "fltCat": m.get("fltCat")}


@source.watched("airports", "airports")
def job() -> None:
    airports = _load() if _airports is None else _airports
    ids = [a["icao"] for a in airports if (a["type"] != "small" or a["scheduled"]) and ICAO.match(a["icao"] or "")]
    if ids:
        fresh = {m["icaoId"]: metar(m) for m in source.fetch(METAR, params={"ids": ",".join(ids), "format": "json"}).json()}
        _metars.clear()
        _metars.update(fresh)
    source.done("airports", f"{len(airports)} lufthavne, {len(_metars)} METAR")


def get() -> dict:
    return {"airports": [{**a, "metar": _metars.get(a["icao"])} for a in _airports or []]}
