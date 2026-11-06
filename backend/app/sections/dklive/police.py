"""Politi Update: short messages from the police districts, through Via Ritzau as RSS.
One item per update; items with the same release id are one case."""
from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import httpx

from . import source

RSS = "https://via.ritzau.dk/rss/short-messages/latest"
KEEP_DAYS = 7
GENTLY = 0.4
DISTRICTS = {90686: "Syd- og Sønderjylland", 90720: "Sydøstjylland", 90721: "Østjylland", 90687: "Midt- og Vestjylland",
             13562880: "Nordjylland", 90797: "Fyn", 90594: "Sydsjælland/L-F", 13562881: "Midt- og Vestsjælland",
             90719: "Nordsjælland", 90718: "Kbh. Vestegn", 90685: "København", 90799: "Bornholm", 90752: "Rigspolitiet",
             13562884: "NSK"}

_cases: list[dict] = []


def reset() -> None:
    global _cases
    _cases = []


def parse(xml: str, district: int) -> list[dict]:
    items = []
    for item in ET.fromstring(xml).iter("item"):
        m = re.search(r"pressemeddelelse/(\d+)", item.findtext("link") or "")
        try:
            at = int(parsedate_to_datetime(item.findtext("pubDate") or "").timestamp() * 1000)
        except (TypeError, ValueError):
            continue
        if m:
            items.append({"release": m[1], "title": (item.findtext("title") or "").strip(), "time": at, "district": district})
    return items


def cases(items: list[dict], now: int) -> list[dict]:
    cutoff = now - KEEP_DAYS * 86_400_000
    by_release: dict[str, dict] = {}
    for i in items:
        if i["time"] < cutoff:
            continue
        case = by_release.setdefault(i["release"], {"id": i["release"], "district": i["district"], "title": i["title"],
                                                    "first": i["time"], "last": i["time"], "updates": 0})
        case["first"] = min(case["first"], i["time"])
        if i["time"] >= case["last"]:
            case["last"], case["title"] = i["time"], i["title"]
        case["updates"] += 1
    return sorted(by_release.values(), key=lambda c: c["last"], reverse=True)


@source.watched("police")
def job() -> None:
    global _cases
    items: list[dict] = []
    missing = 0
    for district in DISTRICTS:
        try:
            items += parse(source.fetch(RSS, params={"publisherId": district}).text, district)
        except (httpx.HTTPError, ET.ParseError):
            missing += 1
        time.sleep(GENTLY)
    if missing == len(DISTRICTS):
        raise RuntimeError("ingen politikredse svarer")
    _cases = cases(items, source.now_ms())
    source.done("police", f"{len(_cases)} sager" + (f", {missing} kredse svarede ikke" if missing else ""))


def get() -> dict:
    return {"cases": _cases}
