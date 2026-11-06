/** Ships from AIS, and what else sends AIS: rescue helicopters, sea marks, distress beacons. */
import { empty, Live, point, shapeIcon } from '../live'
import { flag, kind, KIND_NAME, NAV_STATUS, typeName } from '../shipInfo'
import { esc, link, rows, type Row } from '../text'
import type { Ship } from '../types'
import { labelPaint } from '../theme'

const POLL_MS = 15_000
const HULL = '#5fd3b0', RESCUE = '#ff8a5c', MARK = '#8fd3ff', DISTRESS = '#ff5c4d'

function details(s: Ship): string {
  const k = kind(s.id)
  const ago = Math.round((Date.now() - s.seen) / 60_000)
  const pad = (n: number | null | undefined) => String(n ?? 0).padStart(2, '0')
  const list: Row[] = [
    ['Klasse', KIND_NAME[k]],
    ['Status', k === 'ship' && s.navStatus != null ? NAV_STATUS[s.navStatus] : null],
    ['Type', k === 'ship' ? typeName(s.type) : null],
    ['Flag', flag(s.id)],
    ['Fart', s.sog != null ? `${s.sog.toFixed(1).replace('.', ',')} kn (${Math.round(s.sog * 1.852)} km/t)` : null],
    ['Kurs', s.cog != null ? `${Math.round(s.cog)}°${s.heading != null && Math.abs(s.heading - s.cog) > 5 ? `, stævn ${Math.round(s.heading)}°` : ''}` : null],
    ['Drej', s.rot ? (s.rot > 0 ? 'styrbord' : 'bagbord') : null],
    ['Destination', s.dest],
    ['ETA', s.eta ? `${pad(s.eta.day)}/${pad(s.eta.month)} ${pad(s.eta.hour)}:${pad(s.eta.minute)}` : null],
    ['Størrelse', s.length ? `${s.length} × ${s.beam ?? '?'} m` : null],
    ['Dybgang', s.draught ? `${s.draught.toFixed(1).replace('.', ',')} m` : null],
    ['Kaldesignal', s.callsign],
    ['IMO', s.imo ? String(s.imo) : null],
    ['MMSI', String(s.id)],
    ['Set', ago < 1 ? 'nu' : `for ${ago} min siden`],
  ]
  return `<div class="popup"><h3>${esc(s.name || KIND_NAME[k] || `MMSI ${s.id}`)}</h3><div class="photo"></div>
    <dl>${rows(list)}</dl>${link(`https://www.marinetraffic.com/en/ais/details/ships/mmsi:${s.id}`, 'MarineTraffic')}</div>`
}

export function addShips(live: Live): void {
  const { map } = live
  let ships: Ship[] = []
  shapeIcon(map, 'ship', HULL, (ctx, size) => {
    const u = size / 32
    ctx.beginPath()
    ctx.moveTo(0, -12 * u)
    ctx.lineTo(6 * u, -2 * u)
    ctx.lineTo(6 * u, 10 * u)
    ctx.lineTo(-6 * u, 10 * u)
    ctx.lineTo(-6 * u, -2 * u)
    ctx.closePath()
  })
  shapeIcon(map, 'ship-anchored', HULL, (ctx, size) => {
    ctx.beginPath()
    ctx.arc(0, 0, size / 5, 0, Math.PI * 2)
  }, 20)
  shapeIcon(map, 'ship-sar', RESCUE, (ctx, size) => {
    const u = size / 32
    ctx.beginPath()
    ctx.roundRect(-4 * u, -6 * u, 8 * u, 14 * u, 3 * u)
    ctx.rect(-12 * u, -1 * u, 24 * u, 2 * u)
    ctx.rect(-1 * u, -12 * u, 2 * u, 24 * u)
    ctx.rect(-5 * u, 9 * u, 10 * u, 2 * u)
  })
  shapeIcon(map, 'ship-aton', MARK, (ctx, size) => {
    const u = size / 32
    ctx.beginPath()
    ctx.moveTo(0, -7 * u)
    ctx.lineTo(6 * u, 0)
    ctx.lineTo(0, 7 * u)
    ctx.lineTo(-6 * u, 0)
    ctx.closePath()
  }, 18)
  shapeIcon(map, 'ship-sart', DISTRESS, (ctx, size) => {
    ctx.beginPath()
    ctx.arc(0, 0, size / 4, 0, Math.PI * 2)
  }, 22)

  map.addSource('ships', { type: 'geojson', data: empty() })
  live.add({
    id: 'ships-icon',
    type: 'symbol',
    source: 'ships',
    layout: {
      'icon-image': ['match', ['get', 'kind'], 'sar', 'ship-sar', 'aton', 'ship-aton', 'sart', 'ship-sart', 'coast', 'ship-aton',
        ['case', ['<', ['get', 'sog'], 0.5], 'ship-anchored', 'ship']],
      'icon-size': ['interpolate', ['linear'], ['zoom'], 5, 0.8, 9, 1.1, 12, 1.5],
      'icon-rotate': ['get', 'turn'],
      'icon-rotation-alignment': 'map',
      'icon-allow-overlap': true,
      'icon-ignore-placement': true,
      'text-field': ['step', ['zoom'], ['case', ['==', ['get', 'kind'], 'sar'], ['get', 'name'], ''], 8.5, ['get', 'name']],
      'text-font': ['Noto Sans Regular'],
      'text-size': 11,
      'text-offset': [0, 1.2],
      'text-anchor': 'top',
      'text-optional': true,
    },
    paint: {
      ...labelPaint(['match', ['get', 'kind'], 'sar', RESCUE, 'aton', MARK, 'sart', DISTRESS, HULL], 1.2),
    },
  })

  live.onClick('ships-icon', (e) => {
    const s = ships.find((x) => x.id === e.features?.[0].properties.id)
    if (!s) return
    const bubble = live.popup(e.lngLat, details(s), { offset: 12 })
    if (s.name && kind(s.id) === 'ship') void live.photo(bubble, `/api/s/dklive/map/photo/ship/${s.id}?name=${encodeURIComponent(s.name)}`)
  })

  live.feed<{ ships: Ship[] }>('ships', POLL_MS, (data) => {
    ships = data.ships
    live.setData('ships', {
      type: 'FeatureCollection',
      features: ships.map((s) => point(s.lon, s.lat, {
        id: s.id, kind: kind(s.id), name: s.name || (kind(s.id) === 'sar' ? 'SAR' : ''), sog: s.sog ?? 0, turn: s.heading ?? s.cog ?? 0,
      })),
    })
  })
}
