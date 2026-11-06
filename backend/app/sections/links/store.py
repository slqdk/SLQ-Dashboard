"""Folders and links, per person."""
from __future__ import annotations

import re

from ...core import db

SCHEMA = """
CREATE TABLE IF NOT EXISTS link_folders (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    parent_id INTEGER REFERENCES link_folders(id) ON DELETE CASCADE,
    name      TEXT NOT NULL,
    position  INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS links (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    folder_id  INTEGER REFERENCES link_folders(id) ON DELETE CASCADE,
    title      TEXT NOT NULL,
    url        TEXT NOT NULL,
    note       TEXT NOT NULL DEFAULT '',
    pinned     INTEGER NOT NULL DEFAULT 0,
    position   INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS links_folder ON links (user_id, folder_id);
"""

MAX_NAME = 80
MAX_URL = 2000


def migrate_1(con) -> None:
    con.executescript(SCHEMA)


class Problem(ValueError):
    """Input that cannot be stored; the text is shown to the person."""


def clean_url(raw: str) -> str:
    """http(s) only - a link is opened by a click, so javascript: stays out. A
    bare host gets https:// (http:// for an address on the LAN)."""
    url = (raw or "").strip()
    if not url:
        raise Problem("Skriv en adresse.")
    if len(url) > MAX_URL:
        raise Problem("Adressen er for lang.")
    if not re.match(r"^[a-z][a-z0-9+.\-]*://", url, re.I):
        if re.match(r"^[a-z][a-z0-9+.\-]*:(?!\d)", url, re.I):
            raise Problem("Kun http- og https-adresser.")
        lan = re.match(r"^(\d+\.\d+\.\d+\.\d+|localhost|[a-z0-9\-]+\.lan)(:\d+)?(/|$)", url, re.I)
        url = ("http://" if lan else "https://") + url
    if not re.match(r"^https?://[^\s/]+", url, re.I):
        raise Problem("Kun http- og https-adresser.")
    return url


def _name(raw: str, what: str) -> str:
    name = " ".join((raw or "").split())
    if not name:
        raise Problem(f"Skriv {what}.")
    return name[:MAX_NAME]


def _folder_owned(con, user_id: int, folder_id: int | None) -> None:
    if folder_id is None:
        return
    if not con.execute("SELECT 1 FROM link_folders WHERE id=? AND user_id=?",
                       (folder_id, user_id)).fetchone():
        raise LookupError("Mappen findes ikke.")


def _link_dto(r) -> dict:
    return {"id": r["id"], "folderId": r["folder_id"], "title": r["title"], "url": r["url"],
            "note": r["note"], "pinned": bool(r["pinned"]), "createdAt": r["created_at"]}


def tree(user_id: int) -> dict:
    with db.connect() as con:
        folders = con.execute("SELECT * FROM link_folders WHERE user_id=? ORDER BY position, name",
                              (user_id,)).fetchall()
        links = con.execute("SELECT * FROM links WHERE user_id=? ORDER BY position, title",
                            (user_id,)).fetchall()
    return {"folders": [{"id": f["id"], "parentId": f["parent_id"], "name": f["name"]} for f in folders],
            "links": [_link_dto(r) for r in links]}


def add_folder(user_id: int, name: str, parent_id: int | None) -> dict:
    name = _name(name, "et navn")
    with db.connect() as con:
        _folder_owned(con, user_id, parent_id)
        cur = con.execute("INSERT INTO link_folders (user_id, parent_id, name) VALUES (?,?,?)",
                          (user_id, parent_id, name))
    return {"id": cur.lastrowid, "parentId": parent_id, "name": name}


def _descends_from(con, folder_id: int | None, ancestor: int) -> bool:
    while folder_id is not None:
        if folder_id == ancestor:
            return True
        row = con.execute("SELECT parent_id FROM link_folders WHERE id=?", (folder_id,)).fetchone()
        folder_id = row["parent_id"] if row else None
    return False


def update_folder(user_id: int, folder_id: int, body: dict) -> None:
    with db.connect() as con:
        _folder_owned(con, user_id, folder_id)
        if "name" in body:
            con.execute("UPDATE link_folders SET name=? WHERE id=?",
                        (_name(body["name"], "et navn"), folder_id))
        if "parentId" in body:
            parent = body["parentId"]
            _folder_owned(con, user_id, parent)
            if _descends_from(con, parent, folder_id):
                raise Problem("En mappe kan ikke flyttes ind i sig selv.")
            con.execute("UPDATE link_folders SET parent_id=? WHERE id=?", (parent, folder_id))


def _subtree(con, folder_id: int) -> list[int]:
    out, todo = [], [folder_id]
    while todo:
        current = todo.pop()
        out.append(current)
        todo += [r["id"] for r in con.execute(
            "SELECT id FROM link_folders WHERE parent_id=?", (current,)).fetchall()]
    return out


def folder_size(user_id: int, folder_id: int) -> dict:
    with db.connect() as con:
        _folder_owned(con, user_id, folder_id)
        ids = _subtree(con, folder_id)
        marks = ",".join("?" * len(ids))
        links = con.execute(f"SELECT COUNT(*) FROM links WHERE folder_id IN ({marks})", ids).fetchone()[0]
    return {"folders": len(ids) - 1, "links": links}


def delete_folder(user_id: int, folder_id: int) -> None:
    """With everything in it (ON DELETE CASCADE). The page asks first."""
    with db.connect() as con:
        _folder_owned(con, user_id, folder_id)
        con.execute("DELETE FROM link_folders WHERE id=?", (folder_id,))


def add_link(user_id: int, body: dict) -> dict:
    url = clean_url(body.get("url"))
    title = " ".join(str(body.get("title") or "").split())[:MAX_NAME] or re.sub(r"^https?://", "", url)[:MAX_NAME]
    folder = body.get("folderId")
    with db.connect() as con:
        _folder_owned(con, user_id, folder)
        cur = con.execute(
            "INSERT INTO links (user_id, folder_id, title, url, note, pinned, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (user_id, folder, title, url, str(body.get("note") or "")[:500],
             int(bool(body.get("pinned"))), db.utcnow()))
        row = con.execute("SELECT * FROM links WHERE id=?", (cur.lastrowid,)).fetchone()
    return _link_dto(row)


def update_link(user_id: int, link_id: int, body: dict) -> dict:
    with db.connect() as con:
        row = con.execute("SELECT * FROM links WHERE id=? AND user_id=?", (link_id, user_id)).fetchone()
        if row is None:
            raise LookupError("Linket findes ikke.")
        fields: dict = {}
        if "url" in body:
            fields["url"] = clean_url(body["url"])
        if "title" in body:
            fields["title"] = _name(body["title"], "en titel")
        if "note" in body:
            fields["note"] = str(body["note"] or "")[:500]
        if "pinned" in body:
            fields["pinned"] = int(bool(body["pinned"]))
        if "folderId" in body:
            _folder_owned(con, user_id, body["folderId"])
            fields["folder_id"] = body["folderId"]
        if fields:
            sets = ", ".join(f"{k}=?" for k in fields)
            con.execute(f"UPDATE links SET {sets} WHERE id=?", (*fields.values(), link_id))
        out = con.execute("SELECT * FROM links WHERE id=?", (link_id,)).fetchone()
    return _link_dto(out)


def delete_link(user_id: int, link_id: int) -> None:
    with db.connect() as con:
        cur = con.execute("DELETE FROM links WHERE id=? AND user_id=?", (link_id, user_id))
        if cur.rowcount == 0:
            raise LookupError("Linket findes ikke.")


def overview(me: dict) -> dict:
    with db.connect() as con:
        pinned = con.execute("SELECT * FROM links WHERE user_id=? AND pinned=1 ORDER BY position, title"
                             " LIMIT 12", (me["id"],)).fetchall()
        total = con.execute("SELECT COUNT(*) FROM links WHERE user_id=?", (me["id"],)).fetchone()[0]
    return {"pinned": [_link_dto(r) for r in pinned], "total": total}
