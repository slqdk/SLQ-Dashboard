/** Danish road incidents from Vejdirektoratet. */
import { empty, Live, point } from '../live'
import { cap, esc, rows, stamp } from '../text'
import type { TrafficEvent } from '../types'
import { labelPaint } from '../theme'

const POLL_MS = 60_000
const COLORS: Record<string, string> = {
  uheld: '#ff7a45', spærring: '#ffb300', kø: '#ffb300', havari: '#f0c060', forhindring: '#f0c060', vejr: '#8fd3ff',
  vejarbejde: '#9aa5b5', begivenhed: '#b58cff', info: '#9aa5b5',
}

export function addTraffic(live: Live): void {
  const { map } = live
  let events: TrafficEvent[] = []
  map.addSource('traffic', { type: 'geojson', data: empty() })
  live.add({
    id: 'traffic-dot',
    type: 'circle',
    source: 'traffic',
    paint: {
      'circle-color': ['get', 'color'],
      'circle-radius': ['case', ['get', 'blocking'], 7, 5],
      'circle-stroke-color': '#0b1720',
      'circle-stroke-width': 1.5,
    },
  })
  live.add({ id: 'traffic-hit', type: 'circle', source: 'traffic', paint: { 'circle-radius': 16, 'circle-opacity': 0, 'circle-stroke-opacity': 0 } })
  live.add({
    id: 'traffic-label',
    type: 'symbol',
    source: 'traffic',
    layout: {
      'text-field': ['step', ['zoom'], ['get', 'title'], 8, ['get', 'label2']],
      'text-font': ['Noto Sans Regular'],
      'text-size': ['interpolate', ['linear'], ['zoom'], 5, 10, 9, 12],
      'text-offset': [0.8, 0],
      'text-anchor': 'left',
      'text-max-width': 16,
      'text-line-height': 1.15,
      'text-optional': true,
      'symbol-sort-key': ['case', ['get', 'blocking'], 0, 1],
    },
    paint: { ...labelPaint(['get', 'color'], 1.3) },
  })

  live.onClick('traffic-hit', (e) => {
    const ev = events.find((x) => x.id === e.features?.[0].properties.id)
    if (!ev) return
    live.popup(e.lngLat, `<div class="popup"><h3>${esc(ev.header)}</h3><p class="text">${esc(ev.text)}</p>
      <dl>${rows([['Start', stamp(ev.begin)], ['Forventet slut', stamp(ev.end)], ['Opdateret', stamp(ev.modified)], ['Kilde', ev.source]])}</dl></div>`)
  })

  live.feed<{ events: TrafficEvent[] }>('traffic', POLL_MS, (data) => {
    events = data.events
    live.setData('traffic', {
      type: 'FeatureCollection',
      features: events.map((ev) => point(ev.lon, ev.lat, {
        id: ev.id,
        blocking: ev.blocking,
        color: COLORS[ev.kind] ?? COLORS.info,
        title: cap(ev.title),
        label2: `${cap(ev.title)}\n${cap(ev.header.replace(/^[^-]+-\s*/, '').split(' mellem ')[0])}`,
      })),
    })
  })
}
