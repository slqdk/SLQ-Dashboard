/** German motorways: warnings, closures and roadworks. */
import { empty, Live, point } from '../live'
import { cap, esc } from '../text'
import type { AutobahnEvent } from '../types'
import { labelPaint } from '../theme'

const POLL_MS = 120_000
const COLORS: Record<string, string> = { melding: '#ff7a45', spærring: '#ffb300', vejarbejde: '#9aa5b5' }

export function addAutobahn(live: Live): void {
  const { map } = live
  let items: AutobahnEvent[] = []
  map.addSource('autobahn', { type: 'geojson', data: empty() })
  live.add({
    id: 'autobahn-dot',
    type: 'circle',
    source: 'autobahn',
    paint: {
      'circle-color': ['get', 'color'],
      'circle-radius': ['case', ['get', 'blocked'], 7, 5],
      'circle-stroke-color': '#0b1720',
      'circle-stroke-width': 1.5,
    },
  })
  live.add({ id: 'autobahn-hit', type: 'circle', source: 'autobahn', paint: { 'circle-radius': 16, 'circle-opacity': 0, 'circle-stroke-opacity': 0 } })
  live.add({
    id: 'autobahn-label',
    type: 'symbol',
    source: 'autobahn',
    minzoom: 7,
    layout: {
      'text-field': ['get', 'label'],
      'text-font': ['Noto Sans Regular'],
      'text-size': ['interpolate', ['linear'], ['zoom'], 7, 10, 10, 12],
      'text-offset': [0.8, 0],
      'text-anchor': 'left',
      'text-max-width': 16,
      'text-line-height': 1.15,
      'text-optional': true,
      'symbol-sort-key': ['case', ['get', 'blocked'], 0, 1],
    },
    paint: { ...labelPaint(['get', 'color'], 1.3) },
  })

  live.onClick('autobahn-hit', (e) => {
    const ev = items.find((x) => x.id === e.features?.[0].properties.id)
    if (!ev) return
    live.popup(e.lngLat, `<div class="popup"><h3>${esc(ev.road)}, ${esc(ev.title)}</h3>
      ${ev.subtitle ? `<p class="muted">${esc(ev.subtitle)}</p>` : ''}<p class="text">${esc(ev.text)}</p>
      ${ev.blocked ? '<p class="warn">Spærret</p>' : ''}</div>`)
  })

  live.feed<{ items: AutobahnEvent[] }>('autobahn', POLL_MS, (data) => {
    items = data.items
    live.setData('autobahn', {
      type: 'FeatureCollection',
      features: items.map((ev) => point(ev.lon, ev.lat, {
        id: ev.id, blocked: ev.blocked, color: COLORS[ev.kind] ?? COLORS.vejarbejde, label: `${ev.road}, ${cap(ev.subtitle || ev.title)}`,
      })),
    })
  })
}
