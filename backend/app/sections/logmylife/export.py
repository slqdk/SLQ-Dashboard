"""Getting a person's log out: everything in one zip with the pictures, or the entries
alone as JSON, as CSV for Excel, or as a calendar file. Only the person's own entries, and
nothing here writes anywhere: the file goes to the browser."""
from __future__ import annotations

import csv
import html
import io
import json
import re
import zipfile
from collections import deque
from datetime import date, datetime, timedelta
from typing import Iterator

from ...core import db
from . import files

CHUNK = 1024 * 1024
# Already packed: squeezing them again costs time and saves nothing.
PACKED = re.compile(r"^(image|video|audio)/|zip|gzip|pdf")


def entries(user_id: int, *, since: str = "", until: str = "", q: str = "", source: str = "") -> list[dict]:
    sql = "SELECT * FROM life_events WHERE user_id = ?"
    args: list = [user_id]
    if since:
        sql += " AND day >= ?"
        args.append(since)
    if until:
        sql += " AND day <= ?"
        args.append(until)
    if q.strip():
        like = f"%{q.strip()}%"
        sql += " AND (title LIKE ? OR description LIKE ? OR location LIKE ?)"
        args += [like, like, like]
    if source:
        sql += " AND source = ?"
        args.append(source)
    with db.connect() as con:
        rows = con.execute(sql + " ORDER BY day, start_at, id", args).fetchall()
        attached: dict[int, list] = {}
        for f in con.execute("SELECT * FROM life_files WHERE user_id = ? ORDER BY id", (user_id,)).fetchall():
            attached.setdefault(f["event_id"], []).append(f)
    out = []
    for r in rows:
        raw = None
        if r["raw"]:
            try:
                raw = json.loads(r["raw"])
            except ValueError:
                raw = r["raw"]
        out.append({"uid": r["uid"], "source": r["source"], "title": r["title"], "description": r["description"],
                    "category": r["category"], "start": r["start_at"], "end": r["end_at"], "allDay": bool(r["all_day"]),
                    "day": r["day"], "location": r["location"], "lat": r["lat"], "lng": r["lng"], "shared": bool(r["shared"]),
                    "deletedAtSource": r["deleted_at_source"], "createdAt": r["created_at"], "updatedAt": r["updated_at"],
                    "raw": raw, "_files": attached.get(r["id"], [])})
    return out


def zip_path(entry: dict, f) -> str:
    """A name that sorts by date, and that nothing in the upload can steer out of the folder."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", f["name"]).strip(". ") or "fil"
    return f"files/{entry['day'][:4]}/{entry['day']}-{f['uid'][:8]}-{name}"


def _public(entry: dict) -> dict:
    out = {k: v for k, v in entry.items() if not k.startswith("_")}
    out["files"] = [{"path": zip_path(entry, f), "name": f["name"], "kind": f["kind"], "mime": f["mime"], "bytes": f["bytes"],
                     "width": f["width"], "height": f["height"], "taken": f["taken_at"]} for f in entry["_files"]]
    return out


def as_json(rows: list[dict]) -> str:
    return json.dumps({"app": "SLQ Dashboard", "section": "LogMyLife", "entries": [_public(e) for e in rows]},
                      ensure_ascii=False, indent=2)


def _cell(value) -> str:
    """Excel runs a cell that starts like a formula, and titles come from other people too."""
    text = "" if value is None else str(value)
    return f"'{text}" if text[:1] in ("=", "+", "-", "@") else text


def as_csv(rows: list[dict]) -> str:
    """Semicolons and a BOM: what a Danish Excel opens as columns, with æøå intact."""
    out = io.StringIO()
    out.write("\ufeff")
    writer = csv.writer(out, delimiter=";", lineterminator="\r\n")
    writer.writerow(["Dato", "Til og med", "Heldags", "Titel", "Tekst", "Sted", "Kategori", "Kilde", "Delt", "Slettet i kilden", "Filer"])
    for e in rows:
        writer.writerow([e["day"], (e["end"] or "")[:10], "ja" if e["allDay"] else "nej", _cell(e["title"]), _cell(e["description"]),
                         _cell(e["location"]), e["category"], e["source"], "ja" if e["shared"] else "nej",
                         "ja" if e["deletedAtSource"] else "nej", " ".join(zip_path(e, f) for f in e["_files"])])
    return out.getvalue()


def _ics_text(text: str) -> str:
    for char, escaped in (("\\", "\\\\"), (";", "\\;"), (",", "\\,"), ("\n", "\\n")):
        text = text.replace(char, escaped)
    return text


def _fold(line: str) -> str:
    """Lines of at most 75 bytes, continued with a space, as the format wants."""
    data, out, part = line.encode("utf-8"), [], b""
    for char in line:
        piece = char.encode("utf-8")
        if len(part) + len(piece) > 74:
            out.append(part.decode("utf-8"))
            part = b" "
        part += piece
    out.append(part.decode("utf-8"))
    return "\r\n".join(out) if len(data) > 74 else line


def _ics_time(value: str, all_day: bool, after: int = 0) -> str:
    if all_day:
        day = date.fromisoformat(value[:10]) + timedelta(days=after)
        return f";VALUE=DATE:{day:%Y%m%d}"
    return f":{datetime.fromisoformat(value.replace('Z', '+00:00')):%Y%m%dT%H%M%SZ}"


def as_ics(rows: list[dict]) -> str:
    stamp = f"{datetime.fromisoformat(db.utcnow()):%Y%m%dT%H%M%SZ}"
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//SLQ Dashboard//LogMyLife//DA", "CALSCALE:GREGORIAN"]
    for e in rows:
        lines += ["BEGIN:VEVENT", f"UID:{e['uid']}@slq-dashboard", f"DTSTAMP:{stamp}", f"DTSTART{_ics_time(e['start'], e['allDay'])}"]
        if e["end"]:
            lines.append(f"DTEND{_ics_time(e['end'], e['allDay'], 1 if e['allDay'] else 0)}")   # the format's end is exclusive
        lines.append(f"SUMMARY:{_ics_text(e['title'])}")
        if e["description"]:
            lines.append(f"DESCRIPTION:{_ics_text(e['description'])}")
        if e["location"]:
            lines.append(f"LOCATION:{_ics_text(e['location'])}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


PAGE = """<!doctype html>
<html lang="da"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>LogMyLife</title>
<style>
body {{ max-width: 860px; margin: 0 auto; padding: 24px 16px 64px; font: 16px/1.5 'Segoe UI', system-ui, sans-serif; color: #1c2730; }}
h1 {{ margin-bottom: 0; }} h2 {{ margin: 32px 0 4px; border-bottom: 1px solid #c6d3da; }}
article {{ padding: 10px 0; border-bottom: 1px solid #e4eaee; }} time, .meta {{ color: #5a6b76; font-size: 14px; }}
h3 {{ margin: 0; font-size: 17px; }} p {{ margin: 4px 0; white-space: pre-wrap; }}
.files {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 6px; }} .files img {{ height: 160px; border-radius: 4px; }}
</style></head><body><h1>LogMyLife</h1><p class="meta">{count} indlæg, hentet {today}.</p>
{body}</body></html>
"""


def as_html(rows: list[dict]) -> str:
    """A page that reads on its own, in ten years too, with the files beside it."""
    parts: list[str] = []
    year = ""
    for e in rows:
        if e["day"][:4] != year:
            year = e["day"][:4]
            parts.append(f"<h2>{year}</h2>")
        shown = []
        for f in e["_files"]:
            href = html.escape(zip_path(e, f), quote=True)
            shown.append(f'<a href="{href}"><img src="{href}" alt="" loading="lazy"></a>' if f["kind"] == "image"
                         else f'<a href="{href}">{html.escape(f["name"])}</a>')
        meta = ", ".join(x for x in (e["location"], e["category"]) if x)
        parts.append(f'<article><time>{e["day"]}</time><h3>{html.escape(e["title"])}</h3>'
                     + (f'<p>{html.escape(e["description"])}</p>' if e["description"] else "")
                     + (f'<p class="meta">{html.escape(meta)}</p>' if meta else "")
                     + (f'<div class="files">{"".join(shown)}</div>' if shown else "") + "</article>")
    return PAGE.format(count=len(rows), today=date.today().isoformat(), body="\n".join(parts))


class _Pipe(io.RawIOBase):
    """What zipfile writes, handed on piece by piece: a zip of many gigabytes must not
    be built in memory or on a disk that is full of the same pictures."""

    def __init__(self):
        super().__init__()
        self.pieces: deque[bytes] = deque()

    def writable(self) -> bool:
        return True

    def write(self, data) -> int:
        self.pieces.append(bytes(data))
        return len(data)

    def drain(self) -> Iterator[bytes]:
        while self.pieces:
            yield self.pieces.popleft()


def as_zip(rows: list[dict]) -> Iterator[bytes]:
    pipe = _Pipe()
    with zipfile.ZipFile(pipe, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
        for name, text in (("index.html", as_html(rows)), ("entries.json", as_json(rows)), ("entries.csv", as_csv(rows)),
                           ("entries.ics", as_ics(rows))):
            archive.writestr(name, text)
            yield from pipe.drain()
        for e in rows:
            for f in e["_files"]:
                path = files.path_of(f)
                if not path.exists():
                    continue
                info = zipfile.ZipInfo(zip_path(e, f), date_time=datetime.fromisoformat(f["created_at"]).timetuple()[:6])
                info.compress_type = zipfile.ZIP_STORED if PACKED.search(f["mime"]) else zipfile.ZIP_DEFLATED
                with path.open("rb") as source, archive.open(info, "w", force_zip64=True) as target:
                    while chunk := source.read(CHUNK):
                        target.write(chunk)
                        yield from pipe.drain()
                yield from pipe.drain()
    yield from pipe.drain()
