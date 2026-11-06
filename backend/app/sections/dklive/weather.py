"""Rain radar from RainViewer (no key: the last two hours in ten-minute frames, to zoom 7)
and lightning from DMI's open API (no key)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import source

RAINVIEWER = "https://api.rainviewer.com/public/weather-maps.json"
LIGHTNING = "https://opendataapi.dmi.dk/v2/lightningdata/collections/observation/items"

_radar: dict = {"updated": 0, "host": None, "frames": [], "nowcast": []}
_lightning: dict = {"updated": 0, "strikes": []}


def reset() -> None:
    global _radar, _lightning
    _radar = {"updated": 0, "host": None, "frames": [], "nowcast": []}
    _lightning = {"updated": 0, "strikes": []}


def parse_radar(data: dict, now: int) -> dict:
    radar = data.get("radar") or {}
    frame = lambda f, ahead: {"time": f["time"] * 1000, "path": f["path"], "nowcast": ahead}
    return {"updated": now, "host": data.get("host"),
            "frames": [frame(f, False) for f in radar.get("past") or []],
            "nowcast": [frame(f, True) for f in radar.get("nowcast") or []]}


def parse_lightning(data: dict, now: int) -> dict:
    strikes = []
    for f in data.get("features") or []:
        coordinates = (f.get("geometry") or {}).get("coordinates") or []
        p = f.get("properties") or {}
        if len(coordinates) == 2:
            strikes.append({"lon": coordinates[0], "lat": coordinates[1], "time": source.iso_ms(p.get("observed")),
                            "type": int(p.get("type") or 0),     # 0 cloud to ground, 1 cloud to cloud
                            "amp": p.get("amp")})
    return {"updated": now, "strikes": strikes}


@source.watched("radar", "radar")
def radar_job() -> None:
    global _radar
    _radar = parse_radar(source.fetch(RAINVIEWER).json(), source.now_ms())
    source.done("radar", f"{len(_radar['frames'])} billeder")


@source.watched("lightning", "lightning")
def lightning_job() -> None:
    global _lightning
    since = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    data = source.fetch(LIGHTNING, params={"bbox": f"{source.WEST},{source.SOUTH},{source.EAST},{source.NORTH}",
                                           "datetime": f"{since}/..", "limit": 5000}).json()
    _lightning = parse_lightning(data, source.now_ms())
    source.done("lightning", f"{len(_lightning['strikes'])} lyn den seneste time")


def radar() -> dict:
    return _radar


def lightning() -> dict:
    return _lightning
