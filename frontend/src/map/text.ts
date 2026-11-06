/** Small pieces of text for the map's labels and popups. No map in here, so it can be tested. */

const LABEL_LENGTH = 25

export const esc = (s: unknown): string =>
  String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c] as string)

export const cap = (s: string | null | undefined): string =>
  s && s.length > LABEL_LENGTH ? `${s.slice(0, LABEL_LENGTH - 1).trimEnd()}…` : s ?? ''

export const hhmm = (t: number): string => new Date(t).toLocaleTimeString('da-DK', { hour: '2-digit', minute: '2-digit' })

export const stamp = (t: number | null | undefined): string =>
  t ? new Date(t).toLocaleString('da-DK', { hour: '2-digit', minute: '2-digit', day: 'numeric', month: 'short' }) : '–'

export type Row = [string, string | null | undefined, boolean?]

/** Rows of a definition list. The third field says the value is already markup. */
export const rows = (list: Row[]): string =>
  list.filter(([, v]) => v != null && v !== '').map(([k, v, html]) => `<dt>${esc(k)}</dt><dd>${html ? v : esc(v)}</dd>`).join('')

/** Addresses in the feeds are other people's: only the web is a link. */
export const webAddress = (href: string | null | undefined): string | null => (href && /^https?:\/\//i.test(href) ? href : null)

export const link = (href: string, text: string): string =>
  webAddress(href) ? `<a class="ext" href="${esc(href)}" target="_blank" rel="noopener noreferrer">${esc(text)}</a>` : ''

const COMPASS = ['N', 'NNØ', 'NØ', 'ØNØ', 'Ø', 'ØSØ', 'SØ', 'SSØ', 'S', 'SSV', 'SV', 'VSV', 'V', 'VNV', 'NV', 'NNV']
export const compass = (d: number | null | undefined): string => (d == null ? '' : COMPASS[Math.round(d / 22.5) % 16])

export const signed = (v: number): string => `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(Math.round(v))}`

export const number = (v: number | null | undefined, digits = 0): string =>
  v == null ? '–' : v.toLocaleString('da-DK', { maximumFractionDigits: digits, minimumFractionDigits: digits })
