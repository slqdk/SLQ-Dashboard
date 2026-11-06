"""The rows of each person's Nordnet export, and what they add up to.

Importing again is safe: a row is known by Nordnet's own id.

What is held comes from the file's running total. The cost is Nordnet's own
purchase value on the rows that bring shares in, reduced in proportion on the rows
that take them out, as the average method does. It is left out for a position where
the rows do not add up: an export that starts after the first purchase, or shares
that arrived with no value. No number is better than a wrong one.
"""
from __future__ import annotations

from ...core import db, settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS nordnet_rows (
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    row_id          TEXT NOT NULL,
    booked          TEXT NOT NULL,
    traded          TEXT NOT NULL,
    depot           TEXT NOT NULL,
    kind            TEXT NOT NULL,
    security        TEXT NOT NULL,
    isin            TEXT NOT NULL,
    quantity        REAL,
    amount          REAL,
    currency        TEXT NOT NULL,
    cost            REAL,
    cost_currency   TEXT NOT NULL,
    result          REAL,
    result_currency TEXT NOT NULL,
    holding         REAL,
    cancelled       TEXT NOT NULL,
    imported_at     TEXT NOT NULL,
    PRIMARY KEY (user_id, row_id)
);
"""
FIELDS = ("booked", "traded", "depot", "kind", "security", "isin", "quantity", "amount", "currency",
          "cost", "cost_currency", "result", "result_currency", "holding", "cancelled")
DIVIDEND = "UDBYTTE"            # also UDBYTTESKAT, so the sum is after tax
TOLERANCE = 0.001               # the file rounds fractional units


def migrate_1(con) -> None:
    con.executescript(SCHEMA)


def ingest(user_id: int, rows: list[dict]) -> dict:
    counts = {"added": 0, "updated": 0, "same": 0}
    now = db.utcnow()
    with db.connect() as con:
        for row in rows:
            values = tuple(row[f] for f in FIELDS)
            old = con.execute(f"SELECT {', '.join(FIELDS)} FROM nordnet_rows WHERE user_id=? AND row_id=?",
                              (user_id, row["row_id"])).fetchone()
            if old is None:
                marks = ", ".join("?" * (len(FIELDS) + 3))
                con.execute(f"INSERT INTO nordnet_rows (user_id, row_id, {', '.join(FIELDS)}, imported_at) "
                            f"VALUES ({marks})", (user_id, row["row_id"], *values, now))
                counts["added"] += 1
            elif tuple(old) == values:
                counts["same"] += 1
            else:
                changes = ", ".join(f"{f}=?" for f in FIELDS)
                con.execute(f"UPDATE nordnet_rows SET {changes} WHERE user_id=? AND row_id=?",
                            (*values, user_id, row["row_id"]))
                counts["updated"] += 1
        con.execute("UPDATE nordnet_rows SET imported_at=? WHERE user_id=?", (now, user_id))
    return counts


def clear(user_id: int) -> None:
    with db.connect() as con:
        con.execute("DELETE FROM nordnet_rows WHERE user_id=?", (user_id,))


def _ordered(user_id: int) -> list:
    with db.connect() as con:
        return con.execute("SELECT * FROM nordnet_rows WHERE user_id=? AND cancelled='' "
                           "ORDER BY booked, CAST(row_id AS INTEGER), row_id", (user_id,)).fetchall()


def _apply(position: dict, row) -> None:
    held, now = position["quantity"], row["holding"]
    if DIVIDEND in row["kind"] or now is None:      # a dividend row's total is 0
        return
    position["quantity"] = now
    change = now - held
    if now < TOLERANCE:
        position.update(cost=0.0, currency="", known=True)      # a new purchase starts clean
    elif abs(change) < TOLERANCE:
        return
    elif row["quantity"] is None or abs(row["quantity"] - abs(change)) > TOLERANCE:
        position["known"] = False                   # the rows before this one are not in the file
    elif change < 0:
        position["cost"] *= now / held
    elif row["cost"] is None or position["currency"] not in ("", row["cost_currency"]):
        position["known"] = False                   # arrived with no value
    else:
        position["cost"] += row["cost"]
        position["currency"] = row["cost_currency"]


def positions(user_id: int) -> list[dict]:
    found: dict[tuple[str, str], dict] = {}
    for row in _ordered(user_id):
        if not row["isin"]:
            continue
        key = (row["depot"], row["isin"])
        position = found.setdefault(key, {"depot": row["depot"], "isin": row["isin"], "name": row["security"],
                                          "quantity": 0.0, "cost": 0.0, "currency": "", "known": True})
        position["name"] = row["security"] or position["name"]
        _apply(position, row)
    held = [p for p in found.values() if p["quantity"] >= TOLERANCE]
    return sorted(({"name": p["name"], "isin": p["isin"], "depot": p["depot"], "quantity": p["quantity"],
                    "cost": round(p["cost"], 2) if p["known"] else None,
                    "currency": p["currency"] if p["known"] else ""} for p in held),
                  key=lambda p: p["name"].lower())


def years(user_id: int) -> list[dict]:
    """Dividends after tax and realised result, per year and currency."""
    found: dict[tuple[str, str], dict] = {}

    def line(year: str, currency: str) -> dict:
        return found.setdefault((year, currency), {"year": year, "currency": currency, "dividends": 0.0, "result": 0.0})

    for row in _ordered(user_id):
        year = row["traded"][:4]
        if DIVIDEND in row["kind"] and row["amount"] is not None:
            line(year, row["currency"])["dividends"] += row["amount"]
        if row["result"] is not None:
            line(year, row["result_currency"])["result"] += row["result"]
    return [{**v, "dividends": round(v["dividends"], 2), "result": round(v["result"], 2)}
            for _key, v in sorted(found.items(), reverse=True)]


def _mode() -> str:
    return settings.load().get("nordnetMode") or "off"


def state(user_id: int) -> dict:
    with db.connect() as con:
        r = con.execute("SELECT COUNT(*) AS rows, MIN(booked) AS first, MAX(booked) AS last, "
                        "MAX(imported_at) AS imported FROM nordnet_rows WHERE user_id=?", (user_id,)).fetchone()
    return {"mode": _mode(), "rows": r["rows"], "first": r["first"], "last": r["last"], "importedAt": r["imported"],
            "positions": positions(user_id), "years": years(user_id)}


def overview(me: dict) -> dict:
    with db.connect() as con:
        imported = con.execute("SELECT MAX(imported_at) AS at FROM nordnet_rows WHERE user_id=?",
                               (me["id"],)).fetchone()["at"]
    return {"mode": _mode(), "positions": len(positions(me["id"])), "importedAt": imported}


def setup_status() -> dict:
    mode = _mode()
    if mode == "off":
        return {"ok": False, "text": "Ikke forbundet."}
    if mode == "api":
        return {"ok": False, "text": "Forbindelsen til API'et er ikke bygget."}
    with db.connect() as con:
        people = con.execute("SELECT COUNT(DISTINCT user_id) AS n FROM nordnet_rows").fetchone()["n"]
    return {"ok": True, "text": f"Importeres på siden Aktier. {people} har importeret."}
