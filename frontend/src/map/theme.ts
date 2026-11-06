/** OpenFreeMap's dark style in the colours of the theme, quiet enough for panels on top.
 *  Every colour in the style is set, since a light map would show any that was left. */
import type { Map as MapLibre } from 'maplibre-gl'

const read = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(`--map-${name}`).trim()

let ink = ''
let halo = '#0b1720'

/** A live layer's label: in its own colour on a dark map, in plain ink on a light one,
 *  where the layer's light colours would not read. */
export const labelPaint = <T,>(color: T, width = 1.2) => ({
  'text-color': ink || color,
  'text-halo-color': halo,
  'text-halo-width': width,
})

export function applyTheme(map: MapLibre): void {
  const land = read('land'), water = read('water'), green = read('green'), town = read('town'), road = read('road')
  ink = read('ink')
  halo = read('halo')
  const set = (id: string, property: string, value: string | number) => {
    try {
      map.setPaintProperty(id, property, value)
    } catch {
      // a layer that does not have this property keeps its own
    }
  }
  for (const layer of map.getStyle().layers) {
    const id = layer.id.toLowerCase()
    if (layer.type === 'background') set(layer.id, 'background-color', land)
    if (layer.type === 'fill') {
      const color = id.includes('water') ? water
        : /park|wood|grass|forest/.test(id) ? green
          : /residential|urban|building/.test(id) ? town
            : id.includes('aeroway') ? road : land
      set(layer.id, 'fill-color', color)
      if (id === 'building') set(layer.id, 'fill-outline-color', color)
    }
    if (layer.type === 'line') {
      if (id.includes('boundary')) {
        set(layer.id, 'line-color', read('border'))
        set(layer.id, 'line-opacity', 0.9)
      } else if (id.includes('casing')) set(layer.id, 'line-color', read('casing'))
      else if (id.includes('dashline')) set(layer.id, 'line-color', land)
      else if (id.includes('waterway')) set(layer.id, 'line-color', water)
      else if (id.includes('rail')) set(layer.id, 'line-color', read('rail'))
      else if (id.includes('pier')) set(layer.id, 'line-color', land)
      else if (/motorway|trunk/.test(id)) set(layer.id, 'line-color', read('motorway'))
      else if (/primary|secondary|major/.test(id)) set(layer.id, 'line-color', read('main'))
      else set(layer.id, 'line-color', road)
    }
    if (layer.type === 'symbol') {
      set(layer.id, 'text-color', read('label'))
      set(layer.id, 'text-halo-color', halo)
    }
  }
}
