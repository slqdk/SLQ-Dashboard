import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api'
import { one, whole } from './format'
import type { NetStatus } from './types'

const SAMPLES = 5

type Grade = 'good' | 'slow' | 'bad' | 'none'

function grade(ms: number | null): Grade {
  if (ms == null) return 'none'
  if (ms < 80) return 'good'
  if (ms < 250) return 'slow'
  return 'bad'
}

const GRADE_TEXT: Record<Grade, string> = { good: 'God', slow: 'Langsom', bad: 'Dårlig', none: 'Intet svar' }

async function roundTrip(): Promise<number> {
  const start = performance.now()
  await fetch('/api/ping', { cache: 'no-store', credentials: 'same-origin' })
  return performance.now() - start
}

function Dot({ g }: { g: Grade }) {
  return <span className={`dot dot-${g}`} aria-hidden="true" />
}

function pageLoadMs(): number | null {
  const entry = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined
  return entry && entry.loadEventEnd > 0 ? entry.loadEventEnd : null
}

/** The ping indicator: from where the person sits to the server, and from the
 *  server onwards. Click for the details. */
export function Ping() {
  const [here, setHere] = useState<number | null>(null)
  const [samples, setSamples] = useState<number[]>([])
  const [net, setNet] = useState<NetStatus | null>(null)
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)

  const measure = useCallback(async () => {
    try {
      await roundTrip() // the first one also pays for the connection
      const ms = await roundTrip()
      setHere(ms)
      setSamples((old) => [...old.slice(1 - SAMPLES), ms])
    } catch {
      setHere(null)
    }
    try {
      setNet(await api<NetStatus>('/api/netstatus'))
    } catch {
      setNet(null)
    }
  }, [])

  useEffect(() => {
    void measure()
    const timer = setInterval(() => {
      if (!document.hidden) void measure()
    }, 15_000)
    return () => clearInterval(timer)
  }, [measure])

  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent) => {
      if (!box.current?.contains(e.target as Node)) setOpen(false)
    }
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', esc)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', esc)
    }
  }, [open])

  const mean = samples.length ? samples.reduce((a, b) => a + b, 0) / samples.length : null
  const server = net?.internetMs ?? null
  const load = net?.load
  const page = pageLoadMs()

  return (
    <div className="ping" ref={box}>
      <button className="ping-button" aria-expanded={open} onClick={() => setOpen(!open)}
        title="Svartid herfra til serveren og fra serveren og ud">
        <span className="ping-item"><Dot g={grade(here)} />Her {here == null ? 'mangler' : `${whole(here)} ms`}</span>
        <span className="ping-item"><Dot g={grade(server)} />Server {server == null ? 'mangler' : `${whole(server)} ms`}</span>
      </button>
      {open && (
        <div className="ping-panel">
          <h3>Herfra til serveren</h3>
          <dl>
            <dt>Svartid nu</dt>
            <dd>{here == null ? 'Intet svar' : `${one(here)} ms, ${GRADE_TEXT[grade(here)].toLowerCase()}`}</dd>
            <dt>Gennemsnit af sidste {samples.length}</dt>
            <dd>{mean == null ? 'Mangler' : `${one(mean)} ms`}</dd>
            <dt>Siden blev indlæst på</dt>
            <dd>{page == null ? 'Mangler' : `${whole(page)} ms`}</dd>
          </dl>
          <h3>Fra serveren og ud</h3>
          <dl>
            {(net?.targets ?? []).map((t) => (
              <div key={t.name} className="ping-row">
                <dt><Dot g={grade(t.ms)} />{t.name}</dt>
                <dd>{t.ms == null ? 'Intet svar' : `${one(t.ms)} ms`}</dd>
              </div>
            ))}
            {!net?.targets.length && <><dt>Første måling</dt><dd>Inden for 30 sekunder</dd></>}
          </dl>
          <h3>Belastning på serveren</h3>
          <dl>
            <dt>1 / 5 / 15 min</dt>
            <dd>{load?.load1 == null ? 'Mangler' : `${one(load.load1)} / ${one(load.load5 ?? 0)} / ${one(load.load15 ?? 0)}`}</dd>
            <dt>Kerner</dt>
            <dd>{load?.cpus ?? 'Mangler'}</dd>
          </dl>
        </div>
      )}
    </div>
  )
}
