"""Traffic flow from TomTom as vector tiles (free key, 2,500 tiles a day). Each road
carries its category and how its speed compares to free flow, so the map draws only
motorways and colours them. Tiles pass through here so the key stays on the server, and
are kept a minute."""
from __future__ import annotations

import time

import httpx

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
        source.off("flow")
        return None
    name = f"{z}/{x}/{y}"
    held = _cache.get(name)
    if held and time.monotonic() - held[0] < FRESH:
        return held[1]
    # Written out as TomTom writes it: `params` would escape the brackets of the tags.
    try:
        content = source.fetch(f"{URL.format(z=z, x=x, y=y)}?key={key}&tags={TAGS}").content
    except httpx.HTTPError as exc:
        source.failed("flow", exc)
        raise
    if b"traffic_level" in content and b"road_category" not in content:
        source.failed("flow", "ingen vejtyper i svaret")
    else:
        source.done("flow", f"{len(_cache) + 1} felter hentet")
    _cache[name] = (time.monotonic(), content)
    while len(_cache) > MOST_KEPT:
        del _cache[next(iter(_cache))]
    return content
