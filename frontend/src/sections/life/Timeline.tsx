/** The log as a line through time: scroll sideways, zoom from a lifetime down to a week.
 *  There can be many thousands of entries, so only what is in view is drawn, and those
 *  without room for a card are counted in the bars along the axis. */
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { fullDate, localDate, whole } from '../../core/format'
import {
  bucketDays, CARD_GAP, CARD_HEIGHT, CARD_WIDTH, dayNumber, density, EDGE, isoOf, laneAbove, laneRow, lanesFor, monthYear, NEAREST, place,
  ticks, unitFor, yearStart, type Entry,
} from './layout'

const AXIS = 58                     // the band with dates and bars, across the middle
const AFTER = CARD_WIDTH + EDGE     // past today, so that the newest card has room
const BAR_ROOM = 26
const TOOLS = 44
const MOST_ZOOM = 320
const STEP = 1.35
const DRAG_START = 4

const SOURCE_NAME: Record<string, string> = {
  manual: 'Eget indlæg', google: 'Google Kalender', strava: 'Strava', 'familylog.dagbog': 'Dagbog', 'familylog.familymap': 'FamilyMap',
}

export const sourceName = (source: string): string => SOURCE_NAME[source] ?? source

export function Timeline({ entries, today, onOpen }: { entries: Entry[]; today: string; onOpen: (id: number) => void }) {
  const scroller = useRef<HTMLDivElement>(null)
  const [view, setView] = useState({ width: 0, height: 0, left: 0 })
  const [pxPerDay, setPxPerDay] = useState(0)
  const anchor = useRef<{ day: number; at: number } | null>(null)
  const started = useRef(false)

  const lastDay = dayNumber(today)
  const firstDay = entries.length ? yearStart(Number(entries[0].day.slice(0, 4))) : dayNumber(today) - 365
  const fitAll = (view.width - EDGE - AFTER) / (lastDay - firstDay + 1)
  const scale = pxPerDay || Math.max(view.width, 1) / 365
  const total = (lastDay - firstDay + 1) * scale + EDGE + AFTER
  const xOf = useCallback((day: number) => (day - firstDay) * scale + EDGE, [firstDay, scale])

  const lanes = lanesFor(view.height, AXIS)
  const placed = useMemo(() => place(entries, scale, firstDay, lastDay, lanes), [entries, scale, firstDay, lastDay, lanes])
  const unit = unitFor(scale)
  const bars = useMemo(() => density(entries, unit), [entries, unit])
  const tallest = useMemo(() => Math.sqrt(Math.max(1, ...bars.values())), [bars])

  useLayoutEffect(() => {
    const el = scroller.current
    if (!el) return undefined
    const measure = () => setView((v) => ({ ...v, width: el.clientWidth, height: el.clientHeight }))
    measure()
    const watcher = new ResizeObserver(measure)
    watcher.observe(el)
    return () => watcher.disconnect()
  }, [])

  // Keep the day under the pointer where it is while the scale changes.
  useLayoutEffect(() => {
    const el = scroller.current
    if (!el || !anchor.current) return
    el.scrollLeft = xOf(anchor.current.day) - anchor.current.at
    anchor.current = null
    setView((v) => ({ ...v, left: el.scrollLeft }))
  }, [scale, xOf])

  // The newest end of the log is where one starts.
  useLayoutEffect(() => {
    const el = scroller.current
    if (!el || started.current || !view.width) return
    started.current = true
    el.scrollLeft = el.scrollWidth
    setView((v) => ({ ...v, left: el.scrollLeft }))
  }, [view.width, total])

  // A search that starts the log later must not move what is in view.
  const shownFrom = useRef(firstDay)
  useLayoutEffect(() => {
    const el = scroller.current
    if (el) el.scrollLeft += (shownFrom.current - firstDay) * scale
    shownFrom.current = firstDay
  }, [firstDay, scale])

  const zoomTo = useCallback((next: number, at: number) => {
    const el = scroller.current
    if (!el) return
    anchor.current = { day: (el.scrollLeft + at - EDGE) / scale + firstDay, at }
    setPxPerDay(Math.min(MOST_ZOOM, Math.max(fitAll, next)))
  }, [scale, firstDay, fitAll])

  const goTo = useCallback((day: number, next = scale) => {
    anchor.current = { day, at: view.width / 2 }
    if (next !== scale) setPxPerDay(Math.min(MOST_ZOOM, Math.max(fitAll, next)))
    else if (scroller.current) {
      scroller.current.scrollLeft = xOf(day) - view.width / 2
      anchor.current = null
    }
  }, [scale, view.width, xOf, fitAll])

  // The wheel moves along the line, and with Ctrl it zooms. It has to be a listener of its
  // own: one set through React may not stop the page from zooming.
  useEffect(() => {
    const el = scroller.current
    if (!el) return undefined
    const wheel = (e: WheelEvent) => {
      e.preventDefault()
      if (e.ctrlKey) zoomTo(scale * Math.exp(-Math.max(-60, Math.min(60, e.deltaY)) / 200), e.clientX - el.getBoundingClientRect().left)
      else el.scrollLeft += Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY
    }
    el.addEventListener('wheel', wheel, { passive: false })
    return () => el.removeEventListener('wheel', wheel)
  }, [scale, zoomTo])

  // Dragging with the mouse. A drag that ends on a card is not a click on it.
  const drag = useRef<{ x: number; left: number; moved: boolean } | null>(null)
  const onPointerDown = (e: React.PointerEvent) => {
    if (e.pointerType === 'mouse' && e.button === 0) drag.current = { x: e.clientX, left: e.currentTarget.scrollLeft, moved: false }
  }
  const onPointerMove = (e: React.PointerEvent) => {
    const d = drag.current
    if (!d) return
    if (!e.buttons) {               // let go outside the timeline
      drag.current = null
      return
    }
    const dx = e.clientX - d.x
    if (!d.moved && Math.abs(dx) < DRAG_START) return
    d.moved = true
    e.currentTarget.scrollLeft = d.left - dx
  }
  const onClickCapture = (e: React.MouseEvent) => {
    if (drag.current?.moved) {
      e.preventDefault()
      e.stopPropagation()
    }
    drag.current = null
  }

  const onKeyDown = (e: React.KeyboardEvent) => {
    const el = e.currentTarget
    if (e.key === 'ArrowLeft') el.scrollLeft -= view.width / 3
    else if (e.key === 'ArrowRight') el.scrollLeft += view.width / 3
    else if (e.key === 'Home') el.scrollLeft = 0
    else if (e.key === 'End') el.scrollLeft = el.scrollWidth
    else if (e.key === '+') zoomTo(scale * STEP, view.width / 2)
    else if (e.key === '-') zoomTo(scale / STEP, view.width / 2)
    else return
    e.preventDefault()
  }

  const onScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const left = e.currentTarget.scrollLeft
    setView((v) => ({ ...v, left }))
  }

  const fromPx = view.left - CARD_WIDTH - 40
  const toPx = view.left + view.width + 40
  const fromDay = Math.floor((fromPx - EDGE) / scale) + firstDay
  const toDay = Math.ceil((toPx - EDGE) / scale) + firstDay
  const shown = placed.filter((p) => p.x >= fromPx && p.x <= toPx)
  const spans = shown.filter((p) => p.entry.end)
  const marks = ticks(Math.max(firstDay, fromDay), Math.min(lastDay, toDay), scale)
  const shownBars = [...bars].filter(([day]) => day + bucketDays(day, unit) >= fromDay && day <= toDay)
  const inView = Math.min(lastDay, Math.round((view.left + view.width / 2 - EDGE) / scale + firstDay))
  const axisTop = (view.height - AXIS) / 2
  const pitch = Math.max(CARD_HEIGHT + CARD_GAP, (axisTop - NEAREST) / (lanes / 2))
  const cardTop = (lane: number) => {
    const row = laneRow(lane) * pitch + NEAREST
    return laneAbove(lane) ? axisTop - row - CARD_HEIGHT : axisTop + AXIS + row
  }
  const preset = (days: number) => (view.width - EDGE * 2) / days

  return (
    <div className="tl">
      <div className="tl-tools" style={{ minHeight: TOOLS }}>
        <strong className="tl-where">{monthYear(inView)}</strong>
        <span className="meta">{whole(placed.length)} af {whole(entries.length)} vist</span>
        <div className="segmented" role="group" aria-label="Hvor meget tidslinjen viser">
          <button onClick={() => setPxPerDay(fitAll)}>Alt</button>
          <button onClick={() => goTo(inView, preset(365))}>År</button>
          <button onClick={() => goTo(inView, preset(31))}>Måned</button>
          <button onClick={() => goTo(inView, preset(7))}>Uge</button>
        </div>
        <button aria-label="Zoom ud" onClick={() => zoomTo(scale / STEP, view.width / 2)}>−</button>
        <button aria-label="Zoom ind" onClick={() => zoomTo(scale * STEP, view.width / 2)}>+</button>
        <button onClick={() => goTo(dayNumber(today))}>I dag</button>
        <input type="date" aria-label="Gå til dato" max={today} onChange={(e) => { if (e.target.value) goTo(dayNumber(e.target.value)) }} />
      </div>

      <div ref={scroller} className="tl-scroll" role="region" aria-label="Tidslinje. Pil til venstre og højre flytter, plus og minus zoomer." tabIndex={0}
        onScroll={onScroll} onKeyDown={onKeyDown} onPointerDown={onPointerDown} onPointerMove={onPointerMove} onClickCapture={onClickCapture}
        onPointerUp={() => { if (!drag.current?.moved) drag.current = null }} onPointerCancel={() => { drag.current = null }}>
        <div className="tl-track" style={{ width: total, height: view.height }}>
          {shown.map((p) => {
            const top = cardTop(p.lane)
            const stemTop = laneAbove(p.lane) ? top + CARD_HEIGHT : axisTop + AXIS
            const stemEnd = laneAbove(p.lane) ? axisTop : top
            return <span key={`s${p.entry.id}`} className="tl-stem" style={{ left: p.x, top: stemTop, height: stemEnd - stemTop }} />
          })}

          <div className="tl-axis" style={{ top: axisTop, height: AXIS }}>
            {marks.map((t) => (
              <span key={t.day} className={`tl-tick ${t.strength}`} style={{ left: xOf(t.day) }}>{t.label}</span>
            ))}
            {shownBars.map(([day, count]) => {
              const width = Math.max(2, bucketDays(day, unit) * scale - 1)
              const height = Math.max(3, (Math.sqrt(count) / tallest) * BAR_ROOM)
              return (
                <button key={day} className="tl-bar" style={{ left: xOf(day), width, height }} title={`${whole(count)} i ${monthYear(day)}`}
                  aria-label={`${whole(count)} indlæg fra ${isoOf(day)}. Zoom ind.`} onClick={() => goTo(day + bucketDays(day, unit) / 2, scale * 3)} />
              )
            })}
            {spans.map((p) => (
              <span key={`b${p.entry.id}`} className="tl-span" style={{ left: p.x, width: Math.max(4, (dayNumber(p.entry.end as string) - dayNumber(p.entry.day) + 1) * scale) }} />
            ))}
            <span className="tl-today" style={{ left: xOf(dayNumber(today)) }} />
          </div>

          {shown.map((p) => <Card key={p.entry.id} entry={p.entry} left={p.x} top={cardTop(p.lane)} onOpen={onOpen} />)}
        </div>
      </div>
    </div>
  )
}

function Card({ entry: e, left, top, onOpen }: { entry: Entry; left: number; top: number; onOpen: (id: number) => void }) {
  const family = e.source.startsWith('familylog') ? 'familylog' : e.source
  return (
    <button className={e.gone ? 'tl-card gone' : 'tl-card'} data-source={family} style={{ left, top, width: CARD_WIDTH, height: CARD_HEIGHT }} onClick={() => onOpen(e.id)}>
      {e.picture != null && <img src={`/api/s/logmylife/files/${e.picture}/thumb`} alt="" loading="lazy" draggable={false} />}
      <span className="tl-card-text">
        <time>{fullDate(localDate(e.day))}</time>
        <span className="tl-title">{e.title}</span>
        <span className="tl-meta">{e.owner ?? (e.files > 1 ? `${e.files} filer` : sourceName(e.source))}</span>
      </span>
    </button>
  )
}
