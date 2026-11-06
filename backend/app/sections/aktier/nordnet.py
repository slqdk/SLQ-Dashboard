"""Reads Nordnet's "transactions and notes" export.

The file, as checked against a real one: UTF-16 with a BOM, tab separated, decimal
commas and ISO dates. `Antal` has no sign, a sale is as positive as a purchase, and
`Totalt antal` is the total held after the row, except on dividend rows, where it
is 0. Amounts are in `Beløb`'s currency, costs and results in the security's own.
Each of those columns has its currency in a `Valuta` column right after it.

A security with no row in the chosen period is not in the file, which is why the
page asks for the whole period.

Nothing from the rows may reach a log or an error text: a wrong file is described
by its column names only. Of the depot number, only the last four digits are kept,
which is enough to tell depots apart.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import datetime

MAX_BYTES = 10_000_000
COLUMNS = {"id": "Id", "booked": "Bogføringsdag", "traded": "Handelsdag", "depot": "Depot",
           "kind": "Transaktionstype", "security": "Værdipapirer", "isin": "ISIN", "quantity": "Antal",
           "amount": "Beløb", "cost": "Indkøbsværdi", "result": "Resultat", "holding": "Totalt antal",
           "cancelled": "Makuleringsdato"}
REQUIRED = ("id", "booked", "kind", "security", "isin", "quantity", "amount", "cost", "holding")
DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%Y")
SPACES = re.compile(r"[\s  ]")


class Problem(ValueError):
    """A file that cannot be read; the text is shown to the person."""


def _decode(data: bytes) -> str:
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16")
    if b"\x00" in data[:200]:
        return data.decode("utf-16-le", errors="replace")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def _rows(text: str) -> list[list[str]]:
    first = text.split("\n", 1)[0]
    delimiter = max("\t;,", key=first.count)
    return [[cell.strip() for cell in row] for row in csv.reader(io.StringIO(text), delimiter=delimiter) if any(row)]


def _number(text: str, mark: str) -> float | None:
    clean = SPACES.sub("", text).replace("−", "-")
    try:
        return float(clean.replace("." if mark == "," else ",", "").replace(mark, ".")) if clean else None
    except ValueError:
        return None


def _day(text: str) -> str:
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text[:10], fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def _mark(rows: list[list[str]], columns: list[int]) -> str:
    """The decimal mark: a comma in any amount settles it."""
    for row in rows:
        if any(i < len(row) and re.search(r",\d+$", row[i]) for i in columns):
            return ","
    return "."


def parse(data: bytes) -> tuple[list[dict], int]:
    """Returns the rows and how many could not be read."""
    rows = _rows(_decode(data))
    if not rows:
        raise Problem("Filen er tom.")
    header = rows[0]
    at = {key: header.index(name) for key, name in COLUMNS.items() if name in header}
    missing = [COLUMNS[key] for key in REQUIRED if key not in at]
    if missing:
        raise Problem(f"Det ligner ikke Nordnets transaktioner. Filen mangler: {', '.join(missing)}. "
                      f"Den har: {', '.join(header[:12])}.")

    def currency_of(name: str) -> int | None:
        # Several columns are called Valuta; each belongs to the amount before it.
        i = at.get(name)
        return i + 1 if i is not None and i + 1 < len(header) and header[i + 1] == "Valuta" else None

    amount_currency, cost_currency = currency_of("amount"), currency_of("cost")
    result_currency = currency_of("result")
    numbers = [at[key] for key in ("quantity", "amount", "cost", "result", "holding") if key in at]
    mark = _mark(rows[1:], numbers)
    out: list[dict] = []
    skipped = 0

    for row in rows[1:]:
        cell = lambda key: row[at[key]] if key in at and at[key] < len(row) else ""
        at_index = lambda i: row[i] if i is not None and i < len(row) else ""
        booked = _day(cell("booked"))
        if not cell("id") or not booked:
            skipped += 1
            continue
        out.append({
            "row_id": cell("id"), "booked": booked, "traded": _day(cell("traded")) or booked,
            "depot": cell("depot")[-4:], "kind": cell("kind").upper(), "security": cell("security"),
            "isin": cell("isin"), "quantity": _number(cell("quantity"), mark),
            "amount": _number(cell("amount"), mark), "currency": at_index(amount_currency),
            "cost": _number(cell("cost"), mark), "cost_currency": at_index(cost_currency),
            "result": _number(cell("result"), mark), "result_currency": at_index(result_currency),
            "holding": _number(cell("holding"), mark), "cancelled": cell("cancelled"),
        })
    return out, skipped
