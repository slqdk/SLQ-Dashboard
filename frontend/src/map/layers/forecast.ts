/** Click the map, not a marker, for the weather there: now, rain for six hours, 24 hours
 *  and three days. Open-Meteo, through the server. */
import type { Live } from '../live'
import { compass, esc } from '../text'
import type { Forecast, Hourly } from '../types'

const WMO: Record<number, [string, string]> = {
  0: ['Klart', '☀'], 1: ['Overvejende klart', '🌤'], 2: ['Delvist skyet', '⛅'], 3: ['Overskyet', '☁'], 45: ['Tåge', '🌫'], 48: ['Rimtåge', '🌫'],
  51: ['Let støvregn', '🌦'], 53: ['Støvregn', '🌦'], 55: ['Kraftig støvregn', '🌧'], 56: ['Isslag, let', '🌧'], 57: ['Isslag', '🌧'],
  61: ['Let regn', '🌦'], 63: ['Regn', '🌧'], 65: ['Kraftig regn', '🌧'], 66: ['Isregn, let', '🌧'], 67: ['Isregn', '🌧'],
  71: ['Let snefald', '🌨'], 73: ['Snefald', '🌨'], 75: ['Kraftigt snefald', '❄'], 77: ['Snekorn', '🌨'], 80: ['Regnbyger', '🌦'], 81: ['Byger', '🌧'],
  82: ['Kraftige byger', '⛈'], 85: ['Snebyger', '🌨'], 86: ['Kraftige snebyger', '❄'], 95: ['Tordenvejr', '⛈'], 96: ['Torden med hagl', '⛈'],
  99: ['Kraftig torden med hagl', '⛈'],
}
const wmo = (code: number | null | undefined): [string, string] => (code != null && WMO[code]) || ['–', '']
const clock = (iso: string) => iso.slice(11, 16)
const comma = (v: number, digits: number) => v.toFixed(digits).replace('.', ',')
const unit = (v: number | null | undefined, text: string, digits = 0) => (v == null ? '–' : `${comma(v, digits)} ${text}`)

// The scale snaps to a readable step, so a drizzle does not look like a downpour.
const STEPS = [0.5, 1, 2, 5, 10, 20, 50]

function chart(list: Hourly[], labelEvery: number, withTemp = false): string {
  if (!list.length) return '<p class="muted">Ingen data.</p>'
  const W = 520, H = 120, left = 44, right = withTemp ? 30 : 8, top = 12, bottom = 20
  const iw = W - left - right, ih = H - top - bottom
  const most = Math.max(...list.map((r) => r.precipitation ?? 0))
  const scale = STEPS.find((v) => v >= most * 1.15) ?? STEPS[STEPS.length - 1]
  const bw = iw / list.length
  const x = (i: number) => left + i * bw
  const y = (v: number) => top + ih - Math.min(1, v / scale) * ih
  const temps = list.map((r) => r.temperature_2m).filter((v): v is number => v != null)
  const low = temps.length ? Math.min(...temps) : 0
  const span = Math.max(1, (temps.length ? Math.max(...temps) : 1) - low)
  const yTemp = (v: number) => top + ih - ((v - low) / span) * (ih * 0.8) - ih * 0.1

  const grid = [0, 0.25, 0.5, 0.75, 1].map((f) => {
    const at = top + ih - f * ih
    const text = f === 1 ? `${comma(scale, scale < 1 ? 1 : 0)} mm` : f === 0 ? '0' : f === 0.5 ? comma(scale / 2, scale / 2 < 1 ? 2 : 1) : ''
    return `<line x1="${left}" x2="${W - right}" y1="${at}" y2="${at}" class="grid${f === 0 ? ' base' : ''}" />${text ? `<text x="${left - 6}" y="${at + 4}" class="ax" text-anchor="end">${text}</text>` : ''}`
  }).join('')
  const bars = list.map((r, i) => {
    const v = r.precipitation ?? 0
    const chance = r.precipitation_probability
    const title = [clock(r.time), `${comma(v, 1)} mm`, chance != null ? `${chance} %` : '', r.temperature_2m != null ? `${comma(r.temperature_2m, 1)} °C` : ''].filter(Boolean).join(', ')
    return `<g class="bar"><title>${esc(title)}</title><rect x="${x(i) + bw * 0.12}" y="${top}" width="${bw * 0.76}" height="${ih}" class="hit" />
      ${v > 0 ? `<rect x="${x(i) + bw * 0.12}" y="${y(v)}" width="${bw * 0.76}" height="${Math.max(1.5, top + ih - y(v))}" rx="1" class="rain" />` : ''}</g>`
  }).join('')
  const last = list[list.length - 1].temperature_2m
  const line = withTemp && temps.length
    ? `<polyline class="temp" points="${list.map((r, i) => (r.temperature_2m == null ? '' : `${(x(i) + bw / 2).toFixed(1)},${yTemp(r.temperature_2m).toFixed(1)}`)).filter(Boolean).join(' ')}" />
       ${last != null ? `<text x="${W - right + 4}" y="${yTemp(last) + 4}" class="ax temp">${Math.round(last)}°</text>` : ''}`
    : ''
  const labels = list.map((r, i) => (i % labelEvery === 0 ? `<text x="${x(i) + bw / 2}" y="${H - 5}" class="ax" text-anchor="middle">${esc(clock(r.time))}</text>` : '')).join('')
  const dry = most === 0 ? `<text x="${left + iw / 2}" y="${top + ih / 2 + 4}" class="dry" text-anchor="middle">ingen nedbør</text>` : ''
  return `<svg viewBox="0 0 ${W} ${H}" class="fchart" preserveAspectRatio="none">${grid}${bars}${line}${dry}${labels}</svg>`
}

function render(d: Forecast): string {
  const c = d.current ?? {}
  const [text, icon] = wmo(c.weather_code)
  const now = Date.now()
  const rain = d.minutely.filter((m) => Date.parse(m.time) >= now - 900_000).slice(0, 24)
  const soon = rain.find((m) => (m.precipitation ?? 0) > 0.05)
  const hours = d.hourly.filter((h) => Date.parse(h.time) >= now - 1_800_000).slice(0, 24)
  const days = d.daily.map((day) => {
    const [t, i] = wmo(day.weather_code as number | null)
    const name = new Date(String(day.time)).toLocaleDateString('da-DK', { weekday: 'short', day: 'numeric', month: 'short' })
    return `<tr><th scope="row">${esc(name)}</th><td>${i} ${esc(t)}</td><td class="n">${Math.round(Number(day.temperature_2m_min))}/${Math.round(Number(day.temperature_2m_max))}°</td>
      <td class="n">${unit(day.precipitation_sum as number | null, 'mm', 1)}</td><td class="n">${Number(day.precipitation_probability_max ?? 0)} %</td></tr>`
  }).join('')
  return `<div class="popup forecast">
    <h3>${icon} ${esc(d.place ?? 'Vejr her')}</h3>
    <div class="now">
      <span class="temp">${c.temperature_2m != null ? `${comma(c.temperature_2m, 1)}°` : '–'}</span>
      <span class="desc">${esc(text)}<br><span class="muted">føles ${c.apparent_temperature != null ? `${Math.round(c.apparent_temperature)}°` : '–'}</span></span>
      <span class="stat" title="Vind, stød og retning">${c.wind_speed_10m != null ? Math.round(c.wind_speed_10m) : '–'}${c.wind_gusts_10m ? ` (${Math.round(c.wind_gusts_10m)})` : ''} m/s ${compass(c.wind_direction_10m)}</span>
      <span class="stat" title="Skydække">${unit(c.cloud_cover, '% skyer')}</span>
      <span class="stat" title="Lufttryk">${unit(c.pressure_msl, 'hPa')}</span>
    </div>
    <div class="outlook">
      <span class="lead">${esc(soon ? `Nedbør fra ca. ${clock(soon.time)}` : 'Ingen nedbør de næste 6 timer')}</span>
      <div class="tabs">
        <button type="button" data-tab="min" class="active">6 t</button>
        <button type="button" data-tab="hour">24 t</button>
        <button type="button" data-tab="days">3 d</button>
      </div>
    </div>
    <div data-pane="min">${chart(rain, 4)}</div>
    <div data-pane="hour" hidden>${chart(hours, 3, true)}</div>
    <div data-pane="days" hidden><table class="days"><tbody>${days}</tbody></table></div>
    <div class="foot">Open-Meteo</div>
  </div>`
}

export function addForecast(live: Live): void {
  live.map.on('click', async (e) => {
    if (live.bubble || live.onFeature(e.point)) return
    const bubble = live.popup(e.lngLat, '<div class="popup forecast"><h3>Vejr</h3><p class="muted">Henter.</p></div>', { offset: 6, maxWidth: '560px' })
    try {
      const response = await fetch(`/api/s/dklive/map/forecast?lat=${e.lngLat.lat.toFixed(4)}&lon=${e.lngLat.lng.toFixed(4)}`)
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail ?? 'Intet svar.')
      bubble.setHTML(render(data as Forecast))
      const root = bubble.getElement()
      root?.querySelector('.tabs')?.addEventListener('click', (click) => {
        const tab = (click.target as HTMLElement).dataset.tab
        if (!tab) return
        root.querySelectorAll<HTMLElement>('[data-tab]').forEach((b) => b.classList.toggle('active', b.dataset.tab === tab))
        root.querySelectorAll<HTMLElement>('[data-pane]').forEach((p) => { p.hidden = p.dataset.pane !== tab })
        bubble.fit()
      })
    } catch (exc) {
      bubble.setHTML(`<div class="popup forecast"><h3>Vejr</h3><p class="err">${esc(exc instanceof Error ? exc.message : 'Intet svar.')}</p></div>`)
    }
  })
}
