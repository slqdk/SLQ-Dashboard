"""The newest monologues from the shows still on air, as titles and links.

From each show's YouTube channel. With a YouTube API key (Admin → Opsætning)
it uses the official Data API. Without one it uses the channel's RSS feed,
which needs no key, but YouTube's feed answers 404 for hours at a time. The last
good list is kept on disk, so an outage only means the list stands still.

YouTube's titles never say "monologue", so each show has its own rule for what
counts: guests, music and games are left out.
"""
from __future__ import annotations

import json
import os
import re
import xml.etree.ElementTree as ET

import httpx

from ...core import db, logs, settings

TIMEOUT = 15.0
KEEP_PER_SHOW = 6
UA = "SLQ-Dashboard/0.1 (personal dashboard)"
ATOM = "{http://www.w3.org/2005/Atom}"
YT = "{http://www.youtube.com/xml/schemas/2015}"

# A guest: "Bill Hader on Group Chat...", "Pod Save America Hosts on ...".
GUEST = re.compile(r"^(?:[A-Z][\w.'’-]*\s+){2,4}(?:on|talks|says|reveals|praises|shares|does|used)\b", re.I)
MUSIC = re.compile(r"\s[–-]\s")


def _kimmel(title: str) -> bool:
    return not GUEST.match(title) and not MUSIC.search(title)


def _fallon(title: str) -> bool:
    return title.endswith("| The Tonight Show") and " with Jimmy" not in title


def _meyers(title: str) -> bool:
    return title.endswith(": A Closer Look")


def _daily(title: str) -> bool:
    return title.endswith("| The Daily Show") and not GUEST.match(title) and not MUSIC.search(title)


def _oliver(title: str) -> bool:
    return title.endswith(": Last Week Tonight with John Oliver (HBO)")


# Channel ids read from each channel's page, 6 November 2026.
SHOWS = [
    {"id": "kimmel", "name": "Jimmy Kimmel Live", "channel": "UCa6vGFO9ty8v5KZJXQxdhaw", "keep": _kimmel},
    {"id": "fallon", "name": "The Tonight Show", "channel": "UC8-Th83bH_thdKZDJCrn88g", "keep": _fallon},
    {"id": "meyers", "name": "Late Night with Seth Meyers", "channel": "UCVTyTA7-g9nopHeHbeuvpRA", "keep": _meyers},
    {"id": "daily", "name": "The Daily Show", "channel": "UCwWhs_6x42TyRM4Wstoq8HA", "keep": _daily},
    {"id": "oliver", "name": "Last Week Tonight", "channel": "UC3XTzVzaHQEd30rQbuvCtTQ", "keep": _oliver},
]

_items: dict[str, list[dict]] = {}
_status: dict = {"ok": False, "text": "Venter på første hentning."}


def reset() -> None:
    _items.clear()
    _status.update(ok=False, text="Venter på første hentning.")


def _feed_base() -> str:
    return os.environ.get("APP_YOUTUBE_FEED_URL") or "https://www.youtube.com/feeds/videos.xml"


def _api_base() -> str:
    return (os.environ.get("APP_YOUTUBE_API_BASE") or "https://www.googleapis.com/youtube/v3").rstrip("/")


def _video(show: dict, video_id: str, title: str, at: str | None) -> dict:
    return {"show": show["name"], "title": title, "at": at,
            "url": f"https://www.youtube.com/watch?v={video_id}"}


def parse_feed(text: str, show: dict) -> list[dict]:
    out = []
    for entry in ET.fromstring(text).iter(f"{ATOM}entry"):
        video = entry.findtext(f"{YT}videoId") or ""
        title = (entry.findtext(f"{ATOM}title") or "").strip()
        if video and title and show["keep"](title):
            out.append(_video(show, video, title, entry.findtext(f"{ATOM}published")))
    return out


def parse_api(data: dict, show: dict) -> list[dict]:
    out = []
    for item in data.get("items") or []:
        s = item.get("snippet") or {}
        video = (s.get("resourceId") or {}).get("videoId") or ""
        title = (s.get("title") or "").strip()
        if video and title and show["keep"](title):
            out.append(_video(show, video, title, s.get("publishedAt")))
    return out


def fetch(show: dict, api_key: str) -> list[dict]:
    if api_key:
        # A channel's uploads playlist: its id with UU in place of UC.
        playlist = "UU" + show["channel"][2:]
        r = httpx.get(f"{_api_base()}/playlistItems", timeout=TIMEOUT,
                      params={"part": "snippet", "playlistId": playlist, "maxResults": 25, "key": api_key})
        r.raise_for_status()
        return parse_api(r.json(), show)
    r = httpx.get(_feed_base(), params={"channel_id": show["channel"]}, timeout=TIMEOUT,
                  headers={"User-Agent": UA}, follow_redirects=True)
    r.raise_for_status()
    return parse_feed(r.text, show)


def _path():
    return db.data_dir() / "monologues.json"


def _load() -> None:
    p = _path()
    if _items or not p.exists():
        return
    try:
        _items.update(json.loads(p.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass


def job() -> None:
    _load()
    key = settings.load().get("youtubeApiKey") or ""
    failed: list[str] = []
    for show in SHOWS:
        try:
            found = fetch(show, key)
        except (httpx.HTTPError, ET.ParseError, ValueError) as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            failed.append(f"{show['name']}: {status or type(exc).__name__}")
            continue
        if found:
            _items[show["id"]] = found[:KEEP_PER_SHOW]
    if failed:
        text = f"YouTube svarede ikke for {len(failed)} af {len(SHOWS)} ({failed[0]})."
        if not key:
            text += " En API-nøgle gør det stabilt."
        _status.update(ok=False, text=text)
        logs.record_problem("monologues", text)
    else:
        _status.update(ok=True, text=f"{len(SHOWS)} shows hentet.")
    if _items:
        p = _path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(_items, ensure_ascii=False), encoding="utf-8")


def newest(limit: int = 20) -> list[dict]:
    """Newest first across the shows; every video is 'at' or goes last."""
    every = [i for items in _items.values() for i in items]
    return sorted(every, key=lambda i: i["at"] or "", reverse=True)[:limit]


def status() -> dict:
    return dict(_status)
