"""German motorways from Autobahn GmbH's open API (no key): warnings, closures, roadworks
and roadside cameras on the roads that reach into the map. Kilde: Autobahn GmbH des Bundes."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import httpx

from . import source

BASE = "https://verkehr.autobahn.de/o/autobahn"
ROADS = ("A7", "A1", "A20", "A21", "A23", "A24", "A25", "A26", "A210", "A215", "A226", "A252", "A255", "A261")
SERVICES = {"warning": "melding", "closure": "spærring", "roadworks": "vejarbejde"}
AT_ONCE = 4                 # so the API is not hammered

_events: dict = {"updated": 0, "items": []}
_cameras: dict = {"updated": 0, "items": []}


def reset() -> None:
    global _events, _cameras
    _events = {"updated": 0, "items": []}
    _cameras = {"updated": 0, "items": []}


def _number(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _place(item: dict) -> tuple[float, float] | None:
    coordinate = item.get("coordinate") or {}
    lat, lon = _number(coordinate.get("lat")), _number(coordinate.get("long"))
    return (lat, lon) if lat is not None and lon is not None and source.in_bbox(lat, lon) else None


def _text(description) -> str:
    joined = "\n".join(p for p in description if p) if isinstance(description, list) else (description or "")
    return "\n".join(line.strip() for line in joined.split("\n")).strip()


def _true(value) -> bool:
    return value is True or value == "true"


def event(road: str, service: str, e: dict) -> dict | None:
    place = _place(e)
    if not place:
        return None
    return {"id": e.get("identifier") or f"{road}-{service}-{place[0]},{place[1]}",
            "road": road,
            "kind": SERVICES[service],
            "title": (e.get("title") or e.get("subtitle") or road).strip(),
            "subtitle": (e.get("subtitle") or "").strip(),
            "text": _text(e.get("description")),
            "blocked": _true(e.get("isBlocked")),
            "future": _true(e.get("future")),
            "start": source.iso_ms(e.get("startTimestamp")),
            "lat": place[0],
            "lon": place[1]}


def camera(road: str, c: dict) -> dict | None:
    place = _place(c)
    if not place:
        return None
    return {"id": c.get("identifier") or f"{road}-{place[0]},{place[1]}",
            "road": road,
            "title": (c.get("title") or c.get("subtitle") or road).strip(),
            "subtitle": (c.get("subtitle") or "").strip(),
            "operator": c.get("operator"),
            "image": c.get("imageurl"),
            "link": c.get("linkurl"),
            "lat": place[0],
            "lon": place[1]}


def _get(road: str, service: str) -> list[dict]:
    data = source.fetch(f"{BASE}/{road}/services/{service}").json()
    return data.get(service) or (next(iter(data.values()), []) if data else [])


def _all(pairs: list[tuple[str, str]], build) -> tuple[list[dict], int]:
    """A few roads at a time. One that fails is left out of this round."""
    failed = 0

    def one(pair: tuple[str, str]) -> list[dict]:
        nonlocal failed
        try:
            return [x for x in (build(pair[0], pair[1], item) for item in _get(*pair)) if x]
        except (httpx.HTTPError, ValueError):
            failed += 1
            return []

    with ThreadPoolExecutor(AT_ONCE) as pool:
        return [x for part in pool.map(one, pairs) for x in part], failed


def _report(name: str, count: int, failed: int, total: int, what: str) -> None:
    if failed == total:
        source.failed(name, "ingen veje svarer")
    else:
        source.done(name, f"{count} {what}" + (f", {failed} af {total} svarede ikke" if failed else ""))


@source.watched("autobahn", "autobahn")
def job() -> None:
    global _events
    pairs = [(road, service) for road in ROADS for service in SERVICES]
    items, failed = _all(pairs, event)
    unique = list({item["id"]: item for item in items if not item["future"]}.values())
    if failed < len(pairs):
        _events = {"updated": source.now_ms(), "items": unique}
    _report("autobahn", len(unique), failed, len(pairs), "hændelser")


@source.watched("autobahn-cameras", "webcams")
def camera_job() -> None:
    global _cameras
    pairs = [(road, "webcam") for road in ROADS]
    items, failed = _all(pairs, lambda road, _service, c: camera(road, c))
    items = list({c["id"]: c for c in items if c["image"]}.values())
    if failed < len(pairs):
        _cameras = {"updated": source.now_ms(), "items": items}
    _report("autobahn-cameras", len(items), failed, len(pairs), "kameraer")


def get() -> dict:
    return _events


def cameras() -> dict:
    return _cameras
