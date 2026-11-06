"""The Danish power system from Energinet's Energi Data Service (no key): a one-minute
snapshot of wind, sun, production, CO2 and the cables abroad, and the day-ahead prices.

The service limits each dataset by how often it changes and answers 429 to what asks more
often, and asking during the wait may prolong it. So the snapshot is fetched only while a
layer shows it, and the prices, which come once a day, only when those in hand run out.
They are kept over a restart, so that an update does not need the service to answer.
"""
from __future__ import annotations

import json
import re

import httpx

from ...core import settings
from . import source, store

BASE = "https://api.energidataservice.dk/dataset"

MINUTE_MS = 60_000
FEW_HOURS_LEFT = 12         # tomorrow's come early in the afternoon, when less than this is left
ASK_EVERY_MIN = 30          # while they are being waited for
AFTER_FAILURE_MIN = 10
KEEP_HOURS = 72

_cache: dict = {"updated": 0, "area": "", "now": None, "prices": []}
_next_ask = 0


def reset() -> None:
    global _cache, _next_ask
    _cache = {"updated": 0, "area": "", "now": None, "prices": []}
    _next_ask = 0


def pick(record: dict, *names: str):
    """Energinet has renamed columns; the same one under its known names, in any case."""
    for name in names:
        for key, value in record.items():
            if key.lower() == name.lower() and value is not None:
                return value
    return None


def snapshot(r: dict, now: int) -> dict:
    offshore = pick(r, "OffshoreWindPower", "OffshoreWindGe100MW_MWh") or 0
    onshore = pick(r, "OnshoreWindPower") or 0
    return {"time": source.iso_ms(pick(r, "Minutes1UTC", "Minutes5UTC")) or now,
            "offshoreWind": offshore, "onshoreWind": onshore, "wind": offshore + onshore,
            "solar": pick(r, "SolarPower", "SolarPowerSelfConMWh") or 0,
            "central": pick(r, "ProductionGe100MW", "ProductionGe100MW_MWh") or 0,
            "local": pick(r, "ProductionLt100MW", "ProductionLt100MW_MWh") or 0,
            "co2": pick(r, "CO2Emission"),
            "exchangeSum": pick(r, "Exchange_Sum"),
            "exchanges": {k: v for k, v in r.items() if re.match(r"^exchange_", k, re.I) and "sum" not in k.lower()
                          and isinstance(v, (int, float))}}


def prices(records: list[dict]) -> list[dict]:
    """TimeUTC, not TimeDK: read as UTC, Danish time puts every price an hour or two late.
    DKK/MWh to DKK/kWh: the raw spot price, before tariffs, duties and VAT."""
    out = []
    for r in records:
        at = source.iso_ms(pick(r, "TimeUTC", "HourUTC"))
        if at:
            out.append({"time": at, "dkk": round((pick(r, "DayAheadPriceDKK", "SpotPriceDKK") or 0) / 1000, 3)})
    return sorted(out, key=lambda p: p["time"])


def merged(held: list[dict], fresh: list[dict], now: int) -> list[dict]:
    """A later answer starts later, so what is already here is kept, for a while."""
    cutoff = now - KEEP_HOURS * 60 * MINUTE_MS
    return sorted(({p["time"]: p for p in held + fresh if p["time"] >= cutoff}).values(), key=lambda p: p["time"])


def running_out(held: list[dict], now: int) -> bool:
    return not held or held[-1]["time"] - now < FEW_HOURS_LEFT * 60 * MINUTE_MS


def stated_wait(exc: httpx.HTTPStatusError) -> int:
    """Minutes to stay away after a 429, which says \"Try again in X seconds\"."""
    found = re.search(r"(\d+) second", exc.response.text)
    return max(AFTER_FAILURE_MIN, int(found.group(1)) // 60 + 1 if found else 0)


@source.watched("energy", "energy", "interconnect")
def now_job() -> None:
    global _cache
    latest = source.fetch(f"{BASE}/PowerSystemRightNow", params={"start": "now-PT10M", "sort": "Minutes1UTC DESC", "limit": 1}).json()
    records = latest.get("records") or []
    if not records:
        source.failed("energy", "intet nyt de sidste 10 minutter")
        return
    now = source.now_ms()
    _cache = {**_cache, "updated": now, "now": snapshot(records[0], now)}
    source.done("energy", "opdateret")


@source.watched("prices")
def price_job() -> None:
    global _cache, _next_ask
    area = settings.load().get("priceArea") or "DK1"
    now = source.now_ms()
    moved = _cache["area"] != area
    if moved:
        kept = store.load("prices") or {}
        _cache = {**_cache, "area": area, "prices": kept.get("prices", []) if kept.get("area") == area else []}
        if _cache["prices"]:
            source.done("prices", f"{len(_cache['prices'])} priser for {area}, gemt fra før")
    held = _cache["prices"]
    if not running_out(held, now) or (now < _next_ask and not moved):
        return
    _next_ask = now + AFTER_FAILURE_MIN * MINUTE_MS
    # 400 rows: the last day and what is published ahead, quarter by quarter.
    try:
        day_ahead = source.fetch(f"{BASE}/DayAheadPrices", params={"start": "now-P1D", "end": "now+P2D", "sort": "TimeUTC ASC", "limit": 400,
                                                                   "filter": json.dumps({"PriceArea": [area]})}).json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 429:
            raise
        wait = stated_wait(exc)
        _next_ask = now + wait * MINUTE_MS
        source.failed("prices", f"HTTP 429, prøver igen om {wait} min")
        return
    fresh = prices(day_ahead.get("records") or [])
    if not fresh:
        source.failed("prices", "ingen priser i svaret")
        return
    _next_ask = now + ASK_EVERY_MIN * MINUTE_MS
    _cache = {**_cache, "prices": merged(held, fresh, now)}
    store.save("prices", {"area": area, "prices": _cache["prices"]})
    source.done("prices", f"{len(_cache['prices'])} priser for {area}")


def get() -> dict:
    return _cache
