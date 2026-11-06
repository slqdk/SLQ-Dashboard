export interface User {
  id: number
  username: string
  role: 'admin' | 'family'
  name: string
  sections: string[]
}

export interface LifeEvent {
  id: number
  uid: string
  source: string
  title: string
  description: string
  category: string
  start: string
  end: string | null
  allDay: boolean
  day: string
  location: string
  shared: boolean
  deletedAtSource: string | null
  mine: boolean
  owner: string | null
}

export interface CalendarEvent {
  id: string
  title: string
  start: string
  end: string | null
  allDay: boolean
  day: string
  location: string
  color: string
  calendar: string
}

export interface CalendarBlock {
  configured: boolean
  connected: boolean
  status: string
  email: string
  events: CalendarEvent[]
}

export interface PricePoint {
  t: string
  dkk: number
}

export interface Power {
  area: string
  now: number
  nowAt: string
  low: PricePoint
  high: PricePoint
  series: PricePoint[]
  wind: number | null
  solar: number | null
  co2: number | null
}

export interface HourWeather {
  t: string
  temp: number | null
  rain: number | null
  code: number | null
}

export interface Weather {
  temp: number | null
  feels: number | null
  wind: number | null
  gusts: number | null
  text: string
  place: string
  hourly: HourWeather[]
  daily: { day: string; max: number; min: number; rain: number; text: string; sunrise: string; sunset: string }[]
}

export interface LiveUpdate {
  kind: '112' | 'politi' | 'trafik'
  id: string
  at: string
  title: string
  detail: string
  km: number | null
  blocking?: boolean
  updates?: number
}

export interface DkLive {
  configured: boolean
  link: string
  home: string
  ok?: boolean
  error?: string
  updated?: string
  map?: string
  power?: Power | null
  weather?: Weather | null
  feed?: LiveUpdate[]
  traffic?: { total: number; near: number; blocking: number; items: LiveUpdate[] }
}

export interface NewsItem {
  source: string
  title: string
  url: string
  summary: string
  at: string | null
}

export interface NewsFeedState {
  name: string
  ok: boolean
  count: number
  dropped: number
  error: string
}

export interface F1Session {
  season: number
  round: number
  meeting: string
  country: string
  circuit: string
  name: string
  start: string
  end: string
  race: boolean
}

export interface F1Block {
  next: F1Session | null
  meeting?: string
  weekend: F1Session[]
  sessions?: F1Session[]
}

export interface Fact {
  id: number
  date: string
  title: string
  body: string
  kind: string
  hosts: string[]
  story: string
  sourceUrl: string
  yearsAgo: number | null
}

export interface Monologue {
  show: string
  title: string
  url: string
  at: string | null
}

export interface LateNightBlock {
  date: string
  exact: Fact[]
  near: Fact[]
  total: number
  monologues: Monologue[]
}

export interface FamilyLogState {
  address: boolean
  connected: boolean
  checkedAt?: string
  error?: string
  added?: number
  month?: {
    from: string
    to: string
    spent: number
    income: number
    count: number
    top: { name: string; spent: number }[]
  } | null
}

export interface LinkItem {
  id: number
  folderId: number | null
  title: string
  url: string
  note: string
  pinned: boolean
}

export interface Folder {
  id: number
  parentId: number | null
  name: string
}

export interface PrinterState {
  id: number
  name: string
  online: boolean
  problem: string
  state: string
  stateText: string
  active: boolean
  percent: number | null
  remainingMin: number | null
  layer: number | null
  totalLayers: number | null
  nozzle: number | null
  nozzleTarget: number | null
  bed: number | null
  bedTarget: number | null
  file: string
  error: string
}

export interface CameraItem {
  id: number
  name: string
}

export interface StockWeek {
  days: string[]
  total: number[]
  value?: number
  change?: number
  changeKr?: number
  items: { name: string; isin: string; points: number[]; close: number; currency: string; value: number; change: number }[]
  missing: string[]
}

export interface Overview {
  serverTime: string
  blocks: {
    calendar?: CalendarBlock
    dklive?: DkLive
    news?: { items: NewsItem[]; feeds: NewsFeedState[] }
    logmylife?: { onThisDay: LifeEvent[]; latest: LifeEvent[]; total: number }
    aktier?: { mode: string; positions: number; importedAt: string | null; week: StockWeek | null }
    familylog?: FamilyLogState
    f1?: F1Block
    latenight?: LateNightBlock
    links?: { pinned: LinkItem[]; total: number }
    printers?: { printers: PrinterState[] }
    cameras?: { cameras: CameraItem[] }
  }
}

export interface NetStatus {
  targets: { name: string; ms: number | null; ok: boolean }[]
  internetMs: number | null
  history: (number | null)[]
  load: { load1: number | null; load5: number | null; load15: number | null; cpus: number }
}
