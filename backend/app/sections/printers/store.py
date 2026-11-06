"""The printers set up in Admin. Access codes are sealed by core/vault.py."""
from __future__ import annotations

import re

from ...core import db, vault

SCHEMA = """
CREATE TABLE IF NOT EXISTS printers (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    host       TEXT NOT NULL,
    serial     TEXT NOT NULL,
    code       TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def migrate_1(con) -> None:
    con.executescript(SCHEMA)


HOST = re.compile(r"^[A-Za-z0-9.-]+(:\d{1,5})?$")
SERIAL = re.compile(r"^[A-Za-z0-9]+$")          # it becomes part of an MQTT topic


class Problem(ValueError):
    """Input that cannot be stored; the text is shown to the person."""


def _dto(r) -> dict:
    return {"id": r["id"], "name": r["name"], "host": r["host"], "serial": r["serial"]}


def all_printers() -> list[dict]:
    with db.connect() as con:
        return [_dto(r) for r in con.execute("SELECT * FROM printers ORDER BY name, id").fetchall()]


def code_of(printer_id: int) -> str:
    with db.connect() as con:
        r = con.execute("SELECT code FROM printers WHERE id=?", (printer_id,)).fetchone()
    return vault.unseal(r["code"]) if r else ""


def _clean(body: dict) -> tuple[str, str, str]:
    name = " ".join(str(body.get("name") or "").split())[:60]
    host = str(body.get("host") or "").strip()[:100]
    serial = str(body.get("serial") or "").strip()[:40]
    if not name or not host or not serial:
        raise Problem("Printeren skal have navn, adresse og serienummer.")
    if not HOST.match(host):
        raise Problem("Adressen skal være en IP-adresse eller et værtsnavn.")
    if not SERIAL.match(serial):
        raise Problem("Serienummeret må kun bestå af bogstaver og tal.")
    return name, host, serial


def add(body: dict) -> dict:
    name, host, serial = _clean(body)
    code = str(body.get("code") or "").strip()
    if not code:
        raise Problem("Skriv adgangskoden fra printerens skærm.")
    with db.connect() as con:
        cur = con.execute("INSERT INTO printers (name, host, serial, code, created_at) VALUES (?,?,?,?,?)",
                          (name, host, serial, vault.seal(code), db.utcnow()))
        return _dto(con.execute("SELECT * FROM printers WHERE id=?", (cur.lastrowid,)).fetchone())


def update(printer_id: int, body: dict) -> dict:
    """An empty code keeps the old one."""
    name, host, serial = _clean(body)
    code = str(body.get("code") or "").strip()
    with db.connect() as con:
        cur = con.execute("UPDATE printers SET name=?, host=?, serial=? WHERE id=?",
                          (name, host, serial, printer_id))
        if cur.rowcount == 0:
            raise LookupError("Findes ikke.")
        if code:
            con.execute("UPDATE printers SET code=? WHERE id=?", (vault.seal(code), printer_id))
        return _dto(con.execute("SELECT * FROM printers WHERE id=?", (printer_id,)).fetchone())


def delete(printer_id: int) -> None:
    with db.connect() as con:
        con.execute("DELETE FROM printers WHERE id=?", (printer_id,))
