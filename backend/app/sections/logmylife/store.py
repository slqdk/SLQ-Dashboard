"""The timeline's storage. Everything about a life event goes through here."""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta, timezone

from ...core import db, settings
from . import files

SCHEMA = """
CREATE TABLE IF NOT EXISTS life_events (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id           INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    uid               TEXT NOT NULL UNIQUE,        -- stable id, whatever else changes
    source            TEXT NOT NULL,               -- manual | google | familylog.dagbog ...
    source_id         TEXT,                        -- the event's id at the source
    title             TEXT NOT NULL,
    description       TEXT NOT NULL DEFAULT '',
    category          TEXT NOT NULL DEFAULT '',
    start_at          TEXT NOT NULL,               -- UTC ISO, or YYYY-MM-DD when all day
    end_at            TEXT,                        -- the same; all-day end is inclusive
    all_day           INTEGER NOT NULL DEFAULT 1,
    day               TEXT NOT NULL,               -- local YYYY-MM-DD of the start
    location          TEXT NOT NULL DEFAULT '',
    lat               REAL,
    lng               REAL,
    shared            INTEGER NOT NULL DEFAULT 0,  -- the family may see it
    deleted_at_source TEXT,                        -- gone at the source, kept here
    raw               TEXT,                        -- the source's own record
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    UNIQUE (user_id, source, source_id)
);
CREATE INDEX IF NOT EXISTS life_events_day ON life_events (user_id, day);
CREATE INDEX IF NOT EXISTS life_events_mmdd ON life_events (substr(day, 6));
"""

MANUAL = "manual"
MAX_TITLE = 200
MAX_TEXT = 20000
CATEGORIES = ("Familie", "Rejse", "Arbejde", "Milepæl", "Fritid", "Andet")


def migrate_1(con) -> None:
    con.executescript(SCHEMA)


class Problem(ValueError):
    """Input that cannot be stored; the text is shown to the person."""


def _day_of(start: str, all_day: bool) -> str:
    if all_day:
        return start[:10]
    return datetime.fromisoformat(start.replace("Z", "+00:00")).astimezone(settings.tz()).date().isoformat()


def _utc_iso(value: str) -> str:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=settings.tz())
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _dto(r, me_id: int | None = None) -> dict:
    return {"id": r["id"], "uid": r["uid"], "source": r["source"], "title": r["title"],
            "description": r["description"], "category": r["category"],
            "start": r["start_at"], "end": r["end_at"], "allDay": bool(r["all_day"]),
            "day": r["day"], "location": r["location"], "lat": r["lat"], "lng": r["lng"],
            "shared": bool(r["shared"]), "deletedAtSource": r["deleted_at_source"],
            "mine": me_id is None or r["user_id"] == me_id,
            "owner": r["owner"] if "owner" in r.keys() else None}


# ---- what other sections call --------------------------------------------------

def when(start: str, end: str | None, all_day: bool) -> tuple[str, str | None, str]:
    """A source's times as they are stored: start, end, and the local day."""
    start = start if all_day else _utc_iso(start)
    if end:
        end = end if all_day else _utc_iso(end)
    return start, end, _day_of(start, all_day)


def ingest(user_id: int, source: str, source_id: str, *, title: str, start: str,
           end: str | None = None, all_day: bool = False, description: str = "",
           location: str = "", category: str = "", raw: dict | None = None) -> str:
    """Add or update one event from a source. Safe to run again: the same
    (user, source, source_id) updates the row instead of adding a new one, and
    a row that was marked deleted comes back when the source has it again.
    Returns 'added', 'updated' or 'same'."""
    start, end, day = when(start, end, all_day)
    now = db.utcnow()
    blob = json.dumps(raw, ensure_ascii=False) if raw is not None else None
    with db.connect() as con:
        row = con.execute(
            "SELECT * FROM life_events WHERE user_id=? AND source=? AND source_id=?",
            (user_id, source, source_id)).fetchone()
        if row is None:
            con.execute(
                "INSERT INTO life_events (user_id, uid, source, source_id, title, description,"
                " category, start_at, end_at, all_day, day, location, raw, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (user_id, str(uuid.uuid4()), source, source_id, title[:MAX_TITLE],
                 description[:MAX_TEXT], category, start, end, int(all_day), day, location,
                 blob, now, now))
            return "added"
        same = (row["title"] == title[:MAX_TITLE] and row["description"] == description[:MAX_TEXT]
                and row["start_at"] == start and row["end_at"] == end
                and bool(row["all_day"]) == all_day and row["location"] == location
                and row["deleted_at_source"] is None)
        if same:
            return "same"
        con.execute(
            "UPDATE life_events SET title=?, description=?, start_at=?, end_at=?, all_day=?,"
            " day=?, location=?, raw=?, deleted_at_source=NULL, updated_at=? WHERE id=?",
            (title[:MAX_TITLE], description[:MAX_TEXT], start, end, int(all_day), day,
             location, blob, now, row["id"]))
        return "updated"


def event_id(user_id: int, source: str, source_id: str) -> int:
    with db.connect() as con:
        return con.execute("SELECT id FROM life_events WHERE user_id=? AND source=? AND source_id=?",
                           (user_id, source, source_id)).fetchone()["id"]


def mark_deleted(user_id: int, source: str, source_id: str) -> bool:
    """The source no longer has it. The row stays: the log remembers."""
    with db.connect() as con:
        cur = con.execute(
            "UPDATE life_events SET deleted_at_source=?, updated_at=?"
            " WHERE user_id=? AND source=? AND source_id=? AND deleted_at_source IS NULL",
            (db.utcnow(), db.utcnow(), user_id, source, source_id))
        return cur.rowcount > 0


def forget(user_id: int, source: str, prefix: str) -> int:
    """Take the rows whose source id starts with `prefix` out of the log. The one
    exception to the log remembering: the person moved it to another calendar."""
    where = "user_id=? AND source=? AND substr(source_id, 1, ?)=?"
    args = (user_id, source, len(prefix), prefix)
    with db.connect() as con:
        files.drop_with_events(con, f"SELECT id FROM life_events WHERE {where}", args)
        return con.execute(f"DELETE FROM life_events WHERE {where}", args).rowcount


# ---- entries by hand ------------------------------------------------------------

def _clean(body: dict) -> dict:
    title = " ".join(str(body.get("title") or "").split())
    if not title:
        raise Problem("Skriv en titel.")
    if len(title) > MAX_TITLE:
        raise Problem(f"Titlen er for lang (højst {MAX_TITLE} tegn).")
    try:
        start = date.fromisoformat(str(body.get("start") or "")).isoformat()
    except ValueError:
        raise Problem("Vælg en dato.") from None
    end = body.get("end") or None
    if end:
        try:
            end = date.fromisoformat(str(end)).isoformat()
        except ValueError:
            raise Problem("Slutdatoen er ikke en dato.") from None
        if end < start:
            raise Problem("Slutdatoen ligger før startdatoen.")
    category = str(body.get("category") or "")
    if category and category not in CATEGORIES:
        raise Problem("Ukendt kategori.")
    return {"title": title, "start": start, "end": end, "category": category,
            "description": str(body.get("description") or "")[:MAX_TEXT],
            "location": " ".join(str(body.get("location") or "").split())[:200],
            "shared": bool(body.get("shared"))}


def add(user_id: int, body: dict) -> dict:
    v = _clean(body)
    now = db.utcnow()
    with db.connect() as con:
        cur = con.execute(
            "INSERT INTO life_events (user_id, uid, source, source_id, title, description, category,"
            " start_at, end_at, all_day, day, location, shared, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,1,?,?,?,?,?)",
            (user_id, str(uuid.uuid4()), MANUAL, None, v["title"], v["description"], v["category"],
             v["start"], v["end"], v["start"], v["location"], int(v["shared"]), now, now))
        row = con.execute("SELECT * FROM life_events WHERE id=?", (cur.lastrowid,)).fetchone()
    return _dto(row, user_id)


def _own(con, user_id: int, event_id: int):
    row = con.execute("SELECT * FROM life_events WHERE id=? AND user_id=?",
                      (event_id, user_id)).fetchone()
    if row is None:
        raise LookupError("Findes ikke.")
    return row


def update(user_id: int, event_id: int, body: dict) -> dict:
    """A hand-written entry can change completely. One from a source keeps
    what the source says; only its sharing and category are the person's."""
    with db.connect() as con:
        row = _own(con, user_id, event_id)
        if row["source"] == MANUAL:
            v = _clean(body)
            con.execute(
                "UPDATE life_events SET title=?, description=?, category=?, start_at=?, end_at=?,"
                " day=?, location=?, shared=?, updated_at=? WHERE id=?",
                (v["title"], v["description"], v["category"], v["start"], v["end"], v["start"],
                 v["location"], int(v["shared"]), db.utcnow(), event_id))
        else:
            category = str(body.get("category") or "")
            if category and category not in CATEGORIES:
                raise Problem("Ukendt kategori.")
            con.execute("UPDATE life_events SET shared=?, category=?, updated_at=? WHERE id=?",
                        (int(bool(body.get("shared"))), category, db.utcnow(), event_id))
        out = con.execute("SELECT * FROM life_events WHERE id=?", (event_id,)).fetchone()
    return _dto(out, user_id)


def remove(user_id: int, event_id: int) -> None:
    """Only what the person wrote. What came from a source stays: it would
    only come back at the next sync, and the log is meant to remember."""
    with db.connect() as con:
        row = _own(con, user_id, event_id)
        if row["source"] != MANUAL:
            raise Problem("Kun egne indlæg kan slettes. Dette kom fra en anden kilde.")
        files.drop_with_events(con, "SELECT ?", (event_id,))
        con.execute("DELETE FROM life_events WHERE id=?", (event_id,))


# ---- reading ---------------------------------------------------------------------

def today() -> str:
    return datetime.now(settings.tz()).date().isoformat()


def timeline(user_id: int, *, scope: str = "mine", before: str | None = None, q: str = "",
             source: str = "", year: str = "", limit: int = 100) -> dict:
    """Newest first, up to today. scope: mine | family (what others shared)."""
    limit = max(1, min(limit, 300))
    sql = ("SELECT e.*, COALESCE(NULLIF(u.name, ''), u.username) AS owner"
           " FROM life_events e JOIN users u ON u.id = e.user_id WHERE ")
    args: list = []
    if scope == "family":
        sql += "e.shared = 1 AND e.user_id != ?"
    else:
        sql += "e.user_id = ?"
    args.append(user_id)
    sql += " AND e.day <= ?"
    args.append(before or today())
    if q.strip():
        like = f"%{q.strip()}%"
        sql += " AND (e.title LIKE ? OR e.description LIKE ? OR e.location LIKE ?)"
        args += [like, like, like]
    if source:
        sql += " AND e.source = ?"
        args.append(source)
    if year:
        sql += " AND substr(e.day, 1, 4) = ?"
        args.append(year)
    sql += " ORDER BY e.day DESC, e.start_at DESC, e.id DESC LIMIT ?"
    args.append(limit + 1)
    with db.connect() as con:
        rows = con.execute(sql, args).fetchall()
    more = len(rows) > limit
    return {"events": [_dto(r, user_id) for r in rows[:limit]], "more": more}


INDEX_FIELDS = ("id", "day", "end", "title", "source", "category", "picture", "files", "gone", "owner")


def index(user_id: int, *, scope: str = "mine", q: str = "", source: str = "") -> dict:
    """Every entry up to today, oldest first, with what a place on the timeline needs and
    no more: one list per row, so thousands of them stay small."""
    sql = ("SELECT e.id, e.day, e.end_at, e.all_day, e.title, e.source, e.category, e.deleted_at_source, e.user_id,"
           " COALESCE(NULLIF(u.name, ''), u.username) AS owner,"
           " (SELECT MIN(f.id) FROM life_files f WHERE f.event_id = e.id AND f.kind = 'image') AS picture,"
           " (SELECT COUNT(*) FROM life_files f WHERE f.event_id = e.id) AS files"
           " FROM life_events e JOIN users u ON u.id = e.user_id WHERE ")
    sql += "e.shared = 1 AND e.user_id != ?" if scope == "family" else "e.user_id = ?"
    args: list = [user_id]
    sql += " AND e.day <= ?"
    args.append(today())
    if q.strip():
        like = f"%{q.strip()}%"
        sql += " AND (e.title LIKE ? OR e.description LIKE ? OR e.location LIKE ?)"
        args += [like, like, like]
    if source:
        sql += " AND e.source = ?"
        args.append(source)
    sql += " ORDER BY e.day, e.id"
    with db.connect() as con:
        rows = con.execute(sql, args).fetchall()

    def last_day(r) -> str | None:
        end = (r["end_at"] or "")[:10]
        return end if r["all_day"] and end > r["day"] else None

    return {"fields": INDEX_FIELDS, "today": today(),
            "rows": [[r["id"], r["day"], last_day(r), r["title"], r["source"], r["category"], r["picture"], r["files"],
                      1 if r["deleted_at_source"] else 0, None if r["user_id"] == user_id else r["owner"]] for r in rows]}


def entry(user_id: int, event_id: int) -> dict:
    """One entry in full, with its files: the person's own, or one shared with them."""
    with db.connect() as con:
        row = con.execute("SELECT e.*, COALESCE(NULLIF(u.name, ''), u.username) AS owner"
                          " FROM life_events e JOIN users u ON u.id = e.user_id"
                          " WHERE e.id = ? AND (e.user_id = ? OR e.shared = 1)", (event_id, user_id)).fetchone()
        if row is None:
            raise LookupError("Findes ikke.")
        return {**_dto(row, user_id), "files": files.of_event(con, event_id)}


def on_this_day(user_id: int, day: str | None = None, limit: int = 6) -> list[dict]:
    """Earlier years on this date: your own, and what the family shared."""
    day = day or today()
    with db.connect() as con:
        rows = con.execute(
            "SELECT e.*, COALESCE(NULLIF(u.name, ''), u.username) AS owner"
            " FROM life_events e JOIN users u ON u.id = e.user_id"
            " WHERE substr(e.day, 6) = ? AND e.day < ? AND (e.user_id = ? OR e.shared = 1)"
            " ORDER BY e.day DESC LIMIT ?",
            (day[5:], day[:4] + "-01-01", user_id, limit)).fetchall()
    return [_dto(r, user_id) for r in rows]


def stats(user_id: int) -> dict:
    with db.connect() as con:
        rows = con.execute("SELECT source, COUNT(*) AS n, MIN(day) AS first FROM life_events"
                           " WHERE user_id=? GROUP BY source", (user_id,)).fetchall()
    return {"bySource": {r["source"]: r["n"] for r in rows},
            "total": sum(r["n"] for r in rows),
            "first": min((r["first"] for r in rows), default=None)}


def overview(me: dict) -> dict:
    latest = timeline(me["id"], limit=4)["events"]
    return {"onThisDay": on_this_day(me["id"], limit=3), "latest": latest,
            "total": stats(me["id"])["total"]}
