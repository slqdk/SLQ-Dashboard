"""The F1 season calendar from Jolpica, cached on disk for restarts without
network. Session lengths and names as in F1Schedule.cs, in Danish."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

import httpx

from ...core import db, logs, settings

SESSION_KEYS = [
    ("FirstPractice", "1. træning", 60),
    ("SecondPractice", "2. træning", 60),
    ("ThirdPractice", "3. træning", 60),
    ("SprintShootout", "Sprintkvalifikation", 45),
    ("SprintQualifying", "Sprintkvalifikation", 45),
    ("Sprint", "Sprint", 45),
    ("Qualifying", "Kvalifikation", 60),
]
RACE = "Løb"

_sessions: list[dict] = []
_status = {"ok": False, "text": "Venter på første hentning."}


def reset() -> None:
    _sessions.clear()
    _status.update(ok=False, text="Venter på første hentning.")


def _base() -> str:
    return (os.environ.get("APP_JOLPICA_URL") or "https://api.jolpi.ca/ergast/f1").rstrip("/")


def _utc(date: str, time: str) -> datetime | None:
    if not date:
        return None
    text = f"{date}T{time or '12:00:00Z'}".replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def parse(payload: dict) -> list[dict]:
    races = payload.get("MRData", {}).get("RaceTable", {}).get("Races", []) or []
    out: list[dict] = []
    for r in races:
        base = {"season": int(r.get("season") or 0), "round": int(r.get("round") or 0),
                "meeting": r.get("raceName") or "",
                "country": (r.get("Circuit", {}).get("Location", {}) or {}).get("country", ""),
                "circuit": r.get("Circuit", {}).get("circuitName", "")}
        for key, name, minutes in SESSION_KEYS:
            s = r.get(key)
            if isinstance(s, dict) and (start := _utc(s.get("date", ""), s.get("time", ""))):
                out.append({**base, "name": name, "start": start, "minutes": minutes, "race": False})
        if start := _utc(r.get("date", ""), r.get("time", "")):
            out.append({**base, "name": RACE, "start": start, "minutes": 120, "race": True})
    return sorted(out, key=lambda s: s["start"])


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _dto(s: dict) -> dict:
    return {"season": s["season"], "round": s["round"], "meeting": s["meeting"],
            "country": s["country"], "circuit": s["circuit"], "name": s["name"],
            "start": _iso(s["start"]), "end": _iso(s["start"] + timedelta(minutes=s["minutes"])),
            "race": s["race"]}


def _cache_path():
    return db.data_dir() / "f1-schedule.json"


def _load_cache() -> None:
    p = _cache_path()
    if _sessions or not p.exists():
        return
    try:
        for s in json.loads(p.read_text(encoding="utf-8")):
            _sessions.append({**s, "start": datetime.fromisoformat(s["start"])})
    except (OSError, ValueError, KeyError):
        _sessions.clear()


def job() -> None:
    _load_cache()
    year = datetime.now(settings.tz()).year
    found: list[dict] = []
    try:
        for y in (year, year + 1):
            r = httpx.get(f"{_base()}/{y}.json", params={"limit": 100}, timeout=20,
                          follow_redirects=True)
            if r.status_code == 200:
                found += parse(r.json())
            elif y == year:
                raise RuntimeError(f"HTTP {r.status_code}")
    except (httpx.HTTPError, RuntimeError, ValueError) as exc:
        _status.update(ok=False, text=f"Jolpica svarer ikke ({exc}). Viser sidst hentede plan.")
        logs.record_problem("f1", _status["text"])
        return
    if found:
        _sessions[:] = found
        p = _cache_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps([{**s, "start": s["start"].isoformat()} for s in found]), encoding="utf-8")
    _status.update(ok=bool(found), text=f"{len(found)} sessioner i planen." if found else "Planen er tom.")


def upcoming(now: datetime | None = None) -> list[dict]:
    """Sessions that are not over yet."""
    now = now or datetime.now(timezone.utc)
    return [s for s in _sessions if s["start"] + timedelta(minutes=s["minutes"]) > now]


def season() -> list[dict]:
    """This season's weekends: [{round, meeting, sessions, over}]."""
    now = datetime.now(timezone.utc)
    next_up = upcoming(now)
    year = next_up[0]["season"] if next_up else (_sessions[-1]["season"] if _sessions else 0)
    weekends: dict[int, dict] = {}
    for s in _sessions:
        if s["season"] != year:
            continue
        w = weekends.setdefault(s["round"], {"season": s["season"], "round": s["round"],
                                             "meeting": s["meeting"], "country": s["country"],
                                             "circuit": s["circuit"], "sessions": []})
        w["sessions"].append(_dto(s))
    out = list(weekends.values())
    for w in out:
        w["over"] = w["sessions"][-1]["end"] <= _iso(now)
    return out


def overview(_me: dict) -> dict:
    next_up = upcoming()
    if not next_up:
        return {"next": None, "weekend": []}
    first = next_up[0]
    weekend = [_dto(s) for s in next_up if s["round"] == first["round"] and s["season"] == first["season"]]
    return {"next": _dto(first), "weekend": weekend, "meeting": first["meeting"],
            "sessions": [_dto(s) for s in next_up[:12]]}


def setup_status() -> dict:
    return dict(_status)
