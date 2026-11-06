"""Fetch and clean the news feeds."""
from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

from ...core import logs, settings

MAX_BYTES = 3_000_000
PER_FEED = 40
SUMMARY_LENGTH = 320
UA = "SLQ-Dashboard/0.1 (personal dashboard)"

# Paid content that travels in a news feed. Narrow on purpose: "annoncerede"
# and "sponsor" are ordinary words in real news, so the title only counts when
# it says outright that it is paid; a category or address may say it anywhere.
PAID_TITLE = re.compile(
    r"^\s*(annonce|sponsoreret|reklame)\b|annoncørbetalt|annoncørindhold|advertorial"
    r"|betalt indhold|betalt samarbejde", re.I)
PAID_CATEGORY = re.compile(r"annonc|sponsor|advertorial|reklame|partnerindhold|betalt", re.I)
PAID_LINK = re.compile(r"/(annonce|annoncoer|sponsored|sponsoreret|advertorial|partnerindhold)\b", re.I)

_cache: dict[str, dict] = {}


def reset() -> None:
    _cache.clear()


def _strip(text: str | None) -> str:
    """Plain text only: tags, scripts and entities out."""
    text = re.sub(r"<(script|style)\b.*?</\1>", " ", text or "", flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(html.unescape(text).split())


def _when(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(node, *names: str):
    for child in node:
        if _local(child.tag) in names:
            return child
    return None


def _text(node, *names: str) -> str:
    child = _child(node, *names)
    return (child.text or "") if child is not None else ""


def is_paid(title: str, categories: list[str], link: str) -> bool:
    return bool(PAID_TITLE.search(title) or PAID_CATEGORY.search(" ".join(categories))
                or PAID_LINK.search(link))


def parse(xml_text: str, source: str) -> tuple[list[dict], int]:
    """RSS 2.0 or Atom → (items, how many paid ones were dropped)."""
    root = ET.fromstring(xml_text)
    entries = [n for n in root.iter() if _local(n.tag) in ("item", "entry")]
    items: list[dict] = []
    dropped = 0
    for node in entries[:PER_FEED * 2]:
        title = _strip(_text(node, "title"))
        link_node = _child(node, "link")
        link = ""
        if link_node is not None:
            link = (link_node.text or link_node.get("href") or "").strip()
        categories = [(c.text or c.get("term") or "") for c in node if _local(c.tag) == "category"]
        if not title or not link.startswith(("http://", "https://")):
            continue
        if is_paid(title, categories, link):
            dropped += 1
            continue
        summary = _strip(_text(node, "description", "summary", "content"))
        if summary == title:
            summary = ""
        items.append({"source": source, "title": title, "url": link,
                      "summary": summary[:SUMMARY_LENGTH],
                      "at": _when(_text(node, "pubDate", "published", "updated", "date"))})
    return items[:PER_FEED], dropped


def fetch_feed(feed: dict) -> dict:
    url = feed["url"]
    try:
        with httpx.stream("GET", url, timeout=15, follow_redirects=True,
                          headers={"User-Agent": UA}) as r:
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}")
            body = b""
            for chunk in r.iter_bytes():
                body += chunk
                if len(body) > MAX_BYTES:
                    raise RuntimeError("for stor")
        items, dropped = parse(body.decode("utf-8", "replace").lstrip("﻿"), feed["name"])
        return {"name": feed["name"], "ok": True, "items": items, "dropped": dropped, "error": ""}
    except (httpx.HTTPError, ET.ParseError, RuntimeError) as exc:
        return {"name": feed["name"], "ok": False, "items": _cache.get(url, {}).get("items", []),
                "dropped": 0, "error": str(exc) or type(exc).__name__}


def job() -> None:
    feeds = settings.load().get("newsFeeds") or []
    keep = {f["url"] for f in feeds}
    for url in list(_cache):
        if url not in keep:
            del _cache[url]
    for f in feeds:
        result = fetch_feed(f)
        if not result["ok"]:
            logs.record_problem("news", f"{f['name']}: {result['error']}")
        _cache[f["url"]] = result


def merged() -> list[dict]:
    """Newest first; the same story from two sources shows once."""
    seen: set[str] = set()
    out = []
    every = [i for f in _cache.values() for i in f.get("items", [])]
    for item in sorted(every, key=lambda i: i["at"] or "", reverse=True):
        key = re.sub(r"\W+", "", item["title"].lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def feeds_state() -> list[dict]:
    return [{"name": f["name"], "ok": f["ok"], "count": len(f["items"]),
             "dropped": f["dropped"], "error": f["error"]} for f in _cache.values()]


def overview(_me: dict) -> dict:
    return {"items": merged()[:7], "feeds": feeds_state()}


def setup_status() -> dict:
    feeds = feeds_state()
    bad = [f for f in feeds if not f["ok"]]
    if not feeds:
        return {"ok": False, "text": "Venter på første hentning."}
    if bad:
        return {"ok": False, "text": f"{bad[0]['name']}: {bad[0]['error']}"}
    return {"ok": True, "text": f"{len(feeds)} kilder virker."}
