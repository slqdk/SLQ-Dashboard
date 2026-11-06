import { useMemo, useState } from 'react'
import { cap, clock, inkOn, kr, one, shortDay } from '../core/format'
import { useWidth } from '../core/useWidth'
import type { CalendarBlock, CalendarEvent, DkLive, F1Block, HourWeather, PricePoint } from '../core/types'

// Dagsbåndet: one time axis for everything on the day, like the channels of a
// scope. Elpris, vejr and the calendar line up under one cursor; hover (or the
// arrow keys) moves it, and each channel's value stands in the left margin.

const GUTTER = 104
const RIGHT = 12
const AXIS = 16
const LANES = 3
const LANE = 15
const ROWS = { calendar: 47, price: 30, temp: 26, rain: 14 }
const HOUR = 3_600_000

interface Block {
  start: number
  end: number
  title: string
  kind: 'event' | 'allday' | 'f1'
  lane: number
  color?: string
}

const ms = (iso: string) => new Date(iso).getTime()

function blocksFrom(events: CalendarEvent[], f1: F1Block | undefined, from: number, to: number): Block[] {
  const raw: Omit<Block, 'lane'>[] = []
  for (const e of events) {
    if (e.allDay) {
      const [y, m, d] = e.day.split('-').map(Number)
      const last = (e.end ?? e.day).split('-').map(Number)
      raw.push({ start: new Date(y, m - 1, d).getTime(), end: new Date(last[0], last[1] - 1, last[2] + 1).getTime(), title: e.title, kind: 'allday', color: e.color })
    } else {
      const start = ms(e.start)
      raw.push({ start, end: e.end ? ms(e.end) : start + HOUR, title: e.title, kind: 'event', color: e.color })
    }
  }
  for (const s of f1?.sessions ?? []) {
    raw.push({ start: ms(s.start), end: ms(s.end), title: s.name, kind: 'f1' })
  }
  const visible = raw.filter((b) => b.end > from && b.start < to).sort((a, b) => a.start - b.start)
  // What does not fit in the lanes stays off the band: the Kalender page has it all.
  const lanes: number[] = []
  const placed: Block[] = []
  for (const b of visible) {
    let lane = lanes.findIndex((end) => end <= b.start)
    if (lane < 0) lane = lanes.length
    if (lane >= LANES) continue
    lanes[lane] = b.end
    placed.push({ ...b, lane })
  }
  return placed
}

function nearest<T extends { t: string }>(list: T[], at: number, span: number): T | null {
  let best: T | null = null
  for (const item of list) {
    const t = ms(item.t)
    if (t <= at && at < t + span) best = item
  }
  return best
}

interface Props {
  now: Date
  dk?: DkLive
  calendar?: CalendarBlock
  f1?: F1Block
}

export function DayBand({ now, dk, calendar, f1 }: Props) {
  const { ref, width } = useWidth()
  const [cursor, setCursor] = useState<number | null>(null)

  const hours = width < 760 ? 24 : 36
  const from = new Date(now).setMinutes(0, 0, 0) - 3 * HOUR
  const to = from + hours * HOUR
  const plotW = Math.max(120, width - GUTTER - RIGHT)
  const x = (t: number) => GUTTER + ((t - from) / (to - from)) * plotW
  const time = (px: number) => from + ((px - GUTTER) / plotW) * (to - from)
  const nowT = now.getTime()
  const at = cursor ?? nowT

  const prices: PricePoint[] = dk?.power?.series ?? []
  const hourly: HourWeather[] = dk?.weather?.hourly ?? []
  const events = useMemo(() => calendar?.events ?? [], [calendar])
  const blocks = useMemo(() => blocksFrom(events, f1, from, to), [events, f1, from, to])

  const rowY = {
    calendar: AXIS,
    price: AXIS + ROWS.calendar,
    temp: AXIS + ROWS.calendar + ROWS.price,
    rain: AXIS + ROWS.calendar + ROWS.price + ROWS.temp,
  }
  const height = rowY.rain + ROWS.rain + 2

  // ---- the price: a step line, because a price holds for its whole slot ----
  const seen = prices.filter((p) => ms(p.t) + 15 * 60_000 > from && ms(p.t) < to)
  const priceMin = Math.min(0, ...seen.map((p) => p.dkk))
  const priceMax = Math.max(0.1, ...seen.map((p) => p.dkk))
  const py = (v: number) => rowY.price + ROWS.price - 4 - ((v - priceMin) / (priceMax - priceMin)) * (ROWS.price - 14)
  let pricePath = ''
  seen.forEach((p, i) => {
    const left = x(Math.max(ms(p.t), from))
    const right = x(Math.min(ms(p.t) + 15 * 60_000, to))
    pricePath += `${i === 0 ? 'M' : 'L'}${left.toFixed(1)} ${py(p.dkk).toFixed(1)}L${right.toFixed(1)} ${py(p.dkk).toFixed(1)}`
  })
  const priceArea = seen.length
    ? `${pricePath}L${x(Math.min(ms(seen[seen.length - 1].t) + 15 * 60_000, to)).toFixed(1)} ${py(priceMin)}L${x(Math.max(ms(seen[0].t), from)).toFixed(1)} ${py(priceMin)}Z`
    : ''
  const low = seen.length ? seen.reduce((a, b) => (b.dkk < a.dkk ? b : a)) : null
  const high = seen.length ? seen.reduce((a, b) => (b.dkk > a.dkk ? b : a)) : null

  // ---- the temperature ----
  const temps = hourly.filter((h) => h.temp != null && ms(h.t) >= from - HOUR && ms(h.t) <= to + HOUR)
  const tMin = Math.min(...temps.map((h) => h.temp as number))
  const tMax = Math.max(...temps.map((h) => h.temp as number))
  const tSpan = Math.max(4, tMax - tMin)
  const ty = (v: number) => rowY.temp + ROWS.temp - 5 - ((v - tMin) / tSpan) * (ROWS.temp - 10)
  const tempPath = temps.map((h, i) => `${i === 0 ? 'M' : 'L'}${x(ms(h.t)).toFixed(1)} ${ty(h.temp as number).toFixed(1)}`).join('')

  // ---- the rain ----
  const rain = hourly.filter((h) => (h.rain ?? 0) > 0 && ms(h.t) >= from && ms(h.t) < to)
  const rainMax = Math.max(1, ...rain.map((h) => h.rain as number))
  const barW = Math.max(3, Math.min(14, (plotW / hours) * 0.7))

  // ---- day and night, from the forecast's sunrise and sunset ----
  const nights: { a: number; b: number }[] = []
  const daily = dk?.weather?.daily ?? []
  for (let i = 0; i < daily.length; i++) {
    const set = daily[i]?.sunset
    const rise = daily[i + 1]?.sunrise
    if (set && rise) nights.push({ a: new Date(set).getTime(), b: new Date(rise).getTime() })
  }
  if (daily[0]?.sunrise) nights.unshift({ a: from, b: new Date(daily[0].sunrise).getTime() })

  // ---- the time axis ----
  const ticks: { t: number; midnight: boolean }[] = []
  const step = plotW / hours < 26 ? 6 : 3
  for (let t = from; t <= to; t += HOUR) {
    const d = new Date(t)
    if (d.getHours() === 0) ticks.push({ t, midnight: true })
    else if (d.getHours() % step === 0) ticks.push({ t, midnight: false })
  }

  // ---- the cursor's values, in the margin ----
  const price = nearest(prices, at, 15 * 60_000)
  const hour = nearest(hourly, at, HOUR)
  const onNow = blocks.filter((b) => b.start <= at && at < b.end && b.kind !== 'allday')
  const next = blocks.find((b) => b.start > at && b.kind !== 'allday')

  const move = (e: React.PointerEvent<SVGSVGElement>) => {
    const box = e.currentTarget.getBoundingClientRect()
    const px = e.clientX - box.left
    setCursor(px >= GUTTER && px <= GUTTER + plotW ? time(px) : null)
  }
  const keys = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
      e.preventDefault()
      const change = (e.key === 'ArrowRight' ? 1 : -1) * HOUR
      setCursor(Math.max(from, Math.min(to, at + change)))
    } else if (e.key === 'Escape') setCursor(null)
  }

  const fit = (text: string, px: number) => {
    const chars = Math.floor(px / 5.6)
    if (text.length <= chars) return text
    return chars < 8 ? '' : `${text.slice(0, chars - 1).trimEnd()}…`
  }

  const describe = `Dagsbånd fra ${clock(new Date(from))}. ${
    dk?.power ? `Elpris nu ${kr(dk.power.now)} kroner. ` : ''
  }${dk?.weather?.temp != null ? `${one(dk.weather.temp)} grader.` : ''}`

  return (
    <div className="band" ref={ref}>
      <svg width={width} height={height} role="img" aria-label={describe} tabIndex={0}
        onPointerMove={move} onPointerLeave={() => setCursor(null)} onKeyDown={keys}>
        {nights.map((n, i) => {
          const a = Math.max(x(n.a), GUTTER)
          const b = Math.min(x(n.b), GUTTER + plotW)
          return b > a ? <rect key={i} x={a} y={AXIS} width={b - a} height={height - AXIS - 2} className="band-night" /> : null
        })}

        {ticks.map((tick) => (
          <g key={tick.t}>
            <line x1={x(tick.t)} x2={x(tick.t)} y1={AXIS} y2={height - 2} className={tick.midnight ? 'band-grid strong' : 'band-grid'} />
            <text x={x(tick.t) + 3} y={12} className={tick.midnight ? 'band-tick strong' : 'band-tick'}>
              {tick.midnight ? cap(shortDay(new Date(tick.t))) : String(new Date(tick.t).getHours()).padStart(2, '0')}
            </text>
          </g>
        ))}

        {[rowY.calendar, rowY.price, rowY.temp, rowY.rain].map((y) => (
          <line key={y} x1={0} x2={GUTTER + plotW} y1={y} y2={y} className="band-rule" />
        ))}

        {/* The channels */}
        {blocks.map((b, i) => {
          const left = Math.max(x(b.start), GUTTER)
          const right = Math.min(x(b.end), GUTTER + plotW)
          const y = rowY.calendar + 2 + b.lane * LANE
          const inside = fit(b.title, right - left - 8)
          // Too short for its name: the name goes beside it when there is room.
          const after = blocks.slice(i + 1).find((o) => o.lane === b.lane)
          const room = (after ? Math.max(x(after.start), GUTTER) : GUTTER + plotW) - right - 8
          const beside = inside ? '' : fit(b.title, room)
          return (
            <g key={i}>
              <rect x={left} y={y} width={Math.max(3, right - left - 2)} height={13} rx={2} className={`band-block ${b.kind}`}
                style={b.color ? { fill: b.color, fillOpacity: b.kind === 'allday' ? 0.5 : 1 } : undefined} />
              {inside && <text x={left + 4} y={y + 10} className={`band-block-text ${b.kind}`}
                style={b.color && b.kind === 'event' ? { fill: inkOn(b.color) } : undefined}>{inside}</text>}
              {beside && <text x={right + 3} y={y + 10} className="band-block-text beside">{beside}</text>}
            </g>
          )
        })}

        {priceArea && <path d={priceArea} className="band-price-area" />}
        {pricePath && <path d={pricePath} className="band-price" />}
        {low && high && low !== high && (
          <>
            <text x={Math.min(x(ms(high.t)) + 4, GUTTER + plotW - 34)} y={py(high.dkk) - 2} className="band-note">{kr(high.dkk)}</text>
            <text x={Math.min(x(ms(low.t)) + 4, GUTTER + plotW - 34)} y={py(low.dkk) + 9} className="band-note">{kr(low.dkk)}</text>
          </>
        )}

        {tempPath && <path d={tempPath} className="band-temp" />}

        {rain.map((h) => {
          const barH = Math.max(2, ((h.rain as number) / rainMax) * (ROWS.rain - 2))
          return <path key={h.t} className="band-rain"
            d={`M${x(ms(h.t)) - barW / 2} ${rowY.rain + ROWS.rain}v${-barH + 2}q0 -2 2 -2h${barW - 4}q2 0 2 2v${barH - 2}z`} />
        })}

        {/* Now, and the cursor */}
        <line x1={x(nowT)} x2={x(nowT)} y1={AXIS} y2={height - 2} className="band-now" />
        <text x={x(nowT)} y={12} textAnchor="middle" className="band-now-label">nu</text>
        {cursor != null && (
          <>
            <line x1={x(cursor)} x2={x(cursor)} y1={AXIS} y2={height - 2} className="band-cursor" />
            <text x={Math.min(x(cursor) + 6, GUTTER + plotW - 80)} y={12} className="band-cursor-label">
              {cap(shortDay(new Date(cursor)))} {clock(new Date(cursor))}
            </text>
          </>
        )}

        {/* The left margin */}
        <rect x={0} y={AXIS} width={GUTTER - 1} height={height - AXIS - 2} className="band-margin" />
        <Margin y={rowY.calendar} h={ROWS.calendar} swatch="cal" name="Kalender"
          value={onNow.length ? 'Nu' : next ? clock(new Date(next.start)) : 'Intet'} />
        <Margin y={rowY.price} h={ROWS.price} swatch="price" name="Elpris" value={price ? kr(price.dkk) : '–'} />
        <Margin y={rowY.temp} h={ROWS.temp} swatch="temp" name="Temp." value={hour?.temp != null ? `${one(hour.temp)}°` : '–'} />
        <Margin y={rowY.rain} h={ROWS.rain} swatch="rain" name="Regn" value={hour?.rain != null ? `${one(hour.rain)} mm` : '–'} />
      </svg>
      {!dk?.power && !dk?.weather && (
        <p className="band-empty">Elpris og vejr kommer fra DK live, som ikke svarer endnu.</p>
      )}
    </div>
  )
}

function Margin({ y, h, swatch, name, value }: { y: number; h: number; swatch: string; name: string; value: string }) {
  return (
    <g>
      <rect x={0} y={y + h / 2 - 5} width={3} height={10} className={`band-swatch ${swatch}`} />
      <text x={9} y={y + h / 2 + 4} className="band-name">{name}</text>
      <text x={GUTTER - 7} y={y + h / 2 + 5} textAnchor="end" className="band-value">{value}</text>
    </g>
  )
}
