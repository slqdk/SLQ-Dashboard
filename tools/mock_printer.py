#!/usr/bin/env python3
"""A stand-in for the MQTT broker in a Bambu Lab printer, for the tests and the
browser check: TLS with its own certificate, user `bblp`, the access code as
password, reports on device/<serial>/report. Everything it says is made up, and it
knows only the MQTT 3.1.1 packets the dashboard uses.

    python3 tools/mock_printer.py 9101
"""
from __future__ import annotations

import json
import socket
import ssl
import struct
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

SERIAL = "01S00C000000001"
CODE = "12345678"
FULL = {"print": {"command": "push_status", "gcode_state": "RUNNING", "mc_percent": 62, "mc_remaining_time": 74,
                  "layer_num": 118, "total_layer_num": 190, "nozzle_temper": 219.8, "nozzle_target_temper": 220,
                  "bed_temper": 54.9, "bed_target_temper": 55, "subtask_name": "beslag-v3.3mf", "print_error": 0}}


def _context(folder: Path) -> ssl.SSLContext:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, SERIAL)])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=1)).sign(key, hashes.SHA256()))
    path = folder / "printer.pem"
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM) + key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(path)
    return context


def _packet(kind: int, body: bytes = b"") -> bytes:
    length, size = bytearray(), len(body)
    while True:
        size, digit = size // 128, size % 128
        length.append(digit | (128 if size else 0))
        if not size:
            return bytes([kind]) + bytes(length) + body


def _read(stream) -> tuple[int, bytes] | None:
    first = stream.read(1)
    if not first:
        return None
    size, shift = 0, 0
    while True:
        byte = stream.read(1)[0]
        size |= (byte & 127) << shift
        shift += 7
        if not byte & 128:
            return first[0], stream.read(size)


def _text(data: bytes, at: int) -> tuple[str, int]:
    size = struct.unpack_from(">H", data, at)[0]
    return data[at + 2:at + 2 + size].decode(), at + 2 + size


class Printer:
    def __init__(self, serial: str = SERIAL, code: str = CODE, report: dict | None = None):
        self.serial, self.code, self.report = serial, code, report or FULL
        self.requests: list[dict] = []          # what the dashboard has sent
        self.clients: list = []
        self._folder = tempfile.TemporaryDirectory()
        self._context = _context(Path(self._folder.name))
        self._listener = socket.create_server(("127.0.0.1", 0))

    def start(self, port: int = 0) -> int:
        if port:
            self._listener.close()
            self._listener = socket.create_server(("127.0.0.1", port))
        threading.Thread(target=self._accept, daemon=True).start()
        return self._listener.getsockname()[1]

    def stop(self) -> None:
        self._listener.close()
        for conn in self.clients:
            try:
                conn.close()
            except OSError:
                pass
        self._folder.cleanup()

    def send(self, report: dict) -> None:
        """Report to everyone connected, as the printer does by itself."""
        topic = f"device/{self.serial}/report".encode()
        packet = _packet(0x30, struct.pack(">H", len(topic)) + topic + json.dumps(report).encode())
        for conn in list(self.clients):
            try:
                conn.sendall(packet)
            except OSError:
                self.clients.remove(conn)

    def _accept(self) -> None:
        while True:
            try:
                conn, _ = self._listener.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, plain: socket.socket) -> None:
        try:
            conn = self._context.wrap_socket(plain, server_side=True)
            stream = conn.makefile("rb")
            while (packet := _read(stream)) is not None:
                self._handle(conn, *packet)
        except (OSError, IndexError, struct.error):
            pass

    def _handle(self, conn, kind: int, data: bytes) -> None:
        if kind == 0x10:                        # CONNECT
            _protocol, at = _text(data, 0)
            flags = data[at + 1]
            _client, at = _text(data, at + 4)
            user, at = _text(data, at) if flags & 0x80 else ("", at)
            password, at = _text(data, at) if flags & 0x40 else ("", at)
            allowed = user == "bblp" and password == self.code
            conn.sendall(_packet(0x20, bytes([0, 0 if allowed else 5])))
            if not allowed:
                conn.close()
                return
            self.clients.append(conn)
        elif kind == 0x82:                      # SUBSCRIBE
            conn.sendall(_packet(0x90, data[:2] + b"\x00"))
        elif kind & 0xF0 == 0x30:               # PUBLISH, at most once
            topic, at = _text(data, 0)
            message = json.loads(data[at:])
            if topic == f"device/{self.serial}/request":
                self.requests.append(message)
                if message.get("pushing", {}).get("command") == "pushall":
                    self.send(self.report)
        elif kind == 0xC0:                      # PINGREQ
            conn.sendall(_packet(0xD0))


if __name__ == "__main__":
    printer = Printer()
    printer.start(int(sys.argv[1]) if len(sys.argv) > 1 else 9101)
    while True:
        time.sleep(3)
        percent = printer.report["print"]["mc_percent"] % 99 + 1
        printer.report["print"]["mc_percent"] = percent
        printer.send({"print": {"mc_percent": percent}})
