import { useMemo, useState } from 'react'
import { fullDate, localDate } from '../core/format'
import { usePoll } from '../core/usePoll'
import type { Fact, User } from '../core/types'
import { api } from '../core/api'
import { Dialog, SectionHead } from './common'

interface Today {
  date: string
  exact: Fact[]
  near: Fact[]
}

interface Facts {
  facts: Fact[]
  total: number
  stories: Record<string, string>
  kinds: string[]
  hosts: string[]
}

const KIND_TEXT: Record<string, string> = { show: 'Show', 'gæst': 'Gæst', historie: 'Historie' }
const DECADES = ['1960', '1970', '1980', '1990', '2000', '2010', '2020']

/** "I dag for 17 år siden", or the date when it is another day this week. */
export function factWhen(f: Fact, today: string): string {
  const years = f.yearsAgo ?? Number(today.slice(0, 4)) - Number(f.date.slice(0, 4))
  if (f.date.slice(5) === today.slice(5)) return `I dag for ${years} år siden`
  return `${fullDate(localDate(f.date))}, for ${years} år siden`
}

function FactRow({ f, onEdit }: { f: Fact; onEdit?: (f: Fact) => void }) {
  return (
    <li className="fact">
      <time>{fullDate(localDate(f.date))}</time>
      <div>
        <p className="fact-title">{f.title}</p>
        {f.body && <p>{f.body}</p>}
        <p className="meta">
          {KIND_TEXT[f.kind] ?? f.kind}{f.hosts.length ? `, ${f.hosts.join(', ')}` : ''}
          {f.sourceUrl && <>, <a href={f.sourceUrl} target="_blank" rel="noreferrer noopener">kilde</a></>}
          {onEdit && <>, <button className="link" onClick={() => onEdit(f)}>ret</button></>}
        </p>
      </div>
    </li>
  )
}

const BLANK = { date: '', title: '', body: '', kind: 'historie', hosts: '', story: '', sourceUrl: '' }

function FactForm({ fact, stories, onClose, onSaved }: {
  fact: Fact | null; stories: Record<string, string>; onClose: () => void; onSaved: () => void
}) {
  const [form, setForm] = useState(fact ? { ...fact, hosts: fact.hosts.join(', ') } : BLANK)
  const [problem, setProblem] = useState('')
  const set = (key: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setForm({ ...form, [key]: e.target.value })
  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    const body = { ...form, hosts: form.hosts.split(',') }
    try {
      await api(fact ? `/api/s/latenight/facts/${fact.id}` : '/api/s/latenight/facts',
        { method: fact ? 'PUT' : 'POST', body })
      onSaved()
    } catch (exc) {
      setProblem(exc instanceof Error ? exc.message : 'Kunne ikke gemme.')
    }
  }
  const remove = async () => {
    if (!fact) return
    await api(`/api/s/latenight/facts/${fact.id}`, { method: 'DELETE' })
    onSaved()
  }
  return (
    <Dialog title={fact ? 'Ret fakta' : 'Tilføj fakta'} onClose={onClose}>
      <form onSubmit={save}>
        <label>Dato<input type="date" required value={form.date} onChange={set('date')} /></label>
        <label>Hvad skete der<input required value={form.title} onChange={set('title')} /></label>
        <label>Mere om det<textarea rows={3} value={form.body} onChange={set('body')} /></label>
        <label>Værter, adskilt af komma<input value={form.hosts} onChange={set('hosts')} /></label>
        <label>Type
          <select value={form.kind} onChange={set('kind')}>
            {Object.entries(KIND_TEXT).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
        <label>Historie
          <select value={form.story} onChange={set('story')}>
            <option value="">Ingen</option>
            {Object.entries(stories).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
        <label>Kilde<input type="url" value={form.sourceUrl} onChange={set('sourceUrl')} /></label>
        {problem && <p className="problem">{problem}</p>}
        <div className="dialog-actions">
          {fact && <button type="button" className="danger" onClick={remove}>Slet</button>}
          <button type="button" onClick={onClose}>Annullér</button>
          <button type="submit" className="primary">Gem</button>
        </div>
      </form>
    </Dialog>
  )
}

export function LateNight({ user, onAuthLost }: { user: User; onAuthLost: () => void }) {
  const [q, setQ] = useState('')
  const [host, setHost] = useState('')
  const [story, setStory] = useState('')
  const [decade, setDecade] = useState('')
  const [editing, setEditing] = useState<Fact | 'new' | null>(null)

  const query = useMemo(() => new URLSearchParams(
    Object.entries({ q, host, story, decade }).filter(([, v]) => v)), [q, host, story, decade])
  const today = usePoll<Today>('/api/s/latenight/today', 0, onAuthLost)
  const list = usePoll<Facts>(`/api/s/latenight/facts?${query}`, 0, onAuthLost)
  const facts = list.data
  const admin = user.role === 'admin'
  const lead = today.data?.exact.length ? today.data.exact : today.data?.near ?? []

  return (
    <main className="page">
      <SectionHead title="SLQ DL" text="Amerikansk late night-historie, dato for dato.">
        {admin && <button className="primary" onClick={() => setEditing('new')}>Tilføj fakta</button>}
      </SectionHead>

      <section className="dl-lead">
        {lead.map((f) => (
          <article key={f.id}>
            <p className="dl-when">{factWhen(f, today.data?.date ?? '')}</p>
            <p className="dl-title">{f.title}</p>
            {f.body && <p className="dl-body">{f.body}</p>}
          </article>
        ))}
      </section>

      <div className="filters">
        <input type="search" placeholder="Søg" aria-label="Søg i fakta" value={q} onChange={(e) => setQ(e.target.value)} />
        <select aria-label="Vært" value={host} onChange={(e) => setHost(e.target.value)}>
          <option value="">Alle værter</option>
          {facts?.hosts.map((h) => <option key={h}>{h}</option>)}
        </select>
        <select aria-label="Historie" value={story} onChange={(e) => setStory(e.target.value)}>
          <option value="">Alle historier</option>
          {Object.entries(facts?.stories ?? {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select aria-label="Årti" value={decade} onChange={(e) => setDecade(e.target.value)}>
          <option value="">Alle årtier</option>
          {DECADES.map((d) => <option key={d} value={d}>{d}'erne</option>)}
        </select>
        <span className="meta">{facts ? `${facts.facts.length} af ${facts.total}` : ''}</span>
      </div>

      <ol className="facts">
        {facts?.facts.map((f) => <FactRow key={f.id} f={f} onEdit={admin ? setEditing : undefined} />)}
      </ol>
      {facts && !facts.facts.length && <p className="empty">Ingen fakta matcher.</p>}

      {editing && (
        <FactForm fact={editing === 'new' ? null : editing} stories={facts?.stories ?? {}}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); void list.reload() }} />
      )}
    </main>
  )
}
