/** A readable model from what adsb.lol gives: `desc` is "BOEING 737-800" or "LOCKHEED MARTIN
 *  F-16C", `type` the ICAO code (B738, A320, F16). */
import type { Aircraft } from './types'

const MODEL: [RegExp, (m: RegExpMatchArray) => string][] = [
  [/\b(?:F|MIG|SU|EF)[- ]?(\d{1,3})[A-Z]{0,3}\b/i, (x) => `${(x[0].match(/^[A-Za-z]+/) as RegExpMatchArray)[0].toUpperCase()}-${x[1]}`],
  [/\bA-?(3\d{2}|2\d{2}|400M?)\b/i, (x) => `A${x[1].toUpperCase()}`],
  [/\b7(\d)7-?(\d{1,3})?\b/, (x) => `7${x[1]}7${x[2] ? `-${x[2]}` : ''}`],
  [/\bC-?(\d{2,3}[A-Z]?)\b/i, (x) => `C-${x[1].toUpperCase()}`],
  [/\b(CRJ|ERJ|EMB|MD|DC|ATR|BAE|SAAB)[- ]?(\d{2,4})\b/i, (x) => `${x[1].toUpperCase()}-${x[2]}`],
]

// For aircraft with no description; the codes that show up over Denmark.
const TYPE: Record<string, string> = {
  A19N: 'A319neo', A20N: 'A320neo', A21N: 'A321neo', A318: 'A318', A319: 'A319', A320: 'A320', A321: 'A321',
  A332: 'A330-200', A333: 'A330-300', A338: 'A330-800neo', A339: 'A330-900neo', A342: 'A340-200', A343: 'A340-300',
  A345: 'A340-500', A346: 'A340-600', A359: 'A350-900', A35K: 'A350-1000', A388: 'A380', A400: 'A400M', A124: 'An-124',
  A225: 'An-225', B37M: '737 MAX 7', B38M: '737 MAX 8', B39M: '737 MAX 9', B3XM: '737 MAX 10', B733: '737-300',
  B734: '737-400', B735: '737-500', B736: '737-600', B737: '737-700', B738: '737-800', B739: '737-900', B741: '747-100',
  B744: '747-400', B748: '747-8', B74F: '747F', B752: '757-200', B753: '757-300', B762: '767-200', B763: '767-300',
  B764: '767-400', B772: '777-200', B77L: '777-200LR', B773: '777-300', B77W: '777-300ER', B77F: '777F', B788: '787-8',
  B789: '787-9', B78X: '787-10', E170: 'E170', E75L: 'E175', E75S: 'E175', E190: 'E190', E195: 'E195', E290: 'E190-E2',
  E295: 'E195-E2', E135: 'ERJ-135', E145: 'ERJ-145', CRJ2: 'CRJ200', CRJ7: 'CRJ700', CRJ9: 'CRJ900', CRJX: 'CRJ1000',
  AT43: 'ATR 42', AT45: 'ATR 42', AT72: 'ATR 72', AT75: 'ATR 72', AT76: 'ATR 72-600', DH8A: 'Dash 8', DH8C: 'Dash 8',
  DH8D: 'Dash 8 Q400', SB20: 'Saab 2000', SF34: 'Saab 340', MD11: 'MD-11', MD82: 'MD-82', MD83: 'MD-83', MD88: 'MD-88',
  MD90: 'MD-90', BCS1: 'A220-100', BCS3: 'A220-300', C17: 'C-17', C130: 'C-130', C30J: 'C-130J', C295: 'C-295',
  C560: 'Citation V', F16: 'F-16', F16C: 'F-16C', F35: 'F-35', F35A: 'F-35A', F18: 'F/A-18', EUFI: 'Eurofighter',
  A139: 'AW139', EC35: 'EC135', EC45: 'EC145', H60: 'UH-60', S92: 'S-92', MH60: 'MH-60', K35R: 'KC-135', KC30: 'A330 MRTT',
  E3TF: 'E-3 AWACS', P8: 'P-8', GLF4: 'Gulfstream IV', GLF5: 'Gulfstream V', GLF6: 'G650', GL5T: 'Global 5000',
  GLEX: 'Global Express', C25A: 'CJ2', C25B: 'CJ3', C25C: 'CJ4', C68A: 'Citation Latitude', E55P: 'Phenom 300',
  PC12: 'PC-12', PC24: 'PC-24', TBM9: 'TBM 900', SR22: 'SR22', C172: 'Cessna 172', C182: 'Cessna 182', P28A: 'PA-28',
  DA40: 'DA40', DA42: 'DA42', DV20: 'Katana', C152: 'Cessna 152',
}

export const CATEGORY: Record<string, string | null> = {
  A0: null, B0: null, C0: null, A1: 'let', A2: 'lille', A3: 'stor', A4: 'B757-klasse', A5: 'tung', A6: 'højtydende',
  A7: 'helikopter', B1: 'svævefly', B2: 'ballon', B4: 'ultralet', B6: 'drone',
}

export const metres = (ft: number): string => `${Math.round(ft * 0.3048)} m`

export function model(a: Pick<Aircraft, 'type' | 'desc' | 'callsign' | 'reg'>): string {
  const byType = a.type ? TYPE[a.type.toUpperCase()] : undefined
  if (byType) return byType
  const d = a.desc ?? ''
  for (const [pattern, format] of MODEL) {
    const hit = d.match(pattern)
    if (hit) return format(hit)
  }
  const rest = d.split(/\s+/).slice(1).join(' ').trim()      // "PILATUS PC-12" is a PC-12
  if (rest) return rest.slice(0, 12)
  return a.type ?? a.callsign ?? a.reg ?? ''
}

export function secondLabel(a: Aircraft): string {
  const first = model(a)
  if (a.onGround) return `${first}\npå jorden`
  const bits = [a.callsign, a.alt != null ? metres(a.alt) : null, a.route ? `${a.route.from}→${a.route.to}` : null].filter(Boolean)
  return `${first}\n${bits.join(', ')}`
}
