/** Aircraft, moved between reports by their speed and course. Civil and military are two
 *  layers on one feed. */
import { model, metres, secondLabel, CATEGORY } from '../aircraft'
import { empty, Live, plane, point, shapeIcon } from '../live'
import { esc, rows, type Row } from '../text'
import type { Aircraft } from '../types'

const POLL_MS = 10_000
const MOST_AHEAD_S = 90             // an aircraft quiet for this long stops moving
const KNOT = 0.514444
const METRES_PER_DEGREE = 111_320

function ahead(a: Aircraft, now: number): [number, number] {
  let { lat, lon } = a
  const seconds = Math.min((now - a.seen) / 1000, MOST_AHEAD_S)
  if (!a.onGround && a.gs && a.track != null && seconds > 0) {
    const metres = a.gs * KNOT * seconds
    const course = (a.track * Math.PI) / 180
    lat += (metres * Math.cos(course)) / METRES_PER_DEGREE
    lon += (metres * Math.sin(course)) / (METRES_PER_DEGREE * Math.cos((lat * Math.PI) / 180))
  }
  return [lon, lat]
}

/** Every step redraws the map. An airliner crosses a pixel in two seconds at country zoom,
 *  so far out it need not move every second. */
const stepMs = (zoom: number) => (zoom < 8 ? 4000 : zoom < 10 ? 2000 : 1000)

function details(a: Aircraft): string {
  const r = a.route
  const climb = (a.vr ?? 0) > 200 ? ' ↑' : (a.vr ?? 0) < -200 ? ' ↓' : ''
  const list: Row[] = [
    ['Fly', [a.desc, a.type && `(${a.type})`].filter(Boolean).join(' ') || '–'],
    ['Operatør', a.operator ?? '–'],
    ['Reg.', a.reg ?? '–'],
    ['Rute', r ? `${r.from} → ${r.to}` : '–'],
    ['', r ? `${r.fromName ?? ''} → ${r.toName ?? ''}` : null],
    ['Højde', a.onGround ? 'på jorden' : a.alt != null ? `${metres(a.alt)} (${a.alt} ft)${climb}` : '–'],
    ['Stig/fald', a.vr != null && !a.onGround ? `${Math.round(a.vr * 0.00508 * 60)} m/min` : null],
    ['Fart', a.gs != null ? `${Math.round(a.gs * 1.852)} km/t` : '–'],
    ['Kurs', a.track != null ? `${Math.round(a.track)}°` : '–'],
    ['Kategori', a.category ? (a.category in CATEGORY ? CATEGORY[a.category] : a.category) : null],
    ['Squawk', a.squawk ?? '–'],
    ['Nødsignal', a.emergency],
    ['ICAO', a.id],
  ]
  return `<div class="popup"><h3>${esc(a.callsign || a.reg || a.id)}${a.military ? ', militær' : ''}</h3><div class="photo"></div><dl>${rows(list)}</dl></div>`
}

export function addFlights(live: Live, military: boolean): void {
  const { map } = live
  const id = military ? 'military' : 'flights'
  const color = military ? '#5aa9ff' : '#ffd24a'
  let aircraft: Aircraft[] = []
  shapeIcon(map, `${id}-plane`, color, (ctx, size) => plane(ctx, size / 32))
  map.addSource(id, { type: 'geojson', data: empty() })
  live.add({
    id: `${id}-icon`,
    type: 'symbol',
    source: id,
    layout: {
      'icon-image': `${id}-plane`,
      'icon-size': ['interpolate', ['linear'], ['zoom'], 5, 0.75, 9, 1.1, 12, 1.5],
      'icon-rotate': ['get', 'track'],
      'icon-rotation-alignment': 'map',
      'icon-allow-overlap': true,
      'icon-ignore-placement': true,
      'text-field': ['step', ['zoom'], '', 7, ['get', 'label'], 8.5, ['get', 'label2']],
      'text-font': ['Noto Sans Regular'],
      'text-size': 11,
      'text-line-height': 1.15,
      'text-offset': [0, 1.4],
      'text-anchor': 'top',
      'text-optional': true,
    },
    paint: {
      'icon-opacity': ['case', ['get', 'onGround'], 0.5, 1],
      'text-color': color,
      'text-halo-color': '#0b1720',
      'text-halo-width': 1.2,
    },
  })

  let drawn = 0
  const draw = () => {
    const now = Date.now()
    drawn = now
    live.setData(id, {
      type: 'FeatureCollection',
      features: aircraft.map((a) => {
        const [lon, lat] = ahead(a, now)
        return point(lon, lat, { id: a.id, track: a.track ?? 0, onGround: a.onGround, label: model(a), label2: secondLabel(a) })
      }),
    })
  }

  live.onClick(`${id}-icon`, (e) => {
    const a = aircraft.find((x) => x.id === e.features?.[0].properties.id)
    if (!a) return
    const bubble = live.popup(e.lngLat, details(a), { offset: 12 })
    const query = new URLSearchParams()
    if (a.reg) query.set('reg', a.reg)
    if (a.type) query.set('type', a.type)
    void live.photo(bubble, `/api/s/dklive/map/photo/aircraft/${encodeURIComponent(a.id)}?${query}`)
  })

  live.feed<{ aircraft: Aircraft[] }>('flights', POLL_MS, (data) => {
    aircraft = data.aircraft.filter((a) => a.military === military)
    live.aircraft = [...live.aircraft.filter((a) => a.military !== military), ...aircraft]
    if (!map.isMoving()) draw()
  })
  live.every(1000, () => {
    // Not while the map is dragged: it has enough to do.
    if (!document.hidden && aircraft.length && !map.isMoving() && Date.now() - drawn >= stepMs(map.getZoom())) draw()
  })
}
