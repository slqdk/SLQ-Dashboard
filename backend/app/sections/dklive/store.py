"""What is slow to get and worth keeping across restarts: airports, fire stations and
the places found for them."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from ...core import db

SCHEMA = """
CREATE TABLE IF NOT EXISTS live_cache (
    name     TEXT PRIMARY KEY,
    data     TEXT NOT NULL,
    saved_at TEXT NOT NULL
);
"""


def migrate_1(con) -> None:
    con.executescript(SCHEMA)


def load(name: str, default=None):
    with db.connect() as con:
        row = con.execute("SELECT data FROM live_cache WHERE name=?", (name,)).fetchone()
    return json.loads(row["data"]) if row else default


def save(name: str, value) -> None:
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with db.connect() as con:
        con.execute("INSERT INTO live_cache (name, data, saved_at) VALUES (?, ?, ?) "
                    "ON CONFLICT(name) DO UPDATE SET data=excluded.data, saved_at=excluded.saved_at",
                    (name, json.dumps(value, ensure_ascii=False, separators=(",", ":")), stamp))
