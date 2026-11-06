# CLAUDE.md — SLQ Dashboard

Søren's private start page: an overview with info from every section, and a page
per section. Desktop first; phones only have to work. Runs as Docker in its own
Proxmox LXC. **Read `docs/PLAN.md` first: decisions, what is built, what is open.**

## Layout
- `backend/app/core/` — FamilyLog's shell (db, migrations, auth, settings, logs)
  plus `jobs` (background threads), `vault` (per-person secrets), `google`
  (read-only OAuth + Calendar), `netwatch` (the server half of the ping indicator).
- `backend/app/sections/<id>/` — one package per section, each exporting `SECTION`
  (see `core/sections.py`). API under `/api/s/<id>/`; access is checked once, in
  the middleware in `main.py`. Registry: `sections/__init__.py`. `sections/dklive/` holds
  one module per live source, each a job that keeps its newest result in memory.
- `frontend/src/` — React + TypeScript + Vite. `overview/` is the front page,
  `map/` the MapLibre map behind it with one file per layer, `sections/` one component
  per section (`sections/life/` is LogMyLife's timeline, with its placement in `layout.ts`),
  `admin/` users and setup.
- `tools/mock_upstreams.py` — stand-ins for every live source (`APP_LIVE_MOCK`), Jolpica,
  RSS, Google and go2rtc.
  `tools/mock_printer.py` — a stand-in Bambu printer, real TLS and MQTT.
  `tools/browser_check.mjs` — a walk through the app in a real browser.

## Rules that must hold
- **Google is read only.** One scope, `calendar.readonly`. Nothing writes to Google.
- **FamilyLog is read only.** `sections/familylog/client.py` only ever uses GET;
  a test parses the file to hold it to that.
- **The map's keys stay on the server.** AISStream, Rejseplanen, TomTom and Windy are
  called from the backend and TomTom's tiles pass through it. A failing source is recorded
  by the kind of error (`source.why`), never its text: httpx puts the address in the text,
  and an address can hold a key. The map shows the last 6 hours, in `client.recent`, and
  a layer that is off is not fetched.
- **Printers are read only.** `sections/printers/watcher.py` publishes one thing,
  `pushall`, and at most every five minutes; a test parses the file to hold it to that.
- **Camera logins stay in memory.** Streams go to go2rtc with PATCH, never PUT, which
  writes them to its config file. go2rtc has no published port, so every picture
  passes the dashboard's login. Pass on an httpx error's type, never its text.
- **LogMyLife remembers.** Nothing from a source is deleted: a row deleted at the
  source gets `deleted_at_source`. Sections add to the log through `store.ingest`,
  which is safe to repeat. One calendar per person feeds it; the rest stay in
  `google_events` for the page. Moving the log to another calendar is the one thing
  that removes rows, and the page asks first.
- **Pictures keep their originals.** A file on an entry lives in `data/logmylife/<user>/`
  untouched; what is shown is a re-encoded copy without EXIF, and the family gets only that
  copy. Those folders are too big for `update.sh`'s backup, so it skips them and the
  export is the way out. From Strava's zip only `activities.csv` and the files its rows
  name are read; the rest is followers and logins.
- **`overview()` never calls an upstream.** It reads the database or a job's cache,
  so the page always answers at once.
- **No secrets to the browser or the log.** Settings secrets go through
  `settings.public()`; per-person tokens through `core/vault.py`.
- **Nordnet rows are a person's own.** Nothing from them reaches a log or an error
  text, only the last four digits of a depot number are kept, and real exports stay
  out of the repo and its tests. Only ISINs go to Yahoo.
- **No ads, images or trackers from news feeds.** Plain text only, paid items dropped.
- Every SLQ DL fact in `seed.json` has a source. Don't add one from memory.
- Migrations only add; never renumber one that has run.

## Conventions
UI text is Danish; identifiers, comments and these docs English. Colour carries
meaning only. Chart colours are checked with the dataviz palette validator.

## Verify a change
```
cd backend && pip install -r requirements-dev.txt && python -m pytest -q
cd frontend && npm ci && npm test && npm run build
# real browser: run the app with the mock upstreams, see tools/browser_check.mjs
```
