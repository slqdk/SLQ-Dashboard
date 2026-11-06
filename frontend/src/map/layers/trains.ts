/** Trains from Rejseplanen, S-trains in their own colour. */
import { empty, Live, point, shapeIcon } from '../live'
import { esc, rows } from '../text'
import type { Train } from '../types'
import { labelPaint } from '../theme'

const POLL_MS = 60_000

export function addTrains(live: Live): void {
  const { map } = live
  let trains: Train[] = []
  const carriage = (ctx: CanvasRenderingContext2D, size: number) => {
    const u = size / 32
    ctx.beginPath()
    ctx.roundRect(-7 * u, -5 * u, 14 * u, 10 * u, 2 * u)
  }
  shapeIcon(map, 'train', '#7fb3ff', carriage, 24)
  shapeIcon(map, 'train-s', '#ff6b6b', carriage, 24)
  map.addSource('trains', { type: 'geojson', data: empty() })
  live.add({
    id: 'trains-icon',
    type: 'symbol',
    source: 'trains',
    layout: {
      'icon-image': ['case', ['==', ['get', 'category'], 'S'], 'train-s', 'train'],
      'icon-size': ['interpolate', ['linear'], ['zoom'], 5, 0.7, 9, 1, 12, 1.3],
      'icon-allow-overlap': true,
      'icon-ignore-placement': true,
      'text-field': ['step', ['zoom'], '', 7, ['get', 'name'], 9, ['get', 'label2']],
      'text-font': ['Noto Sans Regular'],
      'text-size': 11,
      'text-offset': [0, 1.1],
      'text-anchor': 'top',
      'text-line-height': 1.15,
      'text-optional': true,
    },
    paint: { ...labelPaint('#a9c9ff', 1.2) },
  })

  live.onClick('trains-icon', (e) => {
    const t = trains.find((x) => x.id === e.features?.[0].properties.id)
    if (!t) return
    live.popup(e.lngLat, `<div class="popup"><h3>${esc(t.name)}</h3>
      <dl>${rows([['Retning', t.direction ?? '–'], ['Type', t.category ?? '–'], ['Operatør', t.operator ?? '–'],
        ['Forsinkelse', t.delay ? `${t.delay} min` : 'til tiden eller ukendt']])}</dl></div>`)
  })

  live.feed<{ vehicles: Train[] }>('trains', POLL_MS, (data) => {
    trains = data.vehicles
    live.setData('trains', {
      type: 'FeatureCollection',
      features: trains.map((t) => point(t.lon, t.lat, {
        id: t.id, name: t.name, category: t.category, label2: `${t.name}\nmod ${t.direction ?? ''}${t.delay ? `, ${t.delay} min forsinket` : ''}`,
      })),
    })
  })
}
