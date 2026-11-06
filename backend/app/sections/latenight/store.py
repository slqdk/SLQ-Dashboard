"""The late-night facts. seed.json is the checked starting set; every fact has
a source. New seed lines are added on start, existing ones are left alone, so
an edit made in the app is never overwritten."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from ...core import db, settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS dl_facts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    seed_key    TEXT UNIQUE,                 -- NULL for facts added in the app
    date        TEXT NOT NULL,               -- YYYY-MM-DD
    title       TEXT NOT NULL,
    body        TEXT NOT NULL DEFAULT '',
    kind        TEXT NOT NULL DEFAULT 'historie',   -- show | gæst | historie
    hosts       TEXT NOT NULL DEFAULT '',    -- comma-separated
    story       TEXT NOT NULL DEFAULT '',    -- arvefoelgen | 2010 | ...
    source_url  TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS dl_facts_mmdd ON dl_facts (substr(date, 6));
"""

SEED = Path(__file__).with_name("seed.json")
KINDS = ("show", "gæst", "historie")
STORIES = {"arvefoelgen": "Kampen om Carsons stol, 1991–93",
           "2010": "Tonight Show-konflikten, 2009–10",
           "1990erne": "Late night i 90'erne"}
NEAR_DAYS = 7


def migrate_1(con) -> None:
    con.executescript(SCHEMA)


class Problem(ValueError):
    """Input that cannot be stored; the text is shown to the person."""


def load_seed() -> int:
    facts = json.loads(SEED.read_text(encoding="utf-8"))
    sources = facts["sources"]
    added = 0
    now = db.utcnow()
    with db.connect() as con:
        for f in facts["facts"]:
            key = f"{f['d']}:{f['t'][:40]}"
            cur = con.execute(
                "INSERT OR IGNORE INTO dl_facts (seed_key, date, title, body, kind, hosts, story,"
                " source_url, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (key, f["d"], f["t"], f.get("b", ""), f.get("k", "historie"),
                 ",".join(f.get("h", [])), f.get("st", ""), sources[f["s"]], now))
            added += cur.rowcount
    return added


def _dto(r, year: int | None = None) -> dict:
    return {"id": r["id"], "date": r["date"], "title": r["title"], "body": r["body"],
            "kind": r["kind"], "hosts": [h for h in r["hosts"].split(",") if h],
            "story": r["story"], "sourceUrl": r["source_url"],
            "yearsAgo": (year - int(r["date"][:4])) if year else None}


def today() -> date:
    return datetime.now(settings.tz()).date()


def on_date(day: date | None = None) -> dict:
    """Exactly this date; when nothing happened on it, the nearest in the week
    around it, so the page always has something to say."""
    day = day or today()
    with db.connect() as con:
        exact = con.execute("SELECT * FROM dl_facts WHERE substr(date, 6) = ? AND date <= ?"
                            " ORDER BY date DESC", (day.isoformat()[5:], day.isoformat())).fetchall()
        near: list = []
        if not exact:
            for offset in range(1, NEAR_DAYS + 1):
                for sign in (1, -1):
                    other = (day + timedelta(days=offset * sign)).isoformat()[5:]
                    near += con.execute(
                        "SELECT * FROM dl_facts WHERE substr(date, 6) = ? AND date <= ?"
                        " ORDER BY date DESC", (other, day.isoformat())).fetchall()
                if near:
                    break
    return {"date": day.isoformat(), "exact": [_dto(r, day.year) for r in exact],
            "near": [_dto(r, day.year) for r in near[:3]]}


def facts(q: str = "", host: str = "", story: str = "", kind: str = "", decade: str = "") -> list[dict]:
    sql = "SELECT * FROM dl_facts WHERE 1=1"
    args: list = []
    if q.strip():
        like = f"%{q.strip()}%"
        sql += " AND (title LIKE ? OR body LIKE ? OR hosts LIKE ?)"
        args += [like, like, like]
    if host:
        sql += " AND (',' || hosts || ',') LIKE ?"
        args.append(f"%,{host},%")
    if story:
        sql += " AND story = ?"
        args.append(story)
    if kind:
        sql += " AND kind = ?"
        args.append(kind)
    if decade:
        sql += " AND substr(date, 1, 3) = ?"
        args.append(decade[:3])
    sql += " ORDER BY date LIMIT 2000"
    year = today().year
    with db.connect() as con:
        return [_dto(r, year) for r in con.execute(sql, args).fetchall()]


def meta() -> dict:
    with db.connect() as con:
        hosts: dict[str, int] = {}
        for r in con.execute("SELECT hosts FROM dl_facts").fetchall():
            for h in filter(None, r["hosts"].split(",")):
                hosts[h] = hosts.get(h, 0) + 1
        total = con.execute("SELECT COUNT(*) FROM dl_facts").fetchone()[0]
    return {"total": total, "stories": STORIES, "kinds": KINDS,
            "hosts": sorted(hosts, key=lambda h: -hosts[h])}


def _clean(body: dict) -> tuple:
    title = " ".join(str(body.get("title") or "").split())[:240]
    if not title:
        raise Problem("Skriv hvad der skete.")
    try:
        when = date.fromisoformat(str(body.get("date") or "")).isoformat()
    except ValueError:
        raise Problem("Vælg datoen.") from None
    kind = body.get("kind") or "historie"
    if kind not in KINDS:
        raise Problem("Ukendt type.")
    story = body.get("story") or ""
    if story and story not in STORIES:
        raise Problem("Ukendt historie.")
    hosts = ",".join(h.strip() for h in body.get("hosts") or [] if h.strip())
    source = str(body.get("sourceUrl") or "").strip()[:500]
    if source and not source.startswith(("http://", "https://")):
        raise Problem("Kilden skal være en http- eller https-adresse.")
    return (when, title, str(body.get("body") or "")[:2000], kind, hosts, story, source)


def add(body: dict) -> dict:
    values = _clean(body)
    with db.connect() as con:
        cur = con.execute(
            "INSERT INTO dl_facts (date, title, body, kind, hosts, story, source_url, created_at)"
            " VALUES (?,?,?,?,?,?,?,?)", (*values, db.utcnow()))
        row = con.execute("SELECT * FROM dl_facts WHERE id=?", (cur.lastrowid,)).fetchone()
    return _dto(row, today().year)


def update(fact_id: int, body: dict) -> dict:
    values = _clean(body)
    with db.connect() as con:
        cur = con.execute(
            "UPDATE dl_facts SET date=?, title=?, body=?, kind=?, hosts=?, story=?, source_url=?"
            " WHERE id=?", (*values, fact_id))
        if cur.rowcount == 0:
            raise LookupError("Findes ikke.")
        row = con.execute("SELECT * FROM dl_facts WHERE id=?", (fact_id,)).fetchone()
    return _dto(row, today().year)


def delete(fact_id: int) -> None:
    with db.connect() as con:
        con.execute("DELETE FROM dl_facts WHERE id=?", (fact_id,))


def overview(_me: dict) -> dict:
    from . import monologues
    return {**on_date(), "total": meta()["total"], "monologues": monologues.newest(3)}
