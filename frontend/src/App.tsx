import { useCallback, useEffect, useState } from 'react'
import { Admin } from './admin/Admin'
import { api } from './core/api'
import { clock, longDate } from './core/format'
import { Ping } from './core/Ping'
import { readRoute, SECTIONS } from './core/routes'
import type { User } from './core/types'
import { useNow } from './core/usePoll'
import { Overview } from './overview/Overview'
import { Aktier } from './sections/Aktier'
import { Cameras } from './sections/Cameras'
import { DkLive } from './sections/DkLive'
import { LateNight } from './sections/LateNight'
import { Links } from './sections/Links'
import { LogMyLife } from './sections/LogMyLife'
import { Printers } from './sections/Printers'
import { Calendar, F1, FamilyLog, News, NoAccess } from './sections/Simple'

function useRoute() {
  const [path, setPath] = useState(() => readRoute().path)
  useEffect(() => {
    const onChange = () => {
      setPath(readRoute().path)
      window.scrollTo(0, 0)
    }
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return path
}

function Login({ needsSetup, onDone }: { needsSetup: boolean; onDone: (u: User) => void }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [problem, setProblem] = useState('')
  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const r = await api<{ user: User }>(needsSetup ? '/api/auth/setup' : '/api/auth/login',
        { method: 'POST', body: { username, password } })
      onDone(r.user)
    } catch (exc) {
      setProblem(exc instanceof Error ? exc.message : 'Det lykkedes ikke.')
    }
  }
  return (
    <main className="login">
      <form onSubmit={submit}>
        <h1>SLQ Dashboard</h1>
        {needsSetup && <p>Første gang: opret administratoren.</p>}
        <label>Brugernavn<input required autoFocus autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} /></label>
        <label>Adgangskode<input type="password" required autoComplete={needsSetup ? 'new-password' : 'current-password'} value={password} onChange={(e) => setPassword(e.target.value)} /></label>
        {problem && <p className="problem">{problem}</p>}
        <button type="submit" className="primary">{needsSetup ? 'Opret administrator' : 'Log ind'}</button>
      </form>
    </main>
  )
}

function SmallClock() {
  const now = useNow(1000)
  return <p className="nav-clock"><span>{longDate(now)}</span> <time>{clock(now)}</time></p>
}

export function App() {
  const [user, setUser] = useState<User | null>(null)
  const [needsSetup, setNeedsSetup] = useState(false)
  const [ready, setReady] = useState(false)
  const path = useRoute()

  const lost = useCallback(() => setUser(null), [])

  useEffect(() => {
    api<{ needsSetup: boolean; user: User | null }>('/api/auth/status').then((s) => {
      setNeedsSetup(s.needsSetup)
      setUser(s.user)
      setReady(true)
    }, () => setReady(true))
  }, [])

  if (!ready) return null
  if (!user) return <Login needsSetup={needsSetup} onDone={(u) => { setNeedsSetup(false); setUser(u) }} />

  const logout = async () => {
    await api('/api/auth/logout', { method: 'POST' })
    setUser(null)
  }

  const section = SECTIONS.find((s) => s.path === path)
  const allowed = !section || user.sections.includes(section.id)

  return (
    <div className="shell">
      <header className="nav">
        <a className="mark" href="#/" aria-label="Overblik">SLQ</a>
        <nav aria-label="Sektioner">
          <a href="#/" aria-current={path === '' ? 'page' : undefined}>Overblik</a>
          {SECTIONS.filter((s) => user.sections.includes(s.id)).map((s) => (
            <a key={s.id} href={`#/${s.path}`} aria-current={path === s.path ? 'page' : undefined}>{s.title}</a>
          ))}
          {user.role === 'admin' && <a href="#/admin" aria-current={path === 'admin' ? 'page' : undefined}>Admin</a>}
        </nav>
        <div className="nav-right">
          {path !== '' && <SmallClock />}
          <Ping />
          <button className="nav-user" onClick={() => void logout()} title="Log ud">Log ud {user.name || user.username}</button>
        </div>
      </header>

      {!allowed && <NoAccess />}
      {path === '' && <Overview user={user} onAuthLost={lost} />}
      {allowed && section?.id === 'calendar' && <Calendar onAuthLost={lost} />}
      {allowed && section?.id === 'dklive' && <DkLive onAuthLost={lost} />}
      {allowed && section?.id === 'news' && <News onAuthLost={lost} />}
      {allowed && section?.id === 'logmylife' && <LogMyLife onAuthLost={lost} />}
      {allowed && section?.id === 'aktier' && <Aktier onAuthLost={lost} />}
      {allowed && section?.id === 'familylog' && <FamilyLog user={user} onAuthLost={lost} />}
      {allowed && section?.id === 'f1' && <F1 onAuthLost={lost} />}
      {allowed && section?.id === 'latenight' && <LateNight user={user} onAuthLost={lost} />}
      {allowed && section?.id === 'printers' && <Printers onAuthLost={lost} />}
      {allowed && section?.id === 'cameras' && <Cameras onAuthLost={lost} />}
      {allowed && section?.id === 'links' && <Links onAuthLost={lost} />}
      {path === 'admin' && user.role === 'admin' && <Admin me={user} onAuthLost={lost} />}
    </div>
  )
}
