"""The shell: first run, accounts, section access, setup."""
from __future__ import annotations


def test_first_account_is_admin_and_second_setup_is_refused(fresh_db):
    from fastapi.testclient import TestClient

    from app.main import app
    with TestClient(app) as c:
        assert c.get("/api/auth/status").json()["needsSetup"] is True
        r = c.post("/api/auth/setup", json={"username": "soren", "password": "korrekt-hest-1"})
        assert r.json()["user"]["role"] == "admin"
        assert c.post("/api/auth/setup", json={"username": "x", "password": "korrekt-hest-1"}).status_code == 400


def test_api_needs_a_session(fresh_db):
    from fastapi.testclient import TestClient

    from app.main import app
    with TestClient(app) as c:
        for path in ("/api/overview", "/api/ping", "/api/s/links/tree", "/api/admin/users"):
            assert c.get(path).status_code == 401, path


def test_family_gets_the_default_sections_not_aktier(client, family):
    me = family.get("/api/auth/status").json()["user"]
    assert "links" in me["sections"]
    assert "aktier" not in me["sections"]
    assert family.get("/api/s/aktier/state").status_code == 403
    assert "aktier" not in family.get("/api/overview").json()["blocks"]


def test_admin_controls_a_family_members_sections(client, family):
    uid = family.user_id
    r = client.patch(f"/api/admin/users/{uid}", json={"sections": ["aktier"]})
    assert r.json()["sections"] == ["aktier"]
    assert family.get("/api/s/aktier/state").status_code == 200
    assert family.get("/api/s/links/tree").status_code == 403


def test_unknown_section_is_refused(client, family):
    r = client.patch(f"/api/admin/users/{family.user_id}", json={"sections": ["nope"]})
    assert r.status_code == 400


def test_family_cannot_reach_admin(client, family):
    assert family.get("/api/admin/users").status_code == 403
    assert family.get("/api/admin/setup").status_code == 403
    assert family.put("/api/admin/setup", json={"homeName": "x"}).status_code == 403


def test_last_admin_cannot_be_demoted(client):
    me = client.get("/api/auth/status").json()["user"]
    r = client.patch(f"/api/admin/users/{me['id']}", json={"role": "family"})
    assert r.status_code == 400


def test_new_password_signs_the_other_person_out(client, family):
    r = client.patch(f"/api/admin/users/{family.user_id}/password", json={"password": "en-helt-ny-kode-3"})
    assert r.status_code == 200
    assert family.get("/api/overview").status_code == 401


def test_secrets_never_reach_the_browser(client):
    r = client.put("/api/admin/setup", json={"googleClientSecret": "super-hemmelig-1234", "googleClientId": "id"})
    assert r.status_code == 200
    text = client.get("/api/admin/setup").text
    assert "super-hemmelig" not in text
    s = client.get("/api/admin/setup").json()["settings"]
    assert s["googleClientSecretSet"] is True
    assert s["googleClientSecretHint"] == "…1234"


def test_setup_refuses_bad_values(client):
    assert client.put("/api/admin/setup", json={"dkliveUrl": "ftp://x"}).status_code == 400
    assert client.put("/api/admin/setup", json={"unknown": 1}).status_code == 400
    assert client.put("/api/admin/setup", json={"homeLat": 200}).status_code == 400


def test_a_pinned_value_cannot_be_saved(client, monkeypatch):
    monkeypatch.setenv("APP_DKLIVE_URL", "http://1.2.3.4:4200")
    r = client.put("/api/admin/setup", json={"dkliveUrl": "http://5.6.7.8"})
    assert r.status_code == 400
    assert "APP_DKLIVE_URL" in r.json()["detail"]


def test_overview_survives_a_broken_section(client, monkeypatch):
    from app.main import SECTIONS

    section = next(s for s in SECTIONS if s.id == "links")

    def boom(_me):
        raise RuntimeError("nej")

    object.__setattr__(section, "overview", boom)
    try:
        blocks = client.get("/api/overview").json()["blocks"]
    finally:
        from app.sections.links import store
        object.__setattr__(section, "overview", store.overview)
    assert "error" in blocks["links"]
    assert "calendar" in blocks


def test_ping_and_netstatus(client):
    assert "t" in client.get("/api/ping").json()
    data = client.get("/api/netstatus").json()
    assert data["load"]["cpus"] >= 1
    assert data["targets"] == []


def test_netwatch_measures_a_real_connection():
    import socket
    import threading

    from app.core import netwatch
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    threading.Thread(target=server.accept, daemon=True).start()
    ms = netwatch.connect_ms("127.0.0.1", server.getsockname()[1])
    assert ms is not None and ms >= 0
    server.close()
    assert netwatch.connect_ms("127.0.0.1", 1, timeout=.2) is None


def test_vault_round_trip_and_not_in_clear(fresh_db):
    from app.core import vault
    sealed = vault.seal("min-hemmelige-token")
    assert "min-hemmelige-token" not in sealed
    assert vault.unseal(sealed) == "min-hemmelige-token"


def test_only_files_at_the_top_of_the_build_are_served(tmp_path):
    from app.main import root_file
    (tmp_path / "favicon.svg").write_text("<svg/>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "x.js").write_text("x")
    assert root_file("favicon.svg", tmp_path) == tmp_path / "favicon.svg"
    assert root_file("assets", tmp_path) is None
    assert root_file("assets/x.js", tmp_path) is None
    assert root_file("../secret.key", tmp_path) is None
    assert root_file("..", tmp_path) is None
    assert root_file("", tmp_path) is None
    assert root_file("findes-ikke", tmp_path) is None
