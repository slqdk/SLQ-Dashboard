import { useMemo, useState } from 'react'
import { api } from '../core/api'
import { fullDate, localDate, whole } from '../core/format'
import { usePoll } from '../core/usePoll'
import type { LifeEvent } from '../core/types'
import { Dialog, FileImport, SectionHead } from './common'
import { EntryDialog } from './life/EntryDialog'
import { ExportDialog } from './life/ExportDialog'
import type { Entry } from './life/layout'
import { sourceName, Timeline } from './life/Timeline'

const API = '/api/s/logmylife'

interface Meta {
  categories: string[]
  stats: { bySource: Record<string, number>; total: number; first: string | null }
  files: { count: number; bytes: number; free: number | null }
  onThisDay: LifeEvent[]
}

interface Index {
  fields: string[]
  rows: unknown[][]
  today: string
}

const yearOf = (e: LifeEvent) => e.day.slice(0, 4)

function ListEntry({ e, onOpen }: { e: LifeEvent; onOpen: (id: number) => void }) {
  return (
    <li className={e.deletedAtSource ? 'life-entry gone' : 'life-entry'}>
      <time>{fullDate(localDate(e.day))}</time>
      <div>
        <p className="life-title">{e.title}</p>
        {e.description && <p className="life-text">{e.description}</p>}
        <p className="meta">
          {e.mine ? sourceName(e.source) : `Delt af ${e.owner}`}
          {e.location ? `, ${e.location}` : ''}
          {e.category ? `, ${e.category}` : ''}
          {e.shared && e.mine ? ', delt med familien' : ''}
          {e.deletedAtSource ? ', slettet i Google' : ''}
        </p>
      </div>
      <button onClick={() => onOpen(e.id)}>Åbn</button>
    </li>
  )
}

function ListView({ params, onOpen, onAuthLost }: { params: URLSearchParams; onOpen: (id: number) => void; onAuthLost: () => void }) {
  const list = usePoll<{ events: LifeEvent[]; more: boolean }>(`${API}/events?${params}&limit=300`, 0, onAuthLost)
  const years = useMemo(() => {
    const out = new Map<string, LifeEvent[]>()
    for (const e of list.data?.events ?? []) out.set(yearOf(e), [...(out.get(yearOf(e)) ?? []), e])
    return [...out]
  }, [list.data])
  return (
    <div className="life-list">
      {years.map(([year, events]) => (
        <section key={year} className="life-year">
          <h2>{year}</h2>
          <ol>{events.map((e) => <ListEntry key={e.id} e={e} onOpen={onOpen} />)}</ol>
        </section>
      ))}
      {!years.length && list.data && <p className="empty">Intet at vise.</p>}
    </div>
  )
}

export function LogMyLife({ onAuthLost }: { onAuthLost: () => void }) {
  const [scope, setScope] = useState<'mine' | 'family'>('mine')
  const [view, setView] = useState<'line' | 'list'>('line')
  const [q, setQ] = useState('')
  const [source, setSource] = useState('')
  const [editing, setEditing] = useState<Partial<LifeEvent> | null>(null)
  const [open, setOpen] = useState<number | null>(null)
  const [importing, setImporting] = useState(false)
  const [exporting, setExporting] = useState(false)
  const params = useMemo(() => new URLSearchParams(Object.entries({ scope, q, source }).filter(([, v]) => v)), [scope, q, source])
  const line = usePoll<Index>(`${API}/timeline?${params}`, 0, onAuthLost)
  const meta = usePoll<Meta>(`${API}/meta`, 0, onAuthLost)
  const [version, setVersion] = useState(0)

  const entries = useMemo(() => {
    const data = line.data
    if (!data) return []
    return data.rows.map((row) => Object.fromEntries(data.fields.map((field, i) => [field, row[i]])) as unknown as Entry)
  }, [line.data])

  const stats = meta.data?.stats
  const summary = stats?.total
    ? `${whole(stats.total)} begivenheder, de første fra ${stats.first?.slice(0, 4)}.`
    : 'Din tidslinje. Kalenderen og andre sektioner skriver selv i den, og du kan selv tilføje.'

  const refresh = () => {
    void line.reload()
    void meta.reload()
    setVersion((v) => v + 1)
  }
  const saved = (id?: number) => {
    setEditing(null)
    refresh()
    if (id) setOpen(id)
  }

  return (
    <main className="page life-page">
      <SectionHead title="LogMyLife" text={summary}>
        <button onClick={() => setImporting(true)}>Importér fra Strava</button>
        <button onClick={() => setExporting(true)}>Eksportér</button>
        <button className="primary" onClick={() => setEditing({})}>Nyt indlæg</button>
      </SectionHead>

      {!!meta.data?.onThisDay.length && (
        <section className="on-this-day" aria-label="På denne dag">
          <h2>På denne dag</h2>
          <ul>
            {meta.data.onThisDay.map((e) => (
              <li key={e.id}><button onClick={() => setOpen(e.id)}><span className="meta">{yearOf(e)}</span> {e.title}</button></li>
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
          {Object.keys(stats?.bySource ?? {}).map((s) => <option key={s} value={s}>{sourceName(s)}</option>)}
        </select>
        <div className="segmented" role="group" aria-label="Visning">
          <button className={view === 'line' ? 'on' : ''} onClick={() => setView('line')}>Tidslinje</button>
          <button className={view === 'list' ? 'on' : ''} onClick={() => setView('list')}>Liste</button>
        </div>
      </div>

      {view === 'line' && line.data && (entries.length
        ? <Timeline entries={entries} today={line.data.today} onOpen={setOpen} />
        : <p className="empty">{q || source ? 'Intet matcher.' : scope === 'family' ? 'Familien har ikke delt noget endnu.' : 'Tidslinjen er tom. Skriv det første indlæg.'}</p>)}

      {view === 'list' && <ListView key={version} params={params} onOpen={setOpen} onAuthLost={onAuthLost} />}

      {open != null && (
        <EntryDialog id={open} onClose={() => setOpen(null)} onChanged={refresh}
          onEdit={(e) => { setOpen(null); setEditing(e) }} />
      )}
      {editing && (
        <EventForm event={editing} categories={meta.data?.categories ?? []} onClose={() => setEditing(null)} onSaved={saved} />
      )}
      {exporting && <ExportDialog q={q} source={source} usage={meta.data?.files} onClose={() => setExporting(false)} />}
      {importing && (
        <FileImport title="Importér fra Strava" url={`${API}/import/strava`} label="Zip-filen fra Strava" accept=".zip,.csv"
          onClose={() => setImporting(false)} onDone={refresh}>
          <ol className="steps">
            <li>Gå til Settings → My Account → Download your account på Strava, og bestil dine data.</li>
            <li>Vælg zip-filen fra mailen her, som den er.</li>
          </ol>
          <p className="note">Aktiviteter, billeder og ruter kommer med. Resten af filen, som følgere og logins, bliver ikke læst. Importerer du igen, kommer kun det nye med.</p>
        </FileImport>
      )}
    </main>
  )
}

function EventForm({ event, categories, onClose, onSaved }: {
  event: Partial<LifeEvent>; categories: string[]; onClose: () => void; onSaved: (id?: number) => void
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
      const saved = await api<LifeEvent>(event.id ? `${API}/events/${event.id}` : `${API}/events`, { method: event.id ? 'PUT' : 'POST', body: form })
      onSaved(saved.id)                 // it opens, ready for its pictures
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
          <p className="note">{event.title} kom fra {sourceName(event.source ?? '')} og beholder sin tekst. Du kan vælge kategori og deling.</p>
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
