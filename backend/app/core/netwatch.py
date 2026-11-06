"""The ping indicator's server half: how the server itself is doing.

The browser measures its own way to the server (`/api/ping`, a round trip from
wherever the person is logged on from). This module measures from the server
outwards, plus the server's load.

TCP connect time, not ICMP: a container cannot send ICMP without an extra
capability, and connect time is what a real request feels anyway.
"""
from __future__ import annotations

import os
import socket
import time
from collections import deque
from urllib.parse import urlparse

from . import settings

INTERNET = [("Cloudflare", "1.1.1.1", 443), ("Google", "www.google.com", 443)]
CONNECT_TIMEOUT = 2.0
HISTORY = 60

_results: dict[str, dict] = {}
_history: deque = deque(maxlen=HISTORY)


def connect_ms(host: str, port: int, timeout: float = CONNECT_TIMEOUT) -> float | None:
    """Milliseconds to open a TCP connection, or None if it could not be done."""
    started = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return round((time.perf_counter() - started) * 1000, 1)
    except OSError:
        return None


def _app_targets() -> list[tuple[str, str, int]]:
    """The apps the dashboard reads from, as far as they are set up."""
    s = settings.load()
    out = []
    url = urlparse(s.get("familylogUrl") or "")
    if url.hostname:
        out.append(("FamilyLog", url.hostname, url.port or (443 if url.scheme == "https" else 80)))
    return out


def job() -> None:
    targets = []
    for name, host, port in INTERNET + _app_targets():
        ms = connect_ms(host, port)
        targets.append({"name": name, "ms": ms, "ok": ms is not None})
        _results[name] = targets[-1]
    internet = [t["ms"] for t in targets[:len(INTERNET)] if t["ms"] is not None]
    _history.append({"at": time.time(), "ms": min(internet) if internet else None})
    _results["_targets"] = targets      # type: ignore[assignment]


def load() -> dict:
    try:
        one, five, fifteen = os.getloadavg()
    except OSError:                     # not on every platform
        one = five = fifteen = None
    return {"load1": one, "load5": five, "load15": fifteen, "cpus": os.cpu_count() or 1}


def status() -> dict:
    samples = list(_history)
    return {"targets": _results.get("_targets", []),
            "internetMs": samples[-1]["ms"] if samples else None,
            "history": [s["ms"] for s in samples],
            "load": load()}


def reset() -> None:
    _results.clear()
    _history.clear()
