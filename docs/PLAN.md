# SLQ Dashboard: plan and status

Last updated 2026-11-06. Read this before changing anything.

## Decided by Søren (2026-11-06)

| Topic | Decision |
|---|---|
| Shape | An overview page with info from all sections, then a page per section |
| Target | Desktop PCs. Phones only have to work |
| Platform | A new system of its own, in its own Proxmox container |
| FamilyLog | The new system reads FamilyLog through an API. It can search, never post |
| F1 | Only the calendar of coming practice, qualifying and race. Nothing live |
| DK live | Live on the overview: power prices, traffic and updates |
| LogMyLife | Was never really built, so it is developed here |
| LogMyLife remembers | All calendar events, entries from other sections, own entries |
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
| Overview | Works. Date, clock, a sentence built from the data, Dagsbåndet, a block per section |
| Ping indicator | Works. Browser → server round trip, page load; server → Cloudflare, Google, dk-live, FamilyLog by TCP connect; load average |
| Admin | Works. Users, roles, sections per user, passwords, sign out, setup of everything, lists of printers and cameras |
| Kalender | Works against the mock. Not yet run against real Google, no client exists yet |
| DK live | Works, run against a real dk-live |
| Nyheder | Works, run against real DR and TV 2 feeds |
| LogMyLife | Timeline, own entries, sharing, on this day, Google and FamilyLog ingest, Strava export import. No photos yet |
| Formel 1 | Works, run against real Jolpica |
| SLQ DL | Works. 95 facts, each with a source; admin can add and edit. Newest monologues from YouTube |
| Links | Works. Folder tree per person, pinned links on the overview, drag to move |
| FamilyLog | Works, run against a real FamilyLog on its `read-keys` branch. Month's spending, search, Dagbog and FamilyMap into LogMyLife |
| Printere | Built. One MQTT connection per printer, read only. Run against `tools/mock_printer.py`, never a real printer |
| Kameraer | Built. Pictures every 5 seconds, live video in H.264 through the login, go2rtc behind it. Run in Chrome against real go2rtc and an RTSP test source, never a real C200 |
| Aktier | Placeholder. See Nordnet below |

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
- Real Google OAuth. The whole flow ran against `tools/mock_upstreams.py` only.
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

### Waiting for a merge (needs Søren)
No PRs could be opened from where this was built, so both are pushed as branches:
- **FamilyLog `read-keys`** (0.5.0): read keys, `flk_...`, GET only, an allowlist of paths.
  The dashboard's FamilyLog section needs it.
- **dk-live `fix/power-price-time`**: dk-live read `TimeDK` as UTC, which put every
  price 1 to 2 hours late. The dashboard corrects for it until this is merged
  (`price_time` in `sections/dklive/client.py`) and honours `timeBase: "utc"` after.

### Strava API (needs Søren)
The export needs no subscription and works now. The API has needed a paid Strava
subscription since June 2026. If he has one: `activity:read_all`, and entries must stay
that person's own (Strava's Section 2.3) and never go to any AI (5.3).

### Nordnet (needs Søren)
Nordnet's official API says "currently not onboarding new customers". A key also
gives full trading access, with no read-only mode. Options:
1. If he already has API access (Nordnet: Min side → Indstillinger → Min profil →
   Sikkerhed → API-nøgle): use it, GET only, key kept on the server.
2. Otherwise: import a CSV export for the holdings, and fetch prices from a public
   source. Nothing fragile, but holdings are only as fresh as the last import.
3. Unofficial web session (the route nordpy and nordnet-mcp take, with MitID or QR
   login): real-time holdings, but it depends on unofficial behaviour and needs a
   person to log in again. Not recommended.

### Next, roughly in order
1. Finish the deploy on CT 109, then the real Google connect
2. Merge the two branches above and set the FamilyLog keys
3. Add the real printers and cameras in Admin, and fix what they turn up
4. Nordnet, when the way in is chosen
5. Photos on LogMyLife entries (FamilyLog's `_process`: resized, EXIF stripped)
6. More SLQ DL facts, above all the 90s story and guests
7. Bookmark import for Links
