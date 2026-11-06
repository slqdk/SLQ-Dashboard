"""Traffic flow from TomTom as vector tiles (free key, 2,500 tiles a day). Each road
carries its category and how its speed compares to free flow, so the map draws only
motorways and colours them. Tiles pass through here so the key stays on the server, and
are kept a minute."""
from __future__ import annotations

import time

from ...core import settings
from . import source

URL = "https://api.tomtom.com/traffic/map/4/tile/flow/relative/{z}/{x}/{y}.pbf"
TAGS = "[traffic_level,traffic_road_coverage,road_category,road_subcategory]"
FRESH = 60.0
MOST_KEPT = 2000

_cache: dict[str, tuple[float, bytes]] = {}


def reset() -> None:
    _cache.clear()


def tile(z: int, x: int, y: int) -> bytes | None:
    """One tile; None without a key. Raises httpx errors, whose text holds the key."""
    key = settings.load().get("tomtomKey") or ""
    if not key:
        return None
    name = f"{z}/{x}/{y}"
    held = _cache.get(name)
    if held and time.monotonic() - held[0] < FRESH:
        return held[1]
    content = source.fetch(URL.format(z=z, x=x, y=y), params={"key": key, "tags": TAGS}).content
    _cache[name] = (time.monotonic(), content)
    while len(_cache) > MOST_KEPT:
        del _cache[next(iter(_cache))]
    return content
