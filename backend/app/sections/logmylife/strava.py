"""Strava's own export onto the timeline.

The person asks Strava for their data (strava.com → Settings → My Account → Download
your account) and gets a zip. Importing it needs no subscription and no API app, and
running it again only adds what is new. Out of the zip come activities.csv and the
pictures and tracks its rows name, and nothing else: the rest is the person's followers,
logins and messages, which have no place here.

The file's headers and dates follow the language of the Strava account; English and
Danish are known. The dates are UTC in both: a track starts on the second its row says.
"""
from __future__ import annotations

import csv
import io
import re
import shutil
import zipfile
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import files, store

SOURCE = "strava"
CSV = "activities.csv"
MAX_BYTES = 30_000_000              # of activities.csv; the zip may be as big as any file
COLUMNS = {"id": ("Activity ID", "Aktivitets-id"), "date": ("Activity Date", "Aktivitetsdato"),
           "name": ("Activity Name", "Aktivitetsnavn"), "kind": ("Activity Type", "Aktivitetstype"),
           "text": ("Activity Description", "Beskrivelse af aktiviteten"),
           "seconds": ("Elapsed Time", "Varighed"), "distance": ("Distance",),
           "track": ("Filename", "Filnavn"), "media": ("Media", "Medier")}
REQUIRED = ("id", "date", "name", "kind")
FORMATS = ("%b %d, %Y, %I:%M:%S %p", "%b %d, %Y, %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S")
MONTHS = "jan feb mar apr maj jun jul aug sep okt nov dec".split()
DANISH = re.compile(r"(\d{1,2})\. (\w{3})\.? (\d{4}), (\d{1,2})[.:](\d{2})[.:](\d{2})")
KINDS = {"Run": "Løb", "Ride": "Cykeltur", "Walk": "Gåtur", "Hike": "Vandring", "Swim": "Svømning",
         "Workout": "Træning", "Weight Training": "Styrketræning", "Virtual Ride": "Virtuel cykeltur",
         "Virtual Run": "Virtuelt løb", "Rowing": "Roning", "Yoga": "Yoga"}


class Problem(ValueError):
    """A file that cannot be read; the text is shown to the person."""


def _when(text: str) -> datetime | None:
    clean = " ".join(text.replace("\u202f", " ").split())
    danish = DANISH.fullmatch(clean)
    if danish:
        day, month, year, *clock = danish.groups()
        try:
            return datetime(int(year), MONTHS.index(month.lower()) + 1, int(day), *map(int, clock), tzinfo=timezone.utc)
        except ValueError:
            return None
    for fmt in FORMATS:
        try:
            return datetime.strptime(clean, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _number(text: str) -> float | None:
    try:
        return float(text.replace(",", "."))
    except (TypeError, ValueError):
        return None


def _duration(seconds: float) -> str:
    minutes = round(seconds / 60)
    return f"{minutes // 60} t {minutes % 60} min" if minutes >= 60 else f"{minutes} min"


def summary(kind: str, km: float | None, seconds: float | None) -> str:
    parts = [KINDS.get(kind, kind)] if kind else []
    if km:
        parts.append(f"{km:.1f} km".replace(".", ","))
    if seconds:
        parts.append(_duration(seconds))
    return ", ".join(parts)


def parse(data: bytes) -> tuple[list[dict], int]:
    """(activities, rows that could not be read). Elapsed Time and Distance each appear
    twice. The first Distance is in kilometres, but in metres for a swim, and the second
    always in metres, so that is the one to read."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise Problem("Det ligner hverken Stravas zip-fil eller activities.csv.") from None
    reader = csv.reader(io.StringIO(text))
    header = [name.strip() for name in next(reader, [])]
    places: dict[str, list[int]] = {}
    for index, name in enumerate(header):
        places.setdefault(name, []).append(index)
    where = {key: next((places[name] for name in names if name in places), []) for key, names in COLUMNS.items()}
    if not all(where[key] for key in REQUIRED):
        raise Problem("Filen har ikke Stravas kolonner. Sæt sproget på Strava til dansk eller English, "
                      "og bestil eksporten igen.")

    def get(row: list[str], key: str, twin: int = 0) -> str:
        at = where[key]
        return row[at[twin]].strip() if twin < len(at) and at[twin] < len(row) else ""

    out, bad = [], 0
    for row in reader:
        if not row:
            continue
        when = _when(get(row, "date"))
        if not get(row, "id") or when is None:
            bad += 1
            continue
        metres = _number(get(row, "distance", 1))
        out.append({"id": get(row, "id"), "start": when, "name": get(row, "name"), "kind": get(row, "kind"),
                    "text": get(row, "text"), "seconds": _number(get(row, "seconds")),
                    "km": metres / 1000 if metres else _number(get(row, "distance")),
                    "files": [f for f in (get(row, "track"), *get(row, "media").split("|")) if f.strip()],
                    "columns": {name: value.strip() for name, value in zip(header, row) if name and value.strip()}})
    return out, bad


def _attach(user_id: int, event_id: int, archive: zipfile.ZipFile, member: str) -> bool:
    """One file the row names, onto its entry, once."""
    try:
        info = archive.getinfo(member)
    except KeyError:
        return False
    if info.is_dir() or info.file_size > files.MAX_BYTES or files.has(event_id, member):
        return False
    temporary = files.scratch(user_id)
    try:
        with archive.open(info) as source, temporary.open("wb") as out:
            shutil.copyfileobj(source, out)
    except (zipfile.BadZipFile, zlib.error, EOFError, OSError, RuntimeError):
        temporary.unlink(missing_ok=True)
        return False
    files.add(user_id, event_id, member, temporary)
    return True


def _ingest(user_id: int, activities: list[dict], bad: int, archive: zipfile.ZipFile | None = None) -> dict:
    if not activities and not bad:
        raise Problem("Filen har ingen aktiviteter.")
    counts = {"added": 0, "updated": 0, "same": 0}
    attached = 0
    for a in activities:
        end = a["start"] + timedelta(seconds=a["seconds"]) if a["seconds"] else None
        about = summary(a["kind"], a["km"], a["seconds"])
        counts[store.ingest(
            user_id, SOURCE, a["id"], title=a["name"] or about or "Aktivitet",
            start=a["start"].isoformat(), end=end.isoformat() if end else None,
            description="\n".join(x for x in (about, a["text"]) if x), category="Fritid",
            raw={"type": a["kind"], "km": a["km"], "seconds": a["seconds"], "columns": a["columns"]})] += 1
        if archive is not None:
            event_id = store.event_id(user_id, SOURCE, a["id"])
            attached += sum(_attach(user_id, event_id, archive, member) for member in a["files"])
    return {**counts, "skipped": bad, "files": attached}


def import_file(user_id: int, path: Path) -> dict:
    """Strava's zip as it came, or only the activities.csv from it."""
    with path.open("rb") as start:
        zipped = start.read(4) == b"PK\x03\x04"
    if not zipped:
        if path.stat().st_size > MAX_BYTES:
            raise Problem("Filen er for stor til at være activities.csv.")
        return _ingest(user_id, *parse(path.read_bytes()))
    try:
        with zipfile.ZipFile(path) as archive:
            try:
                info = archive.getinfo(CSV)
            except KeyError:
                raise Problem("Der er ingen activities.csv i zip-filen.") from None
            if info.file_size > MAX_BYTES:
                raise Problem("Der er for mange aktiviteter i zip-filen.")
            return _ingest(user_id, *parse(archive.read(info)), archive)
    except (zipfile.BadZipFile, zlib.error, EOFError):
        raise Problem("Det ligner en zip-fil, men den kan ikke læses. Hent den igen fra Strava.") from None
