"""Turn what the live sources hold into what the dashboard shows. Everything here reads
memory, so the overview answers at once."""
from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone

from ...core import settings
from . import (airports, alarms, autobahn, dmi, energy, flights, flow, forecast, niord, photos, police, ships, source,
               traffic, trains, weather, webcams)

NEAR_KM = 60.0
FEED_SIZE = 40
PRICE_HISTORY_HOURS = 30
TRAFFIC_ITEMS = 6
NEAR_HOURS = 12
MAP_HOURS = 6               # what the map shows from sources with a time
ROUTINE = re.compile(r"^(eftersyn|isl-forespørgsel)", re.I)
SOURCES = {"flights": "Fly", "flights-routes": "Flyruter", "ships": "Skibe", "alarms": "112", "alarms-stations": "Brandstationer",
           "alarms-places": "Stednavne", "traffic": "Trafik", "trains": "Tog", "autobahn": "Autobahn",
           "autobahn-cameras": "Autobahns kameraer", "webcams": "Windy", "flow": "Trafiktæthed", "radar": "Regnradar", "lightning": "Lyn",
           "wind": "Vind", "sealevel": "Vandstand", "navwarnings": "Navigationsadvarsler", "energy": "Elpriser",
           "forecast": "Vejr", "police": "Politi", "airports": "Lufthavne"}


def reset() -> None:
    for module in (source, airports, alarms, autobahn, dmi, energy, flights, flow, forecast, niord, photos, police, ships,
                   traffic, trains, weather, webcams):
        module.reset()


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _ms(ms: float | None) -> str | None:
    return _iso(datetime.fromtimestamp(ms / 1000, timezone.utc)) if ms else None


def km_between(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def build_power(data: dict, now: datetime) -> dict | None:
    cutoff = _iso(now - timedelta(hours=PRICE_HISTORY_HOURS))
    series = [{"t": _ms(p["time"]), "dkk": p["dkk"]} for p in data.get("prices") or [] if p.get("time") and p.get("dkk") is not None]
    series = [p for p in series if p["t"] >= cutoff]
    if not series:
        return None
    stamp = _iso(now)
    past = [p for p in series if p["t"] <= stamp]
    current = past[-1] if past else series[0]
    ahead = [p for p in series if p["t"] >= current["t"]]
    low = min(ahead, key=lambda p: p["dkk"])
    high = max(ahead, key=lambda p: p["dkk"])
    mix = data.get("now") or {}
    return {"area": data.get("area") or "", "now": current["dkk"], "nowAt": current["t"],
            "low": low, "high": high, "series": series,
            "wind": mix.get("wind"), "solar": mix.get("solar"), "co2": mix.get("co2"),
            "plants": (mix.get("central") or 0) + (mix.get("local") or 0) if mix else None,
            "exchange": mix.get("exchangeSum")}


WEATHER_TEXT = [
    (0, "klart"), (1, "mest klart"), (2, "let skyet"), (3, "overskyet"), (48, "tåge"),
    (55, "støvregn"), (57, "isslag"), (63, "regn"), (65, "kraftig regn"), (67, "isslag"),
    (75, "sne"), (77, "snekorn"), (81, "regnbyger"), (82, "kraftige regnbyger"),
    (86, "snebyger"), (99, "torden"),
]


def weather_text(code: int | None) -> str:
    if code is None:
        return ""
    for limit, text in WEATHER_TEXT:
        if code <= limit:
            return text
    return ""


def build_weather(data: dict, tz) -> dict | None:
    current = data.get("current")
    if not current:
        return None
    hourly = []
    for h in data.get("hourly") or []:
        if not h.get("time"):
            continue
        at = datetime.fromisoformat(h["time"]).replace(tzinfo=tz)
        hourly.append({"t": _iso(at), "temp": h.get("temperature_2m"),
                       "rain": h.get("precipitation"), "code": h.get("weather_code")})
    daily = [{"day": d.get("time"), "max": d.get("temperature_2m_max"),
              "min": d.get("temperature_2m_min"), "rain": d.get("precipitation_sum"),
              "text": weather_text(d.get("weather_code")), "sunrise": d.get("sunrise"),
              "sunset": d.get("sunset")} for d in data.get("daily") or []]
    return {"temp": current.get("temperature_2m"), "feels": current.get("apparent_temperature"),
            "wind": current.get("wind_speed_10m"), "gusts": current.get("wind_gusts_10m"),
            "text": weather_text(current.get("weather_code")), "place": data.get("place") or "",
            "hourly": hourly, "daily": daily}


def build_updates(odin: dict, police: dict, traffic: dict, home: tuple[float, float]) -> dict:
    """112, police and traffic as one list, newest first, marked near home."""
    feed: list[dict] = []

    def near(item: dict) -> float | None:
        if item.get("lat") is None or item.get("lon") is None:
            return None
        return round(km_between(home[0], home[1], item["lat"], item["lon"]))

    for a in odin.get("alarms") or []:
        km = near(a)
        feed.append({"kind": "112", "id": f"112-{a.get('id')}", "at": _ms(a.get("time")),
                     "title": a.get("message") or "Alarm",
                     "detail": a.get("station") or a.get("beredskab") or "", "km": km})
    for c in police.get("cases") or []:
        feed.append({"kind": "politi", "id": f"politi-{c.get('id')}", "at": _ms(c.get("last")),
                     "title": c.get("title") or "", "detail": "", "km": None,
                     "updates": c.get("updates")})
    events = traffic.get("events") or []
    for e in events:
        km = near(e)
        feed.append({"kind": "trafik", "id": f"trafik-{e.get('id')}", "at": _ms(e.get("modified") or e.get("begin")),
                     "title": e.get("header") or e.get("title") or "Trafik",
                     "detail": "", "km": km, "blocking": bool(e.get("blocking"))})
    feed = [f for f in feed if f["at"]]
    feed.sort(key=lambda f: f["at"], reverse=True)
    close = [e for e in events if (k := near(e)) is not None and k <= NEAR_KM]
    road = sorted((f for f in feed if f["kind"] == "trafik"),
                  key=lambda f: (f["km"] is None, f["km"] if f["km"] is not None else 0))
    return {"feed": feed[:FEED_SIZE],
            "traffic": {"total": len(events), "near": len(close),
                        "blocking": sum(1 for e in close if e.get("blocking")),
                        "items": road[:TRAFFIC_ITEMS]}}


def headline_updates(feed: list[dict], now: datetime) -> list[dict]:
    """For the overview: what happened near home lately first, then the rest,
    without the routine inspections and the traffic, which has its own list."""
    cutoff = _iso(now - timedelta(hours=NEAR_HOURS))
    useful = [f for f in feed if f["kind"] != "trafik" and not ROUTINE.search(f["title"])]
    close = [f for f in useful if f["km"] is not None and f["km"] <= NEAR_KM and f["at"] >= cutoff]
    return close + [f for f in useful if f not in close]


def state() -> dict:
    s = settings.load()
    now = datetime.now(timezone.utc)
    updates = build_updates(alarms.get(), police.get(), traffic.get(), (s["homeLat"], s["homeLon"]))
    problems = source.problems()
    return {"home": s.get("homeName") or "", "layers": s.get("dkliveLayers") or [],
            "ok": not problems, "error": "; ".join(problems[:3]), "updated": _iso(now),
            "power": build_power(energy.get(), now), "weather": build_weather(forecast.home(), settings.tz()),
            "feed": updates["feed"], "traffic": updates["traffic"]}


def overview(_me: dict) -> dict:
    out = state()
    out["feed"] = headline_updates(out["feed"], datetime.now(timezone.utc))[:6]
    return out


# ---- what the map reads ------------------------------------------------------------

def recent(items: list[dict], *fields: str, now_ms: int | None = None) -> list[dict]:
    """Only what happened in the last six hours. Something with no time stays."""
    cutoff = (now_ms or source.now_ms()) - MAP_HOURS * 3_600_000
    return [item for item in items if (next((item[f] for f in fields if item.get(f)), None) or cutoff) >= cutoff]


FEEDS = {
    "flights": flights.get,
    "ships": ships.get,
    "alarms": lambda: {**alarms.get(), "alarms": recent(alarms.get()["alarms"], "time")},
    "traffic": lambda: {**traffic.get(), "events": recent(traffic.get()["events"], "modified", "begin")},
    "autobahn": lambda: {**autobahn.get(), "items": recent(autobahn.get()["items"], "start")},
    "lightning": lambda: {**weather.lightning(), "strikes": recent(weather.lightning()["strikes"], "time")},
    "navwarnings": lambda: {**niord.get(), "warnings": recent(niord.get()["warnings"], "from")},
    "trains": trains.get,
    "webcams": webcams.get,
    "radar": weather.radar,
    "wind": dmi.wind,
    "sealevel": dmi.sea,
    "energy": energy.get,
    "airports": airports.get,
}


def map_feed(name: str) -> dict | None:
    feed = FEEDS.get(name)
    return feed() if feed else None


def setup_status() -> dict:
    states = source.state()
    if not states:
        return {"ok": False, "text": "Venter på første hentning."}
    bad = [f"{SOURCES.get(name, name)}: {s['text']}" for name, s in states.items() if not s["ok"]]
    return {"ok": not bad, "text": "; ".join(bad[:4]) or f"{len(states)} kilder svarer."}
