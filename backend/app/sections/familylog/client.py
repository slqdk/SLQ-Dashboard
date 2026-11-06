"""The way into FamilyLog. The dashboard can search, never post: the only HTTP
verb in this module is GET, and tests/test_familylog.py holds it to that."""
from __future__ import annotations

from datetime import date

import httpx

from ...core import db, settings, vault

TIMEOUT = 10.0

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


def set_key(user_id: int, key: str | None) -> None:
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
    if r.status_code in (401, 403):
        raise Unavailable("FamilyLog afviste læsenøglen.")
    if r.status_code != 200:
        raise Unavailable(f"FamilyLog svarede {r.status_code}.")
    return r.json()


def month_range(today: date | None = None) -> tuple[str, str]:
    today = today or date.today()
    return today.replace(day=1).isoformat(), today.isoformat()


def state(user_id: int) -> dict:
    s = settings.load()
    return {"address": bool(s.get("familylogUrl")), "connected": bool(key_hint(user_id))}


def overview(me: dict) -> dict:
    return state(me["id"])


def setup_status() -> dict:
    if not settings.load().get("familylogUrl"):
        return {"ok": False, "text": "Adresse mangler."}
    with db.connect() as con:
        n = con.execute("SELECT COUNT(*) FROM familylog_keys").fetchone()[0]
    return {"ok": n > 0, "text": f"{n} læsenøgler sat."}
