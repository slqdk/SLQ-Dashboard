"""The live sources behind the map, each fed a small made-up answer in its own shape."""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
import pytest

CPH = ZoneInfo("Europe/Copenhagen")
NOW = int(datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc).timestamp() * 1000)


class Answers:
    """Stands in for source.fetch: the first address fragment that matches answers."""

    def __init__(self, answers: dict):
        self.answers, self.asked = answers, []

    def __call__(self, url, params=None, headers=None, timeout=None):
        self.asked.append((url, params, headers))
        for fragment, answer in self.answers.items():
            if fragment in url:
                if isinstance(answer, Exception):
                    raise answer
                request = httpx.Request("GET", url)
                if isinstance(answer, int):
                    return httpx.Response(answer, request=request).raise_for_status()
                if isinstance(answer, str):
                    return httpx.Response(200, text=answer, request=request)
                return httpx.Response(200, json=answer, request=request)
        raise AssertionError(f"nothing answers {url}")


@pytest.fixture
def answering(monkeypatch):
    from app.sections.dklive import source

    def install(answers: dict) -> Answers:
        fake = Answers(answers)
        monkeypatch.setattr(source, "fetch", fake)
        return fake

    return install


# ---- what every source shares ------------------------------------------------------

def test_danish_wall_clock_is_read_in_winter_and_summer():
    from app.sections.dklive.source import copenhagen_ms
    assert copenhagen_ms(2026, 11, 6, 8, 0) == int(datetime(2026, 11, 6, 7, 0, tzinfo=timezone.utc).timestamp() * 1000)
    assert copenhagen_ms(2026, 7, 6, 8, 0) == int(datetime(2026, 7, 6, 6, 0, tzinfo=timezone.utc).timestamp() * 1000)


def test_a_failure_is_told_by_its_kind_and_never_its_address(client, answering):
    """The text of an httpx error holds the address, and an address can hold a key."""
    from app.core import logs
    from app.sections.dklive import source, trains
    client.put("/api/admin/setup", json={"dkliveLayers": ["trains"], "rejseplanenKey": "hemmelig-noegle-1"})
    request = httpx.Request("GET", "https://x/?accessId=hemmelig-noegle-1")
    answering({"journeypos": httpx.HTTPStatusError("nej", request=request, response=httpx.Response(403, request=request))})
    logs.clear()
    trains.job()
    assert source.state()["trains"]["text"] == "HTTP 403"
    assert "hemmelig" not in json.dumps(logs.recent())


def test_a_failing_source_goes_into_the_log_once(client, answering):
    from app.core import logs
    from app.sections.dklive import energy
    answering({"energidataservice": httpx.ConnectError("nej")})
    logs.clear()
    energy.job()
    energy.job()
    assert sum("energy" in e["message"] for e in logs.recent()) == 1


def test_a_layer_that_is_off_is_not_fetched(client, answering):
    from app.sections.dklive import flights, source
    client.put("/api/admin/setup", json={"dkliveLayers": ["alarms"]})
    fake = answering({"adsb.lol": {"ac": []}})
    flights.job()
    assert not fake.asked and "flights" not in source.state()
    client.put("/api/admin/setup", json={"dkliveLayers": ["military"]})
    flights.job()
    assert len(fake.asked) == 1 and source.state()["flights"]["ok"]


def test_the_stand_in_replaces_every_address(monkeypatch):
    from app.sections.dklive.source import address
    monkeypatch.setenv("APP_LIVE_MOCK", "http://127.0.0.1:9100/")
    assert address("https://api.adsb.lol/v2") == "http://127.0.0.1:9100/api.adsb.lol/v2"
    assert address("wss://stream.aisstream.io/v0") == "ws://127.0.0.1:9100/stream.aisstream.io/v0"
    monkeypatch.delenv("APP_LIVE_MOCK")
    assert address("https://api.adsb.lol/v2") == "https://api.adsb.lol/v2"


# ---- flights -----------------------------------------------------------------------

def test_aircraft_are_kept_to_the_map():
    from app.sections.dklive import flights
    out = flights.parse({"ac": [
        {"hex": "a1", "flight": "SAS123  ", "lat": 55.5, "lon": 10.0, "alt_baro": 33000, "gs": 400, "seen_pos": 2.5, "dbFlags": 1, "emergency": "none"},
        {"hex": "a2", "lat": 55.6, "lon": 12.6, "alt_baro": "ground"},
        {"hex": "a3", "lat": 40.0, "lon": 10.0},                # outside the map
        {"hex": "a4", "t": "GND", "lat": 55.0, "lon": 10.0},    # a ground vehicle
        {"hex": "a5"},                                          # no position
    ]}, NOW)
    assert [a["id"] for a in out] == ["a1", "a2"]
    assert out[0]["callsign"] == "SAS123" and out[0]["military"] and out[0]["emergency"] is None
    assert out[0]["seen"] == NOW - 2500
    assert out[1]["onGround"] and out[1]["alt"] == 0


def test_routes_are_looked_up_once(client, answering):
    from app.sections.dklive import flights
    client.put("/api/admin/setup", json={"dkliveLayers": ["flights"]})
    fake = answering({"adsb.lol": {"ac": [{"hex": "a1", "flight": "SAS123", "lat": 55.5, "lon": 10.0},
                                          {"hex": "a2", "flight": "bad one", "lat": 55.6, "lon": 10.0}]},
                      "adsbdb": {"response": {"flightroute": {"origin": {"iata_code": "CPH", "municipality": "København"},
                                                              "destination": {"icao_code": "EKYT", "name": "Aalborg Airport"}}}}})
    flights.job()
    assert list(flights._queue) == ["SAS123"]       # the misconfigured transponder is not asked about
    flights.route_job()
    flights.job()
    route = flights.get()["aircraft"][0]["route"]
    assert route == {"from": "CPH", "to": "EKYT", "fromName": "København", "toName": "Aalborg Airport"}
    flights.route_job()
    assert sum("adsbdb" in url for url, _p, _h in fake.asked) == 1


def test_an_unknown_callsign_is_remembered(client, answering):
    from app.sections.dklive import flights
    client.put("/api/admin/setup", json={"dkliveLayers": ["flights"]})
    answering({"adsb.lol": {"ac": [{"hex": "a1", "flight": "XYZ1", "lat": 55.5, "lon": 10.0}]}, "adsbdb": 404})
    flights.job()
    flights.route_job()
    assert "XYZ1" in flights._routes and flights._routes["XYZ1"] is None and not flights._queue


def test_adsb_backs_off_and_asks_later(client, answering):
    from app.sections.dklive import flights, source
    client.put("/api/admin/setup", json={"dkliveLayers": ["flights"]})
    fake = answering({"adsb.lol": 429})
    flights.job()
    flights.job()
    assert len(fake.asked) == 1 and source.state()["flights"]["text"] == "HTTP 429"


# ---- ships: a real websocket -------------------------------------------------------

def test_ships_come_over_a_websocket(client, monkeypatch):
    from websockets.sync.server import serve

    from app.sections.dklive import ships, source
    subscribed = []

    def handler(ws):
        subscribed.append(json.loads(ws.recv()))
        ws.send(json.dumps({"MessageType": "ShipStaticData", "MetaData": {"MMSI": 219000001},
                            "Message": {"ShipStaticData": {"Name": "EKSEMPEL   ", "Type": 70, "Destination": "AARHUS",
                                                           "Dimension": {"A": 90, "B": 20, "C": 10, "D": 8},
                                                           "Eta": {"Month": 11, "Day": 7, "Hour": 8, "Minute": 30}}}}))
        ws.send(json.dumps({"MessageType": "PositionReport",
                            "MetaData": {"MMSI": 219000001, "ShipName": "EKSEMPEL", "latitude": 56.3, "longitude": 11.2},
                            "Message": {"PositionReport": {"Cog": 120.0, "Sog": 11.5, "TrueHeading": 511, "RateOfTurn": -128}}}))
        try:
            ws.recv(timeout=5)
        except Exception:
            pass

    with serve(handler, "127.0.0.1", 0) as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        monkeypatch.setattr(ships, "STREAM", f"ws://127.0.0.1:{server.socket.getsockname()[1]}/")
        client.put("/api/admin/setup", json={"dkliveLayers": ["ships"], "aisstreamKey": "hemmelig-ais-1"})
        ships.job()
        deadline = time.monotonic() + 5
        while not ships.get()["ships"] and time.monotonic() < deadline:
            time.sleep(0.05)
        ships.reset()
        server.shutdown()
    assert subscribed[0]["APIKey"] == "hemmelig-ais-1"
    assert subscribed[0]["BoundingBoxes"] == [[[53.3, 7.5], [57.9, 13.0]]]
    assert source.state()["ships"]["ok"]


def test_a_ship_builds_up_from_its_messages():
    from app.sections.dklive import ships
    ships.reset()
    ships.apply({"MessageType": "ShipStaticData", "MetaData": {"MMSI": 7},
                 "Message": {"ShipStaticData": {"Name": "EKSEMPEL   ", "Type": 70, "Dimension": {"A": 90, "B": 20, "C": 10, "D": 8},
                                                "Eta": {"Month": 11, "Day": 7, "Hour": 8, "Minute": 30}}}}, NOW)
    assert ships.get()["ships"] == []               # no position yet
    ships.apply({"MessageType": "PositionReport", "MetaData": {"MMSI": 7, "latitude": 56.3, "longitude": 11.2},
                 "Message": {"PositionReport": {"Cog": 120.0, "Sog": 11.5, "TrueHeading": 511, "RateOfTurn": -128}}}, NOW)
    ship = ships.get()["ships"][0]
    assert ship["name"] == "EKSEMPEL" and ship["length"] == 110 and ship["beam"] == 18
    assert ship["heading"] is None and ship["rot"] is None and ship["eta"]["day"] == 7
    ships.reset()


def test_a_bad_key_is_said_by_ais_stream_itself(client):
    from app.sections.dklive import ships
    client.put("/api/admin/setup", json={"dkliveLayers": ["ships"]})
    ships.job()
    assert ships.get()["enabled"] is False          # no key, no socket


# ---- 112 ---------------------------------------------------------------------------

ALARM_PAGE = """<table><tr><th>Tidspunkt</th></tr>
<tr><td>06-11-2026 12:50</td><td>TrekantBrand     Station  Kolding</td><td>Bygn.brand-Gård</td></tr>
<tr><td>06-11-2026 12:50</td><td>TrekantBrand     Station  Kolding</td><td>Bygn.brand-Gård</td></tr>
<tr><td>04-11-2026 09:00</td><td>Gammel     Station  Vejle</td><td>For gammel</td></tr>
<tr><td>en anden række</td><td>x</td><td>y</td></tr></table>"""


@pytest.mark.parametrize("raw,clean", [("Falck Haderslev", "Haderslev"), ("Vojens+Gram", "Vojens"), ("Slagelse BV", "Slagelse"),
                                       ("Åsum - Odense", "Åsum"), ("St. Heddinge", "Heddinge")])
def test_station_names_become_places(raw, clean):
    from app.sections.dklive.alarms import clean_station
    assert clean_station(raw) == clean


def test_alarms_are_read_from_the_table(client):
    from app.sections.dklive import alarms
    now = int(datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc).timestamp() * 1000)
    out = alarms.build(alarms.parse_page(ALARM_PAGE), now)
    assert len(out) == 1                            # the repeat and the old one are gone
    a = out[0]
    assert a["beredskab"] == "TrekantBrand" and a["station"] == "Kolding" and a["message"] == "Bygn.brand-Gård"
    assert a["time"] == int(datetime(2026, 11, 6, 11, 50, tzinfo=timezone.utc).timestamp() * 1000)     # 12:50 in Denmark


def test_a_station_is_found_in_osm_first_then_by_name(client, answering):
    from app.sections.dklive import alarms, store
    store.save("stations", [{"name": "Kolding Brandstation", "key": "kolding", "lat": 55.49, "lon": 9.47}])
    assert alarms.geocode("Kolding")["matched"] == "Kolding Brandstation"
    assert alarms.geocode("Fjernby") is None and list(alarms._queue) == ["fjernby"]
    answering({"nominatim": [{"lat": "57.0", "lon": "9.9", "display_name": "Fjernby, Danmark"}]})
    alarms.geocode_job()
    assert alarms.geocode("Fjernby") == {"lat": 57.0, "lon": 9.9, "matched": "Fjernby"}
    alarms.reset()                                  # what was found outlives a restart
    assert alarms.geocode("Fjernby")["matched"] == "Fjernby"


def test_a_name_that_is_no_place_is_not_asked_about_again(client, answering):
    from app.sections.dklive import alarms
    fake = answering({"nominatim": []})
    alarms.geocode("Ingensteds")
    alarms.geocode_job()
    assert alarms.geocode("Ingensteds") is None and not alarms._queue and len(fake.asked) == 1


def test_fire_stations_are_fetched_once(client, monkeypatch):
    from app.sections.dklive import alarms, source
    calls = []

    def overpass(url, data, timeout=None):
        calls.append(url)
        if len(calls) == 1:
            raise httpx.ConnectError("nej")
        return httpx.Response(200, json={"elements": [{"lat": 56.0, "lon": 10.0, "tags": {"name": "Hammel Brandstation"}}, {"lat": 1, "lon": 2}]},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(source, "post", overpass)
    alarms.stations_job()
    alarms.stations_job()
    assert len(calls) == 2                          # one mirror failed, the next answered, and then it is done
    assert alarms.geocode("Hammel")["matched"] == "Hammel Brandstation"


# ---- traffic -----------------------------------------------------------------------

def _road(feature_id, modified, **props):
    return {"geometry": {"coordinates": [10.0, 56.0]},
            "properties": {"featureId": feature_id, "lastModifiedString": modified, "TrafficMan2_Type": "x.y.Accident",
                           "title": "Uheld", "header": "<b>E45</b> &amp; mere", "description": "<periodDescription>skjult</periodDescription><p>En</p><p>To</p>",
                           "lastModified": "06-11-2026 kl. 12:00", "beginPeriod": "06-11-2026 kl. 11:00", **props}}


def test_the_newest_version_of_a_road_event_counts():
    from app.sections.dklive import traffic
    events = traffic.parse([{"layerName": "roadblocks", "features": [
        _road("a", "2026-11-06T10:00"), _road("a", "2026-11-06T11:00", title="Nyere"),
        _road("b", "2026-11-06T10:00", suspended="true"), _road("c", "2026-11-06T10:00", duplicate="true"),
        _road("d", "2026-11-06T10:00", endPeriod="06-11-2026 kl. 09:00"),
    ]}], NOW)
    assert [e["title"] for e in events] == ["Nyere"]
    e = events[0]
    assert e["kind"] == "uheld" and e["blocking"] and e["header"] == "E45 & mere" and e["text"] == "En\nTo"
    assert e["modified"] == int(datetime(2026, 11, 6, 11, 0, tzinfo=timezone.utc).timestamp() * 1000)


# ---- trains, autobahn, webcams -----------------------------------------------------

def test_trains_need_a_key_and_keep_to_the_map(client, answering):
    from app.sections.dklive import trains
    client.put("/api/admin/setup", json={"dkliveLayers": ["trains"]})
    fake = answering({"journeypos": {"JourneyPosList": {"Journey": [
        {"id": "1", "name": " IC 123 ", "lat": 55.4, "lon": 9.6, "dirTxt": "Aarhus", "Product": [{"catOutS": "IC", "operator": "DSB"}]},
        {"id": "2", "name": "Uden position"}]}}})
    trains.job()
    assert not fake.asked and trains.get()["enabled"] is False
    client.put("/api/admin/setup", json={"rejseplanenKey": "noegle-til-tog-1"})
    trains.job()
    vehicles = trains.get()["vehicles"]
    assert [v["name"] for v in vehicles] == ["IC 123"] and vehicles[0]["category"] == "IC" and vehicles[0]["direction"] == "Aarhus"
    assert fake.asked[0][1]["accessId"] == "noegle-til-tog-1" and fake.asked[0][1]["products"] == 3103


def test_autobahn_events_and_cameras(client, answering):
    from app.sections.dklive import autobahn, webcams
    client.put("/api/admin/setup", json={"dkliveLayers": ["autobahn", "webcams"]})
    warning = {"identifier": "w1", "title": "A7 | Rader", "subtitle": " Flensburg ", "description": ["Stau", "", "Ende"], "isBlocked": "true",
               "startTimestamp": "2026-11-06T10:00:00+0100", "coordinate": {"lat": "54.3", "long": "9.7"}}
    answering({"services/warning": {"warning": [warning, {**warning, "identifier": "w2", "future": True},
                                                {**warning, "identifier": "w3", "coordinate": {"lat": "48.0", "long": "9.7"}}]},
               "services/closure": {"closure": []}, "services/roadworks": {"roadworks": []},
               "services/webcam": {"webcam": [{"identifier": "c1", "title": "A7", "imageurl": "https://x/1.jpg", "coordinate": {"lat": 54.3, "long": 9.7}},
                                              {"identifier": "c2", "title": "Uden billede", "coordinate": {"lat": 54.3, "long": 9.7}}]}})
    autobahn.job()
    items = autobahn.get()["items"]
    assert [i["id"] for i in items] == ["w1"] and items[0]["blocked"] and items[0]["text"] == "Stau\nEnde"
    assert items[0]["start"] == int(datetime(2026, 11, 6, 9, 0, tzinfo=timezone.utc).timestamp() * 1000)
    autobahn.camera_job()
    names = [w["id"] for w in webcams.get()["items"]]
    assert names == ["c1", "own-0", "own-1"]


def test_one_road_that_fails_does_not_empty_the_layer(client, answering):
    from app.sections.dklive import autobahn, source
    client.put("/api/admin/setup", json={"dkliveLayers": ["autobahn"]})
    answering({"A7/services": httpx.ConnectError("nej"), "services/": {"warning": [], "closure": [], "roadworks": []}})
    autobahn.job()
    assert source.state()["autobahn"]["ok"] and "3 af 42" in source.state()["autobahn"]["text"]


def test_windy_keeps_its_key_in_a_header_and_gives_fresh_pictures(client, answering):
    from app.sections.dklive import webcams
    client.put("/api/admin/setup", json={"dkliveLayers": ["webcams"], "windyKey": "windy-noegle-1"})
    fake = answering({"/webcams/77": {"images": {"current": {"preview": "https://w/1.jpg?token=x"}}, "player": {"day": "https://w/day"}},
                      "api.windy.com": {"total": 1, "webcams": [{"webcamId": 77, "title": "Havn", "status": "active", "location": {"latitude": 57.0, "longitude": 9.9}},
                                                                {"webcamId": 78, "title": "Ude", "location": {"latitude": 40.0, "longitude": 9.9}}]}})
    webcams.job()
    assert [c["id"] for c in webcams.get()["items"] if c["source"] == "windy"] == ["windy-77"]
    assert all(h["x-windy-api-key"] == "windy-noegle-1" for _u, _p, h in fake.asked)
    assert "windy-noegle-1" not in json.dumps([u for u, _p, _h in fake.asked])
    assert webcams.image("77") == {"image": "https://w/1.jpg?token=x", "live": None, "day": "https://w/day"}


# ---- weather, DMI, sea, power, police, airports ------------------------------------

def test_radar_and_lightning():
    from app.sections.dklive import weather
    radar = weather.parse_radar({"host": "https://t", "radar": {"past": [{"time": 100, "path": "/a"}], "nowcast": [{"time": 200, "path": "/b"}]}}, NOW)
    assert radar["frames"] == [{"time": 100000, "path": "/a", "nowcast": False}] and radar["nowcast"][0]["nowcast"]
    strikes = weather.parse_lightning({"features": [{"geometry": {"coordinates": [9.0, 55.0]}, "properties": {"observed": "2026-11-06T10:00:00Z", "type": "1", "amp": 5}},
                                                    {"geometry": {"coordinates": []}, "properties": {}}]}, NOW)["strikes"]
    assert strikes == [{"lon": 9.0, "lat": 55.0, "time": source_ms("2026-11-06T10:00:00Z"), "type": 1, "amp": 5}]


def source_ms(text):
    from app.sections.dklive.source import iso_ms
    return iso_ms(text)


def test_dmi_takes_the_newest_value_per_station():
    from app.sections.dklive import dmi
    feature = lambda at, value: {"geometry": {"coordinates": [9.0, 56.0]}, "properties": {"stationId": "1", "observed": at, "value": value}}
    speed = dmi.latest([feature("2026-11-06T10:00:00Z", 4.0), feature("2026-11-06T10:10:00Z", 6.0)])
    stations = dmi.wind_stations(speed, dmi.latest([feature("2026-11-06T10:10:00Z", 250)]), {}, {}, {"1": "Eksempel"})
    assert stations[0]["speed"] == 6.0 and stations[0]["dir"] == 250 and stations[0]["gust"] is None and stations[0]["name"] == "Eksempel"


def test_a_quiet_tide_gauge_is_left_out(client, answering):
    from app.sections.dklive import dmi, source
    client.put("/api/admin/setup", json={"dkliveLayers": ["sealevel"]})
    now = datetime.now(timezone.utc)
    stamp = lambda hours: (now - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    gauge = lambda sid, at: {"geometry": {"coordinates": [8.4, 55.4]}, "properties": {"stationId": sid, "observed": at, "value": 104.0}}
    answering({"collections/station": {"features": [{"properties": {"stationId": "2", "name": "Esbjerg"}}]},
               "collections/observation": {"features": [gauge("2", stamp(1)), gauge("3", stamp(5))]}})
    dmi.sea_job()
    assert [s["name"] for s in dmi.sea()["stations"]] == ["Esbjerg"] and source.state()["sealevel"]["ok"]


def test_navigational_warnings_keep_to_the_map():
    from app.sections.dklive import niord
    near = {"geometry": {"type": "GeometryCollection", "geometries": [{"type": "Polygon", "coordinates": [[[11.0, 55.0], [11.1, 55.0], [11.1, 55.1], [11.0, 55.0]]]}]}}
    far = {"geometry": {"type": "Point", "coordinates": [30.0, 70.0]}}
    out = niord.parse([
        {"id": 1, "shortId": "NW-1", "messageSeries": {"seriesId": "dma-fe"}, "publishDateFrom": 5,
         "descs": [{"lang": "en", "title": "Firing"}, {"lang": "da", "title": "Øvelse"}],
         "areas": [{"descs": [{"lang": "da", "name": "Østersøen"}]}],
         "parts": [{"descs": [{"lang": "da", "details": "<p>Tekst</p><br/>&amp; mere"}], "geometry": {"features": [near, far]}}]},
        {"id": 2, "descs": [{"lang": "da", "title": "Langt væk"}], "parts": [{"geometry": {"features": [far]}}]}])
    assert [w["id"] for w in out] == [1]
    w = out[0]
    assert w["kind"] == "fe" and w["title"] == "Øvelse" and w["area"] == "Østersøen" and len(w["geometries"]) == 1
    assert w["details"].startswith("Tekst") and "&" in w["details"]


def test_niord_tries_the_next_host(client, answering):
    from app.sections.dklive import niord
    client.put("/api/admin/setup", json={"dkliveLayers": ["navwarnings"]})
    answering({"niord.dma.dk": httpx.ConnectError("nej"), "soefartsstyrelsen": []})
    niord.job()
    assert niord._host == niord.HOSTS[1]


def test_power_uses_utc_and_the_area_from_admin(client, answering):
    from app.sections.dklive import energy
    client.put("/api/admin/setup", json={"priceArea": "DK2"})
    fake = answering({"PowerSystemRightNow": {"records": [{"Minutes1UTC": "2026-11-06T10:00:00", "OffshoreWindPower": 100.0, "onshorewindpower": 50.0, "SolarPower": 5.0,
                                                           "ProductionGe100MW": 300.0, "ProductionLt100MW": 200.0, "CO2Emission": 90.0, "Exchange_Sum": -10.0, "Exchange_DK1_DE": -410.5}]},
                      "DayAheadPrices": {"records": [{"TimeUTC": "2026-11-06T10:15:00", "TimeDK": "2026-11-06T11:15:00", "DayAheadPriceDKK": 1234.5678}]}})
    energy.job()
    data = energy.get()
    assert data["area"] == "DK2" and data["now"]["wind"] == 150.0 and data["now"]["exchanges"] == {"Exchange_DK1_DE": -410.5}
    assert data["prices"] == [{"time": source_ms("2026-11-06T10:15:00"), "dkk": 1.235}]
    assert '"DK2"' in fake.asked[1][1]["filter"]


def test_police_updates_become_cases():
    from app.sections.dklive import police
    xml = """<rss><channel>
    <item><title>Første</title><link>https://via.ritzau.dk/pressemeddelelse/7?x</link><pubDate>Fri, 06 Nov 2026 09:00:00 GMT</pubDate></item>
    <item><title>Nyeste</title><link>https://via.ritzau.dk/pressemeddelelse/7?y</link><pubDate>Fri, 06 Nov 2026 10:00:00 GMT</pubDate></item>
    <item><title>Gammel</title><link>https://via.ritzau.dk/pressemeddelelse/8</link><pubDate>Fri, 01 Aug 2025 10:00:00 GMT</pubDate></item>
    <item><title>Uden sag</title><link>https://example.com/</link><pubDate>Fri, 06 Nov 2026 10:00:00 GMT</pubDate></item>
    </channel></rss>"""
    cases = police.cases(police.parse(xml, 90686), NOW)
    assert len(cases) == 1 and cases[0]["title"] == "Nyeste" and cases[0]["updates"] == 2


AIRPORT_ROW = dict(id="1", ident="EKYT", type="large_airport", name="Aalborg", latitude_deg="57.09", longitude_deg="9.85", elevation_ft="10",
                   iso_country="DK", municipality="Aalborg", scheduled_service="yes", gps_code="EKYT", iata_code="AAL", home_link="", wikipedia_link="")


def test_airports_are_built_from_three_files():
    from app.sections.dklive import airports
    out = airports.build(
        [AIRPORT_ROW, {**AIRPORT_ROW, "id": "2", "latitude_deg": "51.0"}, {**AIRPORT_ROW, "id": "3", "type": "heliport"}],
        [{"airport_ref": "1", "le_ident": "08", "he_ident": "26", "length_ft": "8700", "width_ft": "150", "surface": "ASP", "lighted": "1", "closed": "0"},
         {"airport_ref": "1", "le_ident": "01", "he_ident": "19", "closed": "1"}],
        [{"airport_ref": "1", "type": "TWR", "description": "", "frequency_mhz": "118.3"}])
    assert [a["iata"] for a in out] == ["AAL"]
    assert out[0]["type"] == "large" and out[0]["runways"][0] == {"ident": "08/26", "lengthM": 2652, "widthM": 46, "surface": "ASP", "lighted": True}
    assert out[0]["frequencies"] == [{"type": "TWR", "desc": None, "mhz": "118.3"}]


def test_a_metar_is_read_both_ways_visibility_comes():
    from app.sections.dklive.airports import metar
    assert metar({"visib": "6+", "altim": 1032.4, "clouds": [{"cover": "FEW", "base": 3000}, {"cover": "CLR"}]}) | {"raw": None} == metar({"visib": "6+", "altim": 1032.4, "clouds": [{"cover": "FEW", "base": 3000}, {"cover": "CLR"}]})
    m = metar({"visib": 2.5, "altim": 1032.4, "clouds": [{"cover": "FEW", "base": 3000}, {"cover": "CLR"}]})
    assert m["visM"] == 4022 and m["qnh"] == 1032 and m["clouds"] == "FEW 3000 ft, CLR"
    assert metar({"visib": "6+"})["visM"] == "6+"


def test_airports_survive_on_what_is_kept(client, answering):
    from app.sections.dklive import airports, store
    client.put("/api/admin/setup", json={"dkliveLayers": ["airports"]})
    store.save("airports", {"at": 0, "airports": [{"id": "1", "icao": "EKYT", "type": "large", "scheduled": True, "name": "Aalborg"}]})
    answering({"ourairports": httpx.ConnectError("nej"), "metar": [{"icaoId": "EKYT", "rawOb": "METAR EKYT"}]})
    airports.job()
    assert airports.get()["airports"][0]["metar"]["raw"] == "METAR EKYT"


# ---- forecast and photos -----------------------------------------------------------

def test_a_forecast_is_kept_ten_minutes_and_names_its_place(client, answering):
    from app.sections.dklive import forecast
    fake = answering({"open-meteo": {"latitude": 56.0, "longitude": 10.0, "current": {"temperature_2m": 7},
                                     "hourly": {"time": ["2026-11-06T07:00"], "temperature_2m": [7]}},
                      "nominatim": {"address": {"town": "Ry", "municipality": "Skanderborg"}}})
    first = forecast.at(56.0, 10.0)
    assert first["place"] == "Ry, Skanderborg" and first["hourly"][0]["temperature_2m"] == 7
    forecast.at(56.0, 10.0)
    assert len(fake.asked) == 2


@pytest.mark.parametrize("address,name,expected", [
    ({"city": "Aarhus", "municipality": "Aarhus"}, None, "Aarhus"),
    ({"village": "Ry", "county": "Midtjylland"}, None, "Ry, Midtjylland"),
    ({"water": "Kattegat"}, None, "Kattegat"),
    ({}, "Et sted", "Et sted"),
])
def test_place_names(address, name, expected):
    from app.sections.dklive.forecast import place_name
    assert place_name(address, name) == expected


def test_aircraft_photos_need_a_contact(client, answering):
    from app.sections.dklive import photos
    fake = answering({"planespotters": {"photos": [{"thumbnail_large": {"src": "https://p/1.jpg"}, "link": "https://p/1", "photographer": "Fotograf"}]}})
    assert photos.aircraft("abc", None, None) is None and not fake.asked
    client.put("/api/admin/setup", json={"photoContact": "https://slq.dk"})
    photo = photos.aircraft("abc", "OY-ABC", "B738")
    assert photo == {"thumb": "https://p/1.jpg", "link": "https://p/1", "credit": "Fotograf", "source": "Planespotters.net"}
    url, params, headers = fake.asked[0]
    assert url.endswith("/ABC") and params == {"reg": "OY-ABC", "icaoType": "B738"} and "https://slq.dk" in headers["User-Agent"]
    photos.aircraft("abc", "OY-ABC", "B738")
    assert len(fake.asked) == 1


def test_a_ship_photo_must_carry_the_name():
    from app.sections.dklive.photos import pick_commons
    page = {"title": "File:Prinsesse Benedikte.jpg", "imageinfo": [{"url": "https://c/1.jpg", "descriptionurl": "https://c/1", "extmetadata": {"Artist": {"value": "<a href='x'>En</a>"}}}]}
    photo = pick_commons([page], "PRINSESSE BENEDIKTE")
    assert photo["uncertain"] and photo["credit"] == "En" and photo["thumb"] == "https://c/1.jpg"
    assert pick_commons([page], "ANDET SKIB") is None


# ---- what the browser gets ----------------------------------------------------------

def test_the_map_shows_only_the_last_six_hours(client, monkeypatch):
    from app.sections.dklive import client as dk
    from app.sections.dklive import alarms, source
    now = source.now_ms()
    monkeypatch.setattr(alarms, "_alarms", [{"id": "ny", "time": now - 3_600_000}, {"id": "gammel", "time": now - 7 * 3_600_000}])
    assert [a["id"] for a in client.get("/api/s/dklive/map/alarms").json()["alarms"]] == ["ny"]
    assert [i["id"] for i in dk.recent([{"id": 1}, {"id": 2, "a": None, "b": now - 7 * 3_600_000}], "a", "b", now_ms=now)] == [1]


def test_the_section_page_keeps_all_the_alarms(client, monkeypatch):
    from app.sections.dklive import alarms, source
    now = source.now_ms()
    monkeypatch.setattr(alarms, "_alarms", [{"id": "a", "time": now - 7 * 3_600_000, "message": "Gammel"}])
    assert [f["title"] for f in client.get("/api/s/dklive/state").json()["feed"]] == ["Gammel"]


def test_the_map_reads_only_its_layers(client):
    assert client.get("/api/s/dklive/map/settings").status_code == 404
    assert client.post("/api/s/dklive/map/flights", json={}).status_code == 405


def test_the_map_needs_the_login_and_the_section(client, family):
    from fastapi.testclient import TestClient

    from app.main import app
    me = family.get("/api/auth/status").json()["user"]
    client.patch(f"/api/admin/users/{me['id']}", json={"sections": [s for s in me["sections"] if s != "dklive"]})
    assert family.get("/api/s/dklive/map/flights").status_code == 403
    assert family.get("/api/s/dklive/map/flow/6/33/19.pbf").status_code == 403
    assert TestClient(app).get("/api/s/dklive/map/flights").status_code == 401


def test_a_tile_passes_through_and_the_key_stays_here(client, answering):
    client.put("/api/admin/setup", json={"tomtomKey": "tomtom-noegle-1"})
    fake = answering({"api.tomtom.com": "tile"})
    r = client.get("/api/s/dklive/map/flow/6/33/19.pbf")
    assert r.content == b"tile" and r.headers["content-type"] == "application/x-protobuf"
    assert fake.asked[0][0].endswith("/flow/relative/6/33/19.pbf?key=tomtom-noegle-1"
                                     "&tags=[traffic_level,traffic_road_coverage,road_category,road_subcategory]")
    client.get("/api/s/dklive/map/flow/6/33/19.pbf")
    assert len(fake.asked) == 1                     # kept a minute


def test_a_tile_that_fails_does_not_show_the_address(client, answering):
    client.put("/api/admin/setup", json={"tomtomKey": "tomtom-noegle-1"})
    request = httpx.Request("GET", "https://api.tomtom.com/x?key=tomtom-noegle-1")
    answering({"api.tomtom.com": httpx.HTTPStatusError("x?key=tomtom-noegle-1", request=request, response=httpx.Response(403, request=request))})
    r = client.get("/api/s/dklive/map/flow/6/33/19.pbf")
    assert r.status_code == 502 and "tomtom-noegle" not in r.text and "HTTP 403" in r.text
    from app.sections.dklive import client as dk
    assert dk.setup_status() == {"ok": False, "text": "Trafiktæthed: HTTP 403"}     # Admin says why the roads are grey


def test_a_tile_without_road_types_is_told_in_admin(client, answering):
    from app.sections.dklive import client as dk
    client.put("/api/admin/setup", json={"tomtomKey": "tomtom-noegle-1"})
    answering({"api.tomtom.com": "Traffic flow traffic_level"})
    assert client.get("/api/s/dklive/map/flow/6/33/19.pbf").status_code == 200
    assert dk.setup_status()["text"] == "Trafiktæthed: ingen vejtyper i svaret"


def test_no_key_no_tile(client):
    assert client.get("/api/s/dklive/map/flow/6/33/19.pbf").status_code == 404


def test_the_keys_stay_on_the_server(client):
    keys = {"aisstreamKey": "ais-noegle-12345", "rejseplanenKey": "rejse-noegle-12345", "tomtomKey": "tomtom-noegle-12345", "windyKey": "windy-noegle-12345"}
    client.put("/api/admin/setup", json=keys)
    settings = client.get("/api/admin/setup").json()["settings"]
    for name, value in keys.items():
        assert value not in json.dumps(settings)
        assert settings[f"{name}Set"] is True and settings[f"{name}Hint"] == "…2345"


def test_a_point_outside_the_map_gets_no_forecast(client):
    assert client.get("/api/s/dklive/map/forecast?lat=40&lon=10").status_code == 400


def test_a_wrong_price_area_is_refused(client):
    assert client.put("/api/admin/setup", json={"priceArea": "DK3"}).status_code == 400


def test_an_unknown_layer_is_refused(client):
    assert client.put("/api/admin/setup", json={"dkliveLayers": ["ubåde"]}).status_code == 400


def test_admin_says_which_sources_fail(client):
    from app.sections.dklive import client as dk
    from app.sections.dklive import source
    assert dk.setup_status() == {"ok": False, "text": "Venter på første hentning."}
    source.done("flights", "3 fly")
    assert dk.setup_status() == {"ok": True, "text": "1 kilder svarer."}
    source.failed("traffic", "HTTP 500")
    assert dk.setup_status() == {"ok": False, "text": "Trafik: HTTP 500"}
