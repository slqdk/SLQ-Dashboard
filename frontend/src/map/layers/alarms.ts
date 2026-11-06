/** 112 alarms, placed at the station that responds. */
import { empty, Live, point } from '../live'
import { cap, esc, hhmm, rows, stamp } from '../text'
import type { Alarm } from '../types'

const POLL_MS = 60_000
const FRESH_MINUTES = 20
const RED = '#ff5c4d'

export function addAlarms(live: Live): void {
  const { map } = live
  let alarms: Alarm[] = []
  map.addSource('alarms', { type: 'geojson', data: empty() })
  live.add({
    id: 'alarms-halo',
    type: 'circle',
    source: 'alarms',
    filter: ['get', 'fresh'],
    paint: { 'circle-color': RED, 'circle-opacity': 0.25, 'circle-radius': 13, 'circle-blur': 0.6 },
  })
  live.add({
    id: 'alarms-dot',
    type: 'circle',
    source: 'alarms',
    paint: {
      'circle-color': RED,
      'circle-radius': ['case', ['get', 'fresh'], 6, 4],
      'circle-opacity': ['interpolate', ['linear'], ['get', 'ageMin'], 0, 1, 180, 0.9, 360, 0.6],
      'circle-stroke-color': '#0b1720',
      'circle-stroke-width': 1.5,
    },
  })
  live.add({ id: 'alarms-hit', type: 'circle', source: 'alarms', paint: { 'circle-radius': 16, 'circle-opacity': 0, 'circle-stroke-opacity': 0 } })
  live.add({
    id: 'alarms-label',
    type: 'symbol',
    source: 'alarms',
    layout: {
      'text-field': ['step', ['zoom'], ['get', 'label1'], 8, ['get', 'label2']],
      'text-font': ['Noto Sans Regular'],
      'text-size': ['interpolate', ['linear'], ['zoom'], 5, 10, 9, 12],
      'text-offset': [0.8, 0],
      'text-anchor': 'left',
      'text-max-width': 14,
      'text-line-height': 1.15,
      'text-optional': true,
      'symbol-sort-key': ['get', 'ageMin'],     // the newest wins when labels collide
    },
    paint: { 'text-color': '#ff8a7e', 'text-halo-color': '#0b1720', 'text-halo-width': 1.3 },
  })

  const draw = () => {
    const now = Date.now()
    const atStation = new Map<string, number>()
    live.setData('alarms', {
      type: 'FeatureCollection',
      features: alarms.filter((a) => a.lat && a.lon).map((a) => {
        // Several alarms at one station are fanned out, so each can be clicked.
        const n = atStation.get(a.station) ?? 0
        atStation.set(a.station, n + 1)
        const ageMin = (now - a.time) / 60_000
        const off = n * 0.004
        return point((a.lon as number) + off, (a.lat as number) + off * 0.6, {
          id: a.id,
          ageMin,
          fresh: ageMin < FRESH_MINUTES,
          label1: cap(a.message),
          label2: `${cap(a.message)}\n${cap(`${a.station}, ${hhmm(a.time)}`)}`,
        })
      }),
    })
  }

  live.onClick('alarms-hit', (e) => {
    const a = alarms.find((x) => x.id === e.features?.[0].properties.id)
    if (!a) return
    live.popup(e.lngLat, `<div class="popup"><h3>${esc(a.message)}</h3>
      <dl>${rows([['Tid', stamp(a.time)], ['Station', a.station], ['Beredskab', a.beredskab]])}</dl>
      <small>Kilde: www.odin.dk/112puls. Positionen er brandstationen, ikke hændelsen.</small></div>`)
  })

  live.feed<{ alarms: Alarm[] }>('alarms', POLL_MS, (data) => {
    alarms = data.alarms
    draw()
  })
  live.every(30_000, draw)
}
