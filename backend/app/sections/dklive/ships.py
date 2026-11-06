"""Live vessels from AISStream (free key): one websocket for the map's area. Positions
stay in memory and the map reads a snapshot.

AISStream can stop sending without closing the socket, and it reports a bad key or
overload as a message followed by a close, so a socket quiet for 90 seconds is dropped
and a new one tried, 10 seconds later and doubling to five minutes."""
from __future__ import annotations

import json
import threading
import time

from websockets.exceptions import WebSocketException
from websockets.sync.client import connect

from ...core import settings
from . import source

STREAM = "wss://stream.aisstream.io/v0/stream"
STALE_MS = 15 * 60 * 1000
SILENCE = 90.0
RETRY_FIRST, RETRY_MOST = 10.0, 300.0

_ships: dict[int, dict] = {}
_lock = threading.Lock()
_watch: "_Watch | None" = None


def _name(text) -> str:
    return (text or "").strip()


def apply(message: dict, now: int) -> None:
    """One message from AISStream into the ship it is about."""
    meta = message.get("MetaData") or {}
    mmsi = meta.get("MMSI")
    if not mmsi:
        return
    kind = message.get("MessageType")
    body = (message.get("Message") or {}).get(kind) or {}
    with _lock:
        ship = _ships.setdefault(mmsi, {"id": mmsi, "name": None, "type": None, "dest": None, "firstSeen": now})
        if kind == "PositionReport":
            turn = body.get("RateOfTurn")
            ship.update({
                "name": _name(meta.get("ShipName")) or ship["name"],
                "lat": meta.get("latitude"),
                "lon": meta.get("longitude"),
                "cog": body.get("Cog"),
                "sog": body.get("Sog"),                 # knots
                "heading": None if body.get("TrueHeading") == 511 else body.get("TrueHeading"),
                "navStatus": body.get("NavigationalStatus"),
                "rot": None if turn in (-128, None) else turn,
                "seen": now,
            })
        elif kind == "ShipStaticData":
            size = body.get("Dimension") or {}
            eta = body.get("Eta") or {}
            ship["name"] = _name(body.get("Name")) or ship["name"]
            ship["type"] = body.get("Type") if body.get("Type") is not None else ship["type"]
            ship["dest"] = _name(body.get("Destination")) or ship["dest"]
            ship["imo"] = body.get("ImoNumber") or ship.get("imo")
            ship["callsign"] = _name(body.get("CallSign")) or ship.get("callsign")
            if size.get("A") is not None:
                ship["length"] = (size.get("A") or 0) + (size.get("B") or 0) or None
                ship["beam"] = (size.get("C") or 0) + (size.get("D") or 0) or None
            ship["draught"] = body.get("MaximumStaticDraught") or ship.get("draught")
            if eta.get("Month") and eta.get("Day"):
                ship["eta"] = {"month": eta["Month"], "day": eta["Day"], "hour": eta.get("Hour"), "minute": eta.get("Minute")}


class _Watch(threading.Thread):
    """One connection at a time for one key, until the key changes."""

    def __init__(self, key: str):
        super().__init__(name="ships", daemon=True)
        self.key = key
        self.halt = threading.Event()

    def stop(self) -> None:
        self.halt.set()

    def _listen(self) -> None:
        subscription = {"APIKey": self.key,
                        "BoundingBoxes": [[[source.SOUTH, source.WEST], [source.NORTH, source.EAST]]],
                        "FilterMessageTypes": ["PositionReport", "ShipStaticData"]}
        with connect(source.address(STREAM), open_timeout=20, close_timeout=2) as ws:
            ws.send(json.dumps(subscription))
            heard = time.monotonic()
            while not self.halt.is_set():
                try:
                    raw = ws.recv(timeout=5)
                except TimeoutError:
                    if time.monotonic() - heard > SILENCE:
                        raise
                    continue
                try:
                    message = json.loads(raw)
                except ValueError:
                    continue
                if message.get("error"):
                    # The text is AISStream's own, about the key or its load.
                    source.failed("ships", str(message["error"])[:120])
                    continue
                heard = time.monotonic()
                self.retry = RETRY_FIRST
                apply(message, source.now_ms())
                source.done("ships", f"{len(_ships)} skibe")

    def run(self) -> None:
        self.retry = RETRY_FIRST
        while not self.halt.is_set():
            try:
                self._listen()
            except (OSError, TimeoutError, WebSocketException) as exc:
                if not self.halt.is_set():
                    source.failed("ships", exc)
            self.halt.wait(self.retry)
            self.retry = min(self.retry * 2, RETRY_MOST)


def job() -> None:
    """Keep one watcher for the key in Admin, and forget ships not heard for a while."""
    global _watch
    key = (settings.load().get("aisstreamKey") or "") if source.shown("ships") else ""
    if _watch and _watch.key != key:
        _watch.stop()
        _watch = None
        with _lock:
            _ships.clear()
    if key and not _watch:
        _watch = _Watch(key)
        _watch.start()
    if not key:
        source.off("ships")
    cutoff = source.now_ms() - STALE_MS
    with _lock:
        for mmsi in [m for m, s in _ships.items() if s.get("seen", 0) < cutoff and s.get("firstSeen", 0) < cutoff]:
            del _ships[mmsi]


def get() -> dict:
    with _lock:
        ships = [dict(s) for s in _ships.values() if isinstance(s.get("lat"), (int, float))]
    return {"enabled": _watch is not None, "ships": ships}


def reset() -> None:
    global _watch
    if _watch:
        _watch.stop()
        _watch = None
    with _lock:
        _ships.clear()
