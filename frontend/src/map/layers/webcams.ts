/** Webcams from three sources. A picture loads when the popup opens: Windy's addresses
 *  expire, so the server fetches a fresh one. */
import { empty, Live, point, shapeIcon } from '../live'
import { esc, link, webAddress } from '../text'
import type { Webcam } from '../types'
import { labelPaint } from '../theme'

const POLL_MS = 15 * 60_000
const COLOR: Record<Webcam['source'], string> = { autobahn: '#b58cff', windy: '#e0a3ff', egen: '#ffd24a' }
const CREDIT: Record<Webcam['source'], string> = { autobahn: 'Autobahn GmbH', windy: 'webcams by Windy', egen: 'egen kilde' }

async function open(live: Live, c: Webcam): Promise<void> {
  const place = [c.city, c.country].filter(Boolean).join(', ')
  const shell = (body: string) => `<div class="popup"><h3>${esc(c.name)}</h3>${place ? `<p class="muted">${esc(place)}</p>` : ''}${body}
    ${c.note ? `<p class="muted">${esc(c.note)}</p>` : ''}
    <div class="links"><span class="muted">${CREDIT[c.source]}</span>${c.link ? link(c.link, 'Åbn') : ''}</div></div>`
  const bubble = live.popup([c.lon, c.lat], shell(c.source === 'windy' ? '<p class="muted">Henter billede.</p>' : ''), { maxWidth: '380px' })
  let image = webAddress(c.image)
  let moving: string | null = null
  if (c.source === 'autobahn' && image) image = `${image}${image.includes('?') ? '&' : '?'}t=${Date.now()}`
  if (c.source === 'windy') {
    try {
      const r = await (await fetch(`/api/s/dklive/map/windy/${c.windyId}`)).json()
      image = webAddress(r.image)
      moving = r.live ?? r.day ?? null
    } catch {
      image = null
    }
  }
  const picture = image ? `<img src="${esc(image)}" alt="${esc(c.name)}" class="cam" loading="lazy" />` : '<p class="muted">Intet stillbillede. Åbn kameraet via linket.</p>'
  bubble.setHTML(shell(`${picture}${moving ? link(moving, 'Se live eller dagens time-lapse') : ''}`))
  bubble.getElement()?.querySelector('img.cam')?.addEventListener('load', () => bubble.fit(), { once: true })
}

export function addWebcams(live: Live): void {
  const { map } = live
  let items: Webcam[] = []
  const camera = (ctx: CanvasRenderingContext2D, size: number) => {
    const u = size / 32
    ctx.beginPath()
    ctx.roundRect(-8 * u, -5 * u, 11 * u, 10 * u, 1.5 * u)
    ctx.moveTo(4 * u, -1 * u)
    ctx.lineTo(9 * u, -5 * u)
    ctx.lineTo(9 * u, 5 * u)
    ctx.lineTo(4 * u, 1 * u)
    ctx.closePath()
  }
  for (const [name, color] of Object.entries(COLOR)) shapeIcon(map, `webcam-${name}`, color, camera, 22)
  map.addSource('webcams', { type: 'geojson', data: empty() })
  live.add({
    id: 'webcams-icon',
    type: 'symbol',
    source: 'webcams',
    layout: {
      'icon-image': ['concat', 'webcam-', ['get', 'source']],
      'icon-size': ['interpolate', ['linear'], ['zoom'], 5, 0.6, 9, 0.9, 12, 1.2],
      'icon-allow-overlap': true,
      'text-field': ['step', ['zoom'], '', 9, ['get', 'label']],
      'text-font': ['Noto Sans Regular'],
      'text-size': 11,
      'text-offset': [0, 1.1],
      'text-anchor': 'top',
      'text-optional': true,
      'symbol-sort-key': ['match', ['get', 'source'], 'egen', 0, 'windy', 1, 2],
    },
    paint: { ...labelPaint(['get', 'color'], 1.2) },
  })
  live.add({ id: 'webcams-hit', type: 'circle', source: 'webcams', paint: { 'circle-radius': 16, 'circle-opacity': 0, 'circle-stroke-opacity': 0 } })

  live.onClick('webcams-hit', (e) => {
    const c = items.find((x) => x.id === e.features?.[0].properties.id)
    if (c) void open(live, c)
  })

  live.feed<{ items: Webcam[] }>('webcams', POLL_MS, (data) => {
    items = data.items
    live.setData('webcams', {
      type: 'FeatureCollection',
      features: items.map((c) => point(c.lon, c.lat, {
        id: c.id, source: c.source, color: COLOR[c.source], label: c.source === 'autobahn' ? `${c.road} ${c.subtitle ?? ''}`.trim() : c.name,
      })),
    })
  })
}
