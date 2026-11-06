"""Read dk-live's API and turn it into what the dashboard shows."""
from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone

import httpx

from ...core import logs, settings

TIMEOUT = 12.0
NEAR_KM = 60.0
FEED_SIZE = 40
PRICE_HISTORY_HOURS = 30
TRAFFIC_ITEMS = 6
NEAR_HOURS = 12
ROUTINE = re.compile(r"^(eftersyn|isl-forespørgsel)", re.I)

_cache: dict = {}
_prices: dict[str, float] = {}      # dk-live only sends what is ahead; the past is kept here


def reset() -> None:
    _cache.clear()
    _prices.clear()


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


def price_time(ms: float, base: str | None, tz) -> datetime:
    """dk-live's energy.js reads Energinet's TimeDK as if it were UTC, so its
    `time` is Danish wall-clock time wearing a UTC label: 1 hour late in winter
    and 2 in summer. Read it as the wall-clock time it is. When dk-live sends
    timeBase "utc" the value is a real instant and is used as it stands."""
    dt = datetime.fromtimestamp(ms / 1000, timezone.utc)
    if base == "utc":
        return dt
    return dt.replace(tzinfo=tz).astimezone(timezone.utc)


def remember_prices(series: list[dict], now: datetime) -> list[dict]:
    """Today's earlier prices stay on the band although dk-live has moved on."""
    for p in series:
        _prices[p["t"]] = p["dkk"]
    cutoff = _iso(now - timedelta(hours=PRICE_HISTORY_HOURS))
    for t in [t for t in _prices if t < cutoff]:
        del _prices[t]
    return [{"t": t, "dkk": _prices[t]} for t in sorted(_prices)]


def build_power(data: dict, tz, now: datetime) -> dict | None:
    prices = data.get("prices") or []
    series = []
    for p in prices:
        if p.get("time") and p.get("dkk") is not None:
            series.append({"t": _iso(price_time(p["time"], data.get("timeBase"), tz)), "dkk": p["dkk"]})
    if not series:
        return None
    series = remember_prices(series, now)
    stamp = _iso(now)
    past = [p for p in series if p["t"] <= stamp]
    current = past[-1] if past else series[0]
    ahead = [p for p in series if p["t"] >= current["t"]]
    low = min(ahead, key=lambda p: p["dkk"])
    high = max(ahead, key=lambda p: p["dkk"])
    mix = data.get("now") or {}
    return {"area": data.get("area") or "", "now": current["dkk"], "nowAt": current["t"],
            "low": low, "high": high, "series": series,
            "wind": mix.get("wind"), "solar": mix.get("solar"), "co2": mix.get("co2")}


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


def _get(base: str, path: str, params: dict | None = None) -> dict:
    r = httpx.get(base + path, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def job() -> None:
    s = settings.load()
    base = (s.get("dkliveUrl") or "").rstrip("/")
    if not base:
        _cache.clear()
        return
    tz = settings.tz()
    now = datetime.now(timezone.utc)
    problems: list[str] = []

    def read(path: str, params: dict | None = None) -> dict:
        try:
            return _get(base, path, params)
        except (httpx.HTTPError, ValueError) as exc:
            problems.append(f"{path}: {type(exc).__name__}")
            return {}

    energy = read("/api/energy")
    forecast = read("/api/forecast", {"lat": s["homeLat"], "lon": s["homeLon"]})
    odin, police, traffic = read("/api/odin"), read("/api/police"), read("/api/traffic")
    power = build_power(energy, tz, now)
    weather = build_weather(forecast, tz)
    updates = build_updates(odin, police, traffic, (s["homeLat"], s["homeLon"]))
    # What one failed read could not refresh stays from the last good round.
    _cache.update({
        "ok": not problems,
        "error": "; ".join(problems[:3]),
        "updated": _iso(now),
        "power": power or _cache.get("power"),
        "weather": weather or _cache.get("weather"),
        "feed": updates["feed"] or _cache.get("feed", []),
        "traffic": updates["traffic"],
    })
    if problems:
        logs.record_problem("dklive", _cache["error"])


def state() -> dict:
    s = settings.load()
    return {"configured": bool(s.get("dkliveUrl")),
            "link": s.get("dkliveLink") or s.get("dkliveUrl") or "",
            "home": s.get("homeName") or "", **_cache}


def overview(_me: dict) -> dict:
    out = state()
    out["feed"] = headline_updates(out.get("feed") or [], datetime.now(timezone.utc))[:6]
    return out


def setup_status() -> dict:
    if not settings.load().get("dkliveUrl"):
        return {"ok": False, "text": "Adresse mangler."}
    if not _cache:
        return {"ok": False, "text": "Venter på første hentning."}
    return {"ok": bool(_cache.get("ok")), "text": _cache.get("error") or "Svarer."}


