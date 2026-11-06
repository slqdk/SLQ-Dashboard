"""Pictures and other files on a person's entries.

They live in the data directory under logmylife/<person>/, named by a random id and never
by what the upload was called:

  <uid><ext>        the file as it came, which is what an export carries
  <uid>.view.jpg    a picture at most 1800 px, upright, without EXIF
  <uid>.thumb.jpg   the same at 480 px

EXIF can say where a picture was taken, so the family, who can see a shared entry, gets
those two and only the owner the original. Anything that is not a picture comes back as a
download: served as itself, an HTML file would run with the dashboard's login.
"""
from __future__ import annotations

import io
import mimetypes
import os
import re
import shutil
import uuid
from pathlib import Path
from typing import AsyncIterator

from ...core import db

MAX_BYTES = 1024 ** 3
VIEW_PX, THUMB_PX = 1800, 480
QUALITY = 85
PLAYABLE = {"video/mp4", "video/webm", "video/ogg"}
SIZES = ("thumb", "view", "original")

SCHEMA = """
CREATE TABLE IF NOT EXISTS life_files (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id   INTEGER NOT NULL REFERENCES life_events(id) ON DELETE CASCADE,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    uid        TEXT NOT NULL UNIQUE,            -- the name on disk
    ext        TEXT NOT NULL DEFAULT '',
    name       TEXT NOT NULL,                   -- what it was called
    kind       TEXT NOT NULL,                   -- image | video | file
    mime       TEXT NOT NULL,
    bytes      INTEGER NOT NULL,
    width      INTEGER,
    height     INTEGER,
    taken_at   TEXT,                            -- from EXIF, as the camera wrote it
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS life_files_event ON life_files (event_id);
"""


def migrate_2(con) -> None:
    con.executescript(SCHEMA)


class Problem(ValueError):
    """A file that cannot be stored; the text is shown to the person."""


def folder(user_id: int) -> Path:
    return db.data_dir() / "logmylife" / str(user_id)


def _clean_name(name: str) -> str:
    name = re.split(r"[/\\]", name or "")[-1]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()
    return name[:200] or "fil"


def _ext(name: str) -> str:
    ext = Path(name).suffix.lower()
    return ext if re.fullmatch(r"\.[a-z0-9]{1,10}", ext) else ""


def _taken(img) -> str | None:
    try:
        value = img.getexif().get_ifd(0x8769).get(36867)        # DateTimeOriginal
    except (AttributeError, KeyError, ValueError, OSError):
        return None
    return str(value).strip()[:32] or None if value else None


def _jpeg(img, px: int) -> bytes:
    from PIL import Image
    copy = img.copy()
    copy.thumbnail((px, px), Image.LANCZOS)
    out = io.BytesIO()
    copy.save(out, "JPEG", quality=QUALITY, optimize=True)      # no EXIF is passed on
    return out.getvalue()


def _picture(path: Path) -> dict | None:
    """The picture's two sizes and facts, or None for anything Pillow cannot read."""
    from PIL import Image, ImageOps, UnidentifiedImageError
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()      # what phones call a photo these days
    except ImportError:
        pass
    try:
        with Image.open(path) as img:
            taken = _taken(img)
            mime = Image.MIME.get(img.format or "", "image/jpeg")
            upright = ImageOps.exif_transpose(img).convert("RGB")
            return {"view": _jpeg(upright, VIEW_PX), "thumb": _jpeg(upright, THUMB_PX), "width": upright.width,
                    "height": upright.height, "taken": taken, "mime": mime}
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        return None


def scratch(user_id: int) -> Path:
    """Where a file waits before `add` takes it, on the same disk as where it ends."""
    where = folder(user_id)
    where.mkdir(parents=True, exist_ok=True)
    return where / f".incoming-{uuid.uuid4().hex}"


async def receive(user_id: int, stream: AsyncIterator[bytes]) -> Path:
    """The upload into a file of its own, so a big one never sits in memory."""
    temporary = scratch(user_id)
    size = 0
    try:
        with temporary.open("wb") as out:
            async for chunk in stream:
                size += len(chunk)
                if size > MAX_BYTES:
                    raise Problem(f"Filen er for stor (højst {MAX_BYTES // 1024 ** 2} MB).")
                out.write(chunk)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    if not size:
        temporary.unlink(missing_ok=True)
        raise Problem("Filen er tom.")
    return temporary


def _dto(r) -> dict:
    return {"id": r["id"], "name": r["name"], "kind": r["kind"], "mime": r["mime"], "bytes": r["bytes"],
            "width": r["width"], "height": r["height"], "taken": r["taken_at"]}


def add(user_id: int, event_id: int, name: str, temporary: Path) -> dict:
    """A received file onto an entry of the person's own."""
    name = _clean_name(name)
    try:
        with db.connect() as con:
            if not con.execute("SELECT 1 FROM life_events WHERE id=? AND user_id=?", (event_id, user_id)).fetchone():
                raise LookupError("Findes ikke.")
        picture = _picture(temporary)
        mime = picture["mime"] if picture else mimetypes.guess_type(name)[0] or "application/octet-stream"
        kind = "image" if picture else "video" if mime.startswith("video/") else "file"
        uid, ext = uuid.uuid4().hex, _ext(name)
        where = folder(user_id)
        if picture:
            (where / f"{uid}.view.jpg").write_bytes(picture["view"])
            (where / f"{uid}.thumb.jpg").write_bytes(picture["thumb"])
        size = temporary.stat().st_size
        temporary.replace(where / f"{uid}{ext}")
    finally:
        temporary.unlink(missing_ok=True)
    with db.connect() as con:
        cur = con.execute(
            "INSERT INTO life_files (event_id, user_id, uid, ext, name, kind, mime, bytes, width, height, taken_at, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (event_id, user_id, uid, ext, name, kind, mime, size, picture["width"] if picture else None,
             picture["height"] if picture else None, picture["taken"] if picture else None, db.utcnow()))
        row = con.execute("SELECT * FROM life_files WHERE id=?", (cur.lastrowid,)).fetchone()
    return _dto(row)


def has(event_id: int, name: str) -> bool:
    """Whether the entry holds a file of that name, so that an import can run again."""
    with db.connect() as con:
        return con.execute("SELECT 1 FROM life_files WHERE event_id=? AND name=?", (event_id, _clean_name(name))).fetchone() is not None


def of_event(con, event_id: int) -> list[dict]:
    return [_dto(r) for r in con.execute("SELECT * FROM life_files WHERE event_id=? ORDER BY id", (event_id,)).fetchall()]


def readable(user_id: int, file_id: int):
    """A file the person may see: their own, or on an entry shared with them."""
    with db.connect() as con:
        return con.execute("SELECT f.* FROM life_files f JOIN life_events e ON e.id = f.event_id"
                           " WHERE f.id = ? AND (f.user_id = ? OR e.shared = 1)", (file_id, user_id)).fetchone()


def path_of(row, size: str = "original") -> Path:
    where = folder(row["user_id"])
    return where / (f"{row['uid']}{row['ext']}" if size == "original" else f"{row['uid']}.{size}.jpg")


def _unlink(row) -> None:
    for size in SIZES:
        path_of(row, size).unlink(missing_ok=True)


def remove(user_id: int, file_id: int) -> None:
    with db.connect() as con:
        row = con.execute("SELECT * FROM life_files WHERE id=? AND user_id=?", (file_id, user_id)).fetchone()
        if row is None:
            raise LookupError("Findes ikke.")
        con.execute("DELETE FROM life_files WHERE id=?", (file_id,))
    _unlink(row)


def drop_with_events(con, events_sql: str, args: tuple) -> None:
    """The files of entries about to go: their rows go with the entries, their disk here."""
    for row in con.execute(f"SELECT * FROM life_files WHERE event_id IN ({events_sql})", args).fetchall():
        _unlink(row)


def on_user_deleted(user_id: int) -> None:
    shutil.rmtree(folder(user_id), ignore_errors=True)


def usage(user_id: int) -> dict:
    with db.connect() as con:
        row = con.execute("SELECT COUNT(*) AS n, COALESCE(SUM(bytes), 0) AS size FROM life_files WHERE user_id=?",
                          (user_id,)).fetchone()
    try:
        free = shutil.disk_usage(os.fspath(db.data_dir())).free
    except OSError:
        free = None
    return {"count": row["n"], "bytes": row["size"], "free": free}
