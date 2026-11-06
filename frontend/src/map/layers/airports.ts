/** Airports with their runways, frequencies and METAR, and which aircraft are around them. */
import { empty, Live, plane, point, shapeIcon } from '../live'
import { esc, link, rows, type Row } from '../text'
import type { Aircraft, Airport } from '../types'
import { labelPaint } from '../theme'

const POLL_MS = 10 * 60_000
const NEAR_KM = 15          // aircraft this close are "near"
const GROUND_KM = 4         // on the ground this close is "at the airport"

const SURFACE: Record<string, string> = {
  ASP: 'asfalt', ASPH: 'asfalt', CON: 'beton', CONC: 'beton', GRS: 'græs', GRASS: 'græs', GRE: 'grus', GRV: 'grus', GRAVEL: 'grus',
  TURF: 'græs', 'ASPH-G': 'asfalt/græs', PEM: 'asfalt', BIT: 'asfalt', UNK: 'ukendt', WATER: 'vand',
}
const FREQUENCY: Record<string, string> = {
  TWR: 'Tårn', APP: 'Approach', GND: 'Ground', ATIS: 'ATIS', AFIS: 'AFIS', CTAF: 'CTAF', UNIC: 'Unicom', DEP: 'Departure', RDO: 'Radio',
  CLD: 'Clearance', DEL: 'Delivery', APRON: 'Apron', 'A/G': 'Air/Ground',
}
const FLYING: Record<string, string> = { VFR: 'VFR, godt flyvevejr', MVFR: 'MVFR, marginalt', IFR: 'IFR, lavt skydække eller sigt', LIFR: 'LIFR, meget lavt' }

function km(a: { lat: number; lon: number }, b: { lat: number; lon: number }): number {
  const rad = Math.PI / 180
  const dLat = (b.lat - a.lat) * rad, dLon = (b.lon - a.lon) * rad
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLon / 2) ** 2
  return 2 * 6371 * Math.asin(Math.sqrt(h))
}

function details(a: Airport, aircraft: Aircraft[]): string {
  const near = aircraft.map((f) => ({ f, d: km(a, f) })).filter((x) => x.d <= NEAR_KM)
  const onGround = near.filter((x) => x.f.onGround && x.d <= GROUND_KM)
  const airborne = near.filter((x) => !x.f.onGround).sort((x, y) => x.d - y.d)
  const codes = [a.iata, a.icao].filter(Boolean) as string[]
  const inbound = aircraft.filter((f) => f.route && codes.includes(f.route.to) && !f.onGround)
  const outbound = aircraft.filter((f) => f.route && codes.includes(f.route.from) && !f.onGround)
  const name = (x: { f: Aircraft; d: number }) => `${esc(x.f.callsign ?? x.f.reg ?? x.f.id)} (${x.d.toFixed(0)} km${x.f.alt != null && !x.f.onGround ? `, ${Math.round(x.f.alt * 0.3048)} m` : ''})`
  const runway = (r: Airport['runways'][number]) => esc(`${r.ident}${r.lengthM ? ` ${r.lengthM} m` : ''}${r.surface ? ` ${SURFACE[r.surface.toUpperCase()] ?? r.surface.toLowerCase()}` : ''}${r.lighted ? ', lys' : ''}`)
  const place: Row[] = [
    ['Kode', codes.join(' / ')],
    ['Type', { large: 'stor lufthavn', medium: 'mellemstor', small: 'flyveplads' }[a.type]],
    ['By', a.municipality],
    ['Højde', a.elevationFt != null ? `${Math.round(a.elevationFt * 0.3048)} m` : null],
    ['Rutefly', a.scheduled ? 'ja' : 'nej'],
    ['Baner', a.runways.length ? a.runways.map(runway).join('<br>') : null, true],
    ['Frekvenser', a.frequencies.length ? a.frequencies.map((f) => esc(`${FREQUENCY[f.type] ?? f.type} ${f.mhz}`)).join('<br>') : null, true],
    ['På jorden', onGround.length ? onGround.map(name).join('<br>') : aircraft.length ? 'ingen set' : null, true],
    ['I luften nær', airborne.length ? airborne.slice(0, 6).map(name).join('<br>') + (airborne.length > 6 ? `<br>${airborne.length - 6} mere` : '') : null, true],
    ['På vej hertil', inbound.length ? inbound.map((f) => esc(`${f.callsign} fra ${f.route?.from}`)).join('<br>') : null, true],
    ['Afgået herfra', outbound.length ? outbound.map((f) => esc(`${f.callsign} til ${f.route?.to}`)).join('<br>') : null, true],
  ]
  const m = a.metar
  const seen = m && m.visM != null ? (typeof m.visM === 'string' ? m.visM : m.visM >= 9999 ? 'mindst 10 km' : `${(m.visM / 1000).toFixed(1).replace('.', ',')} km`) : null
  const wind = m && m.windDir != null ? `${m.windDir === 'VRB' ? 'variabel' : `${m.windDir}°`} ${m.windKt ?? 0} kt${m.gustKt ? ` (stød ${m.gustKt})` : ''}` : null
  const age = m?.time ? ` <span class="muted">(${Math.round((Date.now() - m.time) / 60_000)} min)</span>` : ''
  const weather: Row[] = m ? [
    ['Vejr', m.fltCat ? FLYING[m.fltCat] ?? m.fltCat : null],
    ['Vind', wind],
    ['Sigt', seen],
    ['Skyer', m.clouds],
    ['Fænomen', m.wx],
    ['Temp / dug', m.tempC != null ? `${m.tempC} °C / ${m.dewC ?? '–'} °C` : null],
    ['QNH', m.qnh != null ? `${m.qnh} hPa` : null],
    ['METAR', `<code>${esc(m.raw)}</code>${age}`, true],
  ] : []
  const links = [a.website && link(a.website, 'Hjemmeside'), a.wikipedia && link(a.wikipedia, 'Wikipedia'),
    link(`https://www.flightradar24.com/airport/${(a.iata ?? a.icao).toLowerCase()}`, 'Flightradar24')].filter(Boolean).join('')
  return `<div class="popup airport"><h3>${esc(a.name)}</h3><dl>${rows(place)}</dl>
    ${weather.length ? `<h4>Vejr nu</h4><dl>${rows(weather)}</dl>` : ''}<div class="links">${links}</div></div>`
}

export function addAirports(live: Live): void {
  const { map } = live
  let airports: Airport[] = []
  const badge = (back: string, front: string) => (ctx: CanvasRenderingContext2D, size: number) => {
    const u = size / 32
    ctx.beginPath()
    ctx.arc(0, 0, 14 * u, 0, Math.PI * 2)
    ctx.fillStyle = back
    ctx.fill()
    ctx.strokeStyle = 'rgba(0,0,0,.55)'
    ctx.lineWidth = 1.2 * u
    ctx.stroke()
    plane(ctx, u * 0.62)
    ctx.fillStyle = front
    ctx.fill()
    ctx.beginPath()                 // nothing left for the shared helper to draw
    ctx.fillStyle = 'rgba(0,0,0,0)'
    ctx.strokeStyle = 'rgba(0,0,0,0)'
  }
  shapeIcon(map, 'airport-large', '#e9eff1', badge('#e9eff1', '#0b1720'), 34)
  shapeIcon(map, 'airport-small', '#7c919d', badge('#3a5261', '#e9eff1'), 26)

  map.addSource('airports', { type: 'geojson', data: empty() })
  live.add({
    id: 'airports-icon',
    type: 'symbol',
    source: 'airports',
    filter: ['any', ['!=', ['get', 'type'], 'small'], ['>=', ['zoom'], 8]],     // no carpet of small fields
    layout: {
      'icon-image': ['case', ['==', ['get', 'type'], 'small'], 'airport-small', 'airport-large'],
      'icon-size': ['interpolate', ['linear'], ['zoom'], 5, 0.55, 9, 0.9, 12, 1.2],
      'icon-allow-overlap': true,
      'text-field': ['step', ['zoom'], ['case', ['==', ['get', 'type'], 'large'], ['get', 'code'], ''], 7.5, ['get', 'code'], 9.5, ['get', 'name']],
      'text-font': ['Noto Sans Regular'],
      'text-size': 11,
      'text-offset': [0, 1.1],
      'text-anchor': 'top',
      'text-optional': true,
      'symbol-sort-key': ['match', ['get', 'type'], 'large', 0, 'medium', 1, 2],
    },
    paint: { ...labelPaint('#c6d3da', 1.2) },
  })
  live.add({ id: 'airports-hit', type: 'circle', source: 'airports', filter: ['any', ['!=', ['get', 'type'], 'small'], ['>=', ['zoom'], 8]], paint: { 'circle-radius': 14, 'circle-opacity': 0, 'circle-stroke-opacity': 0 } })

  live.onClick('airports-hit', (e) => {
    const a = airports.find((x) => x.id === e.features?.[0].properties.id)
    if (a) live.popup([a.lon, a.lat], details(a, live.aircraft), { offset: 12, maxWidth: '360px' })
  })

  live.feed<{ airports: Airport[] }>('airports', POLL_MS, (data) => {
    airports = data.airports
    live.setData('airports', {
      type: 'FeatureCollection',
      features: airports.map((a) => point(a.lon, a.lat, { id: a.id, type: a.type, code: a.iata ?? a.icao, name: a.name })),
    })
  })
}
