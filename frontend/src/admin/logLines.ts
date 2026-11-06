/** The log file's end as lines to show, newest first. A traceback belongs to the line above it. */
export interface LogLine {
  day: string
  time: string
  level: string
  text: string
  more: string
}

const START = /^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}),\d+ (\w+)\s+\S+ \S+\s+(.*)$/

export function parseLog(tail: string): LogLine[] {
  const out: LogLine[] = []
  for (const line of tail.split('\n')) {
    const found = START.exec(line)
    if (found) out.push({ day: found[1], time: found[2], level: found[3], text: found[4], more: '' })
    else if (out.length && line) out[out.length - 1].more += `${line}\n`
  }
  return out.reverse()
}

export const isProblem = (line: LogLine): boolean => line.level === 'ERROR' || line.level === 'CRITICAL' || line.level === 'WARNING'

const LEVEL: Record<string, string> = { WARNING: 'Advarsel', ERROR: 'Fejl', CRITICAL: 'Fejl' }

export const levelName = (level: string): string => LEVEL[level] ?? ''
