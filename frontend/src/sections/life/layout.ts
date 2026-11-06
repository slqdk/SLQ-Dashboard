/** Where things go on the timeline. No DOM in here, so it can be tested. Days are whole
 *  numbers counted in UTC, so summer time cannot move an entry to the wrong day. */

export interface Entry {
  id: number
  day: string
  end: string | null
  title: string
  source: string
  category: string
  picture: number | null
  files: number
  gone: number
  owner: string | null
}

const DAY_MS = 86_400_000

export const CARD_WIDTH = 196
export const CARD_HEIGHT = 74
export const CARD_GAP = 8
export const EDGE = 48              // room before the first day and after the last
export const NEAREST = 16           // from the axis to the first lane

const CELL = 24                     // the grid cards are fitted on, in pixels

export const dayNumber = (iso: string): number =>
  Math.floor(Date.UTC(Number(iso.slice(0, 4)), Number(iso.slice(5, 7)) - 1, Number(iso.slice(8, 10))) / DAY_MS)

export const isoOf = (day: number): string => new Date(day * DAY_MS).toISOString().slice(0, 10)

export const yearStart = (year: number): number => Math.floor(Date.UTC(year, 0, 1) / DAY_MS)

/** Lanes alternate, nearest the axis first: 0 above it, 1 below, 2 above and so on. */
export const laneAbove = (lane: number): boolean => lane % 2 === 0
export const laneRow = (lane: number): number => Math.floor(lane / 2)

export const lanesFor = (height: number, axis: number): number =>
  Math.max(2, Math.floor(((height - axis) / 2 - NEAREST) / (CARD_HEIGHT + CARD_GAP)) * 2)

export interface Placed {
  entry: Entry
  x: number
  lane: number
}

/** What is worth a card when not everything can have one. */
function rank(e: Entry): number {
  if (e.picture != null) return 0
  if (e.source === 'manual') return 1
  if (e.end) return 2
  return 3
}

/** A card for as many entries as there is room for, the ones that matter most first.
 *  The rest are counted in the bars along the axis until the timeline is zoomed in. */
export function place(entries: Entry[], pxPerDay: number, firstDay: number, lastDay: number, lanes: number): Placed[] {
  const span = Math.ceil((CARD_WIDTH + CARD_GAP) / CELL)
  const cells = Math.ceil(((lastDay - firstDay + 1) * pxPerDay + EDGE * 2) / CELL) + span + 1
  const grid = Array.from({ length: lanes }, () => new Uint8Array(cells))
  const ordered = entries.map((e) => ({ e, r: rank(e) })).sort((a, b) => a.r - b.r)
  const out: Placed[] = []
  for (const { e } of ordered) {
    const x = (dayNumber(e.day) - firstDay) * pxPerDay + EDGE
    const from = Math.floor(x / CELL)
    for (let lane = 0; lane < lanes; lane++) {
      const row = grid[lane]
      let free = true
      for (let c = from; c < from + span; c++) {
        if (row[c]) {
          free = false
          break
        }
      }
      if (free) {
        row.fill(1, from, from + span)
        out.push({ entry: e, x, lane })
        break
      }
    }
  }
  return out.sort((a, b) => a.x - b.x)
}

export type Unit = 'month' | 'week' | 'day'

export const unitFor = (pxPerDay: number): Unit => (pxPerDay < 1.6 ? 'month' : pxPerDay < 14 ? 'week' : 'day')

/** The first day of the month, week (Monday) or day a day falls in. */
export function bucketOf(day: number, unit: Unit): number {
  if (unit === 'day') return day
  if (unit === 'week') return day - ((day + 3) % 7)          // day 0 was a Thursday
  const d = new Date(day * DAY_MS)
  return Math.floor(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1) / DAY_MS)
}

export function bucketDays(start: number, unit: Unit): number {
  if (unit === 'day') return 1
  if (unit === 'week') return 7
  const d = new Date(start * DAY_MS)
  return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0)).getUTCDate()
}

export function density(entries: Entry[], unit: Unit): Map<number, number> {
  const out = new Map<number, number>()
  for (const e of entries) {
    const bucket = bucketOf(dayNumber(e.day), unit)
    out.set(bucket, (out.get(bucket) ?? 0) + 1)
  }
  return out
}

export interface Tick {
  day: number
  label: string
  strength: 'year' | 'month' | 'day'
}

const MONTHS = ['jan', 'feb', 'mar', 'apr', 'maj', 'jun', 'jul', 'aug', 'sep', 'okt', 'nov', 'dec']
const WEEKDAYS = ['søn', 'man', 'tir', 'ons', 'tor', 'fre', 'lør']

/** The marks on the axis between two days, as fine as the zoom has room for. */
export function ticks(from: number, to: number, pxPerDay: number): Tick[] {
  const out: Tick[] = []
  const showMonths = pxPerDay * 30 >= 26
  const monthNames = pxPerDay * 30 >= 40
  const showDays = pxPerDay >= 22
  const weekdays = pxPerDay >= 70
  const first = new Date(from * DAY_MS)
  for (let y = first.getUTCFullYear(), m = first.getUTCMonth(); ; m++) {
    const start = Math.floor(Date.UTC(y, m, 1) / DAY_MS)
    if (start > to) break
    const month = new Date(start * DAY_MS).getUTCMonth()
    const year = new Date(start * DAY_MS).getUTCFullYear()
    if (start >= from) {
      if (month === 0) out.push({ day: start, label: String(year), strength: 'year' })
      else if (showMonths) out.push({ day: start, label: monthNames ? MONTHS[month] : '', strength: 'month' })
    }
    if (showDays) {
      const length = bucketDays(start, 'month')
      for (let d = 1; d < length; d++) {
        const day = start + d
        const name = weekdays ? `${WEEKDAYS[new Date(day * DAY_MS).getUTCDay()]} ${d + 1}` : String(d + 1)
        if (day >= from && day <= to) out.push({ day, label: name, strength: 'day' })
      }
    }
  }
  return out
}

export const monthYear = (day: number): string => {
  const d = new Date(day * DAY_MS)
  return `${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`
}
