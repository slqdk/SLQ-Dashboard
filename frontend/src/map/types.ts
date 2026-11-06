/** What /api/s/dklive/map/<feed> sends. */

export interface Route { from: string; to: string; fromName: string | null; toName: string | null }

export interface Aircraft {
  id: string
  callsign: string | null
  reg: string | null
  type: string | null
  desc: string | null
  operator: string | null
  category: string | null
  lat: number
  lon: number
  alt: number | null
  onGround: boolean
  gs: number | null
  track: number | null
  vr: number | null
  squawk: string | null
  emergency: string | null
  military: boolean
  seen: number
  route: Route | null
}

export interface Ship {
  id: number
  name: string | null
  type: number | null
  dest: string | null
  lat: number
  lon: number
  cog: number | null
  sog: number | null
  heading: number | null
  navStatus: number | null
  rot: number | null
  seen: number
  imo?: number | null
  callsign?: string | null
  length?: number | null
  beam?: number | null
  draught?: number | null
  eta?: { month: number; day: number; hour: number | null; minute: number | null } | null
}

export interface Alarm {
  id: string
  time: number
  beredskab: string
  station: string
  message: string
  lat?: number
  lon?: number
}

export interface TrafficEvent {
  id: string
  title: string | null
  header: string
  text: string
  kind: string
  blocking: boolean
  source: string | null
  begin: number | null
  end: number | null
  modified: number | null
  lat: number
  lon: number
}

export interface AutobahnEvent {
  id: string
  road: string
  kind: string
  title: string
  subtitle: string
  text: string
  blocked: boolean
  start: number | null
  lat: number
  lon: number
}

export interface Train {
  id: string
  name: string
  category: string | null
  operator: string | null
  direction: string | null
  delay: number | null
  lat: number
  lon: number
}

export interface Webcam {
  id: string
  source: 'autobahn' | 'windy' | 'egen'
  name: string
  lat: number
  lon: number
  road?: string
  subtitle?: string
  image?: string | null
  link?: string | null
  note?: string | null
  city?: string | null
  country?: string | null
  windyId?: number
}

export interface RadarFrame { time: number; path: string; nowcast: boolean }

export interface Strike { lon: number; lat: number; time: number; type: number }

export interface WindStation {
  id: string
  name: string
  lon: number
  lat: number
  time: number
  speed: number
  dir: number | null
  gust: number | null
  temp: number | null
}

export interface Gauge { id: string; name: string; lon: number; lat: number; time: number; level: number }

export interface NavWarning {
  id: number | string
  shortId: string | null
  kind: 'fe' | 'nw'
  title: string
  area: string | null
  details: string
  from: number | null
  to: number | null
  geometries: GeoJSON.Geometry[]
}

export interface Metar {
  raw: string
  time: number | null
  tempC: number | null
  dewC: number | null
  windDir: number | string | null
  windKt: number | null
  gustKt: number | null
  visM: number | string | null
  qnh: number | null
  wx: string | null
  clouds: string | null
  fltCat: string | null
}

export interface Airport {
  id: string
  icao: string
  iata: string | null
  name: string
  type: 'large' | 'medium' | 'small'
  lat: number
  lon: number
  elevationFt: number | null
  municipality: string | null
  scheduled: boolean
  website: string | null
  wikipedia: string | null
  runways: { ident: string; lengthM: number | null; surface: string | null; lighted: boolean }[]
  frequencies: { type: string; mhz: string }[]
  metar: Metar | null
}

export interface Hourly {
  time: string
  temperature_2m?: number | null
  precipitation?: number | null
  precipitation_probability?: number | null
  weather_code?: number | null
}

export interface Forecast {
  lat: number
  lon: number
  place: string | null
  current: Record<string, number | null> | null
  minutely: Hourly[]
  hourly: Hourly[]
  daily: Record<string, number | string | null>[]
}

export interface Photo {
  thumb?: string | null
  link?: string | null
  credit?: string | null
  license?: string | null
  source?: string
  uncertain?: boolean
}
