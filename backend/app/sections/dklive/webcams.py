"""One list of webcams: Autobahn's roadside cameras (no key), Windy Webcams API v3 (free
key, attribution "webcams by Windy") and a few of our own.

Windy's image addresses expire after ten minutes on the free tier, so the list has no
images and a fresh one is fetched when a popup opens."""
from __future__ import annotations

from ...core import settings
from . import autobahn, source

WINDY = "https://api.windy.com/webcams/api/v3"
OWN = [
    {"id": "own-0", "source": "egen", "name": "Storebæltsbroen, østpylonen", "lat": 55.3420, "lon": 11.0330,
     "image": None, "link": "https://storebaelt.dk/trafik-vejr/webcams/", "note": "Live stream, åbner på storebaelt.dk"},
    {"id": "own-1", "source": "egen", "name": "Sprogø", "lat": 55.3320, "lon": 10.9750,
     "image": None, "link": "https://storebaelt.dk/trafik-vejr/webcams/", "note": "Live stream, åbner på storebaelt.dk"},
]

_windy: list[dict] = []


def reset() -> None:
    global _windy
    _windy = []


def _windy_get(path: str, key: str, params: dict | None = None) -> dict:
    return source.fetch(f"{WINDY}{path}", params=params, headers={"x-windy-api-key": key}).json()


def windy_camera(w: dict) -> dict | None:
    location = w.get("location") or {}
    lat, lon = location.get("latitude"), location.get("longitude")
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)) or not source.in_bbox(lat, lon):
        return None
    if w.get("status") and w["status"] != "active":
        return None
    return {"id": f"windy-{w.get('webcamId')}", "windyId": w.get("webcamId"), "source": "windy",
            "name": w.get("title"), "lat": lat, "lon": lon, "city": location.get("city"),
            "country": location.get("country"),
            "link": (w.get("urls") or {}).get("detail") or (w.get("player") or {}).get("day")}


@source.watched("webcams", "webcams")
def job() -> None:
    """Hourly. Windy allows 250 km around a point, so two circles cover the map."""
    global _windy
    key = settings.load().get("windyKey") or ""
    if not key:
        reset()
        source.off("webcams")
        return
    found: dict = {}
    for lat in (source.NORTH - 1.1, source.SOUTH + 1.1):
        for offset in range(0, 2000, 50):
            data = _windy_get("/webcams", key, {"nearby": f"{lat:.3f},{source.CENTER_LON:.3f},250", "limit": 50,
                                                "offset": offset, "include": "location,categories,player,urls"})
            for w in data.get("webcams") or []:
                camera = windy_camera(w)
                if camera:
                    found[w.get("webcamId")] = camera
            if not data.get("webcams") or offset + 50 >= (data.get("total") or 0):
                break
    _windy = list(found.values())
    source.done("webcams", f"{len(_windy)} fra Windy")


def image(windy_id: str) -> dict | None:
    """A fresh picture of one camera; None without a key. Raises httpx errors."""
    key = settings.load().get("windyKey") or ""
    if not key:
        return None
    data = _windy_get(f"/webcams/{windy_id}", key, {"include": "images,player"})
    current = (data.get("images") or {}).get("current") or {}
    player = data.get("player") or {}
    return {"image": current.get("preview") or current.get("thumbnail"), "live": player.get("live"), "day": player.get("day")}


def get() -> dict:
    roadside = [{**c, "source": "autobahn", "name": f"{c['road']}, {c['title']}"} for c in autobahn.cameras()["items"]]
    return {"items": roadside + _windy + OWN}
