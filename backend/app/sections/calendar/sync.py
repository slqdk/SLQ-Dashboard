"""Google → LogMyLife. One way: nothing here can write to Google."""
from __future__ import annotations

from datetime import date, timedelta

from ...core import db, google, logs, settings, vault
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


def migrate_1(con) -> None:
    con.executescript(SCHEMA)


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


def apply_events(user_id: int, calendar_id: str, items: list[dict]) -> dict:
    counts = {"added": 0, "updated": 0, "same": 0, "deleted": 0, "skipped": 0}
    for ev in items:
        sid = source_id(calendar_id, ev["id"])
        if ev.get("status") == "cancelled":
            counts["deleted" if life.mark_deleted(user_id, SOURCE, sid) else "skipped"] += 1
            continue
        fields = event_fields(ev)
        if fields is None:
            counts["skipped"] += 1
            continue
        keep = {k: ev.get(k) for k in ("id", "htmlLink", "status", "organizer", "recurringEventId")}
        counts[life.ingest(user_id, SOURCE, sid, raw={**keep, "calendarId": calendar_id}, **fields)] += 1
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
             "selected": bool(r["selected"])} for r in rows]


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
    """Stops the sync. What is already in the log stays."""
    with db.connect() as con:
        con.execute("DELETE FROM google_calendars WHERE user_id=?", (user_id,))
        con.execute("DELETE FROM google_accounts WHERE user_id=?", (user_id,))


def select(user_id: int, calendar_id: str, selected: bool) -> None:
    with db.connect() as con:
        con.execute("UPDATE google_calendars SET selected=? WHERE user_id=? AND calendar_id=?",
                    (int(selected), user_id, calendar_id))


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
            cals = con.execute("SELECT * FROM google_calendars WHERE user_id=? AND selected=1",
                               (user_id,)).fetchall()
        for c in cals:
            try:
                items, next_token = google.events(token, c["calendar_id"], c["sync_token"])
            except google.SyncTokenGone:
                items, next_token = google.events(token, c["calendar_id"], None)
            for key, value in apply_events(user_id, c["calendar_id"], items).items():
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

def overview(me: dict) -> dict:
    state = state_of(me["id"])
    return {"configured": state["configured"], "connected": state["connected"],
            "status": state["status"], "email": state["email"],
            "events": life.upcoming(me["id"], days=10, limit=40) if state["connected"] else []}


def setup_status() -> dict:
    s = settings.load()
    if not google.configured(s):
        return {"ok": False, "text": "Google-klient mangler."}
    with db.connect() as con:
        n = con.execute("SELECT COUNT(*) FROM google_accounts").fetchone()[0]
    return {"ok": True, "text": f"{n} forbundet."}
