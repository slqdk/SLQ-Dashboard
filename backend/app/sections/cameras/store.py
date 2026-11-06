"""The cameras set up in Admin. Passwords are sealed by core/vault.py."""
from __future__ import annotations

import re
from urllib.parse import quote

from ...core import db, vault

SCHEMA = """
CREATE TABLE IF NOT EXISTS cameras (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    host       TEXT NOT NULL,
    username   TEXT NOT NULL,
    password   TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def migrate_1(con) -> None:
    con.executescript(SCHEMA)


HOST = re.compile(r"^[A-Za-z0-9.-]+(:\d{1,5})?$")


class Problem(ValueError):
    """Input that cannot be stored; the text is shown to the person."""


def _dto(r) -> dict:
    return {"id": r["id"], "name": r["name"], "host": r["host"], "username": r["username"]}


def all_cameras() -> list[dict]:
    with db.connect() as con:
        return [_dto(r) for r in con.execute("SELECT * FROM cameras ORDER BY name, id").fetchall()]


def source(camera_id: int, stream: str) -> str | None:
    """The camera's RTSP address with its login. It goes to go2rtc and nowhere
    else: not to the browser, and not to the log."""
    with db.connect() as con:
        r = con.execute("SELECT * FROM cameras WHERE id=?", (camera_id,)).fetchone()
    if r is None:
        return None
    user, password = quote(r["username"], safe=""), quote(vault.unseal(r["password"]), safe="")
    host = r["host"] if ":" in r["host"] else f"{r['host']}:554"
    return f"rtsp://{user}:{password}@{host}/{stream}"


def _clean(body: dict) -> tuple[str, str, str]:
    name = " ".join(str(body.get("name") or "").split())[:60]
    host = str(body.get("host") or "").strip()[:100]
    user = str(body.get("username") or "").strip()[:64]
    if not name or not host or not user:
        raise Problem("Kameraet skal have navn, adresse og brugernavn.")
    if not HOST.match(host):
        raise Problem("Adressen skal være en IP-adresse eller et værtsnavn.")
    return name, host, user


def add(body: dict) -> dict:
    name, host, user = _clean(body)
    password = str(body.get("password") or "")
    if not password:
        raise Problem("Skriv adgangskoden til kameraets konto.")
    with db.connect() as con:
        cur = con.execute("INSERT INTO cameras (name, host, username, password, created_at) VALUES (?,?,?,?,?)",
                          (name, host, user, vault.seal(password), db.utcnow()))
        return _dto(con.execute("SELECT * FROM cameras WHERE id=?", (cur.lastrowid,)).fetchone())


def update(camera_id: int, body: dict) -> dict:
    """An empty password keeps the old one."""
    name, host, user = _clean(body)
    password = str(body.get("password") or "")
    with db.connect() as con:
        cur = con.execute("UPDATE cameras SET name=?, host=?, username=? WHERE id=?",
                          (name, host, user, camera_id))
        if cur.rowcount == 0:
            raise LookupError("Findes ikke.")
        if password:
            con.execute("UPDATE cameras SET password=? WHERE id=?", (vault.seal(password), camera_id))
        return _dto(con.execute("SELECT * FROM cameras WHERE id=?", (camera_id,)).fetchone())


def delete(camera_id: int) -> None:
    with db.connect() as con:
        con.execute("DELETE FROM cameras WHERE id=?", (camera_id,))
