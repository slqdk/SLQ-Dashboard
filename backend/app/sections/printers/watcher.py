"""One MQTT connection per printer, kept open, its reports merged into a state.

TLS on port 8883, user `bblp`, the printer's LAN access code as password. The
printer signs with its own certificate, so there is nothing to check it against.
Some models report only what changed, which is why reports are merged, and why
`pushall` goes out after connecting: it asks for the whole picture. It is the only
thing ever sent here, and at most every five minutes, because OpenBambuAPI warns
against sending it more often to a P1.
"""
from __future__ import annotations

import json
import ssl
import threading
import time

import paho.mqtt.client as mqtt

from . import store

PORT = 8883
USER = "bblp"
PUSHALL = json.dumps({"pushing": {"sequence_id": "0", "command": "pushall", "version": 1, "push_target": 1}})
PUSHALL_SECONDS = 300
FIELDS = ("gcode_state", "mc_percent", "mc_remaining_time", "layer_num", "total_layer_num",
          "nozzle_temper", "nozzle_target_temper", "bed_temper", "bed_target_temper",
          "subtask_name", "gcode_file", "print_error")
STATE_TEXT = {"IDLE": "Klar", "PREPARE": "Forbereder", "SLICING": "Forbereder", "RUNNING": "Printer",
              "PAUSE": "På pause", "FINISH": "Færdig", "FAILED": "Fejlet"}
ACTIVE = {"PREPARE", "SLICING", "RUNNING", "PAUSE"}


def merge(state: dict, report: dict) -> None:
    """Add what a report holds to the state; it may be only a field or two."""
    part = report.get("print")
    if isinstance(part, dict):
        state.update({key: part[key] for key in FIELDS if key in part})


def dto(printer: dict, state: dict, connected: bool, problem: str) -> dict:
    online = connected and bool(state)
    code = state.get("gcode_state") or ""
    error = state.get("print_error") or 0
    return {"id": printer["id"], "name": printer["name"], "online": online, "problem": problem,
            "state": code, "stateText": STATE_TEXT.get(code, code.capitalize()) if online else "Offline",
            "active": online and code in ACTIVE, "percent": state.get("mc_percent"),
            "remainingMin": state.get("mc_remaining_time"), "layer": state.get("layer_num"),
            "totalLayers": state.get("total_layer_num"), "nozzle": state.get("nozzle_temper"),
            "nozzleTarget": state.get("nozzle_target_temper"), "bed": state.get("bed_temper"),
            "bedTarget": state.get("bed_target_temper"),
            "file": state.get("subtask_name") or state.get("gcode_file") or "",
            "error": f"{error >> 16:04X}-{error & 0xFFFF:04X}" if isinstance(error, int) and error else ""}


class _Watch:
    def __init__(self, printer: dict, code: str):
        self.printer = printer
        self.code = code
        self.state: dict = {}
        self.connected = False
        self.problem = ""
        self.pushed: float | None = None
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        client.username_pw_set(USER, code)
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        client.tls_set_context(context)
        client.reconnect_delay_set(5, 120)
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        self.client = client

    def start(self) -> None:
        host, _, port = self.printer["host"].partition(":")
        self.client.connect_async(host, int(port or PORT), keepalive=60)
        self.client.loop_start()

    def stop(self) -> None:
        self.client.disconnect()
        self.client.loop_stop()

    def _on_connect(self, client, _userdata, _flags, reason, _props) -> None:
        if reason.is_failure:
            self.connected = False
            self.problem = ("Printeren afviste adgangskoden." if "authorized" in str(reason).lower()
                            else f"Printeren afviste forbindelsen ({reason}).")
            return
        self.connected = True
        self.problem = ""
        serial = self.printer["serial"]
        client.subscribe(f"device/{serial}/report")
        if self.pushed is None or time.monotonic() - self.pushed >= PUSHALL_SECONDS:
            self.pushed = time.monotonic()
            client.publish(f"device/{serial}/request", PUSHALL)

    def _on_disconnect(self, *_args) -> None:
        self.connected = False

    def _on_message(self, _client, _userdata, message) -> None:
        try:
            report = json.loads(message.payload)
        except ValueError:
            return
        if isinstance(report, dict):
            merge(self.state, report)


_watches: dict[int, _Watch] = {}
_lock = threading.Lock()


def job() -> None:
    """Match the connections to the printers set up in Admin."""
    printers = {p["id"]: p for p in store.all_printers()}
    with _lock:
        for pid in list(_watches):
            if printers.get(pid) != _watches[pid].printer or store.code_of(pid) != _watches[pid].code:
                _watches.pop(pid).stop()
        for pid, printer in printers.items():
            if pid not in _watches:
                _watches[pid] = _Watch(printer, store.code_of(pid))
                _watches[pid].start()


def reset() -> None:
    with _lock:
        for watch in _watches.values():
            watch.stop()
        _watches.clear()


def state() -> list[dict]:
    out = []
    for printer in store.all_printers():
        w = _watches.get(printer["id"])
        out.append(dto(printer, w.state, w.connected, w.problem) if w else dto(printer, {}, False, ""))
    return out


def overview(_me: dict) -> dict:
    return {"printers": state()}


def setup_status() -> dict:
    printers = state()
    if not printers:
        return {"ok": False, "text": "Ingen printere sat op."}
    online = sum(1 for p in printers if p["online"])
    problem = next((p["problem"] for p in printers if p["problem"]), "")
    return {"ok": online == len(printers), "text": problem or f"{online} af {len(printers)} svarer."}
