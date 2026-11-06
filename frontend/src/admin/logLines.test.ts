import { describe, expect, it } from 'vitest'
import { isProblem, levelName, parseLog } from './logLines'

const TAIL = `2026-11-06 16:20:01,120 INFO    slq-dashboard jobs:60  started 34 background jobs
2026-11-06 16:20:03,501 ERROR   slq-dashboard logs:205  dklive: prices: HTTP 429
2026-11-06 16:21:00,002 ERROR   slq-dashboard logs:214  job energy: boom
Traceback (most recent call last):
  File "x.py", line 1, in y
ValueError: boom
`

describe('the log', () => {
  it('reads the file, newest first', () => {
    const lines = parseLog(TAIL)
    expect(lines.map((l) => l.time)).toEqual(['16:21:00', '16:20:03', '16:20:01'])
    expect(lines[1].text).toBe('dklive: prices: HTTP 429')
  })

  it('keeps a traceback with its line', () => {
    expect(parseLog(TAIL)[0].more).toContain('ValueError: boom')
    expect(parseLog(TAIL)[1].more).toBe('')
  })

  it('tells problems from the rest', () => {
    const lines = parseLog(TAIL)
    expect(lines.map(isProblem)).toEqual([true, true, false])
    expect(levelName('ERROR')).toBe('Fejl')
    expect(levelName('INFO')).toBe('')
  })

  it('has nothing to show from nothing', () => {
    expect(parseLog('')).toEqual([])
  })
})
