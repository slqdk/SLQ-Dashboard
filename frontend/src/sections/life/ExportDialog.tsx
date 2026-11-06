/** Getting the log out. The browser fetches the file itself, so a zip of many gigabytes is
 *  an ordinary download. */
import { useState } from 'react'
import { Dialog } from '../common'
import { bytes } from './EntryDialog'

const FORMATS: [string, string, string][] = [
  ['zip', 'Alt i én zip', 'Indlæg, billeder og filer i original, og en side, du kan læse uden dashboardet.'],
  ['json', 'JSON', 'Alle felter, til at flytte videre. Uden billeder.'],
  ['csv', 'CSV til Excel', 'Én række pr. indlæg. Uden billeder.'],
  ['ics', 'Kalenderfil', 'Til at åbne i en anden kalender. Uden billeder.'],
]

export function ExportDialog({ q, source, usage, onClose }: {
  q: string; source: string; usage: { count: number; bytes: number; free: number | null } | undefined; onClose: () => void
}) {
  const [format, setFormat] = useState('zip')
  const [since, setSince] = useState('')
  const [until, setUntil] = useState('')
  const [filtered, setFiltered] = useState(false)
  const search = filtered ? { q, source } : {}
  const params = new URLSearchParams(Object.entries({ format, since, until, ...search }).filter(([, v]) => v))
  return (
    <Dialog title="Eksportér LogMyLife" onClose={onClose}>
      <div className="life-export">
        {FORMATS.map(([id, name, text]) => (
          <label key={id} className="check">
            <input type="radio" name="format" checked={format === id} onChange={() => setFormat(id)} />
            <span><strong>{name}</strong><br /><span className="meta">{text}</span></span>
          </label>
        ))}
        <div className="form-row">
          <label>Fra<input type="date" value={since} onChange={(e) => setSince(e.target.value)} /></label>
          <label>Til<input type="date" value={until} onChange={(e) => setUntil(e.target.value)} /></label>
        </div>
        {(q || source) && (
          <label className="check">
            <input type="checkbox" checked={filtered} onChange={(e) => setFiltered(e.target.checked)} />
            Kun det, søgningen viser nu
          </label>
        )}
        {usage && <p className="note">{usage.count} filer, {bytes(usage.bytes)}.{usage.free != null ? ` ${bytes(usage.free)} ledigt på serveren.` : ''} Kun dine egne indlæg kommer med.</p>}
      </div>
      <div className="dialog-actions">
        <button onClick={onClose}>Luk</button>
        <a className="button primary" href={`/api/s/logmylife/export?${params}`} download>Hent</a>
      </div>
    </Dialog>
  )
}
