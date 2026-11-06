#!/usr/bin/env python3
"""Stand-ins for everything the dashboard reads, for development and the
browser check: dk-live, Jolpica, RSS, Google and go2rtc. Everything it serves is
made up. Standard library only. The printers have their own stand-in,
tools/mock_printer.py.

    python3 tools/mock_upstreams.py 9100

Then start the backend with (see tools/dev.sh):

    APP_DKLIVE_URL=http://127.0.0.1:9100
    APP_JOLPICA_URL=http://127.0.0.1:9100/jolpica
    APP_GOOGLE_AUTH_URL=http://127.0.0.1:9100/google/auth
    APP_GOOGLE_TOKEN_URL=http://127.0.0.1:9100/google/token
    APP_GOOGLE_API_BASE=http://127.0.0.1:9100/google/api
    APP_YOUTUBE_FEED_URL=http://127.0.0.1:9100/youtube
    APP_GO2RTC_URL=http://127.0.0.1:9100/go2rtc
"""
from __future__ import annotations

import base64
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlparse
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


# ---- dk-live ---------------------------------------------------------------------

def energy() -> dict:
    """In dk-live's shape, including its wall-clock-as-UTC `time`."""
    local = now().astimezone(CPH).replace(minute=0, second=0, microsecond=0) - timedelta(hours=2)
    prices = []
    for i in range(4 * 42):
        at = local + timedelta(minutes=15 * i)
        hour = at.hour + at.minute / 60
        value = .62 + .44 * math.sin((hour - 12) / 24 * 2 * math.pi) ** 2 + .34 * math.exp(-((hour - 18) ** 2) / 6)
        wall = at.replace(tzinfo=timezone.utc)
        prices.append({"time": ms(wall), "dkk": round(value, 3)})
    return {"updated": ms(now()), "status": "ok", "area": "DK1", "price": prices[8],
            "prices": prices,
            "now": {"wind": 2140, "solar": 12, "co2": 118}}


def forecast() -> dict:
    base = now().astimezone(CPH).replace(hour=0, minute=0, second=0, microsecond=0)
    hourly = []
    for i in range(72):
        at = base + timedelta(hours=i)
        temp = 7.5 + 3.2 * math.sin((at.hour - 9) / 24 * 2 * math.pi) - i * .03
        rain = max(0.0, round(1.4 * math.sin(i / 5) - .55, 1))
        hourly.append({"time": at.strftime("%Y-%m-%dT%H:%M"), "temperature_2m": round(temp, 1),
                       "precipitation": rain, "precipitation_probability": 40, "weather_code": 61 if rain else 3})
    daily = []
    for i in range(3):
        d = base + timedelta(days=i)
        daily.append({"time": d.strftime("%Y-%m-%d"), "weather_code": 61, "temperature_2m_max": 10.2 - i,
                      "temperature_2m_min": 4.1 - i, "precipitation_sum": 3.2 + i,
                      "sunrise": (d + timedelta(hours=7, minutes=38)).strftime("%Y-%m-%dT%H:%M"),
                      "sunset": (d + timedelta(hours=16, minutes=24)).strftime("%Y-%m-%dT%H:%M")})
    return {"lat": 56.0, "lon": 10.0, "place": "Eksempelby", "elevation": 30, "updated": ms(now()),
            "current": {"temperature_2m": 8.4, "apparent_temperature": 5.9, "weather_code": 61,
                        "wind_speed_10m": 6.2, "wind_gusts_10m": 11.4, "is_day": 1},
            "minutely": [], "hourly": hourly, "daily": daily}


def odin() -> dict:
    t = now()
    return {"status": "ok", "alarms": [
        {"id": "a1", "time": ms(t - timedelta(minutes=6)), "beredskab": "Eksempel Brand", "station": "Eksempelby",
         "message": "Eksempel: ild i container", "lat": 56.04, "lon": 9.93},
        {"id": "a2", "time": ms(t - timedelta(minutes=41)), "beredskab": "Eksempel Brand", "station": "Fjernby",
         "message": "Eksempel: automatisk brandalarm", "lat": 57.05, "lon": 9.92},
    ]}


def police() -> dict:
    t = now()
    return {"status": "ok", "districts": [], "cases": [
        {"id": "p1", "district": "syd", "title": "Eksempel: færdselsuheld på motorvejen", "first": ms(t - timedelta(hours=2)),
         "last": ms(t - timedelta(minutes=18)), "updates": 3},
    ]}


def traffic() -> dict:
    t = now()
    return {"updated": ms(t), "status": "ok", "events": [
        {"id": "t1", "title": "Eksempel: uheld på E45 sydgående", "header": "", "text": "", "kind": "uheld", "blocking": True,
         "source": "Eksempel", "begin": ms(t - timedelta(minutes=30)), "end": None, "modified": ms(t - timedelta(minutes=11)),
         "lat": 56.1, "lon": 9.95},
        {"id": "t2", "title": "Eksempel: vejarbejde ved Kolding", "header": "", "text": "", "kind": "vejarbejde", "blocking": False,
         "source": "Eksempel", "begin": ms(t - timedelta(days=2)), "end": None, "modified": ms(t - timedelta(hours=3)),
         "lat": 56.2, "lon": 9.75},
    ]}


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
        {"id": "e1", "summary": "Eksempel: kursusdag", "start": {"dateTime": at(0, 9)}, "end": {"dateTime": at(0, 15, 30)}},
        {"id": "e2", "summary": "Eksempel: træning", "start": {"dateTime": at(0, 18)}, "end": {"dateTime": at(0, 19, 30)}, "location": "Hallen", "colorId": "11"},
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


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def _json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        url = urlparse(self.path)
        path, query = url.path, parse_qs(url.query)
        if path == "/api/energy":
            return self._json(energy())
        if path == "/api/forecast":
            return self._json(forecast())
        if path == "/api/odin":
            return self._json(odin())
        if path == "/api/police":
            return self._json(police())
        if path == "/api/traffic":
            return self._json(traffic())
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
        if urlparse(self.path).path == "/google/token":
            return self._json({"access_token": "mock-access", "refresh_token": "mock-refresh", "expires_in": 3600})
        return self._json({"error": "not found"}, 404)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9100
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
