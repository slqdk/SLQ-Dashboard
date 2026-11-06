"""Shared test fixtures.

Every test runs against a throwaway data directory (APP_DATA_DIR), so the
suite can never touch a real database or settings file. The variables are set
before `app` is imported, and the background jobs stay off.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
_PINS = ("APP_FAMILYLOG_URL", "APP_PUBLIC_URL", "APP_TIMEZONE", "APP_GOOGLE_CLIENT_ID", "APP_GOOGLE_CLIENT_SECRET",
         "APP_LIVE_MOCK")


@pytest.fixture(scope="session", autouse=True)
def _isolate_data(tmp_path_factory):
    data = tmp_path_factory.mktemp("app-data")
    os.environ["APP_DATA_DIR"] = str(data)
    os.environ["APP_NO_JOBS"] = "1"
    for var in _PINS:
        os.environ.pop(var, None)
    sys.path.insert(0, str(BACKEND))
    yield data


@pytest.fixture
def fresh_db(_isolate_data):
    """A database with the schema applied and nothing in it."""
    from app.core import auth, db
    from app.sections import SECTIONS

    data = Path(os.environ["APP_DATA_DIR"])
    for name in ("app.db", "app.db-wal", "app.db-shm", "settings.json", "secret.key", "f1-schedule.json"):
        (data / name).unlink(missing_ok=True)
    shutil.rmtree(data / "logmylife", ignore_errors=True)
    auth._failures.clear()
    for s in SECTIONS:
        if s.reset:
            s.reset()
    db.init_db()
    return db


@pytest.fixture
def client(fresh_db):
    """API client signed in as the administrator."""
    from fastapi.testclient import TestClient

    from app.main import app
    with TestClient(app) as c:
        r = c.post("/api/auth/setup", json={"username": "soren", "password": "korrekt-hest-1"})
        assert r.status_code == 200
        yield c


@pytest.fixture
def family(client):
    """A second client, signed in as a family account."""
    from fastapi.testclient import TestClient

    from app.main import app
    r = client.post("/api/admin/users", json={"username": "mor", "password": "endnu-en-kode-2", "name": "Mor"})
    assert r.status_code == 200
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"username": "mor", "password": "endnu-en-kode-2"}).status_code == 200
    c.user_id = r.json()["id"]
    return c
