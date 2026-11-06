/** The power cables abroad, with live MW. Energinet's sign: positive is into Denmark, and
 *  on Storebælt into DK1. The lines are schematic: a stub out to sea, never across land. */
import { empty, Live, point, sdfIcon } from '../live'
import { esc, rows } from '../text'

const POLL_MS = 120_000
type Spot = [number, number]
interface Cable { name: string; a: Spot; b: Spot; abroad: string }

const GREAT_BELT: Cable = { name: 'Storebælt (DK1 og DK2)', a: [10.8, 55.29], b: [11.12, 55.33], abroad: 'DK2' }
const CABLES: Record<string, Cable> = {
  dk1de: { name: 'Jylland og Tyskland', a: [9.3, 54.86], b: [9.42, 54.62], abroad: 'Tyskland' },
  dk1nl: { name: 'COBRAcable til Holland', a: [8.08, 55.45], b: [7.6, 54.95], abroad: 'Holland' },
  dk1gb: { name: 'Viking Link til Storbritannien', a: [8.06, 55.62], b: [7.55, 55.85], abroad: 'Storbritannien' },
  dk1no: { name: 'Skagerrak til Norge', a: [8.6, 57.14], b: [8.25, 57.75], abroad: 'Norge' },
  dk1se: { name: 'Konti-Skan til Sverige', a: [10.56, 57.34], b: [11.45, 57.5], abroad: 'Sverige' },
  dk1dk2: GREAT_BELT,
  greatbelt: GREAT_BELT,
  dk2de: { name: 'Kontek og Kriegers Flak til Tyskland', a: [11.95, 54.56], b: [12.12, 54.28], abroad: 'Tyskland' },
  dk2se: { name: 'Øresund til Sverige', a: [12.6, 56.02], b: [12.76, 56.06], abroad: 'Sverige' },
}
const COLOR = ['case', ['get', 'into'], '#d4a017', '#a88414']

export const cableKey = (field: string): string => field.replace(/^Exchange_/i, '').replace(/[^a-z0-9]/gi, '').toLowerCase()

function bearing([lon1, lat1]: Spot, [lon2, lat2]: Spot): number {
  const r = Math.PI / 180
  const y = Math.sin((lon2 - lon1) * r) * Math.cos(lat2 * r)
  const x = Math.cos(lat1 * r) * Math.sin(lat2 * r) - Math.sin(lat1 * r) * Math.cos(lat2 * r) * Math.cos((lon2 - lon1) * r)
  return (Math.atan2(y, x) / r + 360) % 360
}

const megawatt = (v: number) => `${Math.round(Math.abs(v)).toLocaleString('da-DK')} MW`

export function addInterconnect(live: Live): void {
  const { map } = live
  const flows = new Map<string, { cable: Cable; mw: number }>()
  sdfIcon(map, 'ic-arrow', 28, (ctx) => {
    ctx.moveTo(14, 3)
    ctx.lineTo(24, 22)
    ctx.lineTo(14, 17)
    ctx.lineTo(4, 22)
  })
  map.addSource('ic-lines', { type: 'geojson', data: empty() })
  map.addSource('ic-mid', { type: 'geojson', data: empty() })
  live.add({
    id: 'ic-line',
    type: 'line',
    source: 'ic-lines',
    layout: { 'line-cap': 'round' },
    paint: { 'line-color': COLOR, 'line-width': ['get', 'width'], 'line-opacity': 0.9, 'line-dasharray': [1, 1] },
  })
  live.add({
    id: 'ic-arrow',
    type: 'symbol',
    source: 'ic-mid',
    layout: {
      'icon-image': 'ic-arrow',
      'icon-rotate': ['get', 'turn'],
      'icon-rotation-alignment': 'map',
      'icon-allow-overlap': true,
      'text-field': ['get', 'label'],
      'text-font': ['Noto Sans Regular'],
      'text-size': 11,
      'text-offset': [0, 1.3],
      'text-anchor': 'top',
      'text-allow-overlap': true,
    },
    paint: { 'icon-color': COLOR, 'text-color': COLOR, 'text-halo-color': '#0b1720', 'text-halo-width': 1.2 },
  })

  live.onClick('ic-arrow', (e) => {
    const flow = flows.get(e.features?.[0].properties.name)
    if (!flow) return
    const { cable, mw } = flow
    const way = Math.abs(mw) < 1 ? 'intet flow' : cable.abroad === 'DK2' ? (mw > 0 ? 'DK2 til DK1' : 'DK1 til DK2') : mw > 0 ? `import fra ${cable.abroad}` : `eksport til ${cable.abroad}`
    live.popup(e.lngLat, `<div class="popup"><h3>${esc(cable.name)}</h3><dl>${rows([['Flow', `${megawatt(mw)}, ${way}`]])}</dl>
      <small>Kilde: Energi Data Service (Energinet). Linjen er skematisk.</small></div>`)
  })

  live.feed<{ now: { exchanges: Record<string, number> } | null }>('energy', POLL_MS, (data) => {
    const lines: GeoJSON.Feature[] = []
    const middles: GeoJSON.Feature[] = []
    flows.clear()
    for (const [field, mw] of Object.entries(data.now?.exchanges ?? {})) {
      const cable = CABLES[cableKey(field)]
      if (!cable || flows.has(cable.name)) continue
      flows.set(cable.name, { cable, mw })
      const into = mw > 0
      const properties = { name: cable.name, into, width: 1.5 + Math.min(Math.abs(mw), 2000) / 350 }
      lines.push({ type: 'Feature', geometry: { type: 'LineString', coordinates: [cable.a, cable.b] }, properties })
      middles.push(point((cable.a[0] + cable.b[0]) / 2, (cable.a[1] + cable.b[1]) / 2, {
        ...properties, turn: into ? bearing(cable.b, cable.a) : bearing(cable.a, cable.b), label: Math.abs(mw) < 1 ? '0 MW' : megawatt(mw),
      }))
    }
    live.setData('ic-lines', { type: 'FeatureCollection', features: lines })
    live.setData('ic-mid', { type: 'FeatureCollection', features: middles })
  })
}
