"""What the sections do with their data."""
from __future__ import annotations

import ast
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest

CPH = ZoneInfo("Europe/Copenhagen")


# ---- Links -------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("slq.dk", "https://slq.dk"),
    ("https://slq.dk/x", "https://slq.dk/x"),
    ("30.11.0.6:10086", "http://30.11.0.6:10086"),
    ("http://dklive.lan", "http://dklive.lan"),
])
def test_addresses_are_completed(raw, expected):
    from app.sections.links.store import clean_url
    assert clean_url(raw) == expected


@pytest.mark.parametrize("raw", ["javascript:alert(1)", "data:text/html,x", "ftp://x.dk", ""])
def test_other_schemes_are_refused(raw):
    from app.sections.links.store import Problem, clean_url
    with pytest.raises(Problem):
        clean_url(raw)


def test_folder_tree_and_cascade(client):
    a = client.post("/api/s/links/folders", json={"name": "Arbejde"}).json()
    b = client.post("/api/s/links/folders", json={"name": "Beckhoff", "parentId": a["id"]}).json()
    client.post("/api/s/links/items", json={"url": "infosys.beckhoff.com", "folderId": b["id"]})
    assert client.get(f"/api/s/links/folders/{a['id']}/size").json() == {"folders": 1, "links": 1}
    client.delete(f"/api/s/links/folders/{a['id']}")
    tree = client.get("/api/s/links/tree").json()
    assert tree == {"folders": [], "links": []}


def test_a_folder_cannot_move_into_itself(client):
    a = client.post("/api/s/links/folders", json={"name": "A"}).json()
    b = client.post("/api/s/links/folders", json={"name": "B", "parentId": a["id"]}).json()
    r = client.patch(f"/api/s/links/folders/{a['id']}", json={"parentId": b["id"]})
    assert r.status_code == 400


def test_links_are_each_persons_own(client, family):
    link = client.post("/api/s/links/items", json={"url": "slq.dk"}).json()
    assert family.get("/api/s/links/tree").json()["links"] == []
    assert family.patch(f"/api/s/links/items/{link['id']}", json={"title": "x"}).status_code == 404
    assert family.delete(f"/api/s/links/items/{link['id']}").status_code == 404


def test_pinned_links_are_on_the_overview(client):
    client.post("/api/s/links/items", json={"url": "slq.dk", "title": "SLQ", "pinned": True})
    client.post("/api/s/links/items", json={"url": "dr.dk", "title": "DR"})
    block = client.get("/api/overview").json()["blocks"]["links"]
    assert [l["title"] for l in block["pinned"]] == ["SLQ"]
    assert block["total"] == 2


# ---- LogMyLife ---------------------------------------------------------------------

def test_own_entry_round_trip(client):
    r = client.post("/api/s/logmylife/events", json={"title": "Italiensturen", "start": "2015-07-03", "end": "2015-07-10"})
    assert r.status_code == 200
    e = r.json()
    assert e["source"] == "manual" and e["day"] == "2015-07-03" and e["allDay"] is True
    events = client.get("/api/s/logmylife/events").json()["events"]
    assert [x["title"] for x in events] == ["Italiensturen"]
    assert client.delete(f"/api/s/logmylife/events/{e['id']}").status_code == 200


@pytest.mark.parametrize("body", [
    {"title": "", "start": "2015-07-03"},
    {"title": "x", "start": "ikke en dato"},
    {"title": "x", "start": "2015-07-03", "end": "2015-07-01"},
    {"title": "x", "start": "2015-07-03", "category": "Ukendt"},
])
def test_bad_entries_are_refused(client, body):
    assert client.post("/api/s/logmylife/events", json=body).status_code == 400


def _me(client):
    return client.get("/api/auth/status").json()["user"]["id"]


def test_ingest_is_safe_to_repeat(client):
    from app.sections.logmylife import store
    uid = _me(client)
    args = dict(title="Møde", start="2020-03-01T09:00:00+01:00", end="2020-03-01T10:00:00+01:00")
    assert store.ingest(uid, "google", "c|1", **args) == "added"
    assert store.ingest(uid, "google", "c|1", **args) == "same"
    assert store.ingest(uid, "google", "c|1", **{**args, "title": "Nyt navn"}) == "updated"
    assert store.stats(uid)["total"] == 1


def test_a_deleted_event_is_remembered_and_can_return(client):
    from app.sections.logmylife import store
    uid = _me(client)
    store.ingest(uid, "google", "c|1", title="Møde", start="2020-03-01T09:00:00Z")
    assert store.mark_deleted(uid, "google", "c|1") is True
    events = client.get("/api/s/logmylife/events").json()["events"]
    assert len(events) == 1 and events[0]["deletedAtSource"]
    store.ingest(uid, "google", "c|1", title="Møde", start="2020-03-01T09:00:00Z")
    assert client.get("/api/s/logmylife/events").json()["events"][0]["deletedAtSource"] is None


def test_what_came_from_a_source_cannot_be_deleted_by_hand(client):
    from app.sections.logmylife import store
    uid = _me(client)
    store.ingest(uid, "google", "c|1", title="Møde", start="2020-03-01T09:00:00Z")
    e = client.get("/api/s/logmylife/events").json()["events"][0]
    assert client.delete(f"/api/s/logmylife/events/{e['id']}").status_code == 400
    r = client.put(f"/api/s/logmylife/events/{e['id']}", json={"title": "Hacket", "shared": True})
    assert r.json()["title"] == "Møde" and r.json()["shared"] is True


def test_day_is_local_not_utc(client):
    from app.sections.logmylife import store
    uid = _me(client)
    # 23:30 UTC on 31 December is already New Year's Day in Copenhagen.
    store.ingest(uid, "google", "c|2", title="Nytår", start="2019-12-31T23:30:00Z")
    assert client.get("/api/s/logmylife/events").json()["events"][0]["day"] == "2020-01-01"


def test_sharing_with_the_family(client, family):
    a = client.post("/api/s/logmylife/events", json={"title": "Privat", "start": "2015-01-01"}).json()
    b = client.post("/api/s/logmylife/events", json={"title": "Delt", "start": "2015-01-02", "shared": True}).json()
    assert family.get("/api/s/logmylife/events").json()["events"] == []
    seen = family.get("/api/s/logmylife/events?scope=family").json()["events"]
    assert [e["title"] for e in seen] == ["Delt"] and seen[0]["mine"] is False
    assert family.delete(f"/api/s/logmylife/events/{b['id']}").status_code == 404
    assert family.put(f"/api/s/logmylife/events/{a['id']}", json={"title": "x", "start": "2015-01-01"}).status_code == 404


def test_on_this_day_finds_earlier_years_only(client):
    from app.sections.logmylife import store
    uid = _me(client)
    today = store.today()
    for title, day in (("Sidste år", f"{int(today[:4]) - 1}{today[4:]}"), ("I år", today), ("Anden dag", "2001-01-15")):
        client.post("/api/s/logmylife/events", json={"title": title, "start": day})
    assert [e["title"] for e in store.on_this_day(uid)] == ["Sidste år"]


# ---- Kalender ----------------------------------------------------------------------

def test_google_all_day_end_is_exclusive_and_ours_is_inclusive():
    from app.sections.calendar.sync import event_fields
    one = event_fields({"summary": "Fødselsdag", "start": {"date": "2026-11-23"}, "end": {"date": "2026-11-24"}})
    assert (one["start"], one["end"], one["all_day"]) == ("2026-11-23", None, True)
    three = event_fields({"summary": "Tur", "start": {"date": "2026-11-23"}, "end": {"date": "2026-11-26"}})
    assert three["end"] == "2026-11-25"


def test_google_event_without_title_and_without_start():
    from app.sections.calendar.sync import event_fields
    assert event_fields({"start": {"date": "2026-01-01"}, "end": {"date": "2026-01-02"}})["title"] == "(uden titel)"
    assert event_fields({"summary": "x"}) is None


def test_sync_copies_events_and_keeps_deleted_ones(client, monkeypatch):
    from app.core import db, google, vault
    from app.sections.calendar import sync
    from app.sections.logmylife import store

    uid = _me(client)
    with db.connect() as con:
        con.execute("INSERT INTO google_accounts (user_id, email, refresh_token, connected_at) VALUES (?,?,?,?)",
                    (uid, "a@b.dk", vault.seal("refresh"), db.utcnow()))
    monkeypatch.setattr(google, "access_token", lambda _r: "token")
    monkeypatch.setattr(google, "calendars", lambda _t: [{"id": "cal", "summary": "Min", "color": "", "primary": True}])
    rounds = [
        ([{"id": "e1", "summary": "Møde", "start": {"dateTime": "2020-05-05T09:00:00+02:00"}, "end": {"dateTime": "2020-05-05T10:00:00+02:00"}}], "tok1"),
        ([{"id": "e1", "status": "cancelled"}], "tok2"),
    ]
    seen_tokens = []

    def events(_t, _cal, token):
        seen_tokens.append(token)
        return rounds.pop(0)

    monkeypatch.setattr(google, "events", events)
    assert sync.sync_user(uid)["added"] == 1
    assert sync.sync_user(uid)["deleted"] == 1
    assert seen_tokens == [None, "tok1"]
    event = store.timeline(uid)["events"][0]
    assert event["title"] == "Møde" and event["deletedAtSource"]


def test_expired_sync_token_starts_over(client, monkeypatch):
    from app.core import db, google, vault
    from app.sections.calendar import sync

    uid = _me(client)
    with db.connect() as con:
        con.execute("INSERT INTO google_accounts (user_id, email, refresh_token, connected_at) VALUES (?,?,?,?)",
                    (uid, "a@b.dk", vault.seal("refresh"), db.utcnow()))
        con.execute("INSERT INTO google_calendars (user_id, calendar_id, sync_token) VALUES (?,?,?)", (uid, "cal", "old"))
    monkeypatch.setattr(google, "access_token", lambda _r: "token")
    monkeypatch.setattr(google, "calendars", lambda _t: [{"id": "cal", "summary": "Min", "color": "", "primary": True}])
    calls = []

    def events(_t, _cal, token):
        calls.append(token)
        if token:
            raise google.SyncTokenGone("forfra")
        return [], "new"

    monkeypatch.setattr(google, "events", events)
    sync.sync_user(uid)
    assert calls == ["old", None]


def test_revoked_consent_asks_to_reconnect(client, monkeypatch):
    from app.core import db, google, vault
    from app.sections.calendar import sync

    uid = _me(client)
    with db.connect() as con:
        con.execute("INSERT INTO google_accounts (user_id, email, refresh_token, connected_at) VALUES (?,?,?,?)",
                    (uid, "a@b.dk", vault.seal("refresh"), db.utcnow()))

    def refused(_r):
        raise google.NeedsReconnect("Forbind igen.")

    monkeypatch.setattr(google, "access_token", refused)
    sync.sync_user(uid)
    assert sync.state_of(uid)["status"] == "reconnect"


def test_only_the_read_scope_and_no_write_verbs():
    """Google to log only: the token cannot write, and the code never tries."""
    from app.core import google
    assert google.SCOPE.endswith("calendar.readonly")
    source = Path(google.__file__).read_text(encoding="utf-8")
    assert "httpx.put" not in source and "httpx.patch" not in source and "httpx.delete" not in source
    # The one POST is the token endpoint.
    assert source.count("httpx.post(") == 1 and "httpx.post(_token_url()" in source


def test_state_works_once_and_for_one_person():
    from app.core import google
    state = google.new_state(7)
    assert google.take_state(state) == 7
    assert google.take_state(state) is None
    assert google.take_state("gættet") is None


def test_connect_needs_the_client_set_up(client):
    assert client.post("/api/s/calendar/connect").status_code == 400


# ---- Nyheder -----------------------------------------------------------------------

RSS = """<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Regeringen annoncerede i dag en plan</title><link>https://x.dk/1</link>
  <description><![CDATA[<p>Tekst med <b>tags</b> &amp; tegn</p><script>alert(1)</script>]]></description>
  <pubDate>Fri, 06 Nov 2026 06:00:00 +0100</pubDate><category>Politik</category></item>
<item><title>Annonce: Køb en bil</title><link>https://x.dk/2</link></item>
<item><title>Ny bil til dig</title><link>https://x.dk/3</link><category>Annonce</category></item>
<item><title>Sådan sparer du penge</title><link>https://x.dk/annonce/4</link></item>
<item><title>Klubben fik ny sponsor</title><link>https://x.dk/5</link></item>
<item><title>Uden adresse</title></item>
</channel></rss>"""


def test_feed_keeps_news_drops_paid_and_strips_html():
    from app.sections.news.feed import parse
    items, dropped = parse(RSS, "DR")
    assert [i["url"] for i in items] == ["https://x.dk/1", "https://x.dk/5"]
    assert dropped == 3
    assert items[0]["summary"] == "Tekst med tags & tegn"
    assert items[0]["at"] == "2026-11-06T05:00:00Z"


def test_atom_feeds_work():
    from app.sections.news.feed import parse
    atom = """<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Hej</title>
    <link href="https://x.dk/a"/><summary>Kort</summary><updated>2026-11-06T06:00:00Z</updated></entry></feed>"""
    items, _ = parse(atom, "Atom")
    assert items[0]["url"] == "https://x.dk/a" and items[0]["summary"] == "Kort"


def test_the_same_story_shows_once_newest_first():
    from app.sections.news import feed
    feed._cache.clear()
    feed._cache["a"] = {"items": [{"title": "Stor nyhed!", "at": "2026-01-01T10:00:00Z", "source": "DR"}]}
    feed._cache["b"] = {"items": [{"title": "stor nyhed", "at": "2026-01-01T09:00:00Z", "source": "TV 2"},
                                  {"title": "Nyere", "at": "2026-01-01T11:00:00Z", "source": "TV 2"}]}
    assert [i["title"] for i in feed.merged()] == ["Nyere", "Stor nyhed!"]
    feed._cache.clear()


# ---- Formel 1 ----------------------------------------------------------------------

def _jolpica():
    return {"MRData": {"RaceTable": {"Races": [{
        "season": "2026", "round": "20", "raceName": "Brazilian Grand Prix",
        "Circuit": {"circuitName": "Interlagos", "Location": {"country": "Brazil"}},
        "date": "2026-11-08", "time": "17:00:00Z",
        "FirstPractice": {"date": "2026-11-06", "time": "15:30:00Z"},
        "SprintQualifying": {"date": "2026-11-06", "time": "19:30:00Z"},
        "Sprint": {"date": "2026-11-07", "time": "15:00:00Z"},
        "Qualifying": {"date": "2026-11-07", "time": "19:00:00Z"},
    }]}}}


def test_season_parses_like_the_f1_app():
    from app.sections.f1.schedule import parse
    sessions = parse(_jolpica())
    assert [s["name"] for s in sessions] == ["1. træning", "Sprintkvalifikation", "Sprint", "Kvalifikation", "Løb"]
    assert sessions[-1]["race"] is True and sessions[-1]["minutes"] == 120


def test_next_session_and_weekend(client):
    from app.sections.f1 import schedule
    schedule._sessions[:] = schedule.parse(_jolpica())
    now = datetime(2026, 11, 6, 16, 0, tzinfo=timezone.utc)
    assert schedule.upcoming(now)[0]["name"] == "1. træning"      # still running
    later = datetime(2026, 11, 8, 19, 30, tzinfo=timezone.utc)
    assert schedule.upcoming(later) == []
    schedule.reset()


# ---- DK live -----------------------------------------------------------------------

def test_current_price_is_the_slot_we_are_in():
    from app.sections.dklive import client as dk
    at = lambda h, m: int(datetime(2026, 11, 6, h, m, tzinfo=timezone.utc).timestamp() * 1000)
    data = {"area": "DK1", "prices": [{"time": at(5, 0), "dkk": 1.8}, {"time": at(6, 0), "dkk": 2.4},
                                      {"time": at(6, 15), "dkk": 2.43}, {"time": at(7, 0), "dkk": 1.2}]}
    power = dk.build_power(data, datetime(2026, 11, 6, 6, 20, tzinfo=timezone.utc))
    assert power["now"] == 2.43
    assert power["low"]["dkk"] == 1.2 and power["high"]["dkk"] == 2.43       # from now on, not the past
    assert [p["dkk"] for p in power["series"]][0] == 1.8                     # earlier today stays on the band


def test_prices_older_than_the_band_are_left_out():
    from app.sections.dklive import client as dk
    now = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)
    old = int((now - timedelta(hours=40)).timestamp() * 1000)
    fresh = int((now - timedelta(hours=1)).timestamp() * 1000)
    power = dk.build_power({"prices": [{"time": old, "dkk": 9.0}, {"time": fresh, "dkk": 1.0}]}, now)
    assert [p["dkk"] for p in power["series"]] == [1.0]


def test_updates_are_merged_near_home_marked():
    from app.sections.dklive.client import build_updates, headline_updates
    home = (56.0, 10.0)
    t = datetime(2026, 11, 6, 6, 0, tzinfo=timezone.utc)
    stamp = lambda minutes: int((t - timedelta(minutes=minutes)).timestamp() * 1000)
    out = build_updates(
        {"alarms": [{"id": "a", "time": stamp(5), "message": "Brandalarm", "station": "København", "lat": 55.68, "lon": 12.57},
                    {"id": "b", "time": stamp(50), "message": "Brand", "station": "Hammel", "lat": 56.26, "lon": 9.86},
                    {"id": "c", "time": stamp(2), "message": "Eftersyn", "station": "Skanderborg", "lat": 56.04, "lon": 9.93}]},
        {"cases": [{"id": "p", "title": "Sag", "last": stamp(10)}]},
        {"events": [{"id": "t", "header": "Uheld på E45", "modified": stamp(20), "lat": 56.1, "lon": 9.95, "blocking": True},
                    {"id": "u", "title": "Kø", "modified": stamp(1), "lat": 55.7, "lon": 12.5}]},
        home)
    assert out["feed"][0]["title"] == "Kø"
    assert out["traffic"] == {"total": 2, "near": 1, "blocking": 1, "items": out["traffic"]["items"]}
    assert out["traffic"]["items"][0]["title"] == "Uheld på E45"
    top = headline_updates(out["feed"], t)
    assert [f["title"] for f in top] == ["Brand", "Brandalarm", "Sag"]       # near first, no routine, no traffic


def test_weather_times_become_real_instants():
    from app.sections.dklive.client import build_weather
    w = build_weather({"current": {"temperature_2m": 7, "weather_code": 3},
                       "hourly": [{"time": "2026-11-06T07:00", "temperature_2m": 7}]}, CPH)
    assert w["hourly"][0]["t"] == "2026-11-06T06:00:00Z" and w["text"] == "overskyet"


def test_the_overview_block_needs_no_setup(client):
    block = client.get("/api/overview").json()["blocks"]["dklive"]
    assert block["layers"] == ["alarms", "traffic", "lightning", "radar"] and block["power"] is None


# ---- FamilyLog ---------------------------------------------------------------------

def test_familylog_client_can_only_read():
    """"Can't post, only search": no HTTP verb but GET in the module."""
    from app.sections.familylog import client as fl
    tree = ast.parse(Path(fl.__file__).read_text(encoding="utf-8"))
    verbs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
             and isinstance(n.value, ast.Name) and n.value.id == "httpx"}
    assert verbs - {"HTTPError"} == {"get"}


def test_familylog_key_is_sealed_and_per_person(client, family):
    from app.core import db
    from app.sections.familylog import client as fl
    client.put(f"/api/admin/users/{family.user_id}/familylog-key", json={"key": "flk_hemmelig_1234"})
    with db.connect() as con:
        row = con.execute("SELECT sealed FROM familylog_keys").fetchone()
    assert "hemmelig" not in row["sealed"]
    assert fl.key_hint(family.user_id) == "1234"
    assert "flk_hemmelig" not in client.get("/api/admin/users").text
    client.put(f"/api/admin/users/{family.user_id}/familylog-key", json={"key": None})
    assert fl.key_hint(family.user_id) == ""


# ---- SLQ DL ------------------------------------------------------------------------

def _seed():
    from app.sections.latenight import store
    return json.loads(store.SEED.read_text(encoding="utf-8"))


def test_every_seed_fact_is_dated_and_sourced():
    from app.sections.latenight import store
    seed = _seed()
    keys = set()
    for f in seed["facts"]:
        date.fromisoformat(f["d"])
        assert f["t"] and f["s"] in seed["sources"], f
        assert f.get("k", "historie") in store.KINDS, f
        assert f.get("st", "") in ("", *store.STORIES), f
        key = f"{f['d']}:{f['t'][:40]}"
        assert key not in keys, f"duplicate: {key}"
        keys.add(key)
    assert len(seed["facts"]) >= 90


def test_seed_loads_once_and_keeps_edits(client):
    from app.sections.latenight import store
    assert store.load_seed() == 0      # lifespan already did it
    fact = store.facts(q="Hugh Grant")[0]
    client.put(f"/api/s/latenight/facts/{fact['id']}", json={**fact, "title": "Rettet"})
    store.load_seed()
    assert store.facts(q="Rettet")


def test_on_this_date_with_years_ago(client):
    from app.sections.latenight import store
    out = store.on_date(date(2026, 11, 6))
    assert out["exact"][0]["date"] == "2009-11-06" and out["exact"][0]["yearsAgo"] == 17


def test_quiet_days_look_at_the_days_around(client):
    from app.sections.latenight import store
    out = store.on_date(date(2026, 8, 31))           # Late Show's premiere was the day before
    assert not out["exact"] and out["near"][0]["date"] == "1993-08-30"


def test_future_facts_are_not_told_before_they_happen(client):
    from app.sections.latenight import store
    out = store.on_date(date(2015, 5, 21))
    assert all(f["date"] <= "2015-05-21" for f in out["exact"] + out["near"])


def test_filters(client):
    from app.sections.latenight import store
    assert all("Carson" in f["hosts"] for f in store.facts(host="Carson"))
    assert all(f["date"].startswith("199") for f in store.facts(decade="1990"))
    assert len(store.facts(story="arvefoelgen")) >= 10


def test_only_admin_changes_facts(client, family):
    body = {"date": "1999-01-01", "title": "Test"}
    assert family.post("/api/s/latenight/facts", json=body).status_code == 403
    r = client.post("/api/s/latenight/facts", json=body)
    assert r.status_code == 200
    assert family.delete(f"/api/s/latenight/facts/{r.json()['id']}").status_code == 403
    assert family.get("/api/s/latenight/today").status_code == 200


def test_a_fact_source_must_be_a_web_address(client):
    body = {"date": "1999-01-01", "title": "Test", "sourceUrl": "javascript:alert(1)"}
    assert client.post("/api/s/latenight/facts", json=body).status_code == 400


# ---- FamilyLog, the sync ------------------------------------------------------------

def test_dagbog_day_becomes_a_timeline_entry():
    from app.sections.familylog.client import dagbog_fields
    f = dagbog_fields({"day": "2026-11-01", "mood": 4, "mental": 7, "tags": ["Sport"], "highlight": "God tur\nMed børnene"})
    assert f["title"] == "God tur" and f["all_day"] is True
    assert "Med børnene" in f["description"] and "Humør 4 af 5" in f["description"] and "Sport" in f["description"]
    assert dagbog_fields({"day": "2026-11-02", "mood": 3})["title"] == "Dagbog, humør 3 af 5"
    assert dagbog_fields({"mood": 3}) is None


def test_review_lands_on_the_day_of_the_visit():
    from app.sections.familylog.client import review_fields
    f = review_fields({"visitedOn": "2026-06-01", "placeName": "Legeland", "text": " Fint ", "createdAt": "2026-07-01T10:00:00"})
    assert (f["start"], f["title"], f["description"], f["location"]) == ("2026-06-01", "Besøg: Legeland", "Fint", "Legeland")
    assert review_fields({"placeName": "X", "createdAt": "2026-07-01T10:00:00"})["start"] == "2026-07-01"


class _FakeFamilyLog:
    """Stands in for client.get. Records the paths, so a test sees what is read."""

    def __init__(self, days, reviews=(), economy=True):
        self.days, self.reviews, self.economy, self.calls = list(days), list(reviews), economy, []

    def __call__(self, _user, path, params=None):
        self.calls.append((path, params))
        if path == "/api/read/me":
            return {"id": 42, "username": "x", "name": ""}
        if path == "/api/okonomi/state":
            return {"access": self.economy}
        if path == "/api/okonomi/overview":
            return {"spent": 1234.5, "income": 100, "count": 7, "categories": [{"name": "Mad", "spent": 500}]}
        if path == "/api/fm/me/reviews":
            return self.reviews
        if path == "/api/dagbog/person":
            before = (params or {}).get("before")
            rows = [d for d in self.days if not before or d["day"] < before]
            page = rows[:params["limit"]]
            return {"entries": page, "more": len(rows) > len(page)}
        raise AssertionError(path)


def test_sync_reads_everything_once_then_stops_early(client, monkeypatch):
    from app.sections.familylog import client as fl
    from app.sections.logmylife import store
    uid = _me(client)
    days = [{"day": (date(2026, 11, 1) - timedelta(days=i)).isoformat(), "mood": 3} for i in range(150)]
    fake = _FakeFamilyLog(days, [{"id": 5, "placeName": "Legeland", "visitedOn": "2026-06-01", "text": ""}])
    monkeypatch.setattr(fl, "get", fake)
    first = fl.sync_user(uid)
    assert first["added"] == 151 and first["error"] == ""
    assert first["month"]["spent"] == 1234.5
    assert store.stats(uid)["bySource"] == {"familylog.dagbog": 150, "familylog.familymap": 1}
    assert [p for p, _ in fake.calls].count("/api/dagbog/person") == 3
    fake.calls.clear()
    assert fl.sync_user(uid)["added"] == 0
    assert [p for p, _ in fake.calls].count("/api/dagbog/person") == 1
    assert fake.calls[1][0] == "/api/okonomi/state"
    assert next(p for p, _ in fake.calls if p == "/api/dagbog/person")
    assert all(p != "/api/dagbog/person" or a["user"] == 42 for p, a in fake.calls)


def test_a_person_without_okonomi_still_syncs(client, monkeypatch):
    from app.sections.familylog import client as fl
    monkeypatch.setattr(fl, "get", _FakeFamilyLog([], economy=False))
    out = fl.sync_user(_me(client))
    assert out["month"] is None and out["error"] == ""


def test_overview_shows_the_month_without_calling_familylog(client, monkeypatch):
    from app.sections.familylog import client as fl
    uid = _me(client)
    monkeypatch.setattr(fl, "get", _FakeFamilyLog([]))
    fl.sync_user(uid)

    def nope(*_a, **_k):
        raise AssertionError("the overview must not call an upstream")

    monkeypatch.setattr(fl, "get", nope)
    assert client.get("/api/overview").json()["blocks"]["familylog"]["month"]["spent"] == 1234.5


def test_search_skips_okonomi_when_the_person_has_none(client, monkeypatch):
    from app.sections.familylog import client as fl

    def get(_u, path, _p=None):
        if "okonomi" in path:
            raise fl.Refused(path)
        return [{"id": 1, "name": "Legeland", "address": "Vej 1"}]

    monkeypatch.setattr(fl, "get", get)
    out = client.get("/api/s/familylog/search?q=lege").json()
    assert out["transactions"] is None and out["places"][0]["name"] == "Legeland"


# ---- SLQ DL, the monologues ---------------------------------------------------------

@pytest.mark.parametrize("show,title,keep", [
    ("kimmel", "Trump Rants & Raves About the Least Important Things Ever", True),
    ("kimmel", "Jimmy Kimmel Breaks Down Midterm Election Results, Trump Loses Bigly", True),
    ("kimmel", "Timothy Simons on Major Soup Fail, Getting into Politics", False),
    ("kimmel", "Pod Save America Hosts on Midterm Results", False),
    ("kimmel", "Cage the Elephant – Make It Easy", False),
    ("fallon", "Trump's Cabinet Distances Themselves from Him After Midterms | The Tonight Show", True),
    ("fallon", "Memory Drawing Challenge with Carrie Coon | The Tonight Show Starring Jimmy Fallon", False),
    ("fallon", "Chef Anthony Vitolo Cooks His Classic Spaghetti Pomodoro with Jimmy | The Tonight Show", False),
    ("fallon", "Ethan Hawke Talks Attending Maya Hawke's Wedding", False),
    ("meyers", "Trump Soothes Himself with Renovations After Midterms: A Closer Look", True),
    ("meyers", "John Malkovich Talks Wild Horse Nine with Sam Rockwell", False),
    ("daily", "Trump Reacts to Midterm Defeat by Focusing on the Ballroom | The Daily Show", True),
    ("daily", "Teddy Schleifer on Elon Musk's $500M Election Flop | The Daily Show", False),
    ("daily", "Min Jin Lee - Family, Education & Sacrifice | The Daily Show", False),
    ("oliver", "Generic Drugs: Last Week Tonight with John Oliver (HBO)", True),
    ("oliver", "S13 E26: Kimberly Guilfoyle & Generic Drugs: 10/11/26: Last Week Tonight with John Oliver", False),
])
def test_what_counts_as_a_monologue(show, title, keep):
    from app.sections.latenight.monologues import SHOWS
    assert next(s for s in SHOWS if s["id"] == show)["keep"](title) is keep


FEED = """<?xml version="1.0"?><feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns="http://www.w3.org/2005/Atom">
<entry><yt:videoId>abc</yt:videoId><title>Trump Does It Again</title><published>2026-11-05T05:00:00+00:00</published></entry>
<entry><yt:videoId>def</yt:videoId><title>Bill Hader on His New Film</title><published>2026-11-05T06:00:00+00:00</published></entry>
</feed>"""


def test_the_feed_and_the_api_give_the_same_thing():
    from app.sections.latenight import monologues as m
    show = m.SHOWS[0]
    feed = m.parse_feed(FEED, show)
    assert feed == [{"show": "Jimmy Kimmel Live", "title": "Trump Does It Again",
                     "at": "2026-11-05T05:00:00+00:00", "url": "https://www.youtube.com/watch?v=abc"}]
    api = m.parse_api({"items": [{"snippet": {"title": "Trump Does It Again", "publishedAt": "2026-11-05T05:00:00+00:00",
                                              "resourceId": {"videoId": "abc"}}}]}, show)
    assert api == feed


def test_an_outage_keeps_the_last_list_and_says_so(client, monkeypatch):
    import httpx

    from app.sections.latenight import monologues as m
    m._items["kimmel"] = [{"show": "x", "title": "Gammel", "url": "https://y", "at": "2026-11-01T00:00:00Z"}]

    def down(*_a, **_k):
        raise httpx.ConnectError("nede")

    monkeypatch.setattr(m, "fetch", down)
    m.job()
    assert m.newest()[0]["title"] == "Gammel"
    assert m.status()["ok"] is False and "API-nøgle" in m.status()["text"]
    assert client.get("/api/overview").json()["blocks"]["latenight"]["monologues"][0]["title"] == "Gammel"


def test_youtube_key_is_a_secret(client):
    client.put("/api/admin/setup", json={"youtubeApiKey": "AIzaHemmelig12345"})
    assert "AIzaHemmelig" not in client.get("/api/admin/setup").text
    assert client.get("/api/admin/setup").json()["settings"]["youtubeApiKeySet"] is True


# ---- LogMyLife, Strava ---------------------------------------------------------------

STRAVA = (
    "Activity ID,Activity Date,Activity Name,Activity Type,Activity Description,Elapsed Time,Distance,Elapsed Time,Distance\n"
    '123,"Mar 4, 2021, 5:47:48 PM",Morgenløb,Run,Koldt,3120,"10.21",3120.0,10210.0\n'
    '124,"Jun 9, 2022, 7:02:11 AM",Tur til Kolding,Ride,,5400,"31.5",5400.0,31500.0\n'
    ',"ikke en række",,,,,,,\n'
).encode("utf-8")


def test_strava_export_lands_on_the_timeline(client):
    r = client.post("/api/s/logmylife/import/strava", content=STRAVA)
    assert r.status_code == 200
    assert r.json() == {"added": 2, "updated": 0, "same": 0, "skipped": 1}
    events = client.get("/api/s/logmylife/events?source=strava").json()["events"]
    assert [e["title"] for e in events] == ["Tur til Kolding", "Morgenløb"]
    run = events[1]
    assert run["start"] == "2021-03-04T17:47:48Z" and run["end"] == "2021-03-04T18:39:48Z"
    assert run["description"] == "Løb, 10,2 km, 52 min\nKoldt" and run["category"] == "Fritid"


def test_importing_again_adds_nothing(client):
    client.post("/api/s/logmylife/import/strava", content=STRAVA)
    r = client.post("/api/s/logmylife/import/strava", content=STRAVA).json()
    assert r["added"] == 0 and r["same"] == 2


def test_a_strava_entry_stays_the_persons_own(client, family):
    client.post("/api/s/logmylife/import/strava", content=STRAVA)
    assert family.get("/api/s/logmylife/events?source=strava").json()["events"] == []


def test_another_language_gets_a_clear_message(client):
    r = client.post("/api/s/logmylife/import/strava", content="Aktivitets-id,Dato\n1,2\n".encode())
    assert r.status_code == 400 and "English" in r.json()["detail"]


def test_a_zip_gets_a_clear_message(client):
    r = client.post("/api/s/logmylife/import/strava", content=b"PK\x03\x04\xff\xfe\x00")
    assert r.status_code == 400 and "zip" in r.json()["detail"]


# ---- Printere ----------------------------------------------------------------------

def _mock_printer():
    import importlib.util
    path = Path(__file__).resolve().parents[2] / "tools" / "mock_printer.py"
    spec = importlib.util.spec_from_file_location("mock_printer", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _wait(check, seconds=6.0):
    import time
    ends = time.monotonic() + seconds
    while time.monotonic() < ends:
        if value := check():
            return value
        time.sleep(.02)
    raise AssertionError("waited in vain")


def test_a_report_of_a_field_or_two_keeps_the_rest():
    from app.sections.printers import watcher
    state = {}
    watcher.merge(state, {"print": {"gcode_state": "RUNNING", "mc_percent": 10, "nozzle_temper": 220.1}})
    watcher.merge(state, {"print": {"mc_percent": 11}})
    watcher.merge(state, {"info": {"command": "get_version"}})
    assert state == {"gcode_state": "RUNNING", "mc_percent": 11, "nozzle_temper": 220.1}


def test_printer_state_in_words():
    from app.sections.printers import watcher
    printer = {"id": 1, "name": "A1"}
    running = {"gcode_state": "RUNNING", "subtask_name": "beslag.3mf", "gcode_file": "/x/plate_1.gcode", "print_error": 0}
    shown = watcher.dto(printer, running, True, "")
    assert (shown["stateText"], shown["active"], shown["file"], shown["error"]) == ("Printer", True, "beslag.3mf", "")
    assert watcher.dto(printer, {"gcode_state": "FINISH"}, True, "")["active"] is False
    assert watcher.dto(printer, running, False, "")["stateText"] == "Offline"
    assert watcher.dto(printer, {**running, "print_error": 0x0300400C}, True, "")["error"] == "0300-400C"


def test_the_printer_section_can_only_ask_for_a_report():
    from app.sections.printers import watcher
    tree = ast.parse(Path(watcher.__file__).read_text(encoding="utf-8"))
    publishes = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                 and n.func.attr == "publish"]
    assert len(publishes) == 1
    assert publishes[0].args[1].id == "PUSHALL"
    assert json.loads(watcher.PUSHALL)["pushing"]["command"] == "pushall"


def test_printer_reports_reach_the_page(client):
    from app.sections.printers import watcher
    mock = _mock_printer()
    printer = mock.Printer()
    port = printer.start()
    try:
        client.post("/api/s/printers/config", json={"name": "P1S", "host": f"127.0.0.1:{port}",
                                                    "serial": mock.SERIAL, "code": mock.CODE})
        watcher.job()
        read = lambda: client.get("/api/s/printers/state").json()["printers"][0]
        shown = _wait(lambda: (p := read())["online"] and p)
        assert (shown["stateText"], shown["percent"], shown["nozzle"], shown["file"]) == ("Printer", 62, 219.8, "beslag-v3.3mf")
        printer.send({"print": {"mc_percent": 63}})
        shown = _wait(lambda: (p := read())["percent"] == 63 and p)
        assert shown["nozzle"] == 219.8 and shown["layer"] == 118
        assert [r["pushing"]["command"] for r in printer.requests] == ["pushall"]
        assert client.get("/api/overview").json()["blocks"]["printers"]["printers"][0]["percent"] == 63
    finally:
        watcher.reset()
        printer.stop()


def test_reconnecting_does_not_ask_for_everything_again():
    from app.sections.printers import watcher
    mock = _mock_printer()
    printer = mock.Printer()
    port = printer.start()
    watch = watcher._Watch({"id": 1, "name": "A1", "host": f"127.0.0.1:{port}", "serial": mock.SERIAL}, mock.CODE)
    watch.client.reconnect_delay_set(1, 1)
    watch.start()
    try:
        _wait(lambda: watch.state)
        printer.clients[0].shutdown(2)
        _wait(lambda: not watch.connected)
        _wait(lambda: watch.connected)
        assert len(printer.requests) == 1
    finally:
        watch.stop()
        printer.stop()


def test_a_wrong_access_code_is_said_in_words(client):
    from app.sections.printers import watcher
    mock = _mock_printer()
    printer = mock.Printer()
    port = printer.start()
    try:
        client.post("/api/s/printers/config", json={"name": "P1S", "host": f"127.0.0.1:{port}",
                                                    "serial": mock.SERIAL, "code": "forkert"})
        watcher.job()
        status = _wait(lambda: "afviste" in (s := client.get("/api/s/printers/config").json()["status"])["text"] and s)
        assert status == {"ok": False, "text": "Printeren afviste adgangskoden."}
    finally:
        watcher.reset()
        printer.stop()


def test_a_new_access_code_opens_a_new_connection(client):
    from app.sections.printers import watcher
    mock = _mock_printer()
    printer = mock.Printer()
    port = printer.start()
    try:
        made = client.post("/api/s/printers/config", json={"name": "P1S", "host": f"127.0.0.1:{port}",
                                                           "serial": mock.SERIAL, "code": "forkert"}).json()
        watcher.job()
        _wait(lambda: watcher._watches[made["id"]].problem)
        client.put(f"/api/s/printers/config/{made['id']}", json={**made, "code": mock.CODE})
        watcher.job()
        assert _wait(lambda: client.get("/api/s/printers/state").json()["printers"][0]["online"])
    finally:
        watcher.reset()
        printer.stop()


def test_an_access_code_stays_on_the_server(client, family):
    from app.core import db
    made = client.post("/api/s/printers/config", json={"name": "A1", "host": "192.0.2.8", "serial": "03919A000000001",
                                                       "code": "hemmelig"})
    assert made.status_code == 200 and "hemmelig" not in made.text
    assert "hemmelig" not in client.get("/api/s/printers/config").text
    assert "hemmelig" not in client.get("/api/s/printers/state").text
    with db.connect() as con:
        assert "hemmelig" not in con.execute("SELECT code FROM printers").fetchone()["code"]
    assert client.put(f"/api/s/printers/config/{made.json()['id']}",
                      json={"name": "A1 mini", "host": "192.0.2.8", "serial": "03919A000000001"}).status_code == 200
    from app.sections.printers import store
    assert store.code_of(made.json()["id"]) == "hemmelig"


def test_only_admin_sets_up_printers(client, family):
    assert family.get("/api/s/printers/state").status_code == 200
    assert family.get("/api/s/printers/config").status_code == 403
    assert family.post("/api/s/printers/config", json={"name": "x", "host": "h", "serial": "s", "code": "c"}).status_code == 403


@pytest.mark.parametrize("body", [
    {"name": "", "host": "192.0.2.8", "serial": "S1", "code": "c"},
    {"name": "A1", "host": "192.0.2.8", "serial": "S1", "code": ""},
    {"name": "A1", "host": "192.0.2.8/x", "serial": "S1", "code": "c"},
    {"name": "A1", "host": "192.0.2.8", "serial": "S1/#", "code": "c"},
])
def test_a_printer_needs_clean_details(client, body):
    assert client.post("/api/s/printers/config", json=body).status_code == 400


# ---- Kameraer ----------------------------------------------------------------------

class _FakeGo2rtc:
    """Stands in for httpx in the camera client."""
    HTTPError = httpx.HTTPError

    def __init__(self, picture=b"jpeg", status=200):
        self.picture, self.status, self.streams, self.calls = picture, status, {}, []

    def patch(self, _url, params, timeout):
        self.streams[params["name"]] = params["src"]
        return httpx.Response(200, request=httpx.Request("PATCH", _url))

    def delete(self, _url, params, timeout):
        self.streams.pop(params["src"])
        return httpx.Response(400)      # go2rtc without a config file; it is gone all the same

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        if url.endswith("/api/streams"):
            return httpx.Response(200, json={k: {} for k in self.streams})
        return httpx.Response(self.status, content=self.picture)


def _camera(client, **extra):
    body = {"name": "Indkørsel", "host": "192.0.2.20", "username": "tapo", "password": "p@ss/w:rd", **extra}
    return client.post("/api/s/cameras/config", json=body)


def _go2rtc(monkeypatch, client, **kwargs):
    from app.sections.cameras import client as cam
    fake = _FakeGo2rtc(**kwargs)
    monkeypatch.setattr(cam, "httpx", fake)
    assert client.put("/api/admin/setup", json={"go2rtcUrl": "http://go2rtc:1984"}).status_code == 200
    return fake, cam


def test_a_camera_is_two_streams_with_the_login_quoted(client, monkeypatch):
    fake, cam = _go2rtc(monkeypatch, client)
    made = _camera(client).json()
    cam.job()
    assert fake.streams == {
        f"cam{made['id']}": "rtsp://tapo:p%40ss%2Fw%3Ard@192.0.2.20:554/stream1",
        f"cam{made['id']}_lo": "rtsp://tapo:p%40ss%2Fw%3Ard@192.0.2.20:554/stream2"}
    assert client.get("/api/s/cameras/config").json()["status"]["ok"] is True


def test_a_removed_camera_leaves_go2rtc_and_other_streams_stay(client, monkeypatch):
    fake, cam = _go2rtc(monkeypatch, client)
    made = _camera(client).json()
    cam.job()
    fake.streams["noget-andet"] = "rtsp://x"
    client.delete(f"/api/s/cameras/config/{made['id']}")
    cam.job()
    assert list(fake.streams) == ["noget-andet"]


def test_the_picture_passes_through_the_dashboard(client, monkeypatch):
    fake, cam = _go2rtc(monkeypatch, client, picture=b"\xff\xd8billede")
    made = _camera(client).json()
    r = client.get(f"/api/s/cameras/{made['id']}/frame.jpg")
    assert (r.status_code, r.content, r.headers["content-type"]) == (200, b"\xff\xd8billede", "image/jpeg")
    assert fake.calls[-1][1]["src"] == f"cam{made['id']}_lo"
    client.get(f"/api/s/cameras/{made['id']}/frame.jpg?size=hi")
    assert fake.calls[-1][1]["src"] == f"cam{made['id']}"


@pytest.mark.parametrize("kwargs", [{"status": 404}, {"status": 200, "picture": b""}])
def test_no_picture_is_said_plainly(client, monkeypatch, kwargs):
    _go2rtc(monkeypatch, client, **kwargs)
    made = _camera(client).json()
    r = client.get(f"/api/s/cameras/{made['id']}/frame.jpg")
    assert r.status_code == 503 and r.json()["detail"] == "Kameraet svarer ikke."


def _live_upstream(monkeypatch, handler):
    from app.sections.cameras import client as cam
    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient",
                        lambda timeout: real(transport=httpx.MockTransport(handler), timeout=timeout))
    return cam


def test_live_video_passes_through_and_has_an_end(client, monkeypatch):
    client.put("/api/admin/setup", json={"go2rtcUrl": "http://go2rtc:1984"})
    made = _camera(client).json()
    asked = {}

    async def endless():
        while True:
            yield b"moof"

    def handler(request):
        asked.update(request.url.params)
        return httpx.Response(200, headers={"content-type": 'video/mp4; codecs="avc1.42001F"'}, content=endless())

    cam = _live_upstream(monkeypatch, handler)
    monkeypatch.setattr(cam, "LIVE_SECONDS", 0)
    r = client.get(f"/api/s/cameras/{made['id']}/live.mp4")
    assert (r.status_code, r.content) == (200, b"moof")
    assert r.headers["content-type"].startswith("video/mp4")
    assert asked == {"src": f"cam{made['id']}", "video": "h264"}


def test_live_video_that_cannot_start_is_said_plainly(client, monkeypatch):
    client.put("/api/admin/setup", json={"go2rtcUrl": "http://go2rtc:1984"})
    made = _camera(client).json()
    _live_upstream(monkeypatch, lambda _request: httpx.Response(500, content=b"streams: dial tcp"))
    r = client.get(f"/api/s/cameras/{made['id']}/live.mp4")
    assert r.status_code == 503 and r.json()["detail"] == "Kameraet svarer ikke."


def test_a_camera_that_does_not_exist_has_no_picture(client, monkeypatch):
    fake, _cam = _go2rtc(monkeypatch, client)
    assert client.get("/api/s/cameras/99/frame.jpg").status_code == 503
    assert client.get("/api/s/cameras/99/live.mp4").status_code == 503
    assert not fake.calls


def test_a_camera_login_stays_on_the_server(client):
    from app.core import db
    from app.sections.cameras import store
    made = _camera(client)
    assert "p@ss" not in made.text and "p@ss" not in client.get("/api/s/cameras/config").text
    assert "p@ss" not in client.get("/api/overview").text
    with db.connect() as con:
        assert "p@ss" not in con.execute("SELECT password FROM cameras").fetchone()["password"]
    client.put(f"/api/s/cameras/config/{made.json()['id']}",
               json={"name": "Have", "host": "192.0.2.20", "username": "tapo"})
    assert "p%40ss" in store.source(made.json()["id"], "stream1")


def test_request_addresses_stay_out_of_the_log(client):
    """httpx logs whole addresses at INFO, with any key or login in them."""
    import logging

    from app.core import logs
    logs.setup()
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING


def test_a_failed_request_does_not_tell_the_login(client, monkeypatch):
    fake, cam = _go2rtc(monkeypatch, client)
    _camera(client)

    def fails(url, params, timeout):
        request = httpx.Request("PATCH", url, params=params)
        raise httpx.HTTPStatusError(f"bad {request.url}", request=request, response=httpx.Response(400))
    monkeypatch.setattr(fake, "patch", fails)
    cam.job()
    assert client.get("/api/s/cameras/config").json()["status"] == {"ok": False, "text": "go2rtc svarer ikke (HTTPStatusError)."}


def test_family_gets_cameras_only_when_given_them(client, family):
    me = family.get("/api/auth/status").json()["user"]
    assert "cameras" not in me["sections"] and "printers" in me["sections"]
    assert family.get("/api/s/cameras/list").status_code == 403
    _camera(client)
    assert family.get("/api/s/cameras/1/frame.jpg").status_code == 403
    assert "cameras" not in family.get("/api/overview").json()["blocks"]
    client.patch(f"/api/admin/users/{me['id']}", json={"sections": me["sections"] + ["cameras"]})
    assert len(family.get("/api/s/cameras/list").json()["cameras"]) == 1
    assert family.get("/api/s/cameras/config").status_code == 403
    assert family.post("/api/s/cameras/config", json={}).status_code == 403


@pytest.mark.parametrize("body", [
    {"name": "", "host": "192.0.2.20", "username": "tapo", "password": "x"},
    {"name": "Have", "host": "192.0.2.20", "username": "tapo", "password": ""},
    {"name": "Have", "host": "192.0.2.20/stream1#x", "username": "tapo", "password": "x"},
])
def test_a_camera_needs_clean_details(client, body):
    assert client.post("/api/s/cameras/config", json=body).status_code == 400


def test_the_overview_never_asks_a_camera(client, monkeypatch):
    fake, _cam = _go2rtc(monkeypatch, client)
    made = _camera(client).json()
    fake.calls.clear()
    assert client.get("/api/overview").json()["blocks"]["cameras"]["cameras"] == [{"id": made["id"], "name": "Indkørsel"}]
    assert not fake.calls


# ---- Aktier ------------------------------------------------------------------------

_HEADER = ["Id", "Bogføringsdag", "Handelsdag", "Valørdag", "Depot", "Transaktionstype", "Værdipapirer", "ISIN",
           "Antal", "Kurs", "Rente", "Samlede afgifter", "Valuta", "Beløb", "Valuta", "Indkøbsværdi", "Valuta",
           "Resultat", "Valuta", "Totalt antal", "Saldo", "Vekslingskurs", "Transaktionstekst", "Makuleringsdato",
           "Notanummer", "Verifikationsnummer", "Kurtage", "Valuta", "Middelkurs", "Oprindelig rente"]


def _nordnet(*rows, encoding="utf-16", delimiter="\t", currency="DKK"):
    """A made-up file in the shape of a real export: unsigned Antal, and the amount
    in DKK with cost and result in the security's currency.
    Rows: id, day, kind, name, isin, antal, beløb, indkøbsværdi, resultat, totalt antal,
    and optionally a cancelled date."""
    lines = [delimiter.join(_HEADER)]
    for id_, day, kind, name, isin, antal, belob, cost, resultat, total, *cancelled in rows:
        lines.append(delimiter.join([
            id_, day, day, day, "12345678", kind, name, isin, antal, "", "", "", "", belob, "DKK",
            cost, currency if cost else "", resultat, currency if resultat else "", total, "", "", "",
            cancelled[0] if cancelled else "", "", id_, "", "", "", ""]))
    return "\n".join(lines).encode(encoding)


_NOVO = "DK0062498333"
_MAERSK = "DK0010244508"
_FILE = _nordnet(
    ("6", "2024-06-01", "INDBETALING", "", "", "", "5000", "", "", ""),
    ("3", "2024-05-02", "SOLGT", "Novo Nordisk B", _NOVO, "5", "2500", "", "1000,5", "15"),
    ("2", "2024-03-01", "UDBYTTE", "Novo Nordisk B", _NOVO, "20", "150,25", "", "", "0"),
    ("7", "2024-03-01", "UDBYTTESKAT", "Novo Nordisk B", _NOVO, "20", "-40,25", "", "", "0"),
    ("5", "2023-03-01", "SOLGT", "Maersk B", _MAERSK, "2", "21000", "", "1000", "0"),
    ("4", "2023-02-01", "KØBT", "Maersk B", _MAERSK, "2", "-20000", "20000", "0", "2"),
    ("1", "2023-01-10", "KØBT", "Novo Nordisk B", _NOVO, "20", "-6000", "6000", "0", "20"),
)


def _import(client, data=_FILE):
    return client.post("/api/s/aktier/import", content=data, headers={"Content-Type": "text/csv"})


@pytest.mark.parametrize("encoding,delimiter", [("utf-16", "\t"), ("utf-8-sig", ";"), ("cp1252", "\t")])
def test_the_export_is_read_whatever_its_encoding(encoding, delimiter):
    from app.sections.aktier import nordnet
    data = _nordnet(("1", "2023-01-10", "KØBT", "Novo Nordisk B", _NOVO, "20,5", "-6000,5", "6000", "0", "20,5"),
                    encoding=encoding, delimiter=delimiter)
    rows, skipped = nordnet.parse(data)
    assert skipped == 0 and rows[0]["kind"] == "KØBT"
    assert (rows[0]["amount"], rows[0]["currency"], rows[0]["holding"], rows[0]["cost_currency"]) == (-6000.5, "DKK", 20.5, "DKK")


@pytest.mark.parametrize("text,mark,value", [
    ("1 234,50", ",", 1234.5), ("1.234,50", ",", 1234.5), ("-1 234,5", ",", -1234.5),
    ("1,234.50", ".", 1234.5), ("12", ",", 12.0), ("", ",", None), ("x", ",", None),
])
def test_danish_numbers(text, mark, value):
    from app.sections.aktier import nordnet
    assert nordnet._number(text, mark) == value


def test_positions_come_from_the_running_total(client):
    assert _import(client).json() == {"added": 7, "updated": 0, "same": 0, "skipped": 0}
    state = client.get("/api/s/aktier/state").json()
    assert state["rows"] == 7 and (state["first"], state["last"]) == ("2023-01-10", "2024-06-01")
    assert [(p["name"], p["quantity"], p["cost"], p["currency"]) for p in state["positions"]] == [
        ("Novo Nordisk B", 15, 4500.0, "DKK")]


def test_a_dividend_row_does_not_look_like_a_sale(client):
    """On a real export Totalt antal is 0 on UDBYTTE and UDBYTTESKAT."""
    _import(client, _nordnet(("2", "2024-03-01", "UDBYTTE", "Novo Nordisk B", _NOVO, "20", "150", "", "", "0"),
                             ("1", "2023-01-10", "KØBT", "Novo Nordisk B", _NOVO, "20", "-6000", "6000", "0", "20")))
    position = client.get("/api/s/aktier/state").json()["positions"][0]
    assert (position["quantity"], position["cost"]) == (20, 6000)


def test_buying_after_a_dividend_still_adds_up(client):
    _import(client, _nordnet(("3", "2024-04-01", "KØBT", "Novo Nordisk B", _NOVO, "5", "-1500", "1500", "0", "25"),
                             ("2", "2024-03-01", "UDBYTTE", "Novo Nordisk B", _NOVO, "20", "150", "", "", "0"),
                             ("1", "2023-01-10", "KØBT", "Novo Nordisk B", _NOVO, "20", "-6000", "6000", "0", "20")))
    position = client.get("/api/s/aktier/state").json()["positions"][0]
    assert (position["quantity"], position["cost"]) == (25, 7500)


def test_a_split_carries_the_cost(client):
    _import(client, _nordnet(("3", "2024-02-01", "SPLIT INDLÆG  VP", "Novo Nordisk B", _NOVO, "40", "0", "6000", "0", "40"),
                             ("2", "2024-02-01", "SPLIT UDTRÆK VP", "Novo Nordisk B", _NOVO, "20", "0", "", "0", "0"),
                             ("1", "2023-01-10", "KØBT", "Novo Nordisk B", _NOVO, "20", "-6000", "6000", "0", "20")))
    position = client.get("/api/s/aktier/state").json()["positions"][0]
    assert (position["quantity"], position["cost"]) == (40, 6000)


def test_cost_is_in_the_currency_of_the_security(client):
    _import(client, _nordnet(("1", "2023-01-10", "KØBT", "Fond", "IE0000000001", "10,5", "-7500", "1000", "0", "10,5"),
                             currency="EUR"))
    position = client.get("/api/s/aktier/state").json()["positions"][0]
    assert (position["quantity"], position["cost"], position["currency"]) == (10.5, 1000, "EUR")


def test_rounded_fractions_still_add_up(client):
    _import(client, _nordnet(("2", "2023-02-10", "KØBT", "Fond", "IE0000000001", "1,3333", "-100", "100", "0", "2,6667"),
                             ("1", "2023-01-10", "KØBT", "Fond", "IE0000000001", "1,3333", "-100", "100", "0", "1,3333")))
    position = client.get("/api/s/aktier/state").json()["positions"][0]
    assert (position["quantity"], position["cost"]) == (2.6667, 200)


def test_sold_out_and_bought_again_starts_clean(client):
    _import(client, _nordnet(("3", "2024-02-01", "KØBT", "Novo Nordisk B", _NOVO, "5", "-1500", "1500", "0", "5"),
                             ("2", "2024-01-01", "SOLGT", "Novo Nordisk B", _NOVO, "20", "7000", "", "100", "0"),
                             ("1", "2023-01-10", "INDFLYTNING", "Novo Nordisk B", _NOVO, "20", "0", "", "0", "20")))
    assert client.get("/api/s/aktier/state").json()["positions"][0]["cost"] == 1500


def test_dividends_after_tax_and_results_per_year(client):
    _import(client)
    assert client.get("/api/s/aktier/state").json()["years"] == [
        {"year": "2024", "currency": "DKK", "dividends": 110.0, "result": 1000.5},
        {"year": "2023", "currency": "DKK", "dividends": 0.0, "result": 1000.0}]


def test_a_year_of_only_purchases_shows_no_line(client):
    _import(client, _nordnet(("1", "2023-01-10", "KØBT", "Novo Nordisk B", _NOVO, "20", "-6000", "6000", "0", "20")))
    assert client.get("/api/s/aktier/state").json()["years"] == []


def test_importing_again_adds_nothing(client):
    _import(client)
    assert _import(client).json() == {"added": 0, "updated": 0, "same": 7, "skipped": 0}
    longer = _nordnet(("8", "2024-07-01", "KØBT", "Novo Nordisk B", _NOVO, "5", "-1500", "1500", "0", "20"))
    assert _import(client, longer).json()["added"] == 1
    position = client.get("/api/s/aktier/state").json()["positions"][0]
    assert (position["quantity"], position["cost"]) == (20, 6000)


def test_an_export_that_starts_late_has_no_cost(client):
    _import(client, _nordnet(("9", "2024-01-10", "KØBT", "Novo Nordisk B", _NOVO, "5", "-1500", "1500", "0", "25")))
    position = client.get("/api/s/aktier/state").json()["positions"][0]
    assert position["quantity"] == 25 and position["cost"] is None


def test_shares_with_no_value_have_no_cost(client):
    _import(client, _nordnet(("9", "2024-01-10", "INDFLYTNING", "Novo Nordisk B", _NOVO, "5", "0", "", "0", "5")))
    assert client.get("/api/s/aktier/state").json()["positions"][0]["cost"] is None


def test_a_cancelled_row_does_not_count(client):
    _import(client, _nordnet(("1", "2024-01-10", "KØBT", "Novo Nordisk B", _NOVO, "5", "-1500", "1500", "0", "5"),
                             ("2", "2024-01-11", "KØBT", "Novo Nordisk B", _NOVO, "5", "-1500", "1500", "0", "10", "2024-01-12")))
    assert client.get("/api/s/aktier/state").json()["positions"][0]["quantity"] == 5


def test_only_the_end_of_a_depot_number_is_kept(client):
    from app.core import db
    _import(client)
    with db.connect() as con:
        assert {r["depot"] for r in con.execute("SELECT depot FROM nordnet_rows").fetchall()} == {"5678"}


def test_a_wrong_file_is_described_by_its_columns_only(client):
    r = _import(client, "Dato;Tekst\n2024-01-01;hemmelig\n".encode())
    assert r.status_code == 400 and "Totalt antal" in r.json()["detail"] and "hemmelig" not in r.json()["detail"]


def test_a_row_without_a_date_is_counted_not_guessed(client):
    bad = _nordnet(("1", "ukendt", "KØBT", "Novo Nordisk B", _NOVO, "5", "-1500", "1500", "0", "5"))
    assert _import(client, bad).json() == {"added": 0, "updated": 0, "same": 0, "skipped": 1}


def test_holdings_are_each_persons_own(client, family):
    _import(client)
    me = family.get("/api/auth/status").json()["user"]
    client.patch(f"/api/admin/users/{me['id']}", json={"sections": me["sections"] + ["aktier"]})
    assert family.get("/api/s/aktier/state").json()["positions"] == []
    assert family.get("/api/overview").json()["blocks"]["aktier"]["positions"] == 0
    assert client.get("/api/overview").json()["blocks"]["aktier"]["positions"] == 1
    family.delete("/api/s/aktier/rows")
    assert len(client.get("/api/s/aktier/state").json()["positions"]) == 1


def test_imported_rows_can_be_removed(client):
    _import(client)
    client.delete("/api/s/aktier/rows")
    assert client.get("/api/s/aktier/state").json()["rows"] == 0


# ---- Kalender: colours, and one calendar to the log --------------------------------

_MAIN = {"id": "mig@x.dk", "summary": "Min", "color": "#4285f4", "primary": True}
_FAMILY = {"id": "familie@x.dk", "summary": "Familien", "color": "#33b679", "primary": False}


def _event(id_, title, **extra):
    day = (datetime.now(CPH) + timedelta(days=1)).strftime("%Y-%m-%d")
    return {"id": id_, "summary": title, "start": {"dateTime": f"{day}T10:00:00+01:00"},
            "end": {"dateTime": f"{day}T11:00:00+01:00"}, **extra}


def _connected(client, monkeypatch, events, calendars=(_MAIN, _FAMILY)):
    """An account with these calendars. `events` is {calendar id: items}, and can be changed."""
    from app.core import db, google, vault
    uid = _me(client)
    with db.connect() as con:
        con.execute("INSERT INTO google_accounts (user_id, email, refresh_token, connected_at) VALUES (?,?,?,?)",
                    (uid, "mig@x.dk", vault.seal("refresh"), db.utcnow()))
    tokens = []

    def read(_t, calendar, token):
        tokens.append((calendar, token))
        return events.get(calendar, []), "tok"

    monkeypatch.setattr(google, "access_token", lambda _r: "token")
    monkeypatch.setattr(google, "calendars", lambda _t: list(calendars))
    monkeypatch.setattr(google, "events", read)
    return uid, tokens


def _page(client):
    return client.get("/api/s/calendar/state").json()


def _log(uid):
    from app.core import db
    with db.connect() as con:
        return [r["title"] for r in con.execute("SELECT title FROM life_events WHERE user_id=? ORDER BY title",
                                                (uid,)).fetchall()]


def test_colours_are_the_ones_google_shows():
    from app.core import google
    assert google.shown_color("#9FC6E7") == "#4285f4"       # the API's classic Cobalt
    assert google.shown_color("#123456") == "#123456"       # mixed by the person
    assert google.shown_color("") == ""


def test_only_the_main_calendar_reaches_the_log(client, monkeypatch):
    from app.sections.calendar import sync
    uid, _tokens = _connected(client, monkeypatch, {"mig@x.dk": [_event("a", "Mit møde")],
                                                    "familie@x.dk": [_event("b", "Fødselsdag")]})
    sync.sync_user(uid)
    assert _log(uid) == ["Mit møde"]
    page = _page(client)
    assert {(e["title"], e["color"], e["calendar"]) for e in page["events"]} == {
        ("Mit møde", "#4285f4", "Min"), ("Fødselsdag", "#33b679", "Familien")}
    assert [c["id"] for c in page["calendars"] if c["toLog"]] == ["mig@x.dk"]
    assert len(client.get("/api/overview").json()["blocks"]["calendar"]["events"]) == 2


def test_an_event_can_have_its_own_colour(client, monkeypatch):
    from app.sections.calendar import sync
    uid, _tokens = _connected(client, monkeypatch, {"mig@x.dk": [_event("a", "Rød", colorId="11")]})
    sync.sync_user(uid)
    assert _page(client)["events"][0]["color"] == "#d50000"


def test_an_unticked_calendar_leaves_the_page(client, monkeypatch):
    from app.sections.calendar import sync
    uid, _tokens = _connected(client, monkeypatch, {"familie@x.dk": [_event("b", "Fødselsdag")]})
    sync.sync_user(uid)
    client.put("/api/s/calendar/selected", json={"calendarId": "familie@x.dk", "selected": False})
    assert _page(client)["events"] == []


def test_the_main_calendar_feeds_the_log_even_unticked(client, monkeypatch):
    from app.sections.calendar import sync
    uid, _tokens = _connected(client, monkeypatch, {"mig@x.dk": [_event("a", "Mit møde")]})
    sync.sync_user(uid)
    client.put("/api/s/calendar/selected", json={"calendarId": "mig@x.dk", "selected": False})
    sync.sync_user(uid)
    assert _page(client)["events"] == [] and _log(uid) == ["Mit møde"]


def test_a_cancelled_event_leaves_the_page_and_stays_in_the_log(client, monkeypatch):
    from app.core import db
    from app.sections.calendar import sync
    events = {"mig@x.dk": [_event("a", "Mit møde")]}
    uid, _tokens = _connected(client, monkeypatch, events)
    sync.sync_user(uid)
    events["mig@x.dk"] = [{"id": "a", "status": "cancelled"}]
    sync.sync_user(uid)
    assert _page(client)["events"] == []
    with db.connect() as con:
        assert con.execute("SELECT deleted_at_source FROM life_events").fetchone()[0]


def test_moving_the_log_to_another_calendar(client, monkeypatch):
    from app.sections.calendar import sync
    uid, tokens = _connected(client, monkeypatch, {"mig@x.dk": [_event("a", "Mit møde")],
                                                   "familie@x.dk": [_event("b", "Fødselsdag")]})
    sync.sync_user(uid)
    assert client.put("/api/s/calendar/log-calendar", json={"calendarId": "familie@x.dk"}).status_code == 200
    assert _log(uid) == []
    tokens.clear()
    sync.sync_user(uid)
    assert ("familie@x.dk", None) in tokens         # read from the start
    assert _log(uid) == ["Fødselsdag"]
    assert [c["id"] for c in _page(client)["calendars"] if c["toLog"]] == ["familie@x.dk"]


def test_picking_the_same_calendar_changes_nothing(client, monkeypatch):
    from app.sections.calendar import sync
    uid, tokens = _connected(client, monkeypatch, {"mig@x.dk": [_event("a", "Mit møde")]})
    sync.sync_user(uid)
    client.put("/api/s/calendar/log-calendar", json={"calendarId": "mig@x.dk"})
    assert _log(uid) == ["Mit møde"]
    tokens.clear()
    sync.sync_user(uid)
    assert ("mig@x.dk", "tok") in tokens


def test_a_calendar_that_does_not_exist_cannot_take_the_log(client, monkeypatch):
    from app.sections.calendar import sync
    uid, _tokens = _connected(client, monkeypatch, {"mig@x.dk": [_event("a", "Mit møde")]})
    sync.sync_user(uid)
    assert client.put("/api/s/calendar/log-calendar", json={"calendarId": "andet"}).status_code == 404
    assert _log(uid) == ["Mit møde"]


def test_the_move_to_one_calendar_cleans_the_log(client):
    """What migration 2 does on a database from before: only the primary's rows stay,
    a person's own entries are not touched, and everything is fetched again."""
    from app.core import db, vault
    from app.sections.calendar import sync
    from app.sections.logmylife import store
    uid = _me(client)
    with db.connect() as con:
        con.execute("INSERT INTO google_accounts (user_id, email, refresh_token, connected_at) VALUES (?,?,?,?)",
                    (uid, "mig@x.dk", vault.seal("refresh"), db.utcnow()))
        con.executemany("INSERT INTO google_calendars (user_id, calendar_id, sync_token) VALUES (?,?,?)",
                        [(uid, "mig@x.dk", "tok"), (uid, "familie@x.dk", "tok")])
    for sid, title in (("mig@x.dk|a", "Mit møde"), ("familie@x.dk|b", "Fødselsdag")):
        store.ingest(uid, "google", sid, title=title, start="2020-05-05", all_day=True)
    store.add(uid, {"title": "Eget indlæg", "start": "2020-05-06"})
    with db.connect() as con:
        sync.migrate_2(con)
    assert sorted(_log(uid)) == ["Eget indlæg", "Mit møde"]
    assert [(c["id"], c["toLog"]) for c in sync.calendars_of(uid)] == [("familie@x.dk", False), ("mig@x.dk", True)]
    with db.connect() as con:
        assert {r["sync_token"] for r in con.execute("SELECT sync_token FROM google_calendars").fetchall()} == {None}


def test_disconnecting_removes_the_copy_and_keeps_the_log(client, monkeypatch):
    from app.core import db
    from app.sections.calendar import sync
    uid, _tokens = _connected(client, monkeypatch, {"mig@x.dk": [_event("a", "Mit møde")]})
    sync.sync_user(uid)
    client.post("/api/s/calendar/disconnect")
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM google_events").fetchone()[0] == 0
    assert _log(uid) == ["Mit møde"]


# ---- Aktier: prices and the week ---------------------------------------------------

_TODAY = date(2026, 11, 6)


def _priced(*rows):
    """Rows: (isin, symbol, currency, {day: close}), straight into the database."""
    from app.core import db
    with db.connect() as con:
        for isin, symbol, currency, closes in rows:
            if isin:
                con.execute("INSERT OR REPLACE INTO stock_symbols (isin, symbol, currency, checked_at) VALUES (?,?,?,?)",
                            (isin, symbol, currency, "2026-11-06"))
            con.executemany("INSERT OR REPLACE INTO stock_prices (symbol, day, close) VALUES (?,?,?)",
                            [(symbol, day, close) for day, close in closes.items()])


def _held(isin=_NOVO, name="Novo Nordisk B", quantity=10.0):
    return {"name": name, "isin": isin, "depot": "5678", "quantity": quantity, "cost": 100.0, "currency": "DKK"}


def test_the_week_is_what_todays_holdings_did(fresh_db):
    from app.sections.aktier import prices
    _priced((_NOVO, "NOVO-B.CO", "DKK", {"2026-10-30": 100.0, "2026-11-06": 110.0}))
    week = prices.week([_held()], _TODAY)
    assert week["days"][0] == "2026-10-30" and week["days"][-1] == "2026-11-06" and len(week["days"]) == 8
    assert (week["value"], week["change"], week["changeKr"]) == (1100.0, 10.0, 100.0)
    assert week["items"][0]["points"][:2] == [100.0, 100.0]     # a day with no price keeps the last one
    assert week["items"][0]["change"] == 10.0 and week["missing"] == []


def test_foreign_holdings_count_in_kroner(fresh_db):
    from app.sections.aktier import prices
    _priced(("IE0000000001", "FOND.DE", "EUR", {"2026-10-30": 100.0, "2026-11-06": 100.0}),
            ("", "EURDKK=X", "", {"2026-10-30": 7.0, "2026-11-06": 8.0}))
    week = prices.week([_held("IE0000000001", "Fond", 2.0)], _TODAY)
    assert week["total"][0] == 1400.0 and week["value"] == 1600.0
    assert week["items"][0]["change"] == 0.0        # the fund stood still, the krone moved


def test_a_holding_without_a_price_is_named_not_guessed(fresh_db):
    from app.sections.aktier import prices
    _priced((_NOVO, "NOVO-B.CO", "DKK", {"2026-10-30": 100.0, "2026-11-06": 110.0}), (_MAERSK, "", "", {}))
    week = prices.week([_held(), _held(_MAERSK, "Maersk B")], _TODAY)
    assert week["missing"] == ["Maersk B"] and len(week["items"]) == 1


def test_nothing_priced_yet_says_so(fresh_db):
    from app.sections.aktier import prices
    assert prices.week([_held()], _TODAY)["items"] == []
    assert prices.week([], _TODAY) is None


def _yahoo(monkeypatch, listings):
    """Stands in for the two endpoints. `listings` is {isin: [(symbol, currency)]}."""
    from app.sections.aktier import prices
    asked = []
    symbols = {s: c for found in listings.values() for s, c in found}

    def get(url, params):
        asked.append((url, params))
        if url.endswith("/search"):
            return {"quotes": [{"symbol": s} for s, _c in listings.get(params["q"], [])]}
        symbol = url.rsplit("/", 1)[1]
        return {"chart": {"result": [{"meta": {"currency": symbols.get(symbol, "DKK"), "gmtoffset": 3600},
                                      "timestamp": [1793865600, 1793869200, 1793955600],
                                      "indicators": {"quote": [{"close": [10.0, 11.0, None]}]}}]}}

    monkeypatch.setattr(prices, "_get", get)
    return asked


def test_the_listing_in_the_right_currency_is_chosen(fresh_db, monkeypatch):
    from app.sections.aktier import prices
    _yahoo(monkeypatch, {"IE0000000001": [("FOND.L", "USD"), ("FOND.DE", "EUR")]})
    assert prices.find("IE0000000001", "EUR") == ("FOND.DE", "EUR")
    assert prices.find("IE0000000001", "SEK") == ("FOND.L", "USD")


def test_the_last_price_of_a_day_counts_and_gaps_are_skipped(fresh_db, monkeypatch):
    from app.sections.aktier import prices
    _yahoo(monkeypatch, {})
    assert prices.closes("X")[1] == {"2026-11-05": 11.0}


def test_the_job_prices_what_is_held_and_says_what_it_cannot(client, monkeypatch):
    from app.core import db
    from app.sections.aktier import prices
    _import(client, _nordnet(("1", "2023-01-10", "KØBT", "Novo Nordisk B", _NOVO, "5", "-1500", "1500", "0", "5"),
                             ("2", "2023-01-10", "KØBT", "Maersk B", _MAERSK, "5", "-1500", "1500", "0", "5")))
    asked = _yahoo(monkeypatch, {_NOVO: [("NOVO-B.CO", "DKK")]})
    prices.job()
    assert prices.status() == "Kurser på 1 af 2."
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM stock_prices WHERE symbol='NOVO-B.CO'").fetchone()[0] == 1
    asked.clear()
    prices.job()
    assert not [a for a in asked if a[0].endswith("/search") and a[1]["q"] == _NOVO]    # the symbol is remembered


def test_only_the_isin_goes_to_yahoo(client, monkeypatch):
    from app.sections.aktier import prices
    _import(client)
    asked = _yahoo(monkeypatch, {_NOVO: [("NOVO-B.CO", "DKK")]})
    prices.job()
    assert all(set(p) <= {"q", "quotesCount", "newsCount", "range", "interval"} for _u, p in asked)


def test_a_failing_yahoo_keeps_the_last_prices(client, monkeypatch):
    from app.sections.aktier import prices
    _import(client)
    _priced((_NOVO, "NOVO-B.CO", "DKK", {"2026-10-30": 100.0}))

    def fails(_url, _params):
        raise httpx.ConnectError("no")

    monkeypatch.setattr(prices, "_get", fails)
    prices.job()
    assert prices.status() == "Kurser på 0 af 1."
    assert client.get("/api/s/aktier/state").status_code == 200


def test_the_overview_never_asks_yahoo(client, monkeypatch):
    from app.sections.aktier import prices
    _import(client)
    asked = _yahoo(monkeypatch, {})
    assert client.get("/api/overview").json()["blocks"]["aktier"]["week"]["items"] == []
    assert not asked

