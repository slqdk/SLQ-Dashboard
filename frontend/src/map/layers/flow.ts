/** TomTom's traffic flow on motorways and trunk roads, coloured by speed against free flow.
 *  The tiles pass through the server, which holds the key. */
import type { Live } from '../live'

export function addFlow(live: Live): void {
  const { map } = live
  // Above the roads, below the labels that follow them.
  const layers = map.getStyle().layers
  const before = layers[layers.map((l) => l.type).lastIndexOf('line') + 1]?.id
  map.addSource('flow', {
    type: 'vector',
    tiles: [`${window.location.origin}/api/s/dklive/map/flow/{z}/{x}/{y}.pbf`],
    minzoom: 5,
    maxzoom: 14,
    attribution: 'Traffic © TomTom',
  })
  const width = (motorway: number, trunk: number) => ['case', ['==', ['get', 'road_category'], 'motorway'], motorway, trunk]
  live.add({
    id: 'flow',
    type: 'line',
    source: 'flow',
    'source-layer': 'Traffic flow',
    filter: ['any', ['!', ['has', 'road_category']], ['in', ['get', 'road_category'], ['literal', ['motorway', 'trunk']]]],
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: {
      'line-color': ['step', ['coalesce', ['get', 'traffic_level'], 1], '#c0392b', 0.35, '#ff5c4d', 0.6, '#ffb300', 0.85, '#4ade80'],
      'line-width': ['interpolate', ['exponential', 1.4], ['zoom'], 5, width(3, 2), 8, width(5, 3.5), 11, width(9, 6), 14, width(14, 9)],
    },
  }, before)
}
