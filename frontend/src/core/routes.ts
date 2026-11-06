// The address of each section. Section ids are the backend's; the address is
// what the person sees.
export const SECTIONS: { id: string; path: string; title: string }[] = [
  { id: 'calendar', path: 'kalender', title: 'Kalender' },
  { id: 'dklive', path: 'dk-live', title: 'DK live' },
  { id: 'news', path: 'nyheder', title: 'Nyheder' },
  { id: 'logmylife', path: 'logmylife', title: 'LogMyLife' },
  { id: 'aktier', path: 'aktier', title: 'Aktier' },
  { id: 'familylog', path: 'familylog', title: 'FamilyLog' },
  { id: 'f1', path: 'formel-1', title: 'Formel 1' },
  { id: 'latenight', path: 'slq-dl', title: 'SLQ DL' },
  { id: 'printers', path: 'printere', title: 'Printere' },
  { id: 'cameras', path: 'kameraer', title: 'Kameraer' },
  { id: 'links', path: 'links', title: 'Links' },
]

export const hrefOf = (id: string) => `#/${SECTIONS.find((s) => s.id === id)?.path ?? ''}`

export function readRoute(): { path: string; query: URLSearchParams } {
  const [path, query] = window.location.hash.replace(/^#\/?/, '').split('?')
  return { path, query: new URLSearchParams(query ?? '') }
}
