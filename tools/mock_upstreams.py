#!/usr/bin/env python3
"""Stand-ins for everything the dashboard reads, for development and the
browser check: the live sources behind the map, Jolpica, RSS, Google, go2rtc and Yahoo
Finance. Everything it serves is made up. Standard library only. The printers have
their own stand-in, tools/mock_printer.py.

    python3 tools/mock_upstreams.py 9100

Then start the backend with (see tools/dev.sh):

    APP_LIVE_MOCK=http://127.0.0.1:9100
    APP_JOLPICA_URL=http://127.0.0.1:9100/jolpica
    APP_GOOGLE_AUTH_URL=http://127.0.0.1:9100/google/auth
    APP_GOOGLE_TOKEN_URL=http://127.0.0.1:9100/google/token
    APP_GOOGLE_API_BASE=http://127.0.0.1:9100/google/api
    APP_YOUTUBE_FEED_URL=http://127.0.0.1:9100/youtube
    APP_GO2RTC_URL=http://127.0.0.1:9100/go2rtc
    APP_YAHOO_SEARCH_URL=http://127.0.0.1:9100/yahoo/search
    APP_YAHOO_CHART_URL=http://127.0.0.1:9100/yahoo/chart
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import struct
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlencode, urlparse
from zoneinfo import ZoneInfo

CPH = ZoneInfo("Europe/Copenhagen")


def now() -> datetime:
    return datetime.now(timezone.utc)


def ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


# ---- go2rtc ----------------------------------------------------------------------

CAMERA_PICTURE = base64.b64decode(
    "/9j/4AAQSkZJRgABAgAAAQABAAD//gAQTGF2YzYwLjMxLjEwMgD/2wBDAAgYGBwYHCEhISEhISckJygoKCcnJyco"
    "KCgrKyszMzMrKysoKCsrMDAzMzc5NzQ0MzQ5OTw8PEhIRUVUVFdnZ3z/xABWAAEBAQEBAQAAAAAAAAAAAAADAAEE"
    "AgcBAQEBAQEBAQAAAAAAAAAAAAIAAQMFBgQQAQEAAAAAAAAAAAAAAAAAAAABEQEAAAAAAAAAAAAAAAAAAAAA/8AA"
    "EQgANgBgAwESAAISAAMSAP/aAAwDAQACEQMRAD8A+TwkfrJ+QTwsNoiaFhkLDQsMgYaFhkImhYZCJ4SGQieEhtET"
    "R6Nosakkkkkkkkny2Ej5snuieEhkInhIZCw8JDIGHhYZCJoWGQiaFhEImj2ZCx6STEkkkkkkkkk+awsfPk9oTwkM"
    "hE8JDIWHhIZAw8JDaDDwkMhE8JDIRe01MSSSSSSSSSSSST59Gx4aeunVGx1TmnVGx1TmnVGx1TmnVGx0a5p1RsdG"
    "gx0NNAkkkkkkkkkkkkkkkn//2Q==")
STREAMS: dict[str, str] = {}
RADAR_TILE = base64.b64decode(        # one see-through pixel
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=")


# ---- Yahoo Finance ---------------------------------------------------------------

LISTINGS = {"DK0000000001": ("EKS.CO", "DKK", 300.0), "IE0000000001": ("FOND.DE", "EUR", 40.0)}


def yahoo_chart(symbol: str) -> dict:
    """A month of closes, wandering a little, as Yahoo's chart answers."""
    listing = next((v for v in LISTINGS.values() if v[0] == symbol), (symbol, "DKK", 7.46))
    start = now().replace(hour=12, minute=0, second=0, microsecond=0) - timedelta(days=30)
    days = [start + timedelta(days=i) for i in range(31)]
    closes = [round(listing[2] * (1 + .02 * math.sin(i / 3)), 3) for i in range(31)]
    return {"chart": {"result": [{"meta": {"currency": listing[1], "gmtoffset": 3600},
                                  "timestamp": [int(d.timestamp()) for d in days],
                                  "indicators": {"quote": [{"close": closes}]}}]}}


# ---- the live sources, each in its own shape --------------------------------------

def stamp(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def danish(dt: datetime, fmt: str) -> str:
    return dt.astimezone(CPH).strftime(fmt)


def energy_now() -> dict:
    return {"records": [{"Minutes1UTC": stamp(now()), "OffshoreWindPower": 1240.5, "OnshoreWindPower": 900.2, "SolarPower": 12.0,
                         "ProductionGe100MW": 610.0, "ProductionLt100MW": 220.0, "CO2Emission": 118.0, "Exchange_Sum": -310.0,
                         "Exchange_DK1_DE": -410.0, "Exchange_DK1_NO": 320.0, "Exchange_DK1_SE": 150.0, "Exchange_DK1_NL": -220.0,
                         "Exchange_DK1_GB": 0.0, "Exchange_GreatBelt": 200.0, "Exchange_DK2_DE": -180.0, "Exchange_DK2_SE": 90.0}]}


def day_ahead() -> dict:
    start = now().astimezone(CPH).replace(minute=0, second=0, microsecond=0) - timedelta(hours=2)
    records = []
    for i in range(4 * 42):
        at = start + timedelta(minutes=15 * i)
        hour = at.hour + at.minute / 60
        value = .62 + .44 * math.sin((hour - 12) / 24 * 2 * math.pi) ** 2 + .34 * math.exp(-((hour - 18) ** 2) / 6)
        records.append({"TimeUTC": stamp(at.astimezone(timezone.utc)), "PriceArea": "DK1", "DayAheadPriceDKK": round(value * 1000, 1)})
    return {"records": records}


def open_meteo() -> dict:
    base = now().astimezone(CPH).replace(hour=0, minute=0, second=0, microsecond=0)
    hours = [base + timedelta(hours=i) for i in range(72)]
    temp = [round(7.5 + 3.2 * math.sin((h.hour - 9) / 24 * 2 * math.pi) - i * .03, 1) for i, h in enumerate(hours)]
    rain = [max(0.0, round(1.4 * math.sin(i / 5) - .55, 1)) for i in range(72)]
    quarter = now().astimezone(CPH).replace(minute=0, second=0, microsecond=0)
    quarters = [quarter + timedelta(minutes=15 * i) for i in range(24)]
    days = [base + timedelta(days=i) for i in range(3)]
    return {"latitude": 56.0, "longitude": 10.0, "elevation": 30,
            "current": {"temperature_2m": 8.4, "apparent_temperature": 5.9, "weather_code": 61, "cloud_cover": 80, "pressure_msl": 1012,
                        "wind_speed_10m": 6.2, "wind_gusts_10m": 11.4, "wind_direction_10m": 250, "is_day": 1},
            "minutely_15": {"time": [q.strftime("%Y-%m-%dT%H:%M") for q in quarters], "precipitation": [0.1 * (i % 5) for i in range(24)],
                            "weather_code": [61] * 24},
            "hourly": {"time": [h.strftime("%Y-%m-%dT%H:%M") for h in hours], "temperature_2m": temp, "precipitation": rain,
                       "precipitation_probability": [40] * 72, "weather_code": [61 if r else 3 for r in rain]},
            "daily": {"time": [d.strftime("%Y-%m-%d") for d in days], "weather_code": [61] * 3, "temperature_2m_max": [10.2, 9.2, 8.2],
                      "temperature_2m_min": [4.1, 3.1, 2.1], "precipitation_sum": [3.2, 4.2, 5.2], "precipitation_probability_max": [60] * 3,
                      "sunrise": [(d + timedelta(hours=7, minutes=38)).strftime("%Y-%m-%dT%H:%M") for d in days],
                      "sunset": [(d + timedelta(hours=16, minutes=24)).strftime("%Y-%m-%dT%H:%M") for d in days]}}


def alarms_page(page: int) -> str:
    rows = [(6, "Eksempel Brand", "Eksempelby", "Eksempel: ild i container"), (41, "Eksempel Brand", "Fjernby", "Eksempel: automatisk brandalarm")]
    cells = "".join(f"<tr><td>{danish(now() - timedelta(minutes=age), '%d-%m-%Y %H:%M')}</td><td>{who}     Station  {station}</td><td>{message}</td></tr>"
                    for age, who, station, message in rows)
    return f"<html><body><table><tr><th>Tidspunkt</th></tr>{cells if page == 1 else ''}</table></body></html>"


def politi() -> str:
    t = now() - timedelta(minutes=18)
    return ('<?xml version="1.0"?><rss version="2.0"><channel>'
            f"<item><title>Eksempel: færdselsuheld på motorvejen</title><link>https://via.ritzau.dk/pressemeddelelse/1?x=1</link>"
            f"<pubDate>{t.strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate></item></channel></rss>")


def traffic_events() -> list:
    def event(id_, kind, title, header, lat, lon, modified, begin, subtype=""):
        return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {"featureId": id_, "title": title, "header": header, "description": "<p>Eksempel på en tekst.</p>",
                               "TrafficMan2_Type": f"x.{kind}", "subtype": subtype, "kommune": "Eksempel", "duplicate": "false",
                               "suspended": "false", "future": "false", "visible": "true", "lastModifiedString": stamp(modified),
                               "beginPeriod": danish(begin, "%d-%m-%Y kl. %H:%M"), "lastModified": danish(modified, "%d-%m-%Y kl. %H:%M")}}
    t = now()
    return [{"layerName": "events", "features": [
        event("t1", "Accident", "Eksempel: uheld på E45", "E45 sydgående - Eksempel: uheld mellem to frakørsler", 56.1, 9.95,
              t - timedelta(minutes=11), t - timedelta(minutes=30), "blocking"),
        event("t2", "Roadworks", "Eksempel: vejarbejde ved Kolding", "Eksempel: vejarbejde", 55.5, 9.45, t - timedelta(hours=2), t - timedelta(days=2)),
        event("t3", "Roadworks", "Eksempel: gammelt vejarbejde", "Eksempel: for gammelt til kortet", 56.2, 9.75, t - timedelta(hours=9), t - timedelta(days=2)),
    ]}]


def aircraft() -> dict:
    return {"ac": [
        {"hex": "aaa001", "flight": "EKS123  ", "r": "OY-EKS", "t": "B738", "desc": "BOEING 737-800", "ownOp": "Eksempel Air", "category": "A3",
         "lat": 55.4, "lon": 10.4, "alt_baro": 35000, "gs": 440, "track": 90, "baro_rate": 0, "squawk": "1234", "seen_pos": 1.2, "dbFlags": 0},
        {"hex": "aaa002", "flight": "HRN77", "r": "ZZ000", "t": "F16", "desc": "LOCKHEED MARTIN F-16C", "category": "A6",
         "lat": 56.6, "lon": 9.1, "alt_baro": 21000, "gs": 410, "track": 300, "seen_pos": 0.4, "dbFlags": 1},
        {"hex": "aaa003", "flight": "EKS9", "t": "A20N", "lat": 55.595, "lon": 12.665, "alt_baro": "ground", "gs": 0, "track": 10, "dbFlags": 0},
        {"hex": "bbb001", "t": "TWR", "lat": 55.0, "lon": 10.0, "alt_baro": "ground", "dbFlags": 0},
    ]}


def ships_messages() -> list:
    return [
        {"MessageType": "ShipStaticData", "MetaData": {"MMSI": 219000001},
         "Message": {"ShipStaticData": {"Name": "EKSEMPEL      ", "Type": 70, "Destination": "AARHUS", "ImoNumber": 9000001, "CallSign": "OXEK",
                                        "Dimension": {"A": 90, "B": 20, "C": 10, "D": 8}, "MaximumStaticDraught": 6.2,
                                        "Eta": {"Month": 11, "Day": 7, "Hour": 8, "Minute": 30}}}},
        {"MessageType": "PositionReport", "MetaData": {"MMSI": 219000001, "ShipName": "EKSEMPEL", "latitude": 56.3, "longitude": 11.2},
         "Message": {"PositionReport": {"Cog": 120.0, "Sog": 11.5, "TrueHeading": 118, "NavigationalStatus": 0, "RateOfTurn": 0}}},
        {"MessageType": "PositionReport", "MetaData": {"MMSI": 111219001, "ShipName": "RESCUE 1", "latitude": 55.0, "longitude": 8.2},
         "Message": {"PositionReport": {"Cog": 10.0, "Sog": 90.0, "TrueHeading": 511, "NavigationalStatus": 15, "RateOfTurn": -128}}},
    ]


def trains() -> dict:
    return {"JourneyPosList": {"Journey": [
        {"id": "tog1", "name": "IC 123", "lat": 55.4, "lon": 9.6, "dirTxt": "Eksempelby", "delay": 3, "Product": {"catOutS": "IC", "operator": "DSB"}},
        {"id": "tog2", "name": "S-tog A", "lat": 55.7, "lon": 12.5, "dirTxt": "Hundested", "Product": [{"catOutS": "S", "operator": "DSB"}]},
    ]}}


def autobahn(service: str) -> dict:
    if service == "warning":
        return {"warning": [{"identifier": "ab1", "title": "A7 | Eksempel", "subtitle": "Flensburg -> Hamburg", "description": ["Eksempel:", "stau"],
                             "isBlocked": "false", "future": False, "startTimestamp": stamp(now() - timedelta(hours=1)) + "+0100",
                             "coordinate": {"lat": "54.40", "long": "9.60"}}]}
    if service == "webcam":
        return {"webcam": [{"identifier": "cam1", "title": "A7 | Kamera", "subtitle": "Rader", "imageurl": "http://127.0.0.1:9100/picture.jpg",
                            "linkurl": "https://example.com/cam", "coordinate": {"lat": "54.30", "long": "9.70"}}]}
    return {service: []}


def windy_list() -> dict:
    return {"total": 1, "webcams": [{"webcamId": 1000, "title": "Eksempel havn", "status": "active", "location": {"latitude": 57.04, "longitude": 9.92, "city": "Eksempelby", "country": "Danmark"},
                                     "urls": {"detail": "https://example.com/windy"}, "player": {}}]}


def rainviewer() -> dict:
    t = int(now().timestamp()) // 600 * 600
    return {"host": "http://127.0.0.1:9100/rainviewer", "radar": {"past": [{"time": t - 600, "path": "/v2/radar/eks1"}, {"time": t, "path": "/v2/radar/eks2"}], "nowcast": []}}


def lightning_data() -> dict:
    t = stamp(now() - timedelta(minutes=9)) + "Z"
    return {"features": [{"geometry": {"type": "Point", "coordinates": [8.9, 55.2]}, "properties": {"observed": t, "type": "0", "amp": -12.5}}]}


def dmi(api: str, collection: str, query: dict) -> dict:
    if collection == "station":
        names = {"metObs": ("06060", "Eksempel Flyveplads"), "oceanObs": ("20002", "Eksempel Havn")}[api]
        return {"features": [{"properties": {"stationId": names[0], "name": names[1]}}]}
    t = stamp(now() - timedelta(minutes=5)) + "Z"
    if api == "oceanObs":
        return {"features": [{"geometry": {"coordinates": [8.45, 55.47]}, "properties": {"stationId": "20002", "observed": t, "value": 104.0}}]}
    value = {"wind_speed": 9.4, "wind_dir": 250, "wind_max": 14.1, "temp_dry": 7.2}[query["parameterId"][0]]
    return {"features": [{"geometry": {"coordinates": [9.1, 56.3]}, "properties": {"stationId": "06060", "observed": t, "value": value}}]}


def niord() -> list:
    return [{"id": "n1", "shortId": "NW-1-26", "messageSeries": {"seriesId": "dma-nw"}, "publishDateFrom": ms(now() - timedelta(hours=1)),
             "descs": [{"lang": "da", "title": "Eksempel: lystønde slukket"}], "areas": [{"descs": [{"lang": "da", "name": "Østersøen"}]}],
             "parts": [{"descs": [{"lang": "da", "details": "<p>Eksempel på en advarsel.</p>"}],
                        "geometry": {"features": [{"geometry": {"type": "Point", "coordinates": [11.8, 54.8]}}]}}]},
            {"id": "n2", "shortId": "FE-2-26", "messageSeries": {"seriesId": "dma-fe"}, "publishDateFrom": ms(now() - timedelta(hours=2)),
             "descs": [{"lang": "da", "title": "Eksempel: skydeøvelse"}],
             "parts": [{"geometry": {"features": [{"geometry": {"type": "Polygon", "coordinates": [[[8.3, 56.4], [8.0, 56.4], [8.0, 56.2], [8.3, 56.2], [8.3, 56.4]]]}}]}}]}]


AIRPORTS = ("id,ident,type,name,latitude_deg,longitude_deg,elevation_ft,iso_country,municipality,scheduled_service,gps_code,iata_code,home_link,wikipedia_link\n"
            "1,EKXX,large_airport,Eksempel Lufthavn,55.62,12.65,17,DK,Eksempelby,yes,EKXX,EKS,https://example.com/,\n"
            "2,EK99,small_airport,Lille Flyveplads,56.0,9.5,100,DK,,no,EK99,,,\n"
            "3,EGXX,large_airport,Udenfor,51.0,0.0,10,GB,,yes,EGXX,,,\n")
RUNWAYS = "airport_ref,le_ident,he_ident,length_ft,width_ft,surface,lighted,closed\n1,04,22,11000,150,ASP,1,0\n"
FREQUENCIES = "airport_ref,type,description,frequency_mhz\n1,TWR,Tower,118.1\n"


def metar() -> list:
    return [{"icaoId": "EKXX", "rawOb": "METAR EKXX 061020Z 25009KT 9999 FEW030 08/05 Q1012", "reportTime": stamp(now() - timedelta(minutes=20)) + ".000Z",
             "temp": 8, "dewp": 5, "wdir": 250, "wspd": 9, "visib": "6+", "altim": 1012.0, "clouds": [{"cover": "FEW", "base": 3000}], "fltCat": "VFR"}]


# ---- Jolpica ---------------------------------------------------------------------

def jolpica(year: int) -> dict:
    start = now().replace(hour=12, minute=0, second=0, microsecond=0)
    start += timedelta(days=(4 - start.weekday()) % 7)
    if start.year != year:
        return {"MRData": {"RaceTable": {"Races": []}}}
    races = []
    for rnd, name in enumerate(("Eksempel Grand Prix", "Prøve Grand Prix", "Sæsonfinale Grand Prix"), 1):
        f = start + timedelta(days=7 * (rnd - 1))
        s = f + timedelta(days=1)
        r = f + timedelta(days=2)
        iso = lambda d, h: {"date": d.strftime("%Y-%m-%d"), "time": f"{h:02d}:30:00Z"}
        race = {"season": str(year), "round": str(rnd), "raceName": name,
                "Circuit": {"circuitName": f"Testbane {rnd}", "Location": {"country": "Eksempel"}},
                "date": r.strftime("%Y-%m-%d"), "time": "15:00:00Z",
                "FirstPractice": iso(f, 12), "SecondPractice": iso(f, 16), "ThirdPractice": iso(s, 11),
                "Qualifying": iso(s, 15)}
        races.append(race)
    return {"MRData": {"RaceTable": {"Races": races}}}


# ---- RSS -------------------------------------------------------------------------

def rss(name: str) -> str:
    items = [
        ("Eksempel: overskrift om noget vigtigt", "Kort tekst fra kilden uden billeder.", 12, "Indland"),
        ("Annonce: Køb den nye bil", "Betalt indhold, som skal sorteres fra.", 20, "Annonce"),
        (f"{name} eksempel: regeringen annoncerede i dag en ny plan", "Almindelig nyhed med ordet annoncerede.", 33, "Politik"),
        (f"{name} eksempel: stærk vind i Sønderjylland", "<p>Tekst med <b>tags</b> og &amp; tegn.</p><script>alert(1)</script>", 64, "Vejr"),
        (f"{name} eksempel: nyt om tog", "Tekst.", 120, "Indland"),
    ]
    out = ['<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>Mock</title>']
    for i, (title, text, age, cat) in enumerate(items):
        when = (now() - timedelta(minutes=age)).strftime("%a, %d %b %Y %H:%M:%S +0000")
        out.append(f"<item><title>{title}</title><link>https://example.com/{name}/{i}</link>"
                   f"<description><![CDATA[{text}]]></description><category>{cat}</category>"
                   f"<pubDate>{when}</pubDate></item>")
    out.append("</channel></rss>")
    return "".join(out)


# ---- YouTube ---------------------------------------------------------------------

def youtube(channel: str) -> str:
    rows = {
        "UCa6vGFO9ty8v5KZJXQxdhaw": ["Eksempel: Jimmy Kimmel on the news of the day", "Gæst Navn on His New Movie", "Band Navn – Song"],
        "UC8-Th83bH_thdKZDJCrn88g": ["Eksempel: Tonight-monolog | The Tonight Show", "Game with Gæst | The Tonight Show Starring Jimmy Fallon"],
        "UCVTyTA7-g9nopHeHbeuvpRA": ["Eksempel: politik i dag: A Closer Look", "Gæst Navn Talks Her Film"],
    }.get(channel, [])
    out = ['<?xml version="1.0" encoding="UTF-8"?><feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" '
           'xmlns="http://www.w3.org/2005/Atom"><title>Mock</title>']
    for i, title in enumerate(rows):
        when = (now() - timedelta(hours=3 + i * 5)).isoformat()
        out.append(f"<entry><id>yt:video:{channel[-4:]}{i}</id><yt:videoId>{channel[-4:]}{i}</yt:videoId>"
                   f"<title>{title.replace('&', '&amp;')}</title><published>{when}</published></entry>")
    out.append("</feed>")
    return "".join(out)


# ---- Google ----------------------------------------------------------------------

def google_events(query: dict) -> dict:
    token = (query.get("syncToken") or [""])[0]
    if token == "gone":
        return {"__status": 410}
    base = now().astimezone(CPH).replace(hour=0, minute=0, second=0, microsecond=0)
    if token:
        return {"items": [], "nextSyncToken": "sync-2"}

    def at(day: int, h: int, m: int = 0) -> str:
        return (base + timedelta(days=day, hours=h, minutes=m)).isoformat()

    items = [
        {"id": "e1", "summary": "Eksempel: kursusdag", "start": {"dateTime": at(0, 9)}, "end": {"dateTime": at(0, 23, 50)}},
        {"id": "e2", "summary": "Eksempel: træning", "start": {"dateTime": at(0, 18)}, "end": {"dateTime": at(0, 23, 55)}, "location": "Hallen", "colorId": "11"},
        {"id": "e3", "summary": "Eksempel: hele dagen", "start": {"date": (base + timedelta(days=1)).strftime("%Y-%m-%d")},
         "end": {"date": (base + timedelta(days=2)).strftime("%Y-%m-%d")}},
        {"id": "e4", "summary": "Eksempel: tandlæge", "start": {"dateTime": at(1, 10)}, "end": {"dateTime": at(1, 11)}},
        {"id": "e5", "summary": "Eksempel: fortidsminde", "start": {"dateTime": at(-400, 12)}, "end": {"dateTime": at(-400, 13)}},
        {"id": "e6", "status": "cancelled"},
    ]
    return {"items": items, "nextSyncToken": "sync-1"}


def family_events(query: dict) -> dict:
    tomorrow = now().astimezone(CPH).replace(hour=12, minute=0, second=0, microsecond=0) + timedelta(days=1)
    item = {"id": "f1", "summary": "Eksempel: familiefest", "start": {"dateTime": tomorrow.isoformat()},
            "end": {"dateTime": (tomorrow + timedelta(hours=2)).isoformat()}}
    return {"items": [] if query.get("syncToken") else [item], "nextSyncToken": "sync-1"}


LIVE_HOSTS = {"api.adsb.lol", "api.adsbdb.com", "www.beredskabsinfo.dk", "nominatim.openstreetmap.org", "storage.googleapis.com",
              "www.rejseplanen.dk", "verkehr.autobahn.de", "api.windy.com", "api.rainviewer.com", "opendataapi.dmi.dk", "api.open-meteo.com",
              "niord.dma.dk", "api.energidataservice.dk", "via.ritzau.dk", "davidmegginson.github.io", "aviationweather.gov", "api.tomtom.com",
              "stream.aisstream.io", "api.planespotters.net", "commons.wikimedia.org"}
SOCKET_MAGIC = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def _send(self, body: bytes, kind: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data, status: int = 200) -> None:
        self._send(json.dumps(data).encode(), "application/json", status)

    def _text(self, text: str, kind: str = "text/plain; charset=utf-8") -> None:
        self._send(text.encode(), kind)

    def _live(self, host: str, rest: str, query: dict) -> None:
        if host == "api.adsb.lol":
            return self._json(aircraft())
        if host == "api.adsbdb.com":
            return self._json({"response": {"flightroute": {"origin": {"iata_code": "CPH", "municipality": "København"},
                                                            "destination": {"iata_code": "AAL", "municipality": "Aalborg"}}}})
        if host == "www.beredskabsinfo.dk":
            return self._text(alarms_page(int(query.get("puls_page", ["1"])[0])), "text/html; charset=utf-8")
        if host == "nominatim.openstreetmap.org":
            if rest == "reverse":
                return self._json({"address": {"town": "Eksempelby", "municipality": "Eksempel Kommune"}})
            return self._json([{"lat": "56.04", "lon": "9.93", "display_name": "Eksempelby, Danmark"}] if "Fjernby" not in query["q"][0]
                              else [{"lat": "57.05", "lon": "9.92", "display_name": "Fjernby, Danmark"}])
        if host == "storage.googleapis.com":
            return self._json(traffic_events())
        if host == "www.rejseplanen.dk":
            return self._json(trains())
        if host == "verkehr.autobahn.de":
            return self._json(autobahn(rest.rsplit("/", 1)[1]))
        if host == "api.windy.com":
            if rest.endswith("/webcams"):
                return self._json(windy_list())
            return self._json({"images": {"current": {"preview": "http://127.0.0.1:9100/picture.jpg"}}, "player": {"day": "https://example.com/day"}})
        if host == "api.rainviewer.com":
            return self._json(rainviewer())
        if host == "opendataapi.dmi.dk":
            parts = rest.split("/")
            if parts[1] == "lightningdata":
                return self._json(lightning_data())
            return self._json(dmi(parts[1], parts[3], query))
        if host == "api.open-meteo.com":
            return self._json(open_meteo())
        if host == "niord.dma.dk":
            return self._json(niord())
        if host == "api.energidataservice.dk":
            return self._json(energy_now() if rest.endswith("PowerSystemRightNow") else day_ahead())
        if host == "via.ritzau.dk":
            return self._text(politi(), "application/rss+xml")
        if host == "davidmegginson.github.io":
            return self._text({"airports.csv": AIRPORTS, "runways.csv": RUNWAYS}.get(rest.rsplit("/", 1)[1], FREQUENCIES))
        if host == "aviationweather.gov":
            return self._json(metar())
        if host == "api.tomtom.com":
            return self._send(b"", "application/x-protobuf")
        if host == "stream.aisstream.io":
            return self._ais()
        return self._json({"photos": [], "query": {"pages": {}}})

    # AISStream is a websocket, and this is just enough of one to stand in for it.
    def _frame(self, opcode: int, payload: bytes) -> None:
        size = len(payload)
        head = bytes([0x80 | opcode]) + (bytes([size]) if size < 126 else bytes([126]) + struct.pack(">H", size))
        with self.writing:
            self.wfile.write(head + payload)
            self.wfile.flush()

    def _read_frames(self) -> None:
        while True:
            first = self.rfile.read(2)
            if len(first) < 2:
                return
            size = first[1] & 0x7f
            if size == 126:
                size = struct.unpack(">H", self.rfile.read(2))[0]
            mask = self.rfile.read(4)
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(self.rfile.read(size)))
            if first[0] & 0x0f == 9:
                self._frame(10, payload)
            elif first[0] & 0x0f == 8:
                return

    def _ais(self) -> None:
        accept = base64.b64encode(hashlib.sha1((self.headers["Sec-WebSocket-Key"] + SOCKET_MAGIC).encode()).digest()).decode()
        self.wfile.write(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                          f"Sec-WebSocket-Accept: {accept}\r\n\r\n").encode())
        self.writing = threading.Lock()
        threading.Thread(target=self._read_frames, daemon=True).start()
        try:
            while True:
                for message in ships_messages():
                    self._frame(1, json.dumps(message).encode())
                time.sleep(5)
        except OSError:
            return

    def do_GET(self):  # noqa: N802
        url = urlparse(self.path)
        path, query = url.path, parse_qs(url.query)
        host, _, rest = path.lstrip("/").partition("/")
        if host in LIVE_HOSTS:
            return self._live(host, rest, query)
        if path.startswith("/rainviewer/"):
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(RADAR_TILE)))
            self.end_headers()
            self.wfile.write(RADAR_TILE)
            return None
        if path.startswith("/jolpica/"):
            return self._json(jolpica(int(path.rsplit("/", 1)[1].split(".")[0])))
        if path.startswith("/rss/"):
            body = rss(path.rsplit("/", 1)[1]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/rss+xml")
            self.end_headers()
            self.wfile.write(body)
            return None
        if path == "/youtube":
            body = youtube(query["channel_id"][0]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/atom+xml")
            self.end_headers()
            self.wfile.write(body)
            return None
        if path == "/yahoo/search":
            listing = LISTINGS.get(query["q"][0])
            return self._json({"quotes": [{"symbol": listing[0]}] if listing else []})
        if path.startswith("/yahoo/chart/"):
            return self._json(yahoo_chart(unquote(path.removeprefix("/yahoo/chart/"))))
        if path == "/picture.jpg":
            return self._send(CAMERA_PICTURE, "image/jpeg")
        if path == "/go2rtc/api/streams":
            return self._json({name: {"producers": [{"url": "rtsp://***@"}]} for name in STREAMS})
        if path == "/go2rtc/api/frame.jpeg":
            if query["src"][0] not in STREAMS:
                return self._json({"error": "stream not found"}, 404)
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.end_headers()
            self.wfile.write(CAMERA_PICTURE)
            return None
        if path == "/google/auth":
            target = query["redirect_uri"][0] + "?" + urlencode({"code": "mock-code", "state": query["state"][0]})
            self.send_response(302)
            self.send_header("Location", target)
            self.end_headers()
            return None
        if path == "/google/api/users/me/calendarList":
            return self._json({"items": [
                {"id": "mig@example.com", "summary": "Min kalender", "primary": True, "colorId": "15", "backgroundColor": "#9fc6e7"},
                {"id": "familie@example.com", "summary": "Familien", "colorId": "13", "backgroundColor": "#92e1c0"}]})
        if path.startswith("/google/api/calendars/"):
            data = google_events(query) if "mig" in path else family_events(query)
            status = data.pop("__status", 200)
            return self._json(data, status)
        return self._json({"error": "not found"}, 404)

    def do_PATCH(self):  # noqa: N802
        query = parse_qs(urlparse(self.path).query)
        STREAMS[query["name"][0]] = query["src"][0]
        return self._json({})

    def do_DELETE(self):  # noqa: N802
        STREAMS.pop(parse_qs(urlparse(self.path).query)["src"][0], None)
        return self._json({"error": "config file disabled"}, 400)

    def do_POST(self):  # noqa: N802
        if urlparse(self.path).path.startswith("/overpass"):
            return self._json({"elements": [{"lat": 56.04, "lon": 9.93, "tags": {"name": "Eksempelby Brandstation"}}]})
        if urlparse(self.path).path == "/google/token":
            return self._json({"access_token": "mock-access", "refresh_token": "mock-refresh", "expires_in": 3600})
        return self._json({"error": "not found"}, 404)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9100
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
