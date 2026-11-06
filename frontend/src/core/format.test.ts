import { describe, expect, it } from 'vitest'
import { ago, dayKey, dayName, duration, kr, localDate, units, until } from './format'

const now = new Date(2026, 10, 6, 7, 15) // Friday 6 November

describe('units', () => {
  it('keeps fractions and drops empty decimals', () => {
    expect(units(15)).toBe('15')
    expect(units(2.6667)).toBe('2,6667')
  })
})

describe('dayName', () => {
  it('names the near days', () => {
    expect(dayName('2026-11-06', now)).toBe('I dag')
    expect(dayName('2026-11-07', now)).toBe('I morgen')
    expect(dayName('2026-11-08', now)).toBe('Søndag')
  })
  it('falls back to a date from a week out', () => {
    expect(dayName('2026-11-20', now)).toMatch(/20\. nov/)
  })
})

describe('times', () => {
  it('counts back and forth', () => {
    const t = now.getTime()
    expect(ago(new Date(t - 30_000).toISOString(), t)).toBe('lige nu')
    expect(ago(new Date(t - 5 * 60_000).toISOString(), t)).toBe('5 min')
    expect(ago(new Date(t - 3 * 3_600_000).toISOString(), t)).toBe('3 t')
    expect(until(new Date(t + 90 * 60_000).toISOString(), t)).toBe('om 1 t 30 min')
    expect(until(new Date(t - 1000).toISOString(), t)).toBe('i gang')
  })
  it('says minutes as hours and minutes', () => {
    expect(duration(45)).toBe('45 min')
    expect(duration(120)).toBe('2 t')
    expect(duration(74)).toBe('1 t 14 min')
  })
  it('keeps a date-only string on its own day', () => {
    expect(dayKey(localDate('2026-01-01'))).toBe('2026-01-01')
  })
})

describe('kr', () => {
  it('uses a Danish decimal comma', () => {
    expect(kr(2.427)).toBe('2,43')
  })
})
