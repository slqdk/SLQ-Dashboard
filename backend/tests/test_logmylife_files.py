"""LogMyLife: the timeline's index, pictures and files on entries, and the export."""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core import db

API = "/api/s/logmylife"


def picture(size=(2400, 1200), exif_date="2014:06:12 10:30:00", fmt="JPEG") -> bytes:
    out = io.BytesIO()
    img = Image.new("RGB", size, (30, 120, 200))
    exif = Image.Exif()
    gps = exif.get_ifd(0x8825)
    gps[1] = "N"
    exif.get_ifd(0x8769)[36867] = exif_date
    img.save(out, fmt, exif=exif)
    return out.getvalue()


def entry(client, title="Tur til Skagen", day="2014-06-12", **fields) -> int:
    r = client.post(f"{API}/events", json={"title": title, "start": day, **fields})
    assert r.status_code == 200
    return r.json()["id"]


def attach(client, event_id, content=None, name="billede.jpg"):
    return client.post(f"{API}/events/{event_id}/files?name={name}", content=picture() if content is None else content)


# ---- the timeline's index ----------------------------------------------------------

def test_the_index_holds_every_entry_oldest_first(client):
    entry(client, "Nyere", "2020-01-01")
    entry(client, "Ferie", "2015-07-01", end="2015-07-14")
    data = client.get(f"{API}/timeline").json()
    rows = [dict(zip(data["fields"], row)) for row in data["rows"]]
    assert [r["title"] for r in rows] == ["Ferie", "Nyere"]
    assert rows[0]["end"] == "2015-07-14" and rows[1]["end"] is None
    assert rows[0]["files"] == 0 and rows[0]["picture"] is None and rows[0]["owner"] is None


def test_the_index_is_not_held_to_a_page(client):
    from app.core import db
    me = client.get("/api/auth/status").json()["user"]["id"]
    with db.connect() as con:
        con.executemany("INSERT INTO life_events (user_id, uid, source, title, start_at, day, created_at, updated_at)"
                        " VALUES (?,?,?,?,?,?,?,?)",
                        [(me, f"u{i}", "x", f"E{i}", "2015-01-01", "2015-01-01", "t", "t") for i in range(700)])
    assert len(client.get(f"{API}/timeline").json()["rows"]) == 700


def test_search_and_source_narrow_the_index(client):
    entry(client, "Skagen", description="med strand")
    entry(client, "Aarhus")
    rows = client.get(f"{API}/timeline", params={"q": "strand"}).json()["rows"]
    assert [r[3] for r in rows] == ["Skagen"]
    assert client.get(f"{API}/timeline", params={"source": "google"}).json()["rows"] == []


def test_the_family_index_holds_only_what_was_shared(client, family):
    entry(client, "Privat")
    entry(client, "Delt", shared=True)
    data = family.get(f"{API}/timeline", params={"scope": "family"}).json()
    rows = [dict(zip(data["fields"], row)) for row in data["rows"]]
    assert [r["title"] for r in rows] == ["Delt"] and rows[0]["owner"] == "soren"
    assert family.get(f"{API}/timeline").json()["rows"] == []


def test_one_entry_comes_with_its_files(client, family):
    private, shared = entry(client, "Privat"), entry(client, "Delt", shared=True)
    attach(client, shared)
    full = client.get(f"{API}/events/{shared}").json()
    assert full["files"][0]["name"] == "billede.jpg" and full["files"][0]["kind"] == "image"
    assert family.get(f"{API}/events/{shared}").status_code == 200
    assert family.get(f"{API}/events/{private}").status_code == 404


# ---- pictures ----------------------------------------------------------------------

def test_a_picture_gets_two_sizes_without_exif(client):
    event = entry(client)
    r = attach(client, event)
    assert r.status_code == 200
    f = r.json()
    assert f["kind"] == "image" and f["width"] == 2400 and f["taken"] == "2014:06:12 10:30:00"
    view = Image.open(io.BytesIO(client.get(f"{API}/files/{f['id']}/view").content))
    assert max(view.size) == 1800 and not view.getexif()
    thumb = Image.open(io.BytesIO(client.get(f"{API}/files/{f['id']}/thumb").content))
    assert max(thumb.size) == 480
    original = client.get(f"{API}/files/{f['id']}/original")
    assert original.content == picture() and "attachment" in original.headers["content-disposition"]


def test_the_index_points_at_the_first_picture(client):
    event = entry(client)
    attach(client, event, b"just some notes", "noter.txt")
    f = attach(client, event).json()
    row = dict(zip(*(lambda d: (d["fields"], d["rows"][0]))(client.get(f"{API}/timeline").json())))
    assert row["picture"] == f["id"] and row["files"] == 2


def test_a_picture_is_upright(client):
    out = io.BytesIO()
    exif = Image.Exif()
    exif[0x0112] = 6                    # turned on its side, as phones save it
    Image.new("RGB", (400, 200)).save(out, "JPEG", exif=exif)
    f = attach(client, entry(client), out.getvalue()).json()
    assert (f["width"], f["height"]) == (200, 400)


def test_the_family_gets_no_original_of_a_shared_picture(client, family):
    f = attach(client, entry(client, shared=True)).json()
    assert family.get(f"{API}/files/{f['id']}/view").status_code == 200
    assert family.get(f"{API}/files/{f['id']}/original").status_code == 404     # it can say where it was taken


def test_a_private_file_is_nobodys_business(client, family):
    f = attach(client, entry(client)).json()
    for size in ("thumb", "view", "original"):
        assert family.get(f"{API}/files/{f['id']}/{size}").status_code == 404
    assert TestClient(client.app).get(f"{API}/files/{f['id']}/view").status_code == 401


def test_nobody_adds_to_or_removes_from_anothers_entry(client, family):
    event = entry(client, shared=True)
    f = attach(client, event).json()
    assert attach(family, event).status_code == 404
    assert family.delete(f"{API}/files/{f['id']}").status_code == 404


def test_a_file_that_is_no_picture_comes_back_as_a_download(client):
    f = attach(client, entry(client), b"<script>alert(1)</script>", "side.html").json()
    assert f["kind"] == "file"
    r = client.get(f"{API}/files/{f['id']}/original")
    assert "attachment" in r.headers["content-disposition"] and r.headers["x-content-type-options"] == "nosniff"
    assert client.get(f"{API}/files/{f['id']}/view").status_code == 404


def test_a_lying_picture_is_not_a_picture(client):
    assert attach(client, entry(client), b"<svg onload=alert(1)>", "billede.jpg").json()["kind"] == "file"


def test_a_film_plays_in_the_page(client):
    f = attach(client, entry(client), b"\x00\x00\x00\x18ftypmp42", "film.mp4").json()
    assert f["kind"] == "video"
    assert "inline" in client.get(f"{API}/files/{f['id']}/original").headers["content-disposition"]


def test_the_upload_name_stays_a_name(client):
    from app.sections.logmylife import files
    f = attach(client, entry(client), b"tekst", "..%2F..%2Fapp.db").json()
    assert f["name"] == "app.db"
    row = files.readable(client.get("/api/auth/status").json()["user"]["id"], f["id"])
    assert files.path_of(row).parent == files.folder(row["user_id"])


def test_an_empty_or_too_big_file_is_refused(client, monkeypatch):
    from app.sections.logmylife import files
    event = entry(client)
    assert attach(client, event, b"").status_code == 413
    monkeypatch.setattr(files, "MAX_BYTES", 10)
    assert attach(client, event, b"x" * 11, "stor.bin").status_code == 413
    me = client.get("/api/auth/status").json()["user"]["id"]
    assert not list(files.folder(me).glob(".incoming-*"))


def _on_disk(client) -> list[Path]:
    from app.sections.logmylife import files
    folder = files.folder(client.get("/api/auth/status").json()["user"]["id"])
    return list(folder.iterdir()) if folder.exists() else []


def test_removing_a_file_empties_the_disk(client):
    f = attach(client, entry(client)).json()
    assert len(_on_disk(client)) == 3
    assert client.delete(f"{API}/files/{f['id']}").status_code == 200
    assert _on_disk(client) == []


def test_removing_an_entry_takes_its_files(client):
    event = entry(client)
    attach(client, event)
    assert client.delete(f"{API}/events/{event}").status_code == 200
    assert _on_disk(client) == []


def test_moving_the_log_to_another_calendar_takes_its_files(client):
    from app.sections.logmylife import store
    me = client.get("/api/auth/status").json()["user"]["id"]
    store.ingest(me, "google", "cal1:e1", title="Møde", start="2015-01-01", all_day=True)
    event = client.get(f"{API}/timeline").json()["rows"][0][0]
    attach(client, event)
    assert store.forget(me, "google", "cal1:") == 1
    assert _on_disk(client) == []


def test_a_picture_can_go_on_an_entry_from_a_source(client):
    from app.sections.logmylife import store
    me = client.get("/api/auth/status").json()["user"]["id"]
    store.ingest(me, "google", "e1", title="Fra kalenderen", start="2015-01-01", all_day=True)
    event = client.get(f"{API}/timeline").json()["rows"][0][0]
    assert attach(client, event).status_code == 200


def test_deleting_a_person_clears_their_folder(client, family):
    from app.sections.logmylife import files
    r = attach(family, entry(family))
    assert r.status_code == 200 and files.folder(family.user_id).exists()
    assert client.delete(f"/api/admin/users/{family.user_id}").status_code == 200
    assert not files.folder(family.user_id).exists()


def test_the_page_says_how_much_is_stored(client):
    attach(client, entry(client))
    usage = client.get(f"{API}/meta").json()["files"]
    assert usage["count"] == 1 and usage["bytes"] > 0 and usage["free"] > 0


# ---- export ------------------------------------------------------------------------

def _zip(client, **params) -> zipfile.ZipFile:
    r = client.get(f"{API}/export", params=params)
    assert r.status_code == 200 and "logmylife-" in r.headers["content-disposition"]
    return zipfile.ZipFile(io.BytesIO(r.content))


def test_the_zip_has_entries_and_files(client):
    event = entry(client, "Tur, nummer 1", location="Skagen", description="Sol; og vand")
    attach(client, event)
    archive = _zip(client)
    names = archive.namelist()
    assert {"index.html", "entries.json", "entries.csv", "entries.ics"} <= set(names)
    stored = next(n for n in names if n.startswith("files/"))
    assert stored.startswith("files/2014/2014-06-12-") and stored.endswith("-billede.jpg")
    assert archive.read(stored) == picture()
    assert archive.testzip() is None
    data = json.loads(archive.read("entries.json"))
    assert data["entries"][0]["title"] == "Tur, nummer 1" and data["entries"][0]["files"][0]["path"] == stored
    assert stored in archive.read("index.html").decode()


def test_a_zip_is_only_ones_own(client, family):
    entry(client, "Mit", shared=True)
    entry(family, "Hendes")
    assert [e["title"] for e in json.loads(_zip(family).read("entries.json"))["entries"]] == ["Hendes"]


def test_a_period_and_a_search_narrow_the_export(client):
    entry(client, "Gammel", "2010-01-01")
    entry(client, "Ny", "2020-01-01")
    data = client.get(f"{API}/export", params={"format": "json", "since": "2015-01-01"}).json()
    assert [e["title"] for e in data["entries"]] == ["Ny"]
    data = client.get(f"{API}/export", params={"format": "json", "q": "Gammel"}).json()
    assert [e["title"] for e in data["entries"]] == ["Gammel"]


def test_the_csv_opens_in_a_danish_excel(client):
    entry(client, "=1+1", description="æøå; med semikolon")
    text = client.get(f"{API}/export", params={"format": "csv"}).content.decode("utf-8")
    assert text.startswith("﻿Dato;Til og med;")
    assert "'=1+1" in text                  # a title is not a formula
    assert '"æøå; med semikolon"' in text


def test_the_calendar_file(client):
    entry(client, "Ferie, i; Skagen", "2015-07-01", end="2015-07-14")
    text = client.get(f"{API}/export", params={"format": "ics"}).text
    assert "DTSTART;VALUE=DATE:20150701" in text and "DTEND;VALUE=DATE:20150715" in text       # the end is exclusive
    assert "SUMMARY:Ferie\\, i\\; Skagen" in text and text.endswith("END:VCALENDAR\r\n")


def test_long_calendar_lines_are_folded(client):
    entry(client, "æ" * 200)
    lines = client.get(f"{API}/export", params={"format": "ics"}).content.split(b"\r\n")
    assert max(len(line) for line in lines) <= 75


def test_an_unknown_format_is_refused(client):
    assert client.get(f"{API}/export", params={"format": "docx"}).status_code == 400


def test_the_export_page_escapes_what_it_shows(client):
    entry(client, "<img src=x onerror=alert(1)>")
    assert "<img src=x" not in _zip(client).read("index.html").decode()


def test_a_zip_comes_out_in_pieces(client):
    from app.sections.logmylife import export
    me = client.get("/api/auth/status").json()["user"]["id"]
    attach(client, entry(client))
    pieces = list(export.as_zip(export.entries(me)))
    assert len(pieces) > 2
    assert zipfile.ZipFile(io.BytesIO(b"".join(pieces))).testzip() is None


@pytest.mark.parametrize("name,clean", [("a/b\\c.jpg", "c.jpg"), ("\x00sjov\x07.png", "sjov.png"), ("", "fil")])
def test_names(name, clean):
    from app.sections.logmylife.files import _clean_name
    assert _clean_name(name) == clean


# ---- Strava's zip ----------------------------------------------------------------

DANISH = (
    "Aktivitets-id,Aktivitetsdato,Aktivitetsnavn,Aktivitetstype,Beskrivelse af aktiviteten,Varighed,Distance,"
    "Filnavn,Varighed,Distance,Medier\n"
    '11,"14. okt. 2023, 17.05.09",Aftentur,Løb,,1800,"5,02",activities/11.gpx.gz,1800.0,5020.0,media/a.jpg|media/b.jpg\n'
    '12,"1. maj 2024, 06.30.00",I svømmehallen,Svømning,,1200,1000,activities/12.fit.gz,1200.0,1000.0,\n'
    '13,"31. dec. 2024, 23.30.00",Nytårsløb,Løb,,600,"2,1",,600.0,2100.0,\n'
)


def strava_zip(rows: str = DANISH, **more) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("activities.csv", rows.encode())
        z.writestr("activities/11.gpx.gz", b"spor")
        z.writestr("activities/12.fit.gz", b"spor")
        z.writestr("media/a.jpg", picture())
        z.writestr("media/b.jpg", picture())
        z.writestr("logins.csv", b"ikke til dashboardet")
        for name, content in more.items():
            z.writestr(name, content)
    return out.getvalue()


def strava_events(client) -> list[dict]:
    return client.get("/api/s/logmylife/events?source=strava").json()["events"]


def test_a_danish_export_is_read(client):
    r = client.post("/api/s/logmylife/import/strava", content=DANISH.encode())
    assert r.status_code == 200 and r.json()["added"] == 3 and r.json()["skipped"] == 0
    new_year, swim, evening = strava_events(client)
    assert evening["start"] == "2023-10-14T17:05:09Z" and evening["description"] == "Løb, 5,0 km, 30 min"
    assert swim["start"] == "2024-05-01T06:30:00Z"
    assert new_year["day"] == "2025-01-01"          # the date is UTC, the day is here


def test_a_swim_is_counted_in_metres(client):
    client.post("/api/s/logmylife/import/strava", content=DANISH.encode())
    assert strava_events(client)[1]["description"] == "Svømning, 1,0 km, 20 min"


def test_the_whole_zip_brings_pictures_and_tracks(client):
    r = client.post("/api/s/logmylife/import/strava", content=strava_zip())
    assert r.status_code == 200 and r.json()["added"] == 3 and r.json()["files"] == 4
    events = {e["title"]: e for e in strava_events(client)}
    attached = client.get(f"/api/s/logmylife/events/{events['Aftentur']['id']}").json()["files"]
    assert sorted((f["name"], f["kind"]) for f in attached) == [("11.gpx.gz", "file"), ("a.jpg", "image"), ("b.jpg", "image")]


def test_importing_the_zip_again_adds_nothing(client):
    client.post("/api/s/logmylife/import/strava", content=strava_zip())
    r = client.post("/api/s/logmylife/import/strava", content=strava_zip()).json()
    assert r["added"] == 0 and r["same"] == 3 and r["files"] == 0


def test_nothing_else_in_the_zip_is_touched(client):
    client.post("/api/s/logmylife/import/strava", content=strava_zip())
    names = [f["name"] for e in strava_events(client) for f in client.get(f"/api/s/logmylife/events/{e['id']}").json()["files"]]
    assert "logins.csv" not in names and len(names) == 4


def test_a_row_naming_a_file_the_zip_lacks_is_fine(client):
    rows = DANISH.replace("activities/12.fit.gz", "activities/mangler.fit.gz")
    r = client.post("/api/s/logmylife/import/strava", content=strava_zip(rows)).json()
    assert r["added"] == 3 and r["files"] == 3


def test_a_name_from_the_file_cannot_climb_out(client):
    rows = DANISH.replace("activities/12.fit.gz", "../../../etc/passwd")
    r = client.post("/api/s/logmylife/import/strava", content=strava_zip(rows)).json()
    assert r["added"] == 3 and r["files"] == 3


def test_the_whole_row_is_kept(client):
    client.post("/api/s/logmylife/import/strava", content=strava_zip())
    with db.connect() as con:
        raw = json.loads(con.execute("SELECT raw FROM life_events WHERE title='Aftentur'").fetchone()["raw"])
    assert raw["columns"]["Aktivitetsnavn"] == "Aftentur" and raw["columns"]["Filnavn"] == "activities/11.gpx.gz"


def test_a_zip_without_activities_says_so(client):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("noget.txt", b"x")
    r = client.post("/api/s/logmylife/import/strava", content=out.getvalue())
    assert r.status_code == 400 and "activities.csv" in r.json()["detail"]


def test_the_upload_leaves_nothing_behind(client):
    client.post("/api/s/logmylife/import/strava", content=strava_zip())
    client.post("/api/s/logmylife/import/strava", content=b"PK\x03\x04 ikke en zip")
    assert not list((db.data_dir() / "logmylife").rglob(".incoming-*"))
