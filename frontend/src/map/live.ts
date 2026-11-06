/** What the map's layers share: the feeds, timers and popups of one map. All of it
 *  ends with the map, when the overview closes. */
import maplibregl from 'maplibre-gl'
import type { GeoJSONSource, LayerSpecification, LngLatLike, Map as MapLibre, MapLayerMouseEvent } from 'maplibre-gl'
import { esc, webAddress } from './text'
import type { Aircraft, Photo } from './types'

const FEED = '/api/s/dklive/map/'
const EDGE = 10         // how near the edge of the free part a popup may come

export const empty = (): GeoJSON.FeatureCollection => ({ type: 'FeatureCollection', features: [] })

export function point<P extends object>(lon: number, lat: number, properties: P): GeoJSON.Feature<GeoJSON.Point, P> {
  return { type: 'Feature', geometry: { type: 'Point', coordinates: [lon, lat] }, properties }
}

/** One popup at a time, always clear of the panels on top of the map. */
export class Bubble extends maplibregl.Popup {
  constructor(private live: Live, options: maplibregl.PopupOptions = {}) {
    super({ closeOnClick: true, maxWidth: '340px', ...options })
    this.on('close', () => { if (live.bubble === this) live.bubble = null })
  }

  addTo(map: MapLibre): this {
    if (this.live.bubble && this.live.bubble !== this) this.live.bubble.remove()
    this.live.bubble = this
    super.addTo(map)
    this.fit()
    return this
  }

  setHTML(html: string): this {
    super.setHTML(html)
    if (this.live.bubble === this) this.fit()
    return this
  }

  /** Nudge the map so the popup sits in the free part. Too big for it, its top counts. */
  fit(): void {
    requestAnimationFrame(() => {
      const el = this.getElement()
      if (!el || !this.isOpen()) return
      const r = el.getBoundingClientRect()
      const free = this.live.freeArea()
      const left = free.left + EDGE, right = free.right - EDGE, top = free.top + EDGE, bottom = free.bottom - EDGE
      let dx = 0, dy = 0
      if (r.left < left || r.width > right - left) dx = left - r.left
      else if (r.right > right) dx = right - r.right
      if (r.top < top || r.height > bottom - top) dy = top - r.top
      else if (r.bottom > bottom) dy = bottom - r.bottom
      if (Math.abs(dx) > 1 || Math.abs(dy) > 1) this.live.map.panBy([-dx, -dy], { duration: 250 })
    })
  }
}

export class Live {
  bubble: Bubble | null = null
  aircraft: Aircraft[] = []         // what the airports' popups ask about
  private clickable: string[] = []
  private timers: number[] = []
  private feeds = new Map<string, ((data: never) => void)[]>()

  constructor(readonly map: MapLibre, readonly freeArea: () => DOMRect) {}

  /** Poll a feed; a second reader of the same feed shares the first one's timer. */
  feed<T>(name: string, ms: number, onData: (data: T) => void): void {
    const known = this.feeds.get(name)
    if (known) {
      known.push(onData as (data: never) => void)
      return
    }
    const readers = [onData as (data: never) => void]
    this.feeds.set(name, readers)
    const tick = async () => {
      if (document.hidden && this.timers.length) return
      try {
        const response = await fetch(FEED + name, { cache: 'no-store' })
        if (!response.ok) return
        const data = await response.json()
        if (this.feeds.size) readers.forEach((read) => read(data as never))
      } catch {
        // the next turn tries again, and the status is in Admin
      }
    }
    void tick()
    this.every(ms, tick)
  }

  every(ms: number, fn: () => void): void {
    this.timers.push(window.setInterval(fn, ms))
  }

  add(layer: object, before?: string): void {
    this.map.addLayer(layer as LayerSpecification, before)
  }

  setData(source: string, data: GeoJSON.FeatureCollection): void {
    (this.map.getSource(source) as GeoJSONSource | undefined)?.setData(data)
  }

  /** A layer you can click, with the pointer that says so. */
  onClick(layer: string, handler: (e: MapLayerMouseEvent) => void): void {
    this.clickable.push(layer)
    this.map.on('click', layer, handler)
    this.map.on('mouseenter', layer, () => { this.map.getCanvas().style.cursor = 'pointer' })
    this.map.on('mouseleave', layer, () => { this.map.getCanvas().style.cursor = '' })
  }

  /** Whether a click hit something of ours rather than the map itself. */
  onFeature(where: maplibregl.PointLike): boolean {
    return this.map.queryRenderedFeatures(where, { layers: this.clickable.filter((id) => this.map.getLayer(id)) }).length > 0
  }

  popup(at: LngLatLike, html: string, options: maplibregl.PopupOptions = {}): Bubble {
    return new Bubble(this, { offset: 10, ...options }).setLngLat(at).setHTML(html).addTo(this.map)
  }

  /** Slot a photo in under a popup's title; no photo, nothing changes. */
  async photo(bubble: Bubble, url: string): Promise<void> {
    try {
      const p = await (await fetch(url)).json() as Photo
      const slot = bubble.getElement()?.querySelector('.photo')
      const thumb = webAddress(p.thumb)
      if (!slot || !thumb) return
      const credit = [p.credit && `© ${esc(p.credit)}`, esc(p.license), esc(p.source)].filter(Boolean).join(', ')
      slot.innerHTML = `<a href="${esc(webAddress(p.link) ?? thumb)}" target="_blank" rel="noopener noreferrer"><img src="${esc(thumb)}" alt="" loading="lazy" /></a>
        <div class="credit">${credit}${p.uncertain ? ', fundet på navnet, kan være et andet skib' : ''}</div>`
      slot.querySelector('img')?.addEventListener('load', () => bubble.fit(), { once: true })
    } catch {
      // a popup without a photo is fine
    }
  }

  dispose(): void {
    this.timers.forEach((t) => window.clearInterval(t))
    this.timers = []
    this.feeds.clear()
  }
}

/** Draw a shape into a canvas and give it to the map as an icon. */
export function shapeIcon(map: MapLibre, name: string, color: string, draw: (ctx: CanvasRenderingContext2D, size: number) => void, size = 32): void {
  if (map.hasImage(name)) return
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = size
  const ctx = canvas.getContext('2d') as CanvasRenderingContext2D
  ctx.translate(size / 2, size / 2)
  ctx.fillStyle = color
  ctx.strokeStyle = 'rgba(0,0,0,.6)'
  ctx.lineWidth = 1.5
  draw(ctx, size)
  ctx.fill()
  ctx.stroke()
  map.addImage(name, ctx.getImageData(0, 0, size, size), { pixelRatio: 1.25 })
}

/** A white shape MapLibre can colour per feature. */
export function sdfIcon(map: MapLibre, name: string, size: number, draw: (ctx: CanvasRenderingContext2D) => void): void {
  if (map.hasImage(name)) return
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = size
  const ctx = canvas.getContext('2d') as CanvasRenderingContext2D
  ctx.fillStyle = '#fff'
  ctx.beginPath()
  draw(ctx)
  ctx.closePath()
  ctx.fill()
  map.addImage(name, ctx.getImageData(0, 0, size, size), { sdf: true, pixelRatio: 2 })
}

/** The silhouette of an aircraft, nose up, `u` being a 32nd of the icon. */
export function plane(ctx: CanvasRenderingContext2D, u: number): void {
  const outline = [[2.2, -3], [13, 3], [13, 5.5], [2, 2.5], [1.4, 8.5], [5, 11], [5, 12.5]]
  ctx.beginPath()
  ctx.moveTo(0, -12 * u)
  for (const [x, y] of outline) ctx.lineTo(x * u, y * u)
  ctx.lineTo(0, 11 * u)
  for (const [x, y] of [...outline].reverse()) ctx.lineTo(-x * u, y * u)
  ctx.closePath()
}
