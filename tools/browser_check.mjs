// A walk through the running app in a real browser, against the mock upstreams.
// Needs the app on $BASE with tools/mock_upstreams.py behind it and
// tools/mock_printer.py on $PRINTER, and an empty data folder (it creates the
// first account).
//
//   BASE=http://127.0.0.1:8090 SHOTS=/tmp/shots node tools/browser_check.mjs
import { createRequire } from 'node:module'
import { mkdirSync } from 'node:fs'

const require = createRequire(import.meta.url)
const { chromium } = require('playwright')

const BASE = process.env.BASE ?? 'http://127.0.0.1:8090'
const MOCK = process.env.MOCK ?? 'http://127.0.0.1:9100'
const PRINTER = process.env.PRINTER ?? '127.0.0.1:9101'
const SHOTS = process.env.SHOTS ?? ''
const WIDTH = Number(process.env.WIDTH ?? 1600)
if (SHOTS) mkdirSync(SHOTS, { recursive: true })

let failures = 0
const check = (ok, text) => {
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${text}`)
  if (!ok) failures++
}

const browser = await chromium.launch()
const context = await browser.newContext({ viewport: { width: WIDTH, height: 1000 } })
const page = await context.newPage()
const problems = []
page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`))
page.on('console', (m) => {
  // The check provokes 400, 401, 403 and 503 on purpose.
  if (m.type() === 'error' && !/favicon|status of (40[013]|503)/.test(m.text())) problems.push(`console: ${m.text()}`)
})

const shot = async (name) => {
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true })
}
const go = async (hash) => {
  await page.goto(`${BASE}/#/${hash}`)
  await page.waitForLoadState('networkidle')
}
const noOverflow = async (name) => {
  const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  check(over <= 0, `${name}: no sideways scroll (${over}px)`)
}

// ---- first run ------------------------------------------------------------------
await page.goto(BASE)
await page.waitForSelector('text=Første gang')
check(true, 'first run asks for the administrator')
const privacy = await page.request.get(`${BASE}/privacy.html`)
check(privacy.status() === 200 && (await privacy.text()).includes('calendar.readonly'), 'the privacy page needs no login')
const icon = await page.request.get(`${BASE}/favicon.svg`)
check(icon.status() === 200 && icon.headers()['content-type'].includes('svg'), 'the tab icon is served')
await page.fill('input[autocomplete="username"]', 'soren')
await page.fill('input[type="password"]', 'korrekt-hest-1')
await page.click('button:has-text("Opret administrator")')
await page.waitForSelector('.hero h1')
check(true, 'administrator created, overview shown')
await page.waitForFunction(() => document.querySelector('.mark img')?.naturalWidth > 0)
check(true, 'the logo is in the top bar')

// ---- Admin: feeds, a family member ------------------------------------------------
await go('admin')
await page.click('.segmented button:has-text("Opsætning")')
await page.waitForSelector('legend:has-text("Nyheder")')
const urls = page.locator('.form-row.feed input').nth(1)
await urls.fill(`${MOCK}/rss/DR`)
await page.locator('.form-row.feed input').nth(3).fill(`${MOCK}/rss/TV2`)
await page.locator('fieldset:has(legend:has-text("Nordnet")) select').selectOption('csv')
await page.click('button:has-text("Gem opsætning")')
await page.waitForSelector('text=Gemt.')
check(true, 'setup saved')
check(await page.locator('input[disabled]').count() >= 3, 'values pinned by the container show locked')

const fillDevice = async (fields) => {
  for (const [label, value] of Object.entries(fields)) await page.locator('dialog').getByLabel(label, { exact: true }).fill(value)
  await page.click('dialog button:has-text("Gem")')
}
await page.click('button:has-text("Tilføj printer")')
await fillDevice({ Navn: 'P1S', 'IP-adresse': 'printer/1', Serienummer: '01S00C000000001', 'LAN Access Code': 'forkert' })
await page.waitForSelector('dialog .problem')
check(true, 'a printer address with a slash refused')
await fillDevice({ 'IP-adresse': PRINTER })
await page.waitForSelector('text=Printeren afviste adgangskoden.', { timeout: 15_000 })
check(true, 'a wrong access code is said in words')
await page.click('.devices li:has-text("P1S") button:has-text("Ret")')
check(await page.inputValue('dialog input[type="password"]') === '', 'the access code does not come back')
await fillDevice({ 'LAN Access Code': '12345678' })
await page.waitForSelector('text=1 af 1 svarer.', { timeout: 15_000 })
check(true, 'the printer answers')
await page.click('button:has-text("Tilføj kamera")')
await fillDevice({ Navn: 'Indkørsel', 'IP-adresse': '192.0.2.20', 'Brugernavn fra Camera Account': 'tapo', 'Adgangskode fra Camera Account': 'p@ss/w:rd' })
await page.waitForSelector('.devices li:has-text("Indkørsel")')
await page.waitForSelector('text=go2rtc svarer, 1 kamera sat op.', { timeout: 15_000 })
check(true, 'the camera is set up')
await shot('admin-setup')

await page.click('.segmented button:has-text("Brugere")')
await page.click('button:has-text("Ny bruger")')
await page.fill('dialog input[autocomplete="off"]', 'mor')
await page.getByRole('textbox', { name: 'Navn', exact: true }).fill('Mor')
await page.fill('dialog input[type="password"]', 'endnu-en-kode-2')
await page.click('dialog button:has-text("Opret bruger")')
await page.waitForSelector('tbody th:has-text("Mor")')
check(true, 'family member created')
const aktier = page.locator('input[aria-label="mor: Aktier"]')
check(!(await aktier.isChecked()), 'Aktier is off by default for family')
check(!(await page.locator('input[aria-label="mor: Kameraer"]').isChecked()), 'Kameraer is off by default for family')
await shot('admin-users')

// ---- Google, through the mock ------------------------------------------------------
await go('kalender')
await page.click('button:has-text("Forbind Google")')
await page.waitForURL(/google=ok/)
await page.waitForSelector('text=Eksempel: kursusdag', { timeout: 10_000 })
check(true, 'Google connected, events arrive')
await shot('kalender')

// ---- Links -------------------------------------------------------------------------
await go('links')
await page.click('button:has-text("Ny mappe")')
await page.fill('dialog input', 'Arbejde')
await page.click('dialog button:has-text("Gem")')
await page.waitForSelector('.tree-item:has-text("Arbejde")')
await page.click('.tree-item:has-text("Arbejde")')
await page.click('button:has-text("Ny mappe")')
await page.fill('dialog input', 'Beckhoff')
await page.click('dialog button:has-text("Gem")')
await page.waitForSelector('.tree-item:has-text("Beckhoff")')
await page.click('.tree-item:has-text("Beckhoff")')
await page.click('button:has-text("Nyt link")')
await page.locator('dialog label:has-text("Adresse") input').fill('infosys.beckhoff.com')
await page.locator('dialog label:has-text("Titel") input').fill('Infosys')
await page.check('dialog input[type="checkbox"]')
await page.click('dialog button:has-text("Gem")')
await page.waitForSelector('.link-list a:has-text("Infosys")')
check(await page.getAttribute('.link-list a', 'href') === 'https://infosys.beckhoff.com', 'bare host gets https')
await page.click('button:has-text("Nyt link")')
await page.locator('dialog label:has-text("Adresse") input').fill('javascript:alert(1)')
await page.click('dialog button:has-text("Gem")')
await page.waitForSelector('dialog .problem')
check((await page.textContent('dialog .problem')).includes('http'), 'javascript: address refused')
await page.click('dialog button:has-text("Annullér")')
await shot('links')

// ---- LogMyLife ---------------------------------------------------------------------
await go('logmylife')
await page.click('button:has-text("Nyt indlæg")')
await page.fill('dialog input[required]:not([type="date"])', 'Første dag som kursusleder')
await page.fill('dialog input[type="date"]', '2019-11-06')
await page.click('dialog button:has-text("Gem")')
await page.waitForSelector('.life-title:has-text("Første dag som kursusleder")')
check(true, 'own entry saved')
check(await page.locator('.life-title:has-text("fortidsminde")').count() === 1, 'a past calendar event is in the log')
check(await page.locator('.on-this-day:has-text("Første dag som kursusleder")').count() === 1, 'on this day finds it')
await page.click('button:has-text("Importér fra Strava")')
await page.setInputFiles('dialog input[type="file"]', {
  name: 'activities.csv',
  mimeType: 'text/csv',
  buffer: Buffer.from('Activity ID,Activity Date,Activity Name,Activity Type,Activity Description,Elapsed Time,Distance\n1,"Mar 4, 2021, 5:47:48 PM",Morgenløb,Run,,3120,10.21\n'),
})
await page.waitForSelector('dialog .lead:has-text("1 nye")')
await page.click('dialog button:has-text("Luk")')
await page.waitForSelector('.life-title:has-text("Morgenløb")')
check(true, 'Strava export imported')
await shot('logmylife')

// ---- the other sections -----------------------------------------------------------
await go('slq-dl')
await page.waitForSelector('.dl-lead .dl-title')
check(await page.locator('.fact').count() > 50, 'SLQ DL lists the facts')
await page.selectOption('select[aria-label="Historie"]', 'arvefoelgen')
await page.waitForFunction(() => document.querySelectorAll('.fact').length < 25)
check(true, 'SLQ DL filters by story')
await page.waitForSelector('.dl-monologues a:has-text("A Closer Look")')
check(await page.locator('.dl-monologues a').count() === 3, 'monologues listed, guests and music left out')
await shot('slq-dl')

await go('formel-1')
await page.waitForSelector('.weekend')
check(await page.locator('.weekend').count() > 0, 'F1 shows the weekends')
await shot('f1')

await go('nyheder')
await page.waitForSelector('.news li:has-text("eksempel")', { timeout: 15_000 })
const news = await page.textContent('.news')
check(!news.includes('Annonce'), 'paid item filtered out')
check(news.includes('annoncerede'), 'ordinary news with "annoncerede" kept')
check(!news.includes('alert('), 'scripts stripped from feed text')
await shot('nyheder')

await go('dk-live')
await page.waitForSelector('.updates li')
check(await page.locator('.prices tbody tr').count() > 10, 'DK live shows prices')
await shot('dk-live')

await go('printere')
await page.waitForSelector('.printer-percent')
check(/\d+ %/.test(await page.textContent('.printer-percent')), 'Printere shows the progress')
check((await page.textContent('.printer')).includes('beslag-v3.3mf'), 'and the file')
await shot('printere')

await go('kameraer')
await page.waitForFunction(() => document.querySelector('.cam-frame img')?.naturalWidth > 0)
check(true, 'Kameraer shows a picture')
const first = await page.getAttribute('.cam-frame img', 'src')
await page.waitForFunction((src) => document.querySelector('.cam-frame img').getAttribute('src') !== src, first, { timeout: 8000 })
check(true, 'the picture is renewed')
await shot('kameraer')
await page.click('.cam')
await page.waitForSelector('dialog:has-text("Live-videoen kører ikke")', { timeout: 8000 })
check(await page.locator('dialog .cam-frame img').count() === 1, 'no live video falls back to pictures')
await page.click('dialog button:has-text("Luk")')

await go('aktier')
await page.click('button:has-text("Importér fra Nordnet")')
await page.setInputFiles('dialog input[type="file"]', {
  name: 'transactions-and-notes-export.csv',
  mimeType: 'text/csv',
  // UTF-16 with a BOM, tabs and decimal commas, as the real export. Made-up rows.
  buffer: Buffer.from('\ufeff' + [
    ['Id', 'Bogføringsdag', 'Handelsdag', 'Depot', 'Transaktionstype', 'Værdipapirer', 'ISIN', 'Antal', 'Beløb', 'Valuta', 'Indkøbsværdi', 'Valuta', 'Resultat', 'Valuta', 'Totalt antal', 'Makuleringsdato'],
    ['3', '2024-03-01', '2024-03-01', '12345678', 'UDBYTTE', 'Eksempel A/S', 'DK0000000001', '20', '150,25', 'DKK', '', '', '', '', '0', ''],
    ['2', '2023-02-10', '2023-02-10', '12345678', 'KØBT', 'Eksempel Fond', 'IE0000000001', '2,5', '-750', 'DKK', '100', 'EUR', '0', 'EUR', '2,5', ''],
    ['1', '2023-01-10', '2023-01-10', '12345678', 'KØBT', 'Eksempel A/S', 'DK0000000001', '20', '-6000', 'DKK', '6000', 'DKK', '0', 'DKK', '20', ''],
  ].map((row) => row.join('\t')).join('\n'), 'utf16le'),
})
await page.waitForSelector('dialog .lead:has-text("3 nye")')
await page.click('dialog button:has-text("Luk")')
await page.waitForSelector('.holdings tbody tr:has-text("Eksempel A/S")')
check((await page.textContent('.holdings tbody tr:has-text("Eksempel A/S")')).includes('6.000,00 DKK'), 'a dividend does not read as a sale')
check((await page.textContent('.holdings tbody tr:has-text("Eksempel Fond")')).includes('2,5'), 'fractions of a fund')
await shot('aktier')
await go('familylog')
await shot('familylog')

// ---- the overview ------------------------------------------------------------------
await go('')
await page.waitForSelector('.band svg')
await page.waitForSelector('.block:has-text("Nyheder") .headlines li')
check((await page.textContent('.block:has-text("Aktier")')).includes('værdipapirer'), 'the holdings on the overview')
for (const title of ['Kalender', 'DK live', 'Nyheder', 'SLQ DL', 'Formel 1', 'LogMyLife', 'Links', 'Aktier', 'FamilyLog', 'Printere', 'Kameraer']) {
  check(await page.locator(`.block h2:has-text("${title}")`).count() === 1, `overview has ${title}`)
}
check(/\d\d:\d\d/.test(await page.textContent('.hero-clock time')), 'the clock shows')
check((await page.textContent('.block:has-text("Links")')).includes('Infosys'), 'pinned link on the overview')
check((await page.textContent('.digest')).includes('P1S er færdig kl.'), 'the digest knows when the print is done')
await page.waitForFunction(() => document.querySelector('.block .cam-frame img')?.naturalWidth > 0)
check(true, 'a camera on the overview')
await page.waitForFunction(() => /\d+ ms/.test(document.querySelector('.ping-button')?.textContent ?? ''))
check(true, 'ping shows milliseconds')
await page.waitForTimeout(300)
await noOverflow('overview')
await shot('overview')
const box = await page.locator('.band svg').boundingBox()
await page.mouse.move(box.x + box.width * 0.6, box.y + 90)
await page.waitForSelector('.band-cursor', { state: 'attached' })
check(true, 'the band has a cursor')
await page.click('.ping-button')
await page.waitForSelector('.ping-panel')
await shot('overview-ping')
await page.click('h1')

// ---- a family member ---------------------------------------------------------------
await page.click('.nav-user')
await page.waitForSelector('text=Log ind')
await page.fill('input[autocomplete="username"]', 'mor')
await page.fill('input[type="password"]', 'endnu-en-kode-2')
await page.click('button:has-text("Log ind")')
await page.waitForSelector('.hero h1')
check(await page.locator('.nav nav a:has-text("Admin")').count() === 0, 'family has no Admin')
check(await page.locator('.nav nav a:has-text("Aktier")').count() === 0, 'family has no Aktier')
check(await page.locator('.block h2:has-text("Aktier")').count() === 0, 'nor on the overview')
check(await page.locator('.nav nav a:has-text("Kameraer")').count() === 0, 'family has no Kameraer')
check(await page.locator('.block h2:has-text("Kameraer")').count() === 0, 'nor on the overview')
check(await page.locator('.block h2:has-text("Printere")').count() === 1, 'but family has Printere')
const denied = await page.evaluate(async () => (await fetch('/api/s/aktier/state')).status)
check(denied === 403, 'the API refuses a section the account does not have')
const cameraDenied = await page.evaluate(async () => (await fetch('/api/s/cameras/1/frame.jpg')).status)
check(cameraDenied === 403, 'the API refuses a camera picture too')
const adminDenied = await page.evaluate(async () => (await fetch('/api/admin/users')).status)
check(adminDenied === 403, 'the API refuses Admin to family')
await shot('family-overview')

check(problems.length === 0, `no page errors${problems.length ? `: ${problems.join(' | ')}` : ''}`)
await browser.close()
console.log(failures ? `${failures} FAILED` : 'all good')
process.exit(failures ? 1 : 0)
