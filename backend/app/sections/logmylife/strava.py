"""Strava's own export onto the timeline.

The person asks Strava for their data (strava.com → Settings → My Account →
Download your account) and gets a zip with activities.csv. Importing that needs
no subscription and no API app, and running it again only adds what is new.

The file's headers follow the language of the Strava account, so it has to be
exported in English. The dates are read as UTC.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone

from . import store

SOURCE = "strava"
MAX_BYTES = 30_000_000
ID, DATE, NAME, KIND = "Activity ID", "Activity Date", "Activity Name", "Activity Type"
DESCRIPTION, ELAPSED, DISTANCE = "Activity Description", "Elapsed Time", "Distance"
FORMATS = ("%b %d, %Y, %I:%M:%S %p", "%b %d, %Y, %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S")
KINDS = {"Run": "Løb", "Ride": "Cykeltur", "Walk": "Gåtur", "Hike": "Vandretur", "Swim": "Svømning",
         "Workout": "Træning", "Weight Training": "Styrketræning", "Virtual Ride": "Cykling indendørs",
         "Virtual Run": "Løb indendørs", "Rowing": "Roning", "Yoga": "Yoga"}


class Problem(ValueError):
    """A file that cannot be read; the text is shown to the person."""


def _when(text: str) -> datetime | None:
    clean = " ".join(text.replace(" ", " ").split())
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
    """(activities, rows that could not be read). Elapsed Time and Distance
    each appear twice in the file; the first of each is the one in seconds
    and kilometres."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise Problem("Det ligner ikke activities.csv. Pak zip-filen ud, og vælg filen fra den.") from None
    reader = csv.reader(io.StringIO(text))
    header = next(reader, [])
    column = {}
    for index, name in enumerate(header):
        column.setdefault(name.strip(), index)
    if any(name not in column for name in (ID, DATE, NAME, KIND)):
        raise Problem("Filen har ikke Stravas kolonner på engelsk. "
                      "Sæt sproget på Strava til English, og bestil eksporten igen.")
    get = lambda row, name: row[column[name]].strip() if name in column and column[name] < len(row) else ""
    out, bad = [], 0
    for row in reader:
        if not row:
            continue
        when = _when(get(row, DATE))
        if not get(row, ID) or when is None:
            bad += 1
            continue
        out.append({"id": get(row, ID), "start": when, "name": get(row, NAME), "kind": get(row, KIND),
                    "text": get(row, DESCRIPTION), "seconds": _number(get(row, ELAPSED)),
                    "km": _number(get(row, DISTANCE))})
    return out, bad


def import_csv(user_id: int, data: bytes) -> dict:
    activities, bad = parse(data)
    if not activities and not bad:
        raise Problem("Filen har ingen aktiviteter.")
    counts = {"added": 0, "updated": 0, "same": 0}
    for a in activities:
        end = a["start"] + timedelta(seconds=a["seconds"]) if a["seconds"] else None
        about = summary(a["kind"], a["km"], a["seconds"])
        counts[store.ingest(
            user_id, SOURCE, a["id"], title=a["name"] or about or "Aktivitet",
            start=a["start"].isoformat(), end=end.isoformat() if end else None,
            description="\n".join(x for x in (about, a["text"]) if x), category="Fritid",
            raw={"type": a["kind"], "km": a["km"], "seconds": a["seconds"]})] += 1
    return {**counts, "skipped": bad}
