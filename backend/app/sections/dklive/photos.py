"""Photos for the map's popups. Aircraft from Planespotters by ICAO hex (free; asks for a
contact, a credit and a link, and at most a request a second). Ships from Wikimedia
Commons by name, which can be a namesake and says so. A hit is kept a day, a miss an hour."""
from __future__ import annotations

import re
import threading
import time
from urllib.parse import quote

import httpx

from ...core import settings
from . import source

PLANESPOTTERS = "https://api.planespotters.net/pub/photos/hex/"
COMMONS = "https://commons.wikimedia.org/w/api.php"
HIT_FOR, MISS_FOR = 24 * 3600.0, 3600.0
MOST_KEPT = 5000

_cache: dict[str, tuple[float, dict | None]] = {}
_lock = threading.Lock()
_next_slot = 0.0


def reset() -> None:
    global _next_slot
    _cache.clear()
    _next_slot = 0.0


def _held(key: str) -> tuple[bool, dict | None]:
    entry = _cache.get(key)
    if not entry or time.monotonic() - entry[0] > (HIT_FOR if entry[1] else MISS_FOR):
        return False, None
    return True, entry[1]


def _keep(key: str, photo: dict | None) -> dict | None:
    _cache[key] = (time.monotonic(), photo)
    while len(_cache) > MOST_KEPT:
        del _cache[next(iter(_cache))]
    return photo


def _wait_turn() -> None:
    global _next_slot
    with _lock:
        now = time.monotonic()
        wait = max(0.0, _next_slot - now)
        _next_slot = max(now, _next_slot) + 1.0
    if wait:
        time.sleep(wait)


def aircraft(hex_id: str, reg: str | None, kind: str | None) -> dict | None:
    contact = (settings.load().get("photoContact") or "").strip()
    if not contact:
        return None
    key = f"ac:{hex_id}"
    known, photo = _held(key)
    if known:
        return photo
    _wait_turn()
    params = {k: v for k, v in (("reg", reg), ("icaoType", kind)) if v}
    try:
        response = source.fetch(PLANESPOTTERS + quote(hex_id.upper(), safe=""), params=params,
                                headers={"User-Agent": f"SLQ-Dashboard/0.6 ({contact})", "Accept": "application/json"})
    except httpx.HTTPStatusError as exc:
        return _keep(key, None) if exc.response.status_code == 404 else None
    except httpx.HTTPError:
        return None             # an error is not "no photo": it is not kept
    photos = response.json().get("photos") or []
    if not photos:
        return _keep(key, None)
    p = photos[0]
    return _keep(key, {"thumb": (p.get("thumbnail_large") or p.get("thumbnail") or {}).get("src"), "link": p.get("link"),
                       "credit": p.get("photographer"), "source": "Planespotters.net"})


def _letters(text: str) -> str:
    return re.sub(r"[^a-z0-9æøå]", "", text.lower())


def pick_commons(pages: list[dict], name: str) -> dict | None:
    """A file whose title holds the ship's name, or none at all."""
    want = _letters(name)
    page = next((p for p in pages if want in _letters(p.get("title") or "")), None)
    info = ((page or {}).get("imageinfo") or [None])[0]
    if not info:
        return None
    meta = info.get("extmetadata") or {}
    return {"thumb": info.get("thumburl") or info.get("url"), "link": info.get("descriptionurl"),
            "credit": re.sub(r"<[^>]+>", "", (meta.get("Artist") or {}).get("value") or "").strip() or None,
            "license": (meta.get("LicenseShortName") or {}).get("value"), "source": "Wikimedia Commons", "uncertain": True}


def ship(mmsi: int, name: str | None) -> dict | None:
    key = f"ship:{mmsi}"
    known, photo = _held(key)
    if known:
        return photo
    name = (name or "").strip()
    if len(name) >= 3:
        try:
            data = source.fetch(COMMONS, params={
                "action": "query", "generator": "search", "gsrnamespace": 6, "gsrlimit": 5,
                "gsrsearch": f'"{name}" (ship OR vessel OR ferry OR færge OR skib) filetype:bitmap',
                "prop": "imageinfo", "iiprop": "url|extmetadata", "iiurlwidth": 480, "format": "json"}).json()
        except (httpx.HTTPError, ValueError):
            return None
        photo = pick_commons(list(((data.get("query") or {}).get("pages") or {}).values()), name)
    return _keep(key, photo)
