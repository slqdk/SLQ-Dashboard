import { useMemo, useState } from 'react'
import { api } from '../core/api'
import { fullDate, localDate, whole } from '../core/format'
import { usePoll } from '../core/usePoll'
import type { LifeEvent } from '../core/types'
import { Dialog, FileImport, SectionHead } from './common'

const API = '/api/s/logmylife'
const SOURCE_TEXT: Record<string, string> = {
  manual: 'Eget indlæg', google: 'Google Kalender', strava: 'Strava',
  'familylog.dagbog': 'Dagbog', 'familylog.familymap': 'FamilyMap',
}

interface Meta {
  categories: string[]
  stats: { bySource: Record<string, number>; total: number; first: string | null }
  onThisDay: LifeEvent[]
}

const yearOf = (e: LifeEvent) => e.day.slice(0, 4)

function Entry({ e, onEdit }: { e: LifeEvent; onEdit: (e: LifeEvent) => void }) {
  return (
    <li className={e.deletedAtSource ? 'life-entry gone' : 'life-entry'}>
      <time>{fullDate(localDate(e.day))}</time>
      <div>
        <p className="life-title">{e.title}</p>
        {e.description && <p className="life-text">{e.description}</p>}
        <p className="meta">
          {e.mine ? SOURCE_TEXT[e.source] ?? e.source : `Delt af ${e.owner}`}
          {e.location ? `, ${e.location}` : ''}
          {e.category ? `, ${e.category}` : ''}
          {e.shared && e.mine ? ', delt med familien' : ''}
          {e.deletedAtSource ? ', slettet i Google' : ''}
        </p>
      </div>
      {e.mine && <button onClick={() => onEdit(e)}>Ret</button>}
    </li>
  )
}

export function LogMyLife({ onAuthLost }: { onAuthLost: () => void }) {
  const [scope, setScope] = useState<'mine' | 'family'>('mine')
  const [q, setQ] = useState('')
  const [source, setSource] = useState('')
  const [editing, setEditing] = useState<Partial<LifeEvent> | null>(null)
  const [importing, setImporting] = useState(false)
  const params = useMemo(() => new URLSearchParams(Object.entries({ scope, q, source, limit: '300' }).filter(([, v]) => v)), [scope, q, source])
  const list = usePoll<{ events: LifeEvent[]; more: boolean }>(`${API}/events?${params}`, 0, onAuthLost)
  const meta = usePoll<Meta>(`${API}/meta`, 0, onAuthLost)
  const events = list.data?.events ?? []

  const years = useMemo(() => {
    const out = new Map<string, LifeEvent[]>()
    for (const e of events) out.set(yearOf(e), [...(out.get(yearOf(e)) ?? []), e])
    return [...out]
  }, [events])

  const stats = meta.data?.stats
  const summary = stats?.total
    ? `${whole(stats.total)} begivenheder, de første fra ${stats.first?.slice(0, 4)}.`
    : 'Din tidslinje. Kalenderen og andre sektioner skriver selv i den, og du kan selv tilføje.'

  const saved = () => {
    setEditing(null)
    void list.reload()
    void meta.reload()
  }

  return (
    <main className="page">
      <SectionHead title="LogMyLife" text={summary}>
        <button onClick={() => setImporting(true)}>Importér fra Strava</button>
        <button className="primary" onClick={() => setEditing({})}>Nyt indlæg</button>
      </SectionHead>

      {!!meta.data?.onThisDay.length && (
        <section className="on-this-day">
          <h2>På denne dag</h2>
          <ul>
            {meta.data.onThisDay.map((e) => (
              <li key={e.id}><span className="meta">{yearOf(e)}</span><span>{e.title}</span></li>
            ))}
          </ul>
        </section>
      )}

      <div className="filters">
        <div className="segmented" role="group" aria-label="Hvis tidslinje">
          <button className={scope === 'mine' ? 'on' : ''} onClick={() => setScope('mine')}>Min</button>
          <button className={scope === 'family' ? 'on' : ''} onClick={() => setScope('family')}>Delt af familien</button>
        </div>
        <input type="search" placeholder="Søg" aria-label="Søg i tidslinjen" value={q} onChange={(e) => setQ(e.target.value)} />
        <select aria-label="Kilde" value={source} onChange={(e) => setSource(e.target.value)}>
          <option value="">Alle kilder</option>
          {Object.keys(stats?.bySource ?? {}).map((s) => <option key={s} value={s}>{SOURCE_TEXT[s] ?? s}</option>)}
        </select>
      </div>

      {years.map(([year, list2]) => (
        <section key={year} className="life-year">
          <h2>{year}</h2>
          <ol>{list2.map((e) => <Entry key={e.id} e={e} onEdit={setEditing} />)}</ol>
        </section>
      ))}
      {!events.length && list.data && (
        <p className="empty">{q || source ? 'Intet matcher.' : scope === 'family' ? 'Familien har ikke delt noget endnu.' : 'Tidslinjen er tom. Skriv det første indlæg.'}</p>
      )}

      {editing && (
        <EventForm event={editing} categories={meta.data?.categories ?? []} onClose={() => setEditing(null)} onSaved={saved} />
      )}
      {importing && (
        <FileImport title="Importér fra Strava" url={`${API}/import/strava`} label="activities.csv" accept=".csv,text/csv"
          onClose={() => setImporting(false)} onDone={() => { void list.reload(); void meta.reload() }}>
          <ol className="steps">
            <li>Sæt sproget på Strava til English.</li>
            <li>Gå til Settings → My Account → Download your account, og bestil dine data.</li>
            <li>Pak zip-filen fra mailen ud, og vælg activities.csv her.</li>
          </ol>
        </FileImport>
      )}
    </main>
  )
}

function EventForm({ event, categories, onClose, onSaved }: {
  event: Partial<LifeEvent>; categories: string[]; onClose: () => void; onSaved: () => void
}) {
  const mineOnly = event.id === undefined || event.source === 'manual'
  const [form, setForm] = useState({
    title: event.title ?? '', start: event.start?.slice(0, 10) ?? '', end: event.end?.slice(0, 10) ?? '',
    description: event.description ?? '', location: event.location ?? '',
    category: event.category ?? '', shared: event.shared ?? false,
  })
  const [problem, setProblem] = useState('')
  const set = (key: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setForm({ ...form, [key]: e.target.value })

  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      await api(event.id ? `${API}/events/${event.id}` : `${API}/events`, { method: event.id ? 'PUT' : 'POST', body: form })
      onSaved()
    } catch (exc) {
      setProblem(exc instanceof Error ? exc.message : 'Kunne ikke gemme.')
    }
  }
  const remove = async () => {
    try {
      await api(`${API}/events/${event.id}`, { method: 'DELETE' })
      onSaved()
    } catch (exc) {
      setProblem(exc instanceof Error ? exc.message : 'Kunne ikke slette.')
    }
  }

  return (
    <Dialog title={event.id ? 'Ret indlæg' : 'Nyt indlæg'} onClose={onClose}>
      <form onSubmit={save}>
        {mineOnly ? (
          <>
            <label>Titel<input required autoFocus value={form.title} onChange={set('title')} /></label>
            <div className="form-row">
              <label>Dato<input type="date" required value={form.start} onChange={set('start')} /></label>
              <label>Til og med<input type="date" value={form.end} onChange={set('end')} /></label>
            </div>
            <label>Sted<input value={form.location} onChange={set('location')} /></label>
            <label>Tekst<textarea rows={4} value={form.description} onChange={set('description')} /></label>
          </>
        ) : (
          <p className="note">{event.title} kom fra {SOURCE_TEXT[event.source ?? ''] ?? event.source} og beholder sin tekst. Du kan vælge kategori og deling.</p>
        )}
        <label>Kategori
          <select value={form.category} onChange={set('category')}>
            <option value="">Ingen</option>
            {categories.map((c) => <option key={c}>{c}</option>)}
          </select>
        </label>
        <label className="check">
          <input type="checkbox" checked={form.shared} onChange={(e) => setForm({ ...form, shared: e.target.checked })} />
          Del med familien
        </label>
        {problem && <p className="problem">{problem}</p>}
        <div className="dialog-actions">
          {event.id && mineOnly && <button type="button" className="danger" onClick={remove}>Slet</button>}
          <button type="button" onClick={onClose}>Annullér</button>
          <button type="submit" className="primary">Gem</button>
        </div>
      </form>
    </Dialog>
  )
}
