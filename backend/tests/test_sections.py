"""What the sections do with their data."""
from __future__ import annotations

import ast
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

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

def test_dklive_price_time_is_wall_clock_in_winter_and_summer():
    from app.sections.dklive.client import price_time
    # dk-live's time: TimeDK read as UTC.
    winter = int(datetime(2026, 11, 6, 7, 15, tzinfo=timezone.utc).timestamp() * 1000)
    assert price_time(winter, None, CPH) == datetime(2026, 11, 6, 6, 15, tzinfo=timezone.utc)
    summer = int(datetime(2026, 7, 6, 7, 15, tzinfo=timezone.utc).timestamp() * 1000)
    assert price_time(summer, None, CPH) == datetime(2026, 7, 6, 5, 15, tzinfo=timezone.utc)
    # After a fix in dk-live, timeBase says so and the value stands.
    assert price_time(winter, "utc", CPH) == datetime(2026, 11, 6, 7, 15, tzinfo=timezone.utc)


def test_current_price_is_the_slot_we_are_in():
    from app.sections.dklive import client as dk
    dk.reset()
    wall = lambda h, m: int(datetime(2026, 11, 6, h, m, tzinfo=timezone.utc).timestamp() * 1000)
    data = {"area": "DK1", "prices": [{"time": wall(6, 0), "dkk": 1.8}, {"time": wall(7, 0), "dkk": 2.4},
                                      {"time": wall(7, 15), "dkk": 2.43}, {"time": wall(8, 0), "dkk": 1.2}]}
    now = datetime(2026, 11, 6, 6, 20, tzinfo=timezone.utc)                  # 07:20 in Denmark
    power = dk.build_power(data, CPH, now)
    assert power["now"] == 2.43
    assert power["low"]["dkk"] == 1.2 and power["high"]["dkk"] == 2.43       # from now on, not the past
    dk.reset()


def test_earlier_prices_stay_on_the_band():
    from app.sections.dklive import client as dk
    dk.reset()
    wall = lambda h: int(datetime(2026, 11, 6, h, 0, tzinfo=timezone.utc).timestamp() * 1000)
    now = datetime(2026, 11, 6, 6, 0, tzinfo=timezone.utc)
    dk.build_power({"prices": [{"time": wall(5), "dkk": 1.0}, {"time": wall(6), "dkk": 2.0}]}, CPH, now)
    power = dk.build_power({"prices": [{"time": wall(6), "dkk": 2.0}]}, CPH, now + timedelta(hours=1))
    assert [p["dkk"] for p in power["series"]] == [1.0, 2.0]
    dk.reset()


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


def test_section_is_quiet_until_set_up(client):
    block = client.get("/api/overview").json()["blocks"]["dklive"]
    assert block["configured"] is False


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
