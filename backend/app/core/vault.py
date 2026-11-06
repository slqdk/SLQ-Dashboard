"""Per-person secrets at rest: Google refresh tokens, FamilyLog read keys.

Fernet with a key in /data/secret.key (created on first use, readable by the
app only). The key lives on the same volume as the database, so this does not
stop someone who has the whole volume. It does keep the tokens out of a copied
app.db, a query result and a log line, which is what the LogMyLife design
asked for: never store them in the clear, never log them.
"""
from __future__ import annotations

import os
import threading

from cryptography.fernet import Fernet, InvalidToken

from . import db

_lock = threading.Lock()


class VaultError(RuntimeError):
    """A stored secret can no longer be read (the key file changed)."""


def _key_path():
    return db.data_dir() / "secret.key"


def _fernet() -> Fernet:
    p = _key_path()
    with _lock:
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(Fernet.generate_key())
            try:
                os.chmod(p, 0o600)
            except OSError:
                pass
        return Fernet(p.read_bytes().strip())


def seal(text: str) -> str:
    return _fernet().encrypt(text.encode()).decode()


def unseal(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise VaultError("Kan ikke læse den gemte nøgle.") from exc
