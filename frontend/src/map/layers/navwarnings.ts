/** Navigational warnings and firing exercises from Nautisk Information. */
import { empty, Live } from '../live'
import { esc, link, rows, stamp } from '../text'
import type { NavWarning } from '../types'

const POLL_MS = 10 * 60_000
const COLOR = ['match', ['get', 'kind'], 'fe', '#ff5c7a', '#ff9f43']
const DETAIL_LENGTH = 280

export function addNavWarnings(live: Live): void {
  const { map } = live
  const byId = new Map<string, NavWarning>()
  map.addSource('navwarn', { type: 'geojson', data: empty() })
  const types = (...list: string[]) => ['in', ['geometry-type'], ['literal', list]]
  live.add({ id: 'navwarn-fill', type: 'fill', source: 'navwarn', filter: types('Polygon', 'MultiPolygon'), paint: { 'fill-color': COLOR, 'fill-opacity': 0.12 } })
  live.add({ id: 'navwarn-line', type: 'line', source: 'navwarn', filter: types('LineString', 'MultiLineString', 'Polygon', 'MultiPolygon'), paint: { 'line-color': COLOR, 'line-width': 1.5, 'line-opacity': 0.85 } })
  live.add({
    id: 'navwarn-dot',
    type: 'circle',
    source: 'navwarn',
    filter: types('Point', 'MultiPoint'),
    paint: { 'circle-color': COLOR, 'circle-radius': ['interpolate', ['linear'], ['zoom'], 5, 3.5, 10, 6], 'circle-stroke-color': '#0b1720', 'circle-stroke-width': 1.2 },
  })

  for (const layer of ['navwarn-fill', 'navwarn-line', 'navwarn-dot']) {
    live.onClick(layer, (e) => {
      // Several warnings can overlap: the first in full, the others by title.
      const ids = [...new Set((e.features ?? []).map((f) => String(f.properties.id)))]
      const w = byId.get(ids[0])
      if (!w) return
      const others = ids.slice(1, 4).map((id) => byId.get(id)?.title).filter(Boolean)
      const period = [w.from ? stamp(w.from) : null, w.to ? stamp(w.to) : null].filter(Boolean).join(' til ')
      live.popup(e.lngLat, `<div class="popup"><h3>${esc(w.title)}</h3>
        <dl>${rows([['Type', `${w.kind === 'fe' ? 'Skydeøvelse' : 'Navigationsadvarsel'}${w.shortId ? `, ${w.shortId}` : ''}`], ['Område', w.area], ['Gælder', period]])}</dl>
        ${w.details ? `<p class="text">${esc(w.details.length > DETAIL_LENGTH ? `${w.details.slice(0, DETAIL_LENGTH)}…` : w.details)}</p>` : ''}
        ${others.length ? `<p class="muted">Også her: ${esc(others.join(', '))}</p>` : ''}
        ${link('https://nautiskinformation.soefartsstyrelsen.dk/#/messages/map', 'Nautisk Information')}</div>`)
    })
  }

  live.feed<{ warnings: NavWarning[] }>('navwarnings', POLL_MS, (data) => {
    byId.clear()
    for (const w of data.warnings) byId.set(String(w.id), w)
    live.setData('navwarn', {
      type: 'FeatureCollection',
      features: data.warnings.flatMap((w) => w.geometries.map((geometry) => ({ type: 'Feature' as const, geometry, properties: { id: String(w.id), kind: w.kind } }))),
    })
  })
}
