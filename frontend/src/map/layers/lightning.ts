/** Lightning from DMI, fading over the hour. */
import { empty, Live, point } from '../live'
import type { Strike } from '../types'

const POLL_MS = 60_000

export function addLightning(live: Live): void {
  live.map.addSource('lightning', { type: 'geojson', data: empty() })
  live.add({
    id: 'lightning-dot',
    type: 'circle',
    source: 'lightning',
    paint: {
      'circle-color': '#ffe066',
      'circle-radius': ['case', ['==', ['get', 'type'], 0], 4, 2.5],
      'circle-opacity': ['interpolate', ['linear'], ['get', 'ageMin'], 0, 1, 60, 0.25],
      'circle-blur': 0.3,
    },
  })
  live.feed<{ strikes: Strike[] }>('lightning', POLL_MS, (data) => {
    const now = Date.now()
    live.setData('lightning', {
      type: 'FeatureCollection',
      features: data.strikes.map((s) => point(s.lon, s.lat, { type: s.type, ageMin: (now - s.time) / 60_000 })),
    })
  })
}
