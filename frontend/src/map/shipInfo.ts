/** What an MMSI and an AIS type code say about a vessel. */

export const NAV_STATUS: Record<number, string> = {
  0: 'Under gang (motor)', 1: 'Til ankers', 2: 'Ikke under kommando', 3: 'Begrænset manøvreevne', 4: 'Begrænset af dybgang',
  5: 'Fortøjet', 6: 'Grundstødt', 7: 'Fisker', 8: 'Under sejl', 11: 'Slæbt eller bugseret', 12: 'Skubber',
  14: 'AIS-SART, nød', 15: 'Ukendt',
}

// The flag from the MMSI's first three digits; the ones seen here.
const FLAGS: Record<string, string> = {
  219: 'DK', 220: 'DK', 211: 'DE', 218: 'DE', 265: 'SE', 266: 'SE', 257: 'NO', 258: 'NO', 259: 'NO', 244: 'NL', 245: 'NL',
  246: 'NL', 230: 'FI', 231: 'FO', 232: 'GB', 233: 'GB', 234: 'GB', 235: 'GB', 261: 'PL', 276: 'EE', 275: 'LV', 277: 'LT',
  273: 'RU', 209: 'CY', 210: 'CY', 212: 'CY', 229: 'MT', 248: 'MT', 249: 'MT', 256: 'MT', 255: 'PT (Madeira)', 304: 'AG',
  305: 'AG', 308: 'BS', 309: 'BS', 311: 'BS', 636: 'LR', 538: 'MH', 351: 'PA', 352: 'PA', 353: 'PA', 354: 'PA', 370: 'PA',
  371: 'PA', 372: 'PA', 373: 'PA', 374: 'PA', 477: 'HK', 563: 'SG', 564: 'SG', 565: 'SG', 566: 'SG', 205: 'BE', 226: 'FR',
  227: 'FR', 228: 'FR', 224: 'ES', 225: 'ES', 247: 'IT', 250: 'IE', 251: 'IS', 271: 'TR', 314: 'BB', 319: 'KY', 341: 'KN',
  375: 'VC', 376: 'VC', 377: 'VC', 378: 'VG', 503: 'AU', 416: 'TW', 412: 'CN', 413: 'CN', 414: 'CN', 431: 'JP', 432: 'JP',
  440: 'KR', 441: 'KR', 366: 'US', 367: 'US', 368: 'US', 369: 'US',
}

export type VesselKind = 'ship' | 'sar' | 'aton' | 'sart' | 'coast'

export const KIND_NAME: Record<VesselKind, string | null> = {
  sar: 'SAR-helikopter eller fly', aton: 'Sømærke', sart: 'Nødsender (AIS-SART)', coast: 'Kyststation', ship: null,
}

/** MMSI classes that are not ships (ITU-R M.585). */
export function kind(mmsi: number | string): VesselKind {
  const m = String(mmsi)
  if (m.startsWith('111')) return 'sar'
  if (m.startsWith('99')) return 'aton'
  if (m.startsWith('98')) return 'ship'         // a craft that belongs to a parent ship
  if (m.startsWith('970') || m.startsWith('972') || m.startsWith('974')) return 'sart'
  if (m.startsWith('00')) return 'coast'
  return 'ship'
}

export function flag(mmsi: number | string): string | null {
  const m = String(mmsi)
  const mid = m.startsWith('111') ? m.slice(3, 6) : m.startsWith('99') || m.startsWith('98') ? m.slice(2, 5) : m.slice(0, 3)
  return FLAGS[mid] ?? null
}

export function typeName(t: number | null | undefined): string {
  if (t == null || Number.isNaN(t)) return 'ukendt'
  if (t >= 60 && t <= 69) return 'Passager'
  if (t >= 70 && t <= 79) return 'Fragt'
  if (t >= 80 && t <= 89) return 'Tank'
  if (t === 30) return 'Fiskeri'
  if (t === 52) return 'Slæbebåd'
  if (t === 36 || t === 37) return 'Fritid'
  if (t >= 40 && t <= 49) return 'Højhastighed'
  if (t === 50 || t === 55) return 'Myndighed'
  return `Type ${t}`
}
