import { useEffect, useState } from 'react'
import { api } from '../core/api'
import { ago, clock, cap, dayName, monthName, shortDay, whole } from '../core/format'
import { hrefOf, readRoute } from '../core/routes'
import { useNow, usePoll } from '../core/usePoll'
import type { F1Session, FamilyLogState, LifeEvent, NewsFeedState, NewsItem, User } from '../core/types'
import { SectionHead } from './common'

// ---- Kalender ---------------------------------------------------------------

interface CalendarState {
  configured: boolean
  connected: boolean
  email: string
  status: string
  lastSyncAt: string | null
  lastError: string
  calendars: { id: string; summary: string; color: string; selected: boolean }[]
  events: LifeEvent[]
}

const CONNECT_RESULT: Record<string, string> = {
  afvist: 'Forbindelsen blev afvist. Prøv igen.',
  fejl: 'Google svarede ikke som ventet. Prøv igen.',
}

export function Calendar({ onAuthLost }: { onAuthLost: () => void }) {
  const now = useNow(60_000)
  const { data, reload, error } = usePoll<CalendarState>('/api/s/calendar/state', 60, onAuthLost)
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState(() => CONNECT_RESULT[readRoute().query.get('google') ?? ''] ?? '')

  // The first sync runs on the server just after Google sends the browser back.
  useEffect(() => {
    if (readRoute().query.get('google') !== 'ok') return
    const timers = [1500, 4000, 9000].map((ms) => setTimeout(() => void reload(), ms))
    return () => timers.forEach(clearTimeout)
  }, [reload])

  const connect = async () => {
    try {
      const { url } = await api<{ url: string }>('/api/s/calendar/connect', { method: 'POST' })
      window.location.href = url
    } catch (exc) {
      setProblem(exc instanceof Error ? exc.message : 'Kunne ikke forbinde.')
    }
  }
  const act = async (path: string, body?: unknown) => {
    setBusy(true)
    try {
      await api(`/api/s/calendar/${path}`, { method: body ? 'PUT' : 'POST', body })
      await reload()
    } catch (exc) {
      setProblem(exc instanceof Error ? exc.message : 'Det lykkedes ikke.')
    }
    setBusy(false)
  }

  const days = new Map<string, LifeEvent[]>()
  for (const e of data?.events ?? []) days.set(e.day, [...(days.get(e.day) ?? []), e])

  return (
    <main className="page">
      <SectionHead title="Kalender" text="Din Google-kalender, kun læsning. Alt gemmes også i LogMyLife.">
        {data?.connected && (
          <>
            <button disabled={busy} onClick={() => void act('sync')}>Hent nu</button>
            <button disabled={busy} onClick={() => void act('disconnect')}>Afbryd</button>
          </>
        )}
      </SectionHead>
      {(problem || error) && <p className="problem">{problem || error}</p>}
      {data && !data.connected && (
        data.configured ? (
          <div className="connect">
            <p>Forbind din egen Google-konto. Dashboardet kan kun læse, aldrig skrive.</p>
            <button className="primary" onClick={() => void connect()}>Forbind Google</button>
          </div>
        ) : <p className="empty">Google er ikke sat op endnu. Det gøres under Admin → Opsætning.</p>
      )}
      {data?.connected && (
        <div className="columns wide-left">
          <div>
            {data.status === 'reconnect' && (
              <p className="problem">Google vil have kontoen forbundet igen. <button className="link" onClick={() => void connect()}>Forbind igen</button></p>
            )}
            {[...days].map(([day, list]) => (
              <section key={day} className="agenda-day big">
                <h2>{dayName(day, now)}</h2>
                <ul>
                  {list.map((e) => (
                    <li key={e.id}>
                      <span className="agenda-time">{e.allDay ? 'Hele dagen' : `${clock(e.start)}${e.end ? `–${clock(e.end)}` : ''}`}</span>
                      <span>{e.title}{e.location ? <span className="meta"> {e.location}</span> : null}</span>
                    </li>
                  ))}
                </ul>
              </section>
            ))}
            {!days.size && <p className="empty">Intet den næste måned.</p>}
          </div>
          <aside>
            <h2>Kalendere</h2>
            <p className="meta">{data.email}{data.lastSyncAt ? `, hentet for ${ago(data.lastSyncAt, now.getTime())} siden` : ''}</p>
            {data.lastError && <p className="problem">{data.lastError}</p>}
            <ul className="check-list">
              {data.calendars.map((c) => (
                <li key={c.id}>
                  <label className="check">
                    <input type="checkbox" checked={c.selected}
                      onChange={(e) => void act('selected', { calendarId: c.id, selected: e.target.checked })} />
                    {c.summary}
                  </label>
                </li>
              ))}
            </ul>
          </aside>
        </div>
      )}
    </main>
  )
}

// ---- Nyheder ----------------------------------------------------------------

export function News({ onAuthLost }: { onAuthLost: () => void }) {
  const now = useNow(60_000)
  const { data, error } = usePoll<{ items: NewsItem[]; feeds: NewsFeedState[] }>('/api/s/news/items', 120, onAuthLost)
  const [source, setSource] = useState('')
  const items = (data?.items ?? []).filter((n) => !source || n.source === source)
  const dropped = (data?.feeds ?? []).reduce((sum, f) => sum + f.dropped, 0)
  return (
    <main className="page narrow">
      <SectionHead title="Nyheder" text="Overskrifter og korte tekster, hentet af serveren. Ingen reklamer.">
        <select aria-label="Kilde" value={source} onChange={(e) => setSource(e.target.value)}>
          <option value="">Alle kilder</option>
          {data?.feeds.map((f) => <option key={f.name}>{f.name}</option>)}
        </select>
      </SectionHead>
      {error && <p className="problem">{error}</p>}
      {data?.feeds.filter((f) => !f.ok).map((f) => <p key={f.name} className="problem">{f.name} svarer ikke: {f.error}</p>)}
      <ul className="news">
        {items.map((n) => (
          <li key={n.url}>
            <a href={n.url} target="_blank" rel="noreferrer noopener">{n.title}</a>
            {n.summary && <p>{n.summary}</p>}
            <p className="meta">{n.source}{n.at ? `, ${ago(n.at, now.getTime())} siden` : ''}</p>
          </li>
        ))}
      </ul>
      {!items.length && !error && <p className="empty">Ingen nyheder endnu. Første hentning sker lige efter start.</p>}
      {dropped > 0 && <p className="note">{dropped} betalte indlæg er sorteret fra.</p>}
    </main>
  )
}

// ---- Formel 1 ---------------------------------------------------------------

interface Weekend {
  season: number
  round: number
  meeting: string
  country: string
  circuit: string
  sessions: F1Session[]
  over: boolean
}

export function F1({ onAuthLost }: { onAuthLost: () => void }) {
  const { data, error } = usePoll<{ weekends: Weekend[]; status: { ok: boolean; text: string } }>('/api/s/f1/season', 3600, onAuthLost)
  const [past, setPast] = useState(false)
  const weekends = data?.weekends ?? []
  const coming = weekends.filter((w) => !w.over)
  const shown = past ? weekends : coming
  return (
    <main className="page">
      <SectionHead title="Formel 1" text={weekends[0] ? `Sæson ${weekends[0].season}. Alle tider er dansk tid.` : 'Sessionerne i sæsonen.'}>
        {weekends.length > coming.length && (
          <button onClick={() => setPast(!past)}>{past ? 'Skjul overståede' : 'Vis overståede'}</button>
        )}
      </SectionHead>
      {error && <p className="problem">{error}</p>}
      {data && !data.status.ok && <p className="problem">{data.status.text}</p>}
      <div className="weekends">
        {shown.map((w, i) => (
          <section key={w.round} className={`weekend ${!w.over && i === (past ? weekends.length - coming.length : 0) ? 'next' : ''} ${w.over ? 'over' : ''}`}>
            <h2>{w.meeting.replace(' Grand Prix', ' GP')}</h2>
            <p className="meta">Afdeling {w.round}, {w.circuit}</p>
            <ul className="sessions">
              {w.sessions.map((s) => (
                <li key={s.start} className={s.race ? 'race' : ''}>
                  <span>{s.name}</span>
                  <span className="meta">{cap(shortDay(s.start))} {clock(s.start)}</span>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
      {data && !weekends.length && <p className="empty">Sæsonplanen er ikke hentet endnu.</p>}
    </main>
  )
}

// ---- FamilyLog --------------------------------------------------------------

interface FamilySearch {
  q: string
  transactions: { total: number; sum: number; rows: { date: string; merchant: string; text: string; amount: number; categoryName: string }[] } | null
  places: { id: number; name: string; address: string }[]
}

export function FamilyLog({ user, onAuthLost }: { user: User; onAuthLost: () => void }) {
  const { data, reload } = usePoll<FamilyLogState>('/api/s/familylog/state', 0, onAuthLost)
  const [q, setQ] = useState('')
  const [found, setFound] = useState<FamilySearch | null>(null)
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState('')

  const search = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      setFound(await api<FamilySearch>(`/api/s/familylog/search?q=${encodeURIComponent(q)}`))
      setProblem('')
    } catch (exc) {
      setProblem(exc instanceof Error ? exc.message : 'Søgningen lykkedes ikke.')
    }
    setBusy(false)
  }
  const sync = async () => {
    setBusy(true)
    try {
      await api('/api/s/familylog/sync', { method: 'POST' })
      await reload()
    } catch (exc) {
      setProblem(exc instanceof Error ? exc.message : 'Det lykkedes ikke.')
    }
    setBusy(false)
  }

  const month = data?.month
  return (
    <main className="page narrow">
      <SectionHead title="FamilyLog" text="Dine egne data fra FamilyLog. Dashboardet kan søge og læse, aldrig skrive.">
        {data?.connected && <button disabled={busy} onClick={() => void sync()}>Hent nu</button>}
      </SectionHead>
      {data && !data.address && <p className="empty">Adressen til FamilyLog mangler.{user.role === 'admin' ? ' Den sættes under Admin → Opsætning.' : ''}</p>}
      {data?.address && !data.connected && <p className="empty">Din læsenøgle mangler.{user.role === 'admin' ? ' Lav den i FamilyLog under Settings → Accounts, og sæt den under Admin → Brugere.' : ' Bed administratoren om at sætte den.'}</p>}
      {data?.error && <p className="problem">{data.error}</p>}
      {problem && <p className="problem">{problem}</p>}
      {month && (
        <section className="fl-month">
          <p className="fl-spent">{whole(month.spent)} kr</p>
          <p className="meta">brugt i {monthName(new Date())}, {whole(month.count)} posteringer</p>
          <ul>
            {month.top.map((c) => <li key={c.name}><span>{c.name}</span><span className="meta">{whole(c.spent)} kr</span></li>)}
          </ul>
        </section>
      )}
      {data?.connected && (
        <form className="filters" onSubmit={search}>
          <input type="search" placeholder="Søg i Økonomi og FamilyMap" aria-label="Søg i FamilyLog" value={q} onChange={(e) => setQ(e.target.value)} />
          <button disabled={busy || !q.trim()} type="submit">Søg</button>
        </form>
      )}
      {found && (
        <>
          {found.transactions && (
            <section>
              <h2>Økonomi</h2>
              <p className="meta">{whole(found.transactions.total)} posteringer, {whole(found.transactions.sum)} kr i alt</p>
              <ul className="fl-rows">
                {found.transactions.rows.map((r, i) => (
                  <li key={i}><span className="meta">{r.date}</span><span>{r.merchant || r.text}</span><span>{whole(r.amount)} kr</span></li>
                ))}
              </ul>
            </section>
          )}
          <section>
            <h2>FamilyMap</h2>
            {found.places.length ? (
              <ul className="fl-places">
                {found.places.map((p) => <li key={p.id}>{p.name}{p.address ? <span className="meta"> {p.address}</span> : null}</li>)}
              </ul>
            ) : <p className="empty">Ingen steder matcher.</p>}
          </section>
        </>
      )}
    </main>
  )
}

export function NoAccess() {
  useEffect(() => {
    window.location.hash = hrefOf('')
  }, [])
  return null
}
