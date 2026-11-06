"""What every live source shares: the map's area, one way to fetch, and its status.

The sources were dk-live's. They live here so the dashboard needs no other container:
each module keeps its newest result in memory, a job refreshes it, and nothing a page
asks for waits on an upstream.

A failure is recorded by the kind of error, never its text: an address can hold a key,
and httpx puts the address in the text.
"""
from __future__ import annotations

import functools
import logging
import os
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx

from ...core import logs, settings
from ...meta import APP_ID

WEST, SOUTH, EAST, NORTH = 7.5, 53.3, 13.0, 57.9
CENTER_LAT = (SOUTH + NORTH) / 2
CENTER_LON = (WEST + EAST) / 2
UA = "SLQ-Dashboard/0.6 (personal dashboard)"
TIMEOUT = 20.0
CPH = ZoneInfo("Europe/Copenhagen")

_state: dict[str, dict] = {}


def reset() -> None:
    _state.clear()


def in_bbox(lat: float, lon: float) -> bool:
    return SOUTH <= lat <= NORTH and WEST <= lon <= EAST


def now_ms() -> int:
    return int(time.time() * 1000)


def copenhagen_ms(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> int:
    """Danish wall-clock time, as Danish sources print it, as an instant."""
    return int(datetime(year, month, day, hour, minute, tzinfo=CPH).timestamp() * 1000)


def iso_ms(text: str | None) -> int | None:
    """An ISO timestamp as an instant; one without an offset is UTC."""
    if not text:
        return None
    try:
        at = datetime.fromisoformat(str(text).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    return int(at.timestamp() * 1000)


def address(url: str) -> str:
    """tools/mock_upstreams.py stands in for every source when APP_LIVE_MOCK is set."""
    mock = os.environ.get("APP_LIVE_MOCK", "").rstrip("/")
    if not mock:
        return url
    scheme, rest = url.split("://", 1)
    return f"{mock.replace('http', 'ws', 1) if scheme == 'wss' else mock}/{rest}"


def fetch(url: str, params=None, headers: dict | None = None, timeout: float = TIMEOUT) -> httpx.Response:
    """A fresh connection each time: adsb.lol throttles kept-alive ones far harder."""
    response = httpx.get(address(url), params=params, headers={"User-Agent": UA, **(headers or {})},
                         timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    return response


def post(url: str, data: dict, timeout: float = TIMEOUT) -> httpx.Response:
    response = httpx.post(address(url), data=data, headers={"User-Agent": UA}, timeout=timeout)
    response.raise_for_status()
    return response


def why(exc: BaseException | str) -> str:
    if isinstance(exc, str):
        return exc
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    return type(exc).__name__


def done(name: str, text: str) -> None:
    """The first answer and the first after a failure go into the log, the others not."""
    if not _state.get(name, {}).get("ok"):
        logging.getLogger(APP_ID).info("dklive %s: %s", name, text)
    at = now_ms()
    _state[name] = {"ok": True, "text": text, "at": at, "lastOk": at}


def failed(name: str, problem: BaseException | str) -> None:
    """Into the log once per episode, not at every failed turn."""
    text = why(problem)
    if _state.get(name, {}).get("ok", True):
        if isinstance(problem, Exception) and not isinstance(problem, httpx.HTTPError):
            logs.record_exception(problem, f"dklive {name}")    # a changed shape, or a bug
        else:
            logs.record_problem("dklive", f"{name}: {text}")
    _state[name] = {"ok": False, "text": text, "at": now_ms(), "lastOk": _state.get(name, {}).get("lastOk")}


def off(name: str) -> None:
    _state.pop(name, None)


def shown(*layers: str) -> bool:
    on = settings.load().get("dkliveLayers") or []
    return any(layer in on for layer in layers)


def watched(name: str, *layers: str):
    """A job's wrapper: it runs only while one of `layers` is on the map (always if none
    are named), and whatever it raises goes to the source's status."""
    def wrap(fn):
        @functools.wraps(fn)
        def run(*args, **kwargs):
            if layers and not shown(*layers):
                off(name)
                return None
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                failed(name, exc)
                return None
        return run
    return wrap


def state() -> dict[str, dict]:
    return dict(_state)


def problems() -> list[str]:
    return [f"{name}: {s['text']}" for name, s in _state.items() if not s["ok"]]
