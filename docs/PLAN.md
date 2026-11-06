# SLQ Dashboard: plan and status

Last updated 2026-11-06. Read this before changing anything.

## Decided by Søren (2026-11-06)

| Topic | Decision |
|---|---|
| Shape | An overview page with info from all sections, then a page per section |
| Overview, from 2026-11-06 | The map of Denmark is the background and can be zoomed, and everything else lies on top of it. Date to the far left, clock to the far right, Dagsbåndet between them, and that top bar low. News, stocks and F1 fixed to the bottom. No Kalender or DK live blocks: the band carries the calendar, the map carries DK live |
| The map | "Modificeret til den her app": built into the dashboard, not dk-live in a frame, with the API keys entered again in Admin. Only things from the last 6 hours, with a toggle for each layer under Admin → Opsætning → DK live og kortet. Only Denmark and Germany down to Hamburg: no further out and no dragging across Europe |
| Aktier | A weekly graph of what he holds |
| Target | Desktop PCs. Phones only have to work |
| Platform | A new system of its own, in its own Proxmox container |
| FamilyLog | The new system reads FamilyLog through an API. It can search, never post |
| F1 | Only the calendar of coming practice, qualifying and race. Nothing live |
| DK live | Live on the overview: power prices in the band, the rest on the map |
| LogMyLife | Was never really built, so it is developed here |
| LogMyLife remembers | One calendar, entries from other sections, own entries. Changed on 2026-11-06: at first all calendars, now only the main one, which is Google's primary until the person picks another |
| LogMyLife ↔ Google | Google to the log only. Nothing is written to Google |
| LogMyLife, who | Each person has their own and their own Google connection, and can share entries |
| Admin | Family user control, and all setup of APIs is done there |
| News | A source or two on the overview, no ads |
| SLQ DL | A history database of US late night (Letterman, Kimmel, Colbert, Carson, Conan): what happened on this date, not only guests but the whole news story from the 90s |
| Ping | An indicator from where he is logged on, and one from the server |
| Clock | The date and time are on the dashboard |
| SLQ DL, new | The newest monologues from the shows on air |
| Strava | Into LogMyLife, "maybe import": the export is built, the API is not |
| Printere | Info from his Bambu Lab printers |
| Kameraer | Feed from his TP-Link Tapo C200 cameras |
| Printer and camera details | Set in Admin, never in chat or in the repo |

The September design doc "Google Calendar Export" (LogMyLife → Google, one-way out,
with review) is superseded by "Google to the log only". Its safety notes that still
apply are in: no secrets in the clear, one day off on Google's all-day end date
(unit tested), `invalid_grant` asks to reconnect.

## Built (0.2.0)

Stack: FastAPI + SQLite + React/Vite, FamilyLog's shell (auth, migrations, settings,
section registry, `update.sh`), same as SLQ Hub and FamilyLog.

| Section | State |
|---|---|
| Overview | Works. The map fills the window under the panels: date, clock, a sentence built from the data and Dagsbåndet on top, blocks either side, news, stocks and F1 at the bottom. Fits the window; the side columns scroll if they must |
| Ping indicator | Works. Browser → server round trip, page load; server → Cloudflare, Google, FamilyLog by TCP connect; load average |
| Admin | Works. Users, roles, sections per user, passwords, sign out, setup of everything, lists of printers and cameras |
| Kalender | Works, run against real Google. Every ticked calendar in Google's colours, the main one also goes to LogMyLife |
| DK live | Works. Every source lives here now, and those without a key ran against the real thing and matched dk-live's own counts. Prices, weather, traffic, 112 and police need no setup |
| Nyheder | Works, run against real DR and TV 2 feeds |
| LogMyLife | Timeline, own entries, sharing, on this day, Google and FamilyLog ingest, Strava export import. No photos yet |
| Formel 1 | Works, run against real Jolpica |
| SLQ DL | Works. 95 facts, each with a source; admin can add and edit. Newest monologues from YouTube |
| Links | Works. Folder tree per person, pinned links on the overview, drag to move |
| FamilyLog | Works, run against a real FamilyLog on its `read-keys` branch. Month's spending, search, Dagbog and FamilyMap into LogMyLife |
| Printere | Built. One MQTT connection per printer, read only. Run against `tools/mock_printer.py`, never a real printer |
| Kameraer | Built. Pictures every 5 seconds, live video in H.264 through the login, go2rtc behind it. Run in Chrome against real go2rtc and an RTSP test source, never a real C200 |
| Aktier | Works from Nordnet's CSV export, run on a real one: holdings, average cost, dividends and results per year, and the week as one line for all holdings with a sparkline for each. Prices from Yahoo, run on the real holdings: 10 of 11 found |

### How Printere and Kameraer work
- **Printere:** TLS on 8883, user `bblp`, the LAN access code as password. Models
  report only what changed, so reports are merged. `pushall` is sent after connecting,
  at most every 5 minutes, and is the only thing ever published. A test holds it to that.
- **Kameraer:** go2rtc 1.9.15 is a second compose service with no published port and
  RTSP and WebRTC off. Streams go in with `PATCH`, not `PUT`: `PUT` also writes the login
  to go2rtc's config file in plain text. The job sends them again if go2rtc restarts.
  go2rtc masks logins in its own log and API. Family accounts do not get the section
  unless the admin ticks it.
- A live view ends when the page closes it, or after 30 minutes, because a login is
  checked once, when the stream starts. A video removed from the page goes on
  downloading unless told to stop, so the page tells it to.

## Not verified

- The Docker image, `proxmox/create-lxc.sh` and the go2rtc image have never run: no
  Docker daemon and no Proxmox where this was built. `tools/container.py` is
  FamilyLog's, renamed. Søren made CT 109 himself (2 cores, 2 GB, about 60 GB), and
  `docs/PROXMOX.md` has the steps for a container that already exists.
- Google's app is External and published, which needs home, privacy and terms links on
  Branding (`frontend/public/privacy.html`, public, serves for both) and no logo: a
  logo would mean verification. The API answers in Google's classic palette, so
  `core/google.py` maps to the modern one. Someone who chose classic in Google's own
  settings sees other shades than here.
- The four sources with a key have not run against the real thing: AISStream, Rejseplanen,
  TomTom and Windy. Their shapes are dk-live's, run against stand-ins, and ships over a real
  local websocket. Overpass does not answer from where this was built, so the fire stations
  ran against a stand-in; 112 alarms were placed through Nominatim meanwhile, which works.
- Real Bambu printers. Field names and the 5-minute rule are from OpenBambuAPI. Firmware
  since early 2025 restricts third-party control; monitoring is reported to work, and
  some setups may need LAN mode or Developer Mode.
- Real C200 cameras: RTSP paths and the Camera Account are from TP-Link's FAQ. The C200's
  audio is left out on purpose, and how fast a frame arrives is unmeasured.
- YouTube: the RSS feed answered 404 from where this was built, and neither it nor the
  Data API has run against the real thing. The keep rules ran on real titles.
- Strava: the date format in `activities.csv` is from second-hand descriptions, and
  dates are read as UTC.
- SLQ DL's dates were read from the linked pages, not checked against a second
  source one by one. One is inferred: NBC naming Leno, 6 June 1991. The source says
  "two weeks later" than 23 May and cites a New York Times article of 7 June.

## Open

### How the map works
dk-live's sources moved into `sections/dklive/`, one module per source, and its 18 layers
into `frontend/src/map/`, so the dashboard needs no other container. dk-live goes on
running on its own; its `embed-map` branch was overtaken by this and does not need merging.
The keys are `aisstreamKey`, `rejseplanenKey`, `tomtomKey` and `windyKey`, in Admin. The
rest needs no key. A layer that is off is not fetched, and `jobs.kick()` starts one that
is switched on.

The panels lie on top, so the map is told what they leave free (`.map-free`): `setPadding`
keeps Denmark, the buttons, the zoom and the popups in that part, and it refits until
someone moves the map. `DK` goes back to the whole map. On a phone the map is a block of
its own above the panels.

How far it goes is in `map/limit.ts`. `maxBounds` will not do: it keeps the whole canvas
inside the bounds, and the canvas reaches far under the panels. So `LiveMap` wraps
`transform.getConstrained` and limits the free part instead, and the zoom that fits the
area in it is the minimum zoom. That method is not public API: the browser check fails if
an update of MapLibre changes it. MapLibre 5 and later have an option for this. 4.7.1 is
kept for now.

Weight, as dragging felt heavy in 0.6.0: the panels had `backdrop-filter`, which redraws a
blur of everything behind each panel on every frame of a moving map, so it is gone. Pixels
are capped at 1.25, aircraft are not redrawn while the map moves and only every 4 seconds
at country zoom, and the pointer looks once per move, not once per layer. It could not be
measured on a real graphics card where this was built: the software renderer here spends
its time compositing and hardly moved.

Time limits, in `client.recent`: alarms and lightning by their time, traffic by when it
last changed, Autobahn and navigation warnings by their start. Things with a position right
now (planes, ships, trains) and things that are simply there (webcams, airports) are not
filtered. The DK live page keeps all of it.

Left behind in dk-live: the 112 statistics and CSV, the police panel's full texts, the radar
player (the map shows the newest picture), "Min position", and the sliders for icon sizes.
The two own webcams from `webcams-dk.json` are in `webcams.py`.

### Strava API (needs Søren)
The export needs no subscription and works now. The API has needed a paid Strava
subscription since June 2026. If he has one: `activity:read_all`, and entries must stay
that person's own (Strava's Section 2.3) and never go to any AI (5.3).

### Nordnet and prices
The API stays closed: Nordnet's docs say it is not onboarding new customers, its FAQ
offers a waiting list and lists a price from 1,290 SEK a month, and Søren has no key.
A key also gives full trading access, with no read-only mode. So the way in is the
"transactions and notes" export, which each person uploads on the Aktier page.

What the real file taught, and `aktier/nordnet.py` and `store.py` rely on: UTF-16 with a
BOM, tabs, decimal commas, ISO dates. `Antal` has no sign. `Totalt antal` is 0 on
UDBYTTE and UDBYTTESKAT rows, so those must not move a position. `Beløb` is mostly DKK,
while `Indkøbsværdi` and `Resultat` are in the security's own currency, EUR and NOK
included. Fractions are rounded, so totals are compared with a tolerance of 0.001.
The cost is `Indkøbsværdi`, which excludes fees on most purchases, so it should match
Nordnet's own average price, not what left the account.

Prices come from Yahoo Finance (`aktier/prices.py`): no key, but not an official API, so
it can stop working. The last prices stay in the database. Only ISINs are sent. Most of
what Søren holds is funds, with one price a day, so the day is the resolution, and they
are asked for by the hour because Yahoo's daily series is nearly empty for some ETFs.
One of his 11 holdings is unknown to Yahoo and shows as "uden kurs". Holdings are as
fresh as the last import.

### Next, roughly in order
1. Finish the deploy on CT 109, then the real Google connect
2. Enter the map's keys in Admin, and set the FamilyLog keys
3. Add the real printers and cameras in Admin, and fix what they turn up
4. Whatever real use of the new overview turns up
5. Photos on LogMyLife entries (FamilyLog's `_process`: resized, EXIF stripped)
6. More SLQ DL facts, above all the 90s story and guests
7. Bookmark import for Links
