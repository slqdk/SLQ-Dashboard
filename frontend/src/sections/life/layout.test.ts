import { describe, expect, it } from 'vitest'
import {
  bucketDays, bucketOf, CARD_GAP, CARD_WIDTH, dayNumber, density, EDGE, isoOf, laneAbove, laneRow, lanesFor, place, ticks, unitFor, yearStart, type Entry,
} from './layout'

const entry = (id: number, day: string, more: Partial<Entry> = {}): Entry => ({
  id, day, end: null, title: `Nr. ${id}`, source: 'google', category: '', picture: null, files: 0, gone: 0, owner: null, ...more,
})

describe('days', () => {
  it('go there and back', () => {
    expect(isoOf(dayNumber('2026-11-06'))).toBe('2026-11-06')
    expect(dayNumber('2024-03-01') - dayNumber('2024-02-28')).toBe(2)
  })

  it('do not slip over summer time', () => {
    expect(dayNumber('2026-03-30') - dayNumber('2026-03-29')).toBe(1)
    expect(dayNumber('2026-10-26') - dayNumber('2026-10-25')).toBe(1)
  })

  it('starts a year on its first of January', () => {
    expect(isoOf(yearStart(2011))).toBe('2011-01-01')
  })
})

describe('lanes', () => {
  it('take turns above and below the axis, nearest first', () => {
    expect([0, 1, 2, 3].map(laneAbove)).toEqual([true, false, true, false])
    expect([0, 1, 2, 3].map(laneRow)).toEqual([0, 0, 1, 1])
  })

  it('there are as many as the height has room for, and always one on each side', () => {
    expect(lanesFor(100, 58)).toBe(2)
    expect(lanesFor(560, 58)).toBe(4)
    expect(lanesFor(640, 58)).toBe(6)
    expect(lanesFor(900, 58) % 2).toBe(0)
  })
})

describe('place', () => {
  const from = dayNumber('2026-01-01')
  const to = dayNumber('2026-12-31')

  it('never lets two cards overlap', () => {
    const many = Array.from({ length: 300 }, (_, i) => entry(i, isoOf(from + i % 200)))
    const placed = place(many, 2, from, to, 6)
    for (let lane = 0; lane < 6; lane++) {
      const row = placed.filter((p) => p.lane === lane).sort((a, b) => a.x - b.x)
      for (let i = 1; i < row.length; i++) expect(row[i].x - row[i - 1].x).toBeGreaterThanOrEqual(CARD_WIDTH + CARD_GAP - 24)
    }
  })

  it('gives every entry a card when there is room', () => {
    const few = [entry(1, '2026-02-01'), entry(2, '2026-06-01'), entry(3, '2026-10-01')]
    expect(place(few, 4, from, to, 6)).toHaveLength(3)
  })

  it('keeps pictures, then own entries, when there is not', () => {
    const crowded = Array.from({ length: 40 }, (_, i) => entry(i, '2026-03-03'))
    crowded[35].picture = 7
    crowded[30].source = 'manual'
    const placed = place(crowded, 1, from, to, 2)
    expect(placed).toHaveLength(2)
    expect(placed.map((p) => p.entry.id).sort()).toEqual([30, 35])
  })

  it('puts a card where its day is', () => {
    const [card] = place([entry(1, '2026-01-11')], 10, from, to, 2)
    expect(card.x).toBe(10 * 10 + EDGE)
  })
})

describe('buckets', () => {
  it('get coarser the further out one is', () => {
    expect(unitFor(0.5)).toBe('month')
    expect(unitFor(5)).toBe('week')
    expect(unitFor(40)).toBe('day')
  })

  it('weeks start on a Monday', () => {
    expect(isoOf(bucketOf(dayNumber('2026-11-06'), 'week'))).toBe('2026-11-02')
    expect(isoOf(bucketOf(dayNumber('2026-11-02'), 'week'))).toBe('2026-11-02')
    expect(isoOf(bucketOf(dayNumber('2026-11-01'), 'week'))).toBe('2026-10-26')
  })

  it('months know their length', () => {
    const feb = bucketOf(dayNumber('2024-02-14'), 'month')
    expect(isoOf(feb)).toBe('2024-02-01')
    expect(bucketDays(feb, 'month')).toBe(29)
  })

  it('count what falls in them', () => {
    const counted = density([entry(1, '2026-03-02'), entry(2, '2026-03-30'), entry(3, '2026-04-01')], 'month')
    expect(counted.get(dayNumber('2026-03-01'))).toBe(2)
    expect(counted.get(dayNumber('2026-04-01'))).toBe(1)
  })
})

describe('ticks', () => {
  const from = dayNumber('2025-11-15')
  const to = dayNumber('2026-02-15')

  it('show only years from far away', () => {
    expect(ticks(from, to, 0.2).map((t) => t.label)).toEqual(['2026'])
  })

  it('name the months a little closer', () => {
    expect(ticks(from, to, 3).map((t) => t.label)).toEqual(['dec', '2026', 'feb'])
  })

  it('count the days close up, in order and without the first of the month twice', () => {
    const marks = ticks(dayNumber('2026-01-30'), dayNumber('2026-02-02'), 30)
    expect(marks.map((t) => isoOf(t.day))).toEqual(['2026-01-30', '2026-01-31', '2026-02-01', '2026-02-02'])
    expect(marks.map((t) => t.label)).toEqual(['30', '31', 'feb', '2'])
  })

  it('name the weekday closest in', () => {
    expect(ticks(dayNumber('2026-11-06'), dayNumber('2026-11-06'), 100)[0].label).toBe('fre 6')
  })
})
