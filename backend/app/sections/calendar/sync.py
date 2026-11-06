"""Google → the dashboard. One way: nothing here can write to Google.

Every calendar that is ticked keeps a copy of its events here, which is what the
page and the overview show. One calendar per person also goes to LogMyLife: Google's
primary one, until the person picks another.
"""
from __future__ import annotations

from datetime import date, timedelta

from ...core import db, google, logs, settings, vault
from ...core.migrations import add_column
from ..logmylife import store as life

SOURCE = "google"

SCHEMA = """
CREATE TABLE IF NOT EXISTS google_accounts (
    user_id       INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    email         TEXT NOT NULL DEFAULT '',
    refresh_token TEXT NOT NULL,                  -- sealed by core/vault.py
    status        TEXT NOT NULL DEFAULT 'ok',     -- ok | reconnect
    connected_at  TEXT NOT NULL,
    last_sync_at  TEXT,
    last_error    TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS google_calendars (
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    calendar_id TEXT NOT NULL,
    summary     TEXT NOT NULL DEFAULT '',
    color       TEXT NOT NULL DEFAULT '',
    selected    INTEGER NOT NULL DEFAULT 1,
    sync_token  TEXT,
    PRIMARY KEY (user_id, calendar_id)
);
"""


EVENTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS google_events (
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    calendar_id TEXT NOT NULL,
    event_id    TEXT NOT NULL,
    title       TEXT NOT NULL,
    start_at    TEXT NOT NULL,
    end_at      TEXT,
    all_day     INTEGER NOT NULL,
    day         TEXT NOT NULL,
    location    TEXT NOT NULL,
    color       TEXT NOT NULL,                    -- the event's own; empty = its calendar's
    PRIMARY KEY (user_id, calendar_id, event_id)
);
CREATE INDEX IF NOT EXISTS google_events_day ON google_events (user_id, day);
"""


def migrate_1(con) -> None:
    con.executescript(SCHEMA)


def migrate_2(con) -> None:
    """Søren, 6 November 2026: only the main calendar goes to the log. It starts as
    Google's primary, whose id is the account's address. What the others had put in
    the log goes, and everything is fetched again into the new table."""
    con.executescript(EVENTS_SCHEMA)
    add_column(con, "google_calendars", "to_log", "INTEGER NOT NULL DEFAULT 0")
    con.execute("UPDATE google_calendars SET sync_token=NULL")
    con.execute("UPDATE google_calendars SET to_log=1 WHERE calendar_id="
                "(SELECT a.email FROM google_accounts a WHERE a.user_id=google_calendars.user_id)")
    if con.execute("SELECT 1 FROM sqlite_master WHERE name='life_events'").fetchone():      # not on a new database
        con.execute("DELETE FROM life_events WHERE source=? AND NOT EXISTS (SELECT 1 FROM google_calendars c"
                    " WHERE c.user_id=life_events.user_id AND c.to_log=1"
                    " AND substr(life_events.source_id, 1, length(c.calendar_id) + 1)=c.calendar_id || '|')", (SOURCE,))


# ---- mapping (pure; tested without a network) -----------------------------------

def event_fields(ev: dict) -> dict | None:
    """A Google event → ingest's fields; None when it has no usable start.

    Google's all-day end date is EXCLUSIVE: a one-day event on 23 November has
    end.date 24 November. The log's end is inclusive, so one day comes off."""
    start = ev.get("start") or {}
    end = ev.get("end") or {}
    fields = {"title": (ev.get("summary") or "").strip() or "(uden titel)",
              "description": ev.get("description") or "",
              "location": ev.get("location") or ""}
    if start.get("date"):
        last = None
        if end.get("date"):
            inclusive = date.fromisoformat(end["date"]) - timedelta(days=1)
            if inclusive.isoformat() > start["date"]:
                last = inclusive.isoformat()
        return {**fields, "start": start["date"], "end": last, "all_day": True}
    if start.get("dateTime"):
        return {**fields, "start": start["dateTime"], "end": end.get("dateTime"), "all_day": False}
    return None


def source_id(calendar_id: str, event_id: str) -> str:
    return f"{calendar_id}|{event_id}"


def apply_events(user_id: int, calendar_id: str, items: list[dict], to_log: bool = True) -> dict:
    """A calendar's changes into the copy here, and into the log when it is the one."""
    counts = {"added": 0, "updated": 0, "same": 0, "deleted": 0, "skipped": 0}
    kept: list[tuple] = []
    gone: list[tuple] = []
    for ev in items:
        sid = source_id(calendar_id, ev["id"])
        if ev.get("status") == "cancelled":
            gone.append((user_id, calendar_id, ev["id"]))
            if to_log:
                counts["deleted" if life.mark_deleted(user_id, SOURCE, sid) else "skipped"] += 1
            continue
        fields = event_fields(ev)
        if fields is None:
            counts["skipped"] += 1
            continue
        start, end, day = life.when(fields["start"], fields["end"], fields["all_day"])
        kept.append((user_id, calendar_id, ev["id"], fields["title"], start, end, int(fields["all_day"]), day,
                     fields["location"], google.EVENT_COLORS.get(ev.get("colorId"), "")))
        if to_log:
            keep = {k: ev.get(k) for k in ("id", "htmlLink", "status", "organizer", "recurringEventId")}
            counts[life.ingest(user_id, SOURCE, sid, raw={**keep, "calendarId": calendar_id}, **fields)] += 1
    with db.connect() as con:
        con.executemany("DELETE FROM google_events WHERE user_id=? AND calendar_id=? AND event_id=?", gone)
        con.executemany(
            "INSERT INTO google_events (user_id, calendar_id, event_id, title, start_at, end_at, all_day, day,"
            " location, color) VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT (user_id, calendar_id, event_id) DO UPDATE SET"
            " title=excluded.title, start_at=excluded.start_at, end_at=excluded.end_at, all_day=excluded.all_day,"
            " day=excluded.day, location=excluded.location, color=excluded.color", kept)
    return counts


# ---- accounts ----------------------------------------------------------------------

def account(user_id: int):
    with db.connect() as con:
        return con.execute("SELECT * FROM google_accounts WHERE user_id=?", (user_id,)).fetchone()


def calendars_of(user_id: int) -> list[dict]:
    with db.connect() as con:
        rows = con.execute("SELECT * FROM google_calendars WHERE user_id=? ORDER BY summary",
                           (user_id,)).fetchall()
    return [{"id": r["calendar_id"], "summary": r["summary"], "color": r["color"],
             "selected": bool(r["selected"]), "toLog": bool(r["to_log"])} for r in rows]


def state_of(user_id: int) -> dict:
    a = account(user_id)
    return {"configured": google.configured(), "connected": a is not None,
            "email": a["email"] if a else "", "status": a["status"] if a else "",
            "lastSyncAt": a["last_sync_at"] if a else None,
            "lastError": a["last_error"] if a else "",
            "calendars": calendars_of(user_id) if a else []}


def _refresh_calendars(user_id: int, token: str) -> list[dict]:
    found = google.calendars(token)
    with db.connect() as con:
        for c in found:
            con.execute(
                "INSERT INTO google_calendars (user_id, calendar_id, summary, color)"
                " VALUES (?,?,?,?) ON CONFLICT (user_id, calendar_id)"
                " DO UPDATE SET summary=excluded.summary, color=excluded.color",
                (user_id, c["id"], c["summary"], c["color"]))
        primary = next((c["id"] for c in found if c["primary"]), None)
        if primary and not con.execute("SELECT 1 FROM google_calendars WHERE user_id=? AND to_log=1",
                                       (user_id,)).fetchone():
            con.execute("UPDATE google_calendars SET to_log=1 WHERE user_id=? AND calendar_id=?", (user_id, primary))
    return found


def connect(user_id: int, code: str, redirect_uri: str) -> None:
    """The end of the connect flow: keep the refresh token, list the calendars."""
    tokens = google.exchange_code(code, redirect_uri)
    refresh = tokens.get("refresh_token")
    if not refresh:
        raise google.GoogleError("Google gav ingen varig adgang. Prøv at forbinde igen.")
    found = google.calendars(tokens["access_token"])
    primary = next((c for c in found if c["primary"]), None)
    with db.connect() as con:
        con.execute(
            "INSERT INTO google_accounts (user_id, email, refresh_token, connected_at)"
            " VALUES (?,?,?,?) ON CONFLICT (user_id) DO UPDATE SET email=excluded.email,"
            " refresh_token=excluded.refresh_token, status='ok', last_error='',"
            " connected_at=excluded.connected_at",
            (user_id, primary["id"] if primary else "", vault.seal(refresh), db.utcnow()))
    _refresh_calendars(user_id, tokens["access_token"])


def disconnect(user_id: int) -> None:
    """Stops the sync. What is already in the log stays; the copy here goes."""
    with db.connect() as con:
        con.execute("DELETE FROM google_events WHERE user_id=?", (user_id,))
        con.execute("DELETE FROM google_calendars WHERE user_id=?", (user_id,))
        con.execute("DELETE FROM google_accounts WHERE user_id=?", (user_id,))


def select(user_id: int, calendar_id: str, selected: bool) -> None:
    with db.connect() as con:
        con.execute("UPDATE google_calendars SET selected=? WHERE user_id=? AND calendar_id=?",
                    (int(selected), user_id, calendar_id))


def set_log_calendar(user_id: int, calendar_id: str) -> None:
    """Move the log to another calendar: the old one's rows go, and the new one is
    read from the start, so all of it arrives."""
    with db.connect() as con:
        rows = con.execute("SELECT calendar_id, to_log FROM google_calendars WHERE user_id=?", (user_id,)).fetchall()
        logged = {r["calendar_id"]: bool(r["to_log"]) for r in rows}
        if calendar_id not in logged:
            raise LookupError("Kalenderen findes ikke.")
        if logged[calendar_id]:
            return
        con.execute("UPDATE google_calendars SET to_log=(calendar_id=?) WHERE user_id=?", (calendar_id, user_id))
        con.execute("UPDATE google_calendars SET sync_token=NULL WHERE user_id=? AND calendar_id=?",
                    (user_id, calendar_id))
    for calendar in (c for c, on in logged.items() if on):
        life.forget(user_id, SOURCE, source_id(calendar, ""))


# ---- the sync ------------------------------------------------------------------------

def _set_status(user_id: int, status: str, error: str = "") -> None:
    with db.connect() as con:
        con.execute("UPDATE google_accounts SET status=?, last_error=?, last_sync_at=?"
                    " WHERE user_id=?", (status, error, db.utcnow(), user_id))


def sync_user(user_id: int) -> dict:
    a = account(user_id)
    if a is None:
        return {}
    totals: dict[str, int] = {}
    try:
        token = google.access_token(vault.unseal(a["refresh_token"]))
        _refresh_calendars(user_id, token)
        with db.connect() as con:
            cals = con.execute("SELECT * FROM google_calendars WHERE user_id=? AND (selected=1 OR to_log=1)",
                               (user_id,)).fetchall()
        for c in cals:
            try:
                items, next_token = google.events(token, c["calendar_id"], c["sync_token"])
            except google.SyncTokenGone:
                items, next_token = google.events(token, c["calendar_id"], None)
            for key, value in apply_events(user_id, c["calendar_id"], items, bool(c["to_log"])).items():
                totals[key] = totals.get(key, 0) + value
            with db.connect() as con:
                con.execute("UPDATE google_calendars SET sync_token=?"
                            " WHERE user_id=? AND calendar_id=?",
                            (next_token, user_id, c["calendar_id"]))
    except (google.NeedsReconnect, vault.VaultError) as exc:
        _set_status(user_id, "reconnect", str(exc))
        return totals
    except google.GoogleError as exc:
        _set_status(user_id, "ok", str(exc))
        return totals
    _set_status(user_id, "ok")
    return totals


def job() -> None:
    if not google.configured():
        return
    with db.connect() as con:
        users = [r["user_id"] for r in con.execute(
            "SELECT user_id FROM google_accounts WHERE status='ok'").fetchall()]
    for uid in users:
        try:
            sync_user(uid)
        except Exception as exc:
            logs.record_exception(exc, f"calendar sync, user {uid}")


# ---- the page ------------------------------------------------------------------------

def upcoming(user_id: int, days: int = 14, limit: int = 200) -> list[dict]:
    """What is coming in the ticked calendars, each event in its colour."""
    start = life.today()
    end = (date.fromisoformat(start) + timedelta(days=days)).isoformat()
    with db.connect() as con:
        rows = con.execute(
            "SELECT e.*, c.summary, c.color AS calendar_color FROM google_events e"
            " JOIN google_calendars c ON c.user_id=e.user_id AND c.calendar_id=e.calendar_id"
            " WHERE e.user_id=? AND c.selected=1 AND e.day >= ? AND e.day <= ?"
            " ORDER BY e.start_at, e.event_id LIMIT ?", (user_id, start, end, limit)).fetchall()
    now = life.when(db.utcnow(), None, False)[0]
    return [{"id": source_id(r["calendar_id"], r["event_id"]), "title": r["title"], "start": r["start_at"],
             "end": r["end_at"], "allDay": bool(r["all_day"]), "day": r["day"], "location": r["location"],
             "color": r["color"] or r["calendar_color"], "calendar": r["summary"]}
            for r in rows if r["all_day"] or (r["end_at"] or r["start_at"]) >= now]     # not what is over today


def overview(me: dict) -> dict:
    state = state_of(me["id"])
    return {"configured": state["configured"], "connected": state["connected"],
            "status": state["status"], "email": state["email"],
            "events": upcoming(me["id"], days=10, limit=40) if state["connected"] else []}


def setup_status() -> dict:
    s = settings.load()
    if not google.configured(s):
        return {"ok": False, "text": "Google-klient mangler."}
    with db.connect() as con:
        n = con.execute("SELECT COUNT(*) FROM google_accounts").fetchone()[0]
    return {"ok": True, "text": f"{n} forbundet."}
