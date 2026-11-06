"""The way into FamilyLog. The dashboard can search, never post: the only HTTP
verb in this module is GET, and tests/test_familylog.py holds it to that."""
from __future__ import annotations

from datetime import date, datetime, timezone

import httpx

from ...core import db, logs, settings, vault
from ..logmylife import store as life

TIMEOUT = 10.0
DAGBOG = "familylog.dagbog"
REVIEWS = "familylog.familymap"
DAYS_PER_PAGE = 60

SCHEMA = """
CREATE TABLE IF NOT EXISTS familylog_keys (
    user_id    INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    sealed     TEXT NOT NULL,
    hint       TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
"""


def migrate_1(con) -> None:
    con.executescript(SCHEMA)


class Unavailable(RuntimeError):
    """FamilyLog could not answer; the text is shown to the person."""


_summaries: dict[int, dict] = {}


def reset() -> None:
    _summaries.clear()


class Refused(Unavailable):
    """FamilyLog says this person may not read this, e.g. no Økonomi."""


def set_key(user_id: int, key: str | None) -> None:
    _summaries.pop(user_id, None)
    with db.connect() as con:
        con.execute("DELETE FROM familylog_keys WHERE user_id=?", (user_id,))
        key = (key or "").strip()
        if key:
            con.execute("INSERT INTO familylog_keys (user_id, sealed, hint, created_at) VALUES (?,?,?,?)",
                        (user_id, vault.seal(key), key[-4:], db.utcnow()))


def key_hint(user_id: int) -> str:
    with db.connect() as con:
        r = con.execute("SELECT hint FROM familylog_keys WHERE user_id=?", (user_id,)).fetchone()
    return r["hint"] if r else ""


def _key(user_id: int) -> str | None:
    with db.connect() as con:
        r = con.execute("SELECT sealed FROM familylog_keys WHERE user_id=?", (user_id,)).fetchone()
    return vault.unseal(r["sealed"]) if r else None


def get(user_id: int, path: str, params: dict | None = None) -> dict:
    """One read as this person."""
    base = (settings.load().get("familylogUrl") or "").rstrip("/")
    key = _key(user_id)
    if not base or not key:
        raise Unavailable("FamilyLog er ikke forbundet.")
    try:
        r = httpx.get(base + path, params=params, timeout=TIMEOUT,
                      headers={"Authorization": f"Bearer {key}"})
    except httpx.HTTPError as exc:
        raise Unavailable(f"FamilyLog svarer ikke ({type(exc).__name__}).") from None
    if r.status_code == 401:
        raise Unavailable("FamilyLog afviste læsenøglen.")
    if r.status_code == 403:
        raise Refused(path)
    if r.status_code != 200:
        raise Unavailable(f"FamilyLog svarede {r.status_code}.")
    return r.json()


def month_range(today: date | None = None) -> tuple[str, str]:
    today = today or date.today()
    return today.replace(day=1).isoformat(), today.isoformat()


# ---- what lands on the timeline (pure; tested without a network) --------------

def dagbog_fields(entry: dict) -> dict | None:
    """A Dagbog day → ingest's fields. The person's own text is the title."""
    day = entry.get("day")
    if not day:
        return None
    text = (entry.get("highlight") or "").strip()
    first, _, rest = text.partition("\n")
    mood = entry.get("mood")
    title = first.strip() or (f"Dagbog, humør {mood} af 5" if mood else "Dagbog")
    lines = [rest.strip()] if rest.strip() else []
    if mood:
        lines.append(f"Humør {mood} af 5.")
    if entry.get("mental"):
        lines.append(f"Mentalt overskud {entry['mental']} af 10.")
    if entry.get("tags"):
        lines.append(", ".join(entry["tags"]) + ".")
    return {"title": title, "description": "\n".join(lines), "start": day, "all_day": True}


def review_fields(review: dict) -> dict | None:
    """A FamilyMap review → ingest's fields, on the day of the visit."""
    day = review.get("visitedOn") or (review.get("createdAt") or "")[:10]
    place = review.get("placeName") or "et sted"
    if not day:
        return None
    return {"title": f"Besøg: {place}", "description": (review.get("text") or "").strip(),
            "location": place, "start": day, "all_day": True}


# ---- the sync -------------------------------------------------------------------

def sync_dagbog(user_id: int, familylog_id: int) -> int:
    """Newest first, until a page holds nothing new, so the first run reads
    every day back and later runs stop after one page."""
    added = 0
    before = ""
    while True:
        params = {"user": familylog_id, "limit": DAYS_PER_PAGE}
        if before:
            params["before"] = before
        page = get(user_id, "/api/dagbog/person", params)
        results = []
        for entry in page.get("entries", []):
            fields = dagbog_fields(entry)
            if fields:
                results.append(life.ingest(user_id, DAGBOG, entry["day"], **fields))
        added += results.count("added")
        entries = page.get("entries", [])
        if not page.get("more") or not entries or set(results) == {"same"}:
            return added
        before = entries[-1]["day"]


def sync_reviews(user_id: int) -> int:
    added = 0
    for review in get(user_id, "/api/fm/me/reviews"):
        fields = review_fields(review)
        if fields and life.ingest(user_id, REVIEWS, str(review["id"]), **fields) == "added":
            added += 1
    return added


def _month(user_id: int) -> dict | None:
    """This month's spending, when the person has an Økonomi."""
    if not get(user_id, "/api/okonomi/state").get("access"):
        return None
    frm, to = month_range()
    o = get(user_id, "/api/okonomi/overview", {"frm": frm, "to": to})
    return {"from": frm, "to": to, "spent": o.get("spent"), "income": o.get("income"),
            "count": o.get("count"),
            "top": [{"name": c.get("name"), "spent": c.get("spent")}
                    for c in (o.get("categories") or [])[:3]]}


def sync_user(user_id: int) -> dict:
    summary: dict = {"checkedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"), "error": ""}
    try:
        who = get(user_id, "/api/read/me")
        summary["month"] = _month(user_id)
        summary["added"] = sync_dagbog(user_id, who["id"]) + sync_reviews(user_id)
    except Unavailable as exc:
        summary["error"] = str(exc)
    _summaries[user_id] = summary
    return summary


def job() -> None:
    if not settings.load().get("familylogUrl"):
        return
    with db.connect() as con:
        users = [r["user_id"] for r in con.execute("SELECT user_id FROM familylog_keys").fetchall()]
    for uid in users:
        try:
            sync_user(uid)
        except Exception as exc:
            logs.record_exception(exc, f"familylog sync, user {uid}")


def search(user_id: int, q: str) -> dict:
    """Økonomi and FamilyMap for a word. Only reads, as the person."""
    q = q.strip()[:100]
    out: dict = {"q": q, "transactions": None, "places": []}
    if not q:
        return out
    try:
        t = get(user_id, "/api/okonomi/transactions", {"q": q})
        out["transactions"] = {"total": t.get("total"), "sum": t.get("sum"), "rows": (t.get("rows") or [])[:25]}
    except Refused:
        pass                                    # this person has no Økonomi
    out["places"] = [{"id": p.get("id"), "name": p.get("name"), "address": p.get("address")}
                     for p in get(user_id, "/api/fm/places", {"q": q, "limit": 20})]
    return out


def state(user_id: int) -> dict:
    s = settings.load()
    return {"address": bool(s.get("familylogUrl")), "connected": bool(key_hint(user_id)),
            **_summaries.get(user_id, {})}


def overview(me: dict) -> dict:
    return state(me["id"])


def setup_status() -> dict:
    if not settings.load().get("familylogUrl"):
        return {"ok": False, "text": "Adresse mangler."}
    with db.connect() as con:
        n = con.execute("SELECT COUNT(*) FROM familylog_keys").fetchone()[0]
    bad = [v["error"] for v in _summaries.values() if v.get("error")]
    if bad:
        return {"ok": False, "text": bad[0]}
    return {"ok": n > 0, "text": f"{n} læsenøgler sat."}
