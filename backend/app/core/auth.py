"""Accounts, passwords and sessions (from FamilyLog's core/auth.py).

* Roles: `admin` (created on first run, sees everything) and `family`
  (sees the sections the admin gave them). There can be several admins.
* Section access: `user_sections`, one row per section per family account.
  It is checked once, in the auth middleware, so no endpoint has to remember.
* Passwords: stdlib scrypt, `scrypt$<salt hex>$<hash hex>` - FamilyLog's and
  SLQ's format.
* Sessions: random 32-byte tokens; only their SHA-256 is stored. Up to
  MAX_SESSIONS_PER_USER devices; the next login drops the least recently used.
* Failed logins are throttled per username.
"""
from __future__ import annotations

import hashlib
import os
import secrets
import time

from ..meta import APP_ID
from . import db

SESSION_DAYS = 30
SESSION_COOKIE = f"{APP_ID}_session"
FAMILY_ROLE = "family"
ROLES = ("admin", FAMILY_ROLE)
MAX_SESSIONS_PER_USER = 5
FAIL_LIMIT = 5
FAIL_WINDOW = 300
LOCKOUT_SECONDS = 300

AUTH_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'family',  -- 'admin' | 'family'
    name          TEXT NOT NULL DEFAULT '',        -- what the family calls the person
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at REAL NOT NULL,
    last_seen  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS user_sections (
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    section_id TEXT NOT NULL,
    PRIMARY KEY (user_id, section_id)
);
"""

_failures: dict[str, list[float]] = {}


# ---- passwords ------------------------------------------------------------

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt_hex, hash_hex = stored.split("$")
        if algo != "scrypt":
            return False
        dk = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex),
                            n=2 ** 14, r=8, p=1, dklen=32)
        return secrets.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


def password_problem(password: str) -> str | None:
    """Minimum bar for something reachable from the internet."""
    if len(password) < 10:
        return "Adgangskoden skal være mindst 10 tegn."
    if password.lower() in {"password12", "1234567890", "qwertyuiop"}:
        return "Vælg en mindre forudsigelig adgangskode."
    return None


# ---- users ----------------------------------------------------------------

def user_dto(r) -> dict:
    return {"id": r["id"], "username": r["username"], "role": r["role"],
            "name": r["name"] or "", "createdAt": r["created_at"]}


def user_count() -> int:
    with db.connect() as con:
        return con.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def _all_section_ids() -> list[str]:
    from ..sections import SECTIONS
    return [x.id for x in SECTIONS]


def sections_of(me: dict) -> list[str]:
    """The sections this account may open, in registry order."""
    every = _all_section_ids()
    if me.get("role") == "admin":
        return every
    with db.connect() as con:
        rows = con.execute("SELECT section_id FROM user_sections WHERE user_id=?",
                           (me["id"],)).fetchall()
    have = {r["section_id"] for r in rows}
    return [i for i in every if i in have]


def set_sections(uid: int, section_ids: list[str]) -> list[str]:
    known = _all_section_ids()
    unknown = [i for i in section_ids if i not in known]
    if unknown:
        raise ValueError(f"Ukendt sektion: {', '.join(unknown)}.")
    with db.connect() as con:
        con.execute("DELETE FROM user_sections WHERE user_id=?", (uid,))
        con.executemany("INSERT INTO user_sections (user_id, section_id) VALUES (?,?)",
                        [(uid, i) for i in dict.fromkeys(section_ids)])
    return [i for i in known if i in section_ids]


def default_sections() -> list[str]:
    from ..sections import SECTIONS
    return [x.id for x in SECTIONS if x.family_default]


def list_users() -> list[dict]:
    with db.connect() as con:
        rows = con.execute("SELECT * FROM users ORDER BY id").fetchall()
    return [user_dto(r) for r in rows]


def get_user(uid: int) -> dict | None:
    with db.connect() as con:
        r = con.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    return user_dto(r) if r else None


def create_user(username: str, password: str, role: str, name: str = "") -> dict:
    username = username.strip()
    if not username:
        raise ValueError("Brugernavn mangler.")
    if role not in ROLES:
        raise ValueError(f"Ukendt rolle: {role}.")
    if problem := password_problem(password):
        raise ValueError(problem)
    with db.connect() as con:
        exists = con.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone()
        if exists:
            raise ValueError("Brugernavnet er taget.")
        cur = con.execute(
            "INSERT INTO users (username, password_hash, role, name, created_at) VALUES (?,?,?,?,?)",
            (username, hash_password(password), role, " ".join(name.split()), db.utcnow()))
        if role == FAMILY_ROLE:
            con.executemany("INSERT INTO user_sections (user_id, section_id) VALUES (?,?)",
                            [(cur.lastrowid, i) for i in default_sections()])
        r = con.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone()
    return user_dto(r)


MAX_NAME = 40


def set_name(uid: int, name: str) -> dict:
    """What the family calls the person - empty for none."""
    name = " ".join((name or "").split())
    if len(name) > MAX_NAME:
        raise ValueError(f"Navnet er for langt (højst {MAX_NAME} tegn).")
    with db.connect() as con:
        con.execute("UPDATE users SET name=? WHERE id=?", (name, uid))
        r = con.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if r is None:
        raise LookupError("No such account.")
    return user_dto(r)


def set_role(uid: int, role: str) -> None:
    if role not in ROLES:
        raise ValueError(f"Ukendt rolle: {role}.")
    with db.connect() as con:
        con.execute("UPDATE users SET role=? WHERE id=?", (role, uid))


def set_password(uid: int, password: str) -> None:
    if problem := password_problem(password):
        raise ValueError(problem)
    with db.connect() as con:
        con.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(password), uid))


def delete_user(uid: int) -> None:
    with db.connect() as con:
        con.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
        con.execute("DELETE FROM users WHERE id=?", (uid,))


# ---- sessions -------------------------------------------------------------

def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def active_sessions() -> list[dict]:
    """Live sessions with their owner, newest first."""
    now = time.time()
    with db.connect() as con:
        con.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
        rows = con.execute(
            "SELECT s.token_hash, s.last_seen, u.id AS uid, u.username, u.role"
            " FROM sessions s JOIN users u ON u.id = s.user_id"
            " ORDER BY s.last_seen DESC").fetchall()
    return [{"tokenHash": r["token_hash"], "lastSeen": r["last_seen"],
             "userId": r["uid"], "username": r["username"], "role": r["role"]}
            for r in rows]


def create_session(uid: int) -> str:
    """A session of SESSION_DAYS. The clock runs from login; there is no
    sliding renewal."""
    token = secrets.token_urlsafe(32)
    now = time.time()
    with db.connect() as con:
        # Up to MAX_SESSIONS_PER_USER devices; room is made by dropping the
        # least recently used. Expired rows go first, or a dead session
        # would evict a live one.
        con.execute("DELETE FROM sessions WHERE user_id=? AND expires_at < ?", (uid, now))
        stale = con.execute(
            "SELECT token_hash FROM sessions WHERE user_id=?"
            " ORDER BY last_seen DESC LIMIT -1 OFFSET ?",
            (uid, MAX_SESSIONS_PER_USER - 1)).fetchall()
        for r in stale:
            con.execute("DELETE FROM sessions WHERE token_hash=?", (r["token_hash"],))
        con.execute(
            "INSERT INTO sessions (token_hash, user_id, created_at, expires_at, last_seen)"
            " VALUES (?,?,?,?,?)",
            (_hash_token(token), uid, db.utcnow(), now + SESSION_DAYS * 86400, now))
    return token


def session_user(token: str | None) -> dict | None:
    """Resolve a cookie value to a user, refreshing last_seen."""
    if not token:
        return None
    now = time.time()
    th = _hash_token(token)
    with db.connect() as con:
        r = con.execute(
            "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id"
            " WHERE s.token_hash=? AND s.expires_at > ?", (th, now)).fetchone()
        if r:
            con.execute("UPDATE sessions SET last_seen=? WHERE token_hash=?", (now, th))
    return user_dto(r) if r else None


def revoke_session(token: str | None) -> None:
    if token:
        with db.connect() as con:
            con.execute("DELETE FROM sessions WHERE token_hash=?", (_hash_token(token),))


def revoke_user_sessions(uid: int) -> None:
    with db.connect() as con:
        con.execute("DELETE FROM sessions WHERE user_id=?", (uid,))


# ---- login ----------------------------------------------------------------

def _throttled(username: str) -> int:
    """Seconds the caller must wait, or 0 if they may try."""
    now = time.time()
    hits = [t for t in _failures.get(username, []) if now - t < FAIL_WINDOW]
    _failures[username] = hits
    if len(hits) >= FAIL_LIMIT:
        return max(int(LOCKOUT_SECONDS - (now - hits[-1])), 1)
    return 0


def _record_failure(username: str) -> None:
    _failures.setdefault(username, []).append(time.time())


def login(username: str, password: str) -> tuple[str | None, str | None]:
    """Returns (token, error)."""
    username = (username or "").strip()
    if wait := _throttled(username):
        return None, f"For mange forsøg. Prøv igen om {wait} sekunder."
    with db.connect() as con:
        r = con.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    if not r or not verify_password(password, r["password_hash"]):
        _record_failure(username)
        return None, "Forkert brugernavn eller adgangskode."
    _failures.pop(username, None)
    return create_session(r["id"]), None
