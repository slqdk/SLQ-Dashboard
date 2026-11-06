"""112 alarms from Beredskabsstyrelsen's ODIN 112-puls, read from beredskabsinfo.dk, which
republishes it as a plain table (odin.dk itself is unreliable). The source wants
attribution: "Kilde: www.odin.dk/112puls".

The address of an incident is not public, so an alarm is placed at the station that
responds: first by the fire stations in OpenStreetMap, then by the station's name as a
place through Nominatim. What is found is kept across restarts."""
from __future__ import annotations

import re
import time
from collections import deque
from html.parser import HTMLParser

import httpx

from . import source, store

URL = "https://www.beredskabsinfo.dk/112-puls/"
PAGES = 3                   # 25 rows a page
KEEP_HOURS = 24
OVERPASS = ("https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
            "https://overpass.private.coffee/api/interpreter")
NOMINATIM = "https://nominatim.openstreetmap.org/search"
ROW_TIME = re.compile(r"^\d{2}-\d{2}-\d{4} \d{2}:\d{2}$")
GEOCODE_PAUSE = 30.0
ALIAS = {"hovedbrandstationen": {"lat": 55.6733, "lon": 12.5697, "matched": "Hovedbrandstationen, København"}}

_alarms: list[dict] = []
_stations: list[dict] | None = None
_found: dict[str, dict | None] | None = None      # normalised station name: place, or None for no such place
_queue: deque[str] = deque()
_geocode_wait_until = 0.0


def reset() -> None:
    global _alarms, _stations, _found, _geocode_wait_until
    _alarms, _stations, _found = [], None, None
    _queue.clear()
    _geocode_wait_until = 0.0


def clean_station(name: str) -> str:
    """"Falck Haderslev" is Haderslev, "Vojens+Gram" Vojens, "Slagelse BV" Slagelse,
    "Åsum - Odense" Åsum."""
    name = re.sub(r"^falck[\s-]*", "", name, flags=re.I)
    name = re.sub(r"^st\.\s*", "", name, flags=re.I)
    name = re.split(r"[+/]", name)[0]
    name = re.sub(r"\s+(bv|brands?|st\.?)$", "", name, flags=re.I)
    return re.sub(r"\s*-\s*.*$", "", name).strip()


def norm(name: str) -> str:
    return re.sub(r"[^a-zæøå0-9]", "", clean_station(name).lower())


def _station_key(name: str) -> str:
    name = re.sub(r"brandstation|brandvæsen|beredskab|station", "", name.lower())
    return re.sub(r"[^a-zæøå0-9]", "", name)


class _Table(HTMLParser):
    """Every table row's cells, as text."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag == "td" and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag == "td" and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def parse_page(html: str) -> list[list[str]]:
    table = _Table()
    table.feed(html)
    return [r for r in table.rows if len(r) >= 3 and ROW_TIME.match(r[0])]


def _time(text: str) -> int | None:
    m = re.search(r"(\d{2})-(\d{2})-(\d{4})\s+(\d{2}):(\d{2})", text)
    return source.copenhagen_ms(int(m[3]), int(m[2]), int(m[1]), int(m[4]), int(m[5])) if m else None


def _places() -> dict:
    global _found
    if _found is None:
        _found = store.load("geocode", {})
    return _found


def _known_stations() -> list[dict]:
    global _stations
    if _stations is None:
        _stations = store.load("stations", [])
    return _stations


def geocode(station: str) -> dict | None:
    key = norm(station)
    if not key:
        return None
    if key in ALIAS:
        return ALIAS[key]
    places = _places()
    if key in places:
        return places[key]
    stations = _known_stations()
    hit = next((s for s in stations if s["key"] == key), None) \
        or next((s for s in stations if s["key"].startswith(key) or key.startswith(s["key"])), None)
    if hit:
        places[key] = {"lat": hit["lat"], "lon": hit["lon"], "matched": hit["name"]}
        return places[key]
    if key not in _queue:
        _queue.append(key)
    return None


def build(rows: list[list[str]], now: int) -> list[dict]:
    cutoff = now - KEEP_HOURS * 3_600_000
    seen, out = set(), []
    for row in rows:
        when, who, message = row[0], row[1], row[2]
        at = _time(when)
        if not at or at < cutoff:
            continue
        parts = re.split(r"\s*Station\s*", who)
        alarm = {"time": at, "beredskab": parts[0].strip(),
                 "station": parts[1].strip() if len(parts) > 1 else "", "message": message.strip()}
        alarm["id"] = f"{at}-{norm(alarm['station'])}-{alarm['message'][:24]}"
        if alarm["id"] in seen:
            continue
        seen.add(alarm["id"])
        alarm.update(geocode(alarm["station"]) or {})
        out.append(alarm)
    out.sort(key=lambda a: a["time"], reverse=True)
    return out


@source.watched("alarms")
def job() -> None:
    global _alarms
    rows: list[list[str]] = []
    for page in range(1, PAGES + 1):
        rows += parse_page(source.fetch(URL, params={"puls_page": page} if page > 1 else None).text)
    _alarms = build(rows, source.now_ms())
    source.done("alarms", f"{len(_alarms)} alarmer")


def _replace_places() -> None:
    for alarm in _alarms:
        if not alarm.get("lat"):
            alarm.update(geocode(alarm["station"]) or {})


@source.watched("alarms-stations")
def stations_job() -> None:
    """The fire stations in OpenStreetMap, once. A mirror that fails is passed over."""
    global _stations
    if _known_stations():
        source.off("alarms-stations")
        return
    query = (f'[out:json][timeout:60];node["amenity"="fire_station"]'
             f'({source.SOUTH},{source.WEST},{source.NORTH},{source.EAST});out;')
    problem: Exception | None = None
    for url in OVERPASS:
        try:
            elements = source.post(url, {"data": query}, timeout=70.0).json().get("elements") or []
        except (httpx.HTTPError, ValueError) as exc:
            problem = exc
            continue
        found = [{"name": e["tags"]["name"], "key": _station_key(e["tags"]["name"]), "lat": e["lat"], "lon": e["lon"]}
                 for e in elements if (e.get("tags") or {}).get("name")]
        _stations = found
        store.save("stations", found)
        source.done("alarms-stations", f"{len(found)} brandstationer")
        _replace_places()
        return
    if problem:
        raise problem


@source.watched("alarms-places")
def geocode_job() -> None:
    """Nominatim for one name a turn: a request every 1.5 seconds at most."""
    global _geocode_wait_until
    if not _queue or time.monotonic() < _geocode_wait_until:
        return
    key = _queue.popleft()
    places = _places()
    if key in places:
        return
    name = next((a["station"] for a in _alarms if norm(a["station"]) == key), key)
    try:
        hits = source.fetch(NOMINATIM, params={"format": "json", "limit": 1, "countrycodes": "dk",
                                               "q": f"{clean_station(name)}, Denmark"}).json()
    except (httpx.HTTPError, ValueError):
        _queue.append(key)
        _geocode_wait_until = time.monotonic() + GEOCODE_PAUSE
        raise
    hit = hits[0] if hits else None
    places[key] = {"lat": float(hit["lat"]), "lon": float(hit["lon"]),
                   "matched": hit["display_name"].split(",")[0]} if hit else None
    store.save("geocode", places)
    if hit:
        _replace_places()
    source.done("alarms-places", f"{sum(1 for p in places.values() if p)} steder")


def get() -> dict:
    return {"source": "Kilde: www.odin.dk/112puls via beredskabsinfo.dk", "alarms": _alarms}
