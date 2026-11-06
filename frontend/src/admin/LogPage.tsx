/** What the dashboard is doing: where each source stands, and the log file. */
import { useMemo, useState } from 'react'
import { since } from '../core/format'
import { usePoll } from '../core/usePoll'
import { isProblem, levelName, parseLog } from './logLines'

interface Source {
  name: string
  ok: boolean
  text: string
  at: number | null
  lastOk: number | null
}

interface LogView {
  sources: Source[]
  tail: string
}

const REFRESH_SECONDS = 15

const when = (ms: number) => since(new Date(ms).toISOString())

function SourceRow({ source: s }: { source: Source }) {
  const note = s.at == null ? '' : s.ok ? when(s.at) : s.lastOk ? `virkede sidst ${when(s.lastOk)}` : 'har ikke svaret siden start'
  return (
    <li>
      <span className={s.ok ? 'dot dot-good' : 'dot dot-bad'} aria-label={s.ok ? 'Virker' : 'Virker ikke'} />
      <strong>{s.name}</strong>
      <span>{s.text}</span>
      {note && <span className="meta">{note}</span>}
    </li>
  )
}

export function LogPage({ onAuthLost }: { onAuthLost: () => void }) {
  const { data, error } = usePoll<LogView>('/api/admin/log', REFRESH_SECONDS, onAuthLost)
  const [q, setQ] = useState('')
  const [onlyProblems, setOnlyProblems] = useState(false)
  const [copied, setCopied] = useState(false)
  const lines = useMemo(() => parseLog(data?.tail ?? ''), [data])
  const sources = useMemo(() => [...(data?.sources ?? [])].sort((a, b) => Number(a.ok) - Number(b.ok)), [data])
  const today = new Date().toLocaleDateString('sv-SE')
  const wanted = q.trim().toLowerCase()
  const shown = lines.filter((l) => (!onlyProblems || isProblem(l)) && (!wanted || `${l.text} ${l.more}`.toLowerCase().includes(wanted)))
  const failing = sources.filter((s) => !s.ok).length

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(data?.tail ?? '')
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      setCopied(false)              // a browser that says no leaves the button as it was
    }
  }

  return (
    <div className="log-page">
      {error && <p className="problem">{error}</p>}
      <h2>Kilder</h2>
      <p className="meta">{failing ? `${failing} af ${sources.length} virker ikke lige nu.` : `Alle ${sources.length} virker.`}</p>
      <ul className="sources">{sources.map((s) => <SourceRow key={s.name} source={s} />)}</ul>

      <div className="log-head">
        <h2>Loggen</h2>
        <input type="search" placeholder="Søg i loggen" aria-label="Søg i loggen" value={q} onChange={(e) => setQ(e.target.value)} />
        <label className="check"><input type="checkbox" checked={onlyProblems} onChange={(e) => setOnlyProblems(e.target.checked)} />Kun problemer</label>
        <button onClick={() => void copy()} disabled={!data?.tail}>{copied ? 'Kopieret' : 'Kopiér loggen'}</button>
      </div>
      {shown.length ? (
        <ol className="log" tabIndex={0} aria-label="Loggen, nyeste først">
          {shown.map((l, i) => (
            <li key={`${l.day}${l.time}${i}`} className={isProblem(l) ? 'bad' : ''}>
              <time>{l.day === today ? l.time : `${l.day.slice(8)}/${Number(l.day.slice(5, 7))} ${l.time}`}</time>
              <span>{levelName(l.level)}</span>
              <span className="log-text">{l.text}</span>
              {l.more && <details><summary>Detaljer</summary><pre>{l.more}</pre></details>}
            </li>
          ))}
        </ol>
      ) : <p className="empty">{lines.length ? 'Intet matcher.' : 'Der står intet i loggen endnu.'}</p>}
    </div>
  )
}
