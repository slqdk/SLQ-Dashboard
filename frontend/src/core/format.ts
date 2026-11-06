// Danish text for dates, times and numbers. All in the browser's own time zone.
const da = 'da-DK'

const dateLong = new Intl.DateTimeFormat(da, { weekday: 'long', day: 'numeric', month: 'long' })
const timeShort = new Intl.DateTimeFormat(da, { hour: '2-digit', minute: '2-digit' })
const dayShort = new Intl.DateTimeFormat(da, { weekday: 'short', day: 'numeric', month: 'short' })
const weekdayLong = new Intl.DateTimeFormat(da, { weekday: 'long' })
const dateFull = new Intl.DateTimeFormat(da, { day: 'numeric', month: 'long', year: 'numeric' })

export const cap = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s)

export const longDate = (d: Date) => cap(dateLong.format(d))
export const clock = (d: Date | string) => timeShort.format(new Date(d)).replace('.', ':')
export const shortDay = (d: Date | string) => dayShort.format(new Date(d)).replace(/\.$/, '')
export const weekday = (d: Date | string) => weekdayLong.format(new Date(d))
export const fullDate = (d: Date | string) => dateFull.format(new Date(d))

export const dayKey = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

/** Date-only strings are local dates, not midnight UTC. */
export const localDate = (day: string) => {
  const [y, m, n] = day.slice(0, 10).split('-').map(Number)
  return new Date(y, m - 1, n)
}

export function dayName(day: string, now = new Date()): string {
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const diff = Math.round((localDate(day).getTime() - today.getTime()) / 86_400_000)
  if (diff === 0) return 'I dag'
  if (diff === 1) return 'I morgen'
  if (diff > 1 && diff < 7) return cap(weekday(localDate(day)))
  return cap(shortDay(localDate(day)))
}

export function ago(iso: string, now = Date.now()): string {
  const min = Math.floor((now - new Date(iso).getTime()) / 60_000)
  if (min < 1) return 'lige nu'
  if (min < 60) return `${min} min`
  const hours = Math.round(min / 60)
  if (hours < 24) return `${hours} t`
  return `${Math.round(hours / 24)} d`
}

export function until(iso: string, now = Date.now()): string {
  const min = Math.round((new Date(iso).getTime() - now) / 60_000)
  if (min <= 0) return 'i gang'
  if (min < 60) return `om ${min} min`
  const hours = Math.floor(min / 60)
  if (hours < 48) return `om ${hours} t ${min % 60} min`
  return `om ${Math.floor(hours / 24)} dage`
}

const number = (digits: number) =>
  new Intl.NumberFormat(da, { minimumFractionDigits: digits, maximumFractionDigits: digits })

export const kr = (v: number) => number(2).format(v)
export const one = (v: number) => number(1).format(v)
export const whole = (v: number) => number(0).format(v)
