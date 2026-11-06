"""The Danish power system from Energinet's Energi Data Service (no key): a one-minute
snapshot of wind, sun, production, CO2 and the cables abroad, and the day-ahead prices."""
from __future__ import annotations

import json
import re

from ...core import settings
from . import source

BASE = "https://api.energidataservice.dk/dataset"

_cache: dict = {"updated": 0, "area": "", "now": None, "prices": []}


def reset() -> None:
    global _cache
    _cache = {"updated": 0, "area": "", "now": None, "prices": []}


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


@source.watched("energy")
def job() -> None:
    global _cache
    area = settings.load().get("priceArea") or "DK1"
    latest = source.fetch(f"{BASE}/PowerSystemRightNow", params={"start": "now-PT10M", "sort": "Minutes1UTC DESC", "limit": 1}).json()
    records = latest.get("records") or []
    if not records:
        raise ValueError("no records")
    # 400 rows: the last day and what is published ahead, quarter by quarter.
    day_ahead = source.fetch(f"{BASE}/DayAheadPrices", params={"start": "now-P1D", "end": "now+P2D", "sort": "TimeUTC ASC", "limit": 400,
                                                               "filter": json.dumps({"PriceArea": [area]})}).json()
    now = source.now_ms()
    _cache = {"updated": now, "area": area, "now": snapshot(records[0], now), "prices": prices(day_ahead.get("records") or [])}
    source.done("energy", f"{len(_cache['prices'])} priser for {area}")


def get() -> dict:
    return _cache
