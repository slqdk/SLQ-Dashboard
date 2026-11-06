"""Navigational warnings and firing exercises from the Danish Niord system (Nautisk
Information, public, no key). Niord has moved hosts, so the known ones are tried in turn
and the first that answers is kept."""
from __future__ import annotations

import html
import re

import httpx

from . import source

HOSTS = ("https://niord.dma.dk", "https://nautiskinformation.soefartsstyrelsen.dk")
MARGIN = 0.5                # a warning just outside the map still matters
DETAIL_LENGTH = 600

_cache: dict = {"updated": 0, "warnings": []}
_host: str | None = None


def reset() -> None:
    global _cache, _host
    _cache = {"updated": 0, "warnings": []}
    _host = None


def strip(text: str | None) -> str:
    text = re.sub(r"<br\s*/?>|</p>|</li>", "\n", text or "", flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\n{3,}", "\n\n", html.unescape(text).replace("\xa0", " ")).strip()


def _desc(descs: list | None, key: str):
    descs = descs or []
    danish = next((d for d in descs if d.get("lang") == "da"), None)
    held = danish.get(key) if danish else None
    return held if held is not None else (descs[0].get(key) if descs else None)


def _coordinates(geometry: dict | None):
    if not geometry:
        return
    if geometry.get("type") == "GeometryCollection":
        for part in geometry.get("geometries") or []:
            yield from _coordinates(part)
        return

    def walk(value):
        if value and isinstance(value[0], (int, float)):
            yield value
        else:
            for item in value or []:
                yield from walk(item)

    yield from walk(geometry.get("coordinates"))


def touches_map(geometry: dict) -> bool:
    return any(source.SOUTH - MARGIN <= c[1] <= source.NORTH + MARGIN and source.WEST - MARGIN <= c[0] <= source.EAST + MARGIN
               for c in _coordinates(geometry))


def parse(messages: list[dict]) -> list[dict]:
    warnings = []
    for m in messages:
        geometries, details = [], []
        for part in m.get("parts") or []:
            for feature in (part.get("geometry") or {}).get("features") or []:
                if feature.get("geometry") and touches_map(feature["geometry"]):
                    geometries.append(feature["geometry"])
            detail = strip(_desc(part.get("descs"), "details"))
            if detail:
                details.append(detail)
        if not geometries:
            continue
        title = _desc(m.get("descs"), "title")
        series = (m.get("messageSeries") or {}).get("seriesId") or ""
        firing = re.search(r"(^|-)fe($|-)", series, re.I) or re.search(r"skyd", title or "", re.I)
        area = (m.get("areas") or [{}])[0].get("descs")
        warnings.append({"id": m.get("id"), "shortId": m.get("shortId"), "kind": "fe" if firing else "nw",
                         "title": title or m.get("shortId") or "Advarsel", "area": _desc(area, "name"),
                         "details": "\n\n".join(details)[:DETAIL_LENGTH],
                         "from": m.get("publishDateFrom") or m.get("eventDateFrom"),
                         "to": m.get("publishDateTo") or m.get("eventDateTo"), "geometries": geometries})
    return warnings


def _read(host: str) -> list[dict]:
    data = source.fetch(f"{host}/rest/public/v1/messages", headers={"Accept": "application/json"},
                        params=[("domain", "niord-nw"), ("domain", "niord-fe"), ("lang", "da"),
                                ("dateFormat", "UNIX_EPOCH")]).json()
    if not isinstance(data, list):
        raise ValueError("not a list")
    return data


@source.watched("navwarnings", "navwarnings")
def job() -> None:
    global _cache, _host
    messages, problem = None, None
    for host in (_host,) if _host else HOSTS:
        try:
            messages = _read(host)
            _host = host
            break
        except (httpx.HTTPError, ValueError) as exc:
            problem = exc
    if messages is None:
        _host = None            # try them all next time
        raise problem
    warnings = parse(messages)
    _cache = {"updated": source.now_ms(), "warnings": warnings}
    source.done("navwarnings", f"{len(warnings)} advarsler")


def get() -> dict:
    return _cache
