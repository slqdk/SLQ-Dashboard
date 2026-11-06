"""Road incidents from Vejdirektoratet. Trafikkort's public feed (no key) is a log of
versions of each event, so the newest per event counts and ended ones go.
Kilde: Vejdirektoratet / trafikinfo.dk"""
from __future__ import annotations

import html as markup
import re

from . import source

URL = "https://storage.googleapis.com/trafikkort-data/geojson/big-screen-events.json"
GRACE_MS = 10 * 60_000      # expired but not yet marked suspended

TYPES = {"Accident": "uheld", "VehicleObstruction": "havari", "GeneralObstruction": "forhindring",
         "RoadOrCarriagewayOrLaneManagement": "spærring", "AbnormalTraffic": "kø", "PoorEnvironmentConditions": "vejr",
         "Roadworks": "vejarbejde", "MaintenanceWorks": "vejarbejde", "ConstructionWorks": "vejarbejde",
         "PublicEvent": "begivenhed", "GeneralInstructionOrMessageToRoadUsers": "info"}

_cache: dict = {"updated": 0, "events": []}


def reset() -> None:
    global _cache
    _cache = {"updated": 0, "events": []}


def strip(text: str | None) -> str:
    text = re.sub(r"<periodDescription>.*?</periodDescription>", "", text or "", flags=re.S)
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"</p>\s*<p>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\n{2,}", "\n", markup.unescape(text)).strip()


def dk_time(text: str | None) -> int | None:
    """"13-09-2026 kl. 15:45" as an instant."""
    m = re.search(r"(\d{2})-(\d{2})-(\d{4}) kl\. (\d{2}):(\d{2})", text or "")
    return source.copenhagen_ms(int(m[3]), int(m[2]), int(m[1]), int(m[4]), int(m[5])) if m else None


def parse(collections: list[dict], now: int) -> list[dict]:
    latest: dict[str, tuple[dict, str]] = {}
    for fc in collections:
        for feature in fc.get("features") or []:
            p = feature.get("properties") or {}
            if p.get("duplicate") == "true" or not p.get("featureId"):
                continue        # a duplicate is an extra point along a route
            held = latest.get(p["featureId"])
            if not held or (p.get("lastModifiedString") or "") > (held[0]["properties"].get("lastModifiedString") or ""):
                latest[p["featureId"]] = (feature, fc.get("layerName") or "")
    events = []
    for feature, layer in latest.values():
        p = feature["properties"]
        if "true" in (p.get("suspended"), p.get("future")) or p.get("visible") == "false":
            continue
        coordinates = (feature.get("geometry") or {}).get("coordinates") or []
        if len(coordinates) < 2 or not isinstance(coordinates[1], (int, float)) or not source.in_bbox(coordinates[1], coordinates[0]):
            continue
        end = dk_time(p.get("endPeriod"))
        if end and end < now - GRACE_MS:
            continue
        kind = (p.get("TrafficMan2_Type") or "").split(".")[-1]
        events.append({
            "id": p["featureId"],
            "title": p.get("title"),
            "header": strip(p.get("header")),
            "text": strip(p.get("description")),
            "kind": TYPES.get(kind, "info"),
            "blocking": p.get("subtype") == "blocking" or "roadblock" in layer or "blocking" in layer,
            "source": p.get("kommune"),
            "begin": dk_time(p.get("beginPeriod")),
            "end": end,
            "modified": dk_time(p.get("lastModified")),
            "lat": coordinates[1],
            "lon": coordinates[0],
        })
    events.sort(key=lambda e: e["modified"] or 0, reverse=True)
    return events


@source.watched("traffic")
def job() -> None:
    global _cache
    now = source.now_ms()
    events = parse(source.fetch(URL).json(), now)
    _cache = {"updated": now, "events": events}
    source.done("traffic", f"{len(events)} hændelser")


def get() -> dict:
    return _cache
