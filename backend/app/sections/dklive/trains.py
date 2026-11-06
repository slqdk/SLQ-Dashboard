"""Live train positions from Rejseplanen API 2.0 (journeypos). A free key, 50,000 calls a
month; one a minute stays well inside that. Key from labs.rejseplanen.dk."""
from __future__ import annotations

from ...core import settings
from . import source

URL = "https://www.rejseplanen.dk/api/journeypos"
# Rejseplanen's products: 1 ICL, 2 IC, 4 RE, 8 Ø/Re-tog, 16 S-tog, 1024 metro, 2048 letbane.
TRAINS = 1 + 2 + 4 + 8 + 16 + 1024 + 2048

_cache: dict = {"enabled": False, "updated": 0, "vehicles": []}


def reset() -> None:
    global _cache
    _cache = {"enabled": False, "updated": 0, "vehicles": []}


def parse(data: dict, now: int) -> list[dict]:
    journeys = (data.get("JourneyPosList") or {}).get("Journey") or data.get("Journey") or []
    out = []
    for j in journeys:
        if not isinstance(j.get("lat"), (int, float)) or not isinstance(j.get("lon"), (int, float)):
            continue
        product = j.get("Product") or {}
        product = (product[0] if product else {}) if isinstance(product, list) else product
        out.append({
            "id": j.get("id") or j.get("jid") or f"{j.get('name')}-{j.get('date')}",
            "name": (j.get("name") or product.get("name") or "").strip(),
            "line": product.get("line") or product.get("num"),
            "category": product.get("catOutS") or product.get("catOut"),    # IC, ICL, RE, S, M
            "operator": product.get("operator"),
            "direction": j.get("dirTxt") or j.get("direction"),
            "delay": j.get("delay"),
            "lat": j["lat"],
            "lon": j["lon"],
            "seen": now,
        })
    return out


@source.watched("trains", "trains")
def job() -> None:
    global _cache
    key = settings.load().get("rejseplanenKey") or ""
    if not key:
        reset()
        source.off("trains")
        return
    data = source.fetch(URL, params={"accessId": key, "format": "json", "llLat": source.SOUTH, "llLon": source.WEST,
                                     "urLat": source.NORTH, "urLon": source.EAST, "products": TRAINS, "maxJny": 500}).json()
    now = source.now_ms()
    vehicles = parse(data, now)
    _cache = {"enabled": True, "updated": now, "vehicles": vehicles}
    source.done("trains", f"{len(vehicles)} tog")


def get() -> dict:
    return _cache
