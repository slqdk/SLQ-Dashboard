/** RainViewer's newest radar picture, under the map's labels. */
import type { Live } from '../live'
import type { RadarFrame } from '../types'

const POLL_MS = 5 * 60_000
const OPACITY = 0.55

export function addRadar(live: Live): void {
  const { map } = live
  let shown: string | null = null
  live.feed<{ host: string | null; frames: RadarFrame[] }>('radar', POLL_MS, (data) => {
    const frame = data.frames[data.frames.length - 1]
    if (!data.host || !frame) return
    const id = `radar-${frame.path.replace(/[^a-z0-9]/gi, '')}`
    if (id === shown) return
    map.addSource(id, {
      type: 'raster',
      tiles: [`${data.host}${frame.path}/256/{z}/{x}/{y}/2/1_1.png`],
      tileSize: 256,
      maxzoom: 7,
      attribution: 'Radar © RainViewer',
    })
    live.add({ id, type: 'raster', source: id, paint: { 'raster-opacity': OPACITY, 'raster-fade-duration': 0 } },
      map.getStyle().layers.find((l) => l.type === 'symbol')?.id)
    if (shown) {
      map.removeLayer(shown)
      map.removeSource(shown)
    }
    shown = id
  })
}
