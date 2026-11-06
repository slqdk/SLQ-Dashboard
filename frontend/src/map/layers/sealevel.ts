/** DMI's tide gauges: water level in cm against DVR90, about the mean sea level. */
import { empty, Live, point } from '../live'
import { esc, hhmm, link, rows, signed } from '../text'
import type { Gauge } from '../types'

const POLL_MS = 5 * 60_000
const COLOR = ['step', ['get', 'level'], '#5aa9ff', -80, '#8b97a8', 100, '#ffd24a', 150, '#ff9f43', 200, '#ff5c4d']
const note = (level: number) => (level >= 200 ? 'stormflodsniveau' : level >= 150 ? 'høj vandstand' : level >= 100 ? 'forhøjet vandstand' : level <= -80 ? 'lavvande' : 'normal')

export function addSeaLevel(live: Live): void {
  const { map } = live
  let gauges: Gauge[] = []
  map.addSource('sealevel', { type: 'geojson', data: empty() })
  live.add({
    id: 'sealevel-dot',
    type: 'circle',
    source: 'sealevel',
    paint: { 'circle-color': COLOR, 'circle-radius': ['interpolate', ['linear'], ['zoom'], 5, 4, 9, 7], 'circle-stroke-color': '#0b1720', 'circle-stroke-width': 1.5 },
  })
  live.add({
    id: 'sealevel-label',
    type: 'symbol',
    source: 'sealevel',
    layout: {
      'text-field': ['step', ['zoom'], '', 6.5, ['get', 'label']],
      'text-font': ['Noto Sans Regular'],
      'text-size': 11,
      'text-offset': [0.9, 0],
      'text-anchor': 'left',
      'text-optional': true,
    },
    paint: { 'text-color': COLOR, 'text-halo-color': '#0b1720', 'text-halo-width': 1.2 },
  })

  live.onClick('sealevel-dot', (e) => {
    const g = gauges.find((x) => x.id === e.features?.[0].properties.id)
    if (!g) return
    live.popup(e.lngLat, `<div class="popup"><h3>${esc(g.name)}</h3>
      <dl>${rows([['Vandstand', `${signed(g.level)} cm (DVR90), ${note(g.level)}`], ['Målt', hhmm(g.time)]])}</dl>
      <small>Kilde: DMI. 0 cm er omtrent middelvandstand.</small>${link('https://www.dmi.dk/vandstand', 'DMI vandstand')}</div>`)
  })

  live.feed<{ stations: Gauge[] }>('sealevel', POLL_MS, (data) => {
    gauges = data.stations
    live.setData('sealevel', {
      type: 'FeatureCollection',
      features: gauges.map((g) => point(g.lon, g.lat, { id: g.id, level: g.level, label: `${signed(g.level)} cm` })),
    })
  })
}
