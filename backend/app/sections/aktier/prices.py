"""Prices for what people hold, one close a day, from Yahoo Finance.

It needs no key, but it is not an official API, so it can change without warning:
the last prices stay in the database and the page says when something is missing.
Yahoo finds a security by its ISIN. A fund has one price a day, which is why the
day is the resolution here. Of a security's listings, the one in the currency it was
bought in is used.

The week is what today's holdings did over the last seven days, so buying more on
Wednesday does not look like a gain. Nothing from Nordnet goes to Yahoo but the ISIN.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone

import httpx

from ...core import db, logs

SCHEMA = """
CREATE TABLE IF NOT EXISTS stock_symbols (
    isin       TEXT PRIMARY KEY,
    symbol     TEXT NOT NULL,                 -- empty: Yahoo does not know it
    currency   TEXT NOT NULL,
    checked_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS stock_prices (
    symbol TEXT NOT NULL,
    day    TEXT NOT NULL,
    close  REAL NOT NULL,
    PRIMARY KEY (symbol, day)
);
"""
UA = {"User-Agent": "Mozilla/5.0"}
TIMEOUT = 15.0
WEEK_DAYS = 7
KEEP_DAYS = 40
RETRY_UNKNOWN_DAYS = 1
CANDIDATES = 5
BASE = "DKK"

_status = {"found": 0, "wanted": 0}


def migrate_2(con) -> None:
    con.executescript(SCHEMA)


def reset() -> None:
    _status.update(found=0, wanted=0)


def _search_url() -> str:
    return os.environ.get("APP_YAHOO_SEARCH_URL", "https://query1.finance.yahoo.com/v1/finance/search")


def _chart_url() -> str:
    return os.environ.get("APP_YAHOO_CHART_URL", "https://query2.finance.yahoo.com/v8/finance/chart")


def _get(url: str, params: dict) -> dict:
    r = httpx.get(url, params=params, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def closes(symbol: str) -> tuple[str, dict[str, float]]:
    """A listing's currency, and its last price on each day of the last month. Asked
    for by the hour, because Yahoo's daily series is nearly empty for some ETFs."""
    result = _get(f"{_chart_url()}/{symbol}", {"range": "1mo", "interval": "1h"})["chart"]["result"][0]
    meta = result["meta"]
    offset = timedelta(seconds=meta.get("gmtoffset") or 0)
    days = {}
    for stamp, close in zip(result.get("timestamp") or [], result["indicators"]["quote"][0].get("close") or []):
        if close is not None:
            days[(datetime.fromtimestamp(stamp, timezone.utc) + offset).date().isoformat()] = close
    return meta.get("currency") or "", days


def find(isin: str, currency: str) -> tuple[str, str]:
    """The listing to use: the one in `currency`, or else the first Yahoo names."""
    quotes = _get(_search_url(), {"q": isin, "quotesCount": CANDIDATES, "newsCount": 0}).get("quotes") or []
    first = ("", "")
    for quote in quotes:
        listed, _days = closes(quote["symbol"])
        if not currency or listed == currency:
            return quote["symbol"], listed
        first = first if first[0] else (quote["symbol"], listed)
    return first


def _symbol(isin: str, currency: str) -> tuple[str, str]:
    with db.connect() as con:
        r = con.execute("SELECT * FROM stock_symbols WHERE isin=?", (isin,)).fetchone()
    stale = (date.today() - timedelta(days=RETRY_UNKNOWN_DAYS)).isoformat()
    if r and (r["symbol"] or r["checked_at"] >= stale):
        return r["symbol"], r["currency"]
    symbol, listed = find(isin, currency)
    with db.connect() as con:
        con.execute("INSERT INTO stock_symbols (isin, symbol, currency, checked_at) VALUES (?,?,?,?)"
                    " ON CONFLICT (isin) DO UPDATE SET symbol=excluded.symbol, currency=excluded.currency,"
                    " checked_at=excluded.checked_at", (isin, symbol, listed, date.today().isoformat()))
    return symbol, listed


def _remember(symbol: str, days: dict[str, float]) -> None:
    oldest = (date.today() - timedelta(days=KEEP_DAYS)).isoformat()
    with db.connect() as con:
        con.executemany("INSERT INTO stock_prices (symbol, day, close) VALUES (?,?,?)"
                        " ON CONFLICT (symbol, day) DO UPDATE SET close=excluded.close",
                        [(symbol, day, close) for day, close in days.items()])
        con.execute("DELETE FROM stock_prices WHERE symbol=? AND day<?", (symbol, oldest))


def _fx_symbol(currency: str) -> str:
    return f"{currency}{BASE}=X"


def job() -> None:
    from . import store                     # store reads the week from here
    wanted = store.held()
    found = 0
    currencies: set[str] = set()
    for isin, currency in wanted.items():
        try:
            symbol, listed = _symbol(isin, currency)
            if symbol:
                _remember(symbol, closes(symbol)[1])
                currencies.add(listed)
                found += 1
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            logs.record_problem("stock prices", f"{isin}: {type(exc).__name__}")
    for currency in currencies - {BASE, ""}:
        try:
            _remember(_fx_symbol(currency), closes(_fx_symbol(currency))[1])
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            logs.record_problem("stock prices", f"{currency}: {type(exc).__name__}")
    _status.update(found=found, wanted=len(wanted))


def status() -> str:
    return f"Kurser på {_status['found']} af {_status['wanted']}." if _status["wanted"] else ""


def _series(symbols: set[str]) -> dict[str, dict[str, float]]:
    if not symbols:
        return {}
    marks = ",".join("?" * len(symbols))
    out: dict[str, dict[str, float]] = {s: {} for s in symbols}
    with db.connect() as con:
        for r in con.execute(f"SELECT * FROM stock_prices WHERE symbol IN ({marks})", tuple(symbols)).fetchall():
            out[r["symbol"]][r["day"]] = r["close"]
    return out


def _filled(prices: dict[str, float], days: list[str]) -> list[float | None]:
    """The close on each day, or the last one before it: no market every day."""
    known = sorted(prices)
    out: list[float | None] = []
    for day in days:
        earlier = [d for d in known if d <= day]
        out.append(prices[earlier[-1]] if earlier else None)
    return out


def week(positions: list[dict], today: date | None = None) -> dict | None:
    """What today's holdings did over the last seven days, in kroner and per cent."""
    if not positions:
        return None
    today = today or date.today()
    days = [(today - timedelta(days=n)).isoformat() for n in range(WEEK_DAYS, -1, -1)]
    isins = tuple(p["isin"] for p in positions)
    with db.connect() as con:
        marks = ",".join("?" * len(isins))
        symbols = {r["isin"]: r for r in con.execute(
            f"SELECT * FROM stock_symbols WHERE isin IN ({marks}) AND symbol != ''", isins).fetchall()}
    wanted = {r["symbol"] for r in symbols.values()} | {_fx_symbol(r["currency"]) for r in symbols.values()
                                                        if r["currency"] not in (BASE, "")}
    series = _series(wanted)
    total = [0.0] * len(days)
    items: list[dict] = []
    missing: list[str] = []
    for position in positions:
        row = symbols.get(position["isin"])
        filled = _filled(series.get(row["symbol"], {}), days) if row else []
        rate = [1.0] * len(days) if row and row["currency"] == BASE else (
            _filled(series.get(_fx_symbol(row["currency"]), {}), days) if row else [])
        if not filled or filled[0] is None or filled[-1] is None or None in rate:
            missing.append(position["name"])
            continue
        values = [close * position["quantity"] * fx for close, fx in zip(filled, rate)]
        total = [t + v for t, v in zip(total, values)]
        items.append({"name": position["name"], "isin": position["isin"], "points": [round(c, 4) for c in filled],
                      "close": filled[-1], "currency": row["currency"], "value": round(values[-1], 2),
                      "change": round((filled[-1] / filled[0] - 1) * 100, 2)})
    if not items:
        return {"days": days, "total": [], "items": [], "missing": missing}
    return {"days": days, "total": [round(t, 2) for t in total], "value": round(total[-1], 2),
            "change": round((total[-1] / total[0] - 1) * 100, 2), "changeKr": round(total[-1] - total[0], 2),
            "items": sorted(items, key=lambda i: -i["value"]), "missing": missing}
