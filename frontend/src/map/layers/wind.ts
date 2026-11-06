/** DMI's weather stations: an arrow the way the wind blows, coloured by mean speed. */
import { empty, Live, point, sdfIcon } from '../live'
import { compass, esc, hhmm, number, rows } from '../text'
import type { WindStation } from '../types'

const POLL_MS = 5 * 60_000
const CLASSES: [number, string][] = [[5.5, 'let til jævn vind'], [10.8, 'frisk vind'], [13.9, 'hård vind'], [17.2, 'kuling'], [20.8, 'hård kuling'],
  [24.5, 'stormende kuling'], [32.7, 'storm'], [Infinity, 'orkan']]
const COLOR = ['step', ['get', 'speed'], '#8fb8de', 5.5, '#6fe3a0', 10.8, '#ffd24a', 13.9, '#ff9f43', 17.2, '#ff5c4d', 24.5, '#e056fd']

export function addWind(live: Live): void {
  const { map } = live
  let stations: WindStation[] = []
  sdfIcon(map, 'wind-arrow', 32, (ctx) => {
    ctx.moveTo(16, 2)
    ctx.lineTo(25, 15)
    ctx.lineTo(19, 14)
    ctx.lineTo(19, 30)
    ctx.lineTo(13, 30)
    ctx.lineTo(13, 14)
    ctx.lineTo(7, 15)
  })
  map.addSource('wind', { type: 'geojson', data: empty() })
  live.add({
    id: 'wind-arrow',
    type: 'symbol',
    source: 'wind',
    layout: {
      'icon-image': 'wind-arrow',
      'icon-rotate': ['get', 'turn'],
      'icon-rotation-alignment': 'map',
      'icon-allow-overlap': true,
      'icon-size': ['interpolate', ['linear'], ['zoom'], 5, 0.7, 9, 1.1],
      'text-field': ['step', ['zoom'], '', 7, ['get', 'label']],
      'text-font': ['Noto Sans Regular'],
      'text-size': 11,
      'text-offset': [0, 1.2],
      'text-anchor': 'top',
      'text-optional': true,
    },
    paint: { 'icon-color': COLOR, 'icon-halo-color': 'rgba(0,0,0,.6)', 'icon-halo-width': 1, 'text-color': COLOR, 'text-halo-color': '#0b1720', 'text-halo-width': 1.2 },
  })

  live.onClick('wind-arrow', (e) => {
    const s = stations.find((x) => x.id === e.features?.[0].properties.id)
    if (!s) return
    const name = (CLASSES.find(([most]) => s.speed < most) as [number, string])[1]
    live.popup(e.lngLat, `<div class="popup"><h3>${esc(s.name)}</h3>
      <dl>${rows([['Vind', `${number(s.speed, 1)} m/s${s.dir != null ? ` fra ${compass(s.dir)} (${Math.round(s.dir)}°)` : ''}, ${name}`],
        ['Vindstød', s.gust != null ? `${number(s.gust, 1)} m/s` : null], ['Temperatur', s.temp != null ? `${number(s.temp, 1)} °C` : null], ['Målt', hhmm(s.time)]])}</dl>
      <small>Kilde: DMI. Middelvind over 10 minutter, stød er det kraftigste i de 10 minutter.</small></div>`)
  })

  live.feed<{ stations: WindStation[] }>('wind', POLL_MS, (data) => {
    stations = data.stations
    live.setData('wind', {
      type: 'FeatureCollection',
      features: stations.map((s) => point(s.lon, s.lat, {
        id: s.id, speed: s.speed, turn: s.dir == null ? 0 : (s.dir + 180) % 360, label: `${number(s.speed)}${s.gust != null ? ` (${number(s.gust)})` : ''}`,
      })),
    })
  })
}
