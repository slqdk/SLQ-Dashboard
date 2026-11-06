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

The September design doc "Google Calendar Export" (LogMyLife → Google, one-way out,
with review) is superseded by "Google to the log only". Its safety notes that still
apply are in: no secrets in the clear, one day off on Google's all-day end date
(unit tested), `invalid_grant` asks to reconnect.

## Built (0.1.0)

Stack: FastAPI + SQLite + React/Vite, FamilyLog's shell (auth, migrations, settings,
section registry, `update.sh`), same as SLQ Hub and FamilyLog.

| Section | State |
|---|---|
| Overview | Works. Date, clock, a sentence built from the data, Dagsbåndet, a block per section |
| Ping indicator | Works. Browser → server round trip, page load; server → Cloudflare, Google, dk-live, FamilyLog by TCP connect; load average |
| Admin | Works. Users, roles, sections per user, passwords, sign out, setup of everything |
| Kalender | Works against the mock. Not yet run against real Google, no client exists yet |
| DK live | Works, run against a real dk-live |
| Nyheder | Works, run against real DR and TV 2 feeds |
| LogMyLife | Timeline, own entries, sharing, on this day, Google ingest. No photos yet |
| Formel 1 | Works, run against real Jolpica |
| SLQ DL | Works. 95 facts, each with a source; admin can add and edit |
| Links | Works. Folder tree per person, pinned links on the overview, drag to move |
| Aktier | Placeholder. See Nordnet below |
| FamilyLog | Key storage and a GET-only client. See below; FamilyLog has no read API yet |

## Not verified

- The Docker image and `proxmox/create-lxc.sh` have never run: no Docker daemon and no
  Proxmox where this was built. `tools/container.py` is FamilyLog's, renamed.
- Real Google OAuth. The whole flow ran against `tools/mock_upstreams.py` only.
- SLQ DL's dates were read from the linked pages, not checked against a second
  source one by one. One is inferred: NBC naming Leno, 6 June 1991. The source says
  "two weeks later" than 23 May and cites a New York Times article of 7 June.

## Open

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

### FamilyLog read API (needs a change in FamilyLog)
FamilyLog has only session cookies, and at most two sessions per person, so the
dashboard must not log in as someone. Proposal, in FamilyLog:
- a table of read keys (`flk_...`), one per person, stored as hashes, made in its Settings
- `Authorization: Bearer flk_...` accepted by the auth middleware for **GET only**;
  anything else 403, whatever the path
- the key acts as that person, so FamilyLog's own rules decide what can be read
- nothing else changes: `/api/okonomi/overview`, `/api/okonomi/transactions?q=`,
  `/api/dagbog/person`, `/api/fm/...` already exist as GET

Then the dashboard adds: search across them, the month's spending on the overview,
and Dagbog days and FamilyMap places on the LogMyLife timeline through `store.ingest`.

### dk-live: power prices are 1 to 2 hours off
`server/energy.js` parses `TimeDK` as UTC, so every price is shown for the wrong hour
in dk-live itself: 2 hours in summer, 1 in winter. Checked against Energi Data Service
on 2026-11-06 at 07:15: dk-live showed 1.82 kr, the actual price was 2.43 kr. The
dashboard corrects for it (`price_time` in `sections/dklive/client.py`). The fix in
dk-live is to read `TimeUTC` and send `timeBase: "utc"`, which the dashboard then
honours.

### Next, roughly in order
1. Deploy to Proxmox and run the real Google connect
2. The FamilyLog read API, then search and the feeds into LogMyLife
3. Nordnet, when the way in is chosen
4. Photos on LogMyLife entries (FamilyLog's `_process`: resized, EXIF stripped)
5. More SLQ DL facts, above all the 90s story and guests
6. Bookmark import for Links
