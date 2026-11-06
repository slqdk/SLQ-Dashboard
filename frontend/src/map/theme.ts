/** OpenFreeMap's dark style in the dashboard's colours, quiet enough for panels on top.
 *  Layer ids come from the style, so they are matched by pattern. */
import type { Map as MapLibre } from 'maplibre-gl'

const LAND = '#1f323d'
const WATER = '#0b1720'
const GREEN = '#21383a'
const TOWN = '#293f4c'
const BORDER = '#6c8796'
const MOTORWAY = '#4d6a7a'
const MAIN_ROAD = '#3c5564'
const ROAD = '#32495a'
const RAIL = '#3f5766'
const LABEL = '#c6d3da'
const HALO = '#0b1720'

export function applyTheme(map: MapLibre): void {
  const set = (id: string, property: string, value: string | number) => {
    try {
      map.setPaintProperty(id, property, value)
    } catch {
      // a layer that does not have this property keeps its own
    }
  }
  for (const layer of map.getStyle().layers) {
    const id = layer.id.toLowerCase()
    if (layer.type === 'background') set(layer.id, 'background-color', LAND)
    if (layer.type === 'fill' && id.includes('water')) set(layer.id, 'fill-color', WATER)
    if (layer.type === 'fill' && /park|wood|grass|forest/.test(id)) set(layer.id, 'fill-color', GREEN)
    if (layer.type === 'fill' && /residential|urban|building/.test(id)) set(layer.id, 'fill-color', TOWN)
    if (layer.type === 'line' && id.includes('boundary')) {
      set(layer.id, 'line-color', BORDER)
      set(layer.id, 'line-opacity', 0.9)
    }
    if (layer.type === 'line' && !id.includes('casing')) {
      if (/motorway|trunk/.test(id)) set(layer.id, 'line-color', MOTORWAY)
      else if (/primary|secondary/.test(id)) set(layer.id, 'line-color', MAIN_ROAD)
      else if (/highway|road|minor/.test(id)) set(layer.id, 'line-color', ROAD)
      if (id.includes('rail')) set(layer.id, 'line-color', RAIL)
    }
    if (layer.type === 'symbol') {
      set(layer.id, 'text-color', LABEL)
      set(layer.id, 'text-halo-color', HALO)
    }
  }
}
