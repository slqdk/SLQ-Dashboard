/** The map of Denmark and northern Germany, behind everything on the overview. Panels lie on
 *  top of it, so Denmark, its buttons and its popups keep to the part they leave free. */
import { useEffect, useRef, type RefObject } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import './map.css'
import { addAirports } from './layers/airports'
import { addAlarms } from './layers/alarms'
import { addAutobahn } from './layers/autobahn'
import { addFlights } from './layers/flights'
import { addFlow } from './layers/flow'
import { addForecast } from './layers/forecast'
import { addInterconnect } from './layers/interconnect'
import { addLightning } from './layers/lightning'
import { addNavWarnings } from './layers/navwarnings'
import { addRadar } from './layers/radar'
import { addSeaLevel } from './layers/sealevel'
import { addShips } from './layers/ships'
import { addTraffic } from './layers/traffic'
import { addTrains } from './layers/trains'
import { addWebcams } from './layers/webcams'
import { addWind } from './layers/wind'
import { AREA, limitCenter } from './limit'
import { Live } from './live'
import { applyTheme } from './theme'

const STYLE = 'https://tiles.openfreemap.org/styles/dark'      // free, no key
const FIT_PADDING = 14
const MOST_PIXELS = 1.25    // the map fills the window, and a screen at 200 % would draw four times the pixels

// Order matters: what comes first lies underneath.
const LAYERS: [string, (live: Live) => void][] = [
  ['radar', addRadar],
  ['forecast', addForecast],
  ['flow', addFlow],
  ['lightning', addLightning],
  ['navwarnings', addNavWarnings],
  ['interconnect', addInterconnect],
  ['traffic', addTraffic],
  ['autobahn', addAutobahn],
  ['webcams', addWebcams],
  ['trains', addTrains],
  ['ships', addShips],
  ['sealevel', addSeaLevel],
  ['wind', addWind],
  ['alarms', addAlarms],
  ['airports', addAirports],
  ['flights', (live) => addFlights(live, false)],
  ['military', (live) => addFlights(live, true)],
]

/** A button back to the whole map after zooming. */
class HomeControl implements maplibregl.IControl {
  private box = document.createElement('div')

  constructor(private home: () => void) {}

  onAdd(): HTMLElement {
    this.box.className = 'maplibregl-ctrl maplibregl-ctrl-group'
    const button = document.createElement('button')
    button.type = 'button'
    button.className = 'map-home'
    button.title = 'Hele kortet'
    button.setAttribute('aria-label', 'Hele kortet')
    button.textContent = 'DK'
    button.addEventListener('click', this.home)
    this.box.append(button)
    return this.box
  }

  onRemove(): void {
    this.box.remove()
  }
}

export default function LiveMap({ layers, free }: { layers: string[]; free: RefObject<HTMLElement> }): JSX.Element | null {
  const box = useRef<HTMLDivElement>(null)
  const wanted = layers.join()

  useEffect(() => {
    const container = box.current as HTMLDivElement
    let map: maplibregl.Map
    try {
      map = new maplibregl.Map({
        container,
        style: STYLE,
        bounds: AREA,
        fitBoundsOptions: { padding: FIT_PADDING },
        minZoom: 4,
        maxZoom: 17,
        pixelRatio: Math.min(window.devicePixelRatio, MOST_PIXELS),
        fadeDuration: 0,            // no label cross-fades, fewer redraws
        refreshExpiredTiles: false,
        renderWorldCopies: false,
        dragRotate: false,
        pitchWithRotate: false,
        attributionControl: { compact: true },
      })
    } catch {
      return undefined              // no WebGL here: the panels work without a map
    }
    map.touchZoomRotate.disableRotation()
    Object.assign(window, { slqMap: map })       // for the browser check and the console

    // This one method decides where the map may be, for dragging, zooming and popups alike.
    const { transform } = map
    const allowed = transform.getConstrained.bind(transform)
    transform.getConstrained = (lngLat, zoom) => {
      const result = allowed(lngLat, zoom)
      const { left, right, top, bottom } = transform.padding
      const center = limitCenter(result.center, result.zoom, transform.width - left - right, transform.height - top - bottom)
      return { ...result, center: new maplibregl.LngLat(center.lng, center.lat) }
    }

    const freeArea = () => {
      const hole = free.current?.getBoundingClientRect()
      return hole && hole.width > 0 && hole.height > 0 ? hole : container.getBoundingClientRect()
    }
    const live = new Live(map, freeArea)
    let moved = false

    // The whole area in the free part is as far out as the map goes.
    const fit = () => {
      const camera = map.cameraForBounds(AREA, { padding: FIT_PADDING })
      if (camera?.zoom != null) map.setMinZoom(camera.zoom)
      if (camera && !moved) map.jumpTo(camera)
    }
    const home = () => {
      moved = false
      fit()
    }
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right')
    map.addControl(new HomeControl(home), 'bottom-right')
    const noteMove = (e: { originalEvent?: unknown }) => { if (e.originalEvent) moved = true }
    map.on('dragstart', noteMove)
    map.on('zoomstart', noteMove)

    const controls = container.querySelector<HTMLElement>('.maplibregl-control-container')
    const place = () => {
      const area = container.getBoundingClientRect()
      const hole = freeArea()
      const padding = { top: hole.top - area.top, right: area.right - hole.right, bottom: area.bottom - hole.bottom, left: hole.left - area.left }
      map.setPadding(padding)
      if (controls) Object.assign(controls.style, { top: `${padding.top}px`, right: `${padding.right}px`, bottom: `${padding.bottom}px`, left: `${padding.left}px` })
      map.resize()
      fit()
    }
    const watcher = new ResizeObserver(place)
    watcher.observe(container)
    if (free.current) watcher.observe(free.current)
    place()

    map.on('load', () => {
      applyTheme(map)
      const on = new Set(wanted.split(','))
      for (const [id, add] of LAYERS) if (on.has(id)) add(live)
    })

    return () => {
      watcher.disconnect()
      live.dispose()
      map.remove()
    }
  }, [wanted, free])

  return <div ref={box} className="map-background" aria-label="Kort over Danmark og Nordtyskland" />
}
