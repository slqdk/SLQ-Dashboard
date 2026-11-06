import { clock, duration, whole } from '../core/format'
import { useNow, usePoll } from '../core/usePoll'
import type { PrinterState } from '../core/types'
import { SectionHead } from './common'

const REFRESH_SECONDS = 10

export function finishesAt(p: PrinterState, now: Date): Date | null {
  if (!p.active || p.remainingMin == null) return null
  return new Date(now.getTime() + p.remainingMin * 60_000)
}

function dotOf(p: PrinterState): string {
  if (!p.online) return 'none'
  if (p.error || p.state === 'FAILED') return 'bad'
  return p.state === 'PAUSE' ? 'slow' : 'good'
}

function State({ p }: { p: PrinterState }) {
  return (
    <span className="printer-state">
      <span className={`dot dot-${dotOf(p)}`} aria-hidden="true" />{p.problem || p.stateText}
    </span>
  )
}

function Progress({ p }: { p: PrinterState }) {
  const percent = p.percent ?? 0
  return (
    <div className="bar" role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100} aria-label={`${p.name}: fremskridt`}>
      <span style={{ width: `${percent}%` }} />
    </div>
  )
}

/** One or two lines for the overview. */
export function PrinterLines({ printers, now }: { printers: PrinterState[]; now: Date }) {
  return (
    <ul className="printer-lines">
      {printers.map((p) => {
        const done = finishesAt(p, now)
        return (
          <li key={p.id}>
            <p className="printer-head"><span className="printer-name">{p.name}</span><State p={p} /></p>
            {p.active && (
              <>
                <Progress p={p} />
                <p className="meta">{p.percent} %{done ? `, færdig kl. ${clock(done)}` : ''}</p>
              </>
            )}
          </li>
        )
      })}
    </ul>
  )
}

const degrees = (value: number | null, target: number | null) =>
  value == null ? 'Ukendt' : `${whole(value)}°${target ? ` af ${whole(target)}°` : ''}`

function Printer({ p, now }: { p: PrinterState; now: Date }) {
  const done = finishesAt(p, now)
  return (
    <article className="printer">
      <header className="printer-head">
        <h2>{p.name}</h2>
        <State p={p} />
      </header>
      {p.online && p.file && <p className="printer-file">{p.file}</p>}
      {p.error && <p className="problem">Printeren melder fejl {p.error}.</p>}
      {p.active && (
        <>
          <p className="printer-percent">{p.percent} %</p>
          <Progress p={p} />
        </>
      )}
      {p.online && (
        <dl>
          {p.active && p.remainingMin != null && <><dt>Tilbage</dt><dd>{duration(p.remainingMin)}{done ? `, færdig kl. ${clock(done)}` : ''}</dd></>}
          {p.active && p.layer != null && <><dt>Lag</dt><dd>{p.layer} af {p.totalLayers ?? '?'}</dd></>}
          <dt>Dyse</dt><dd>{degrees(p.nozzle, p.nozzleTarget)}</dd>
          <dt>Plade</dt><dd>{degrees(p.bed, p.bedTarget)}</dd>
        </dl>
      )}
    </article>
  )
}

export function Printers({ onAuthLost }: { onAuthLost: () => void }) {
  const { data, error } = usePoll<{ printers: PrinterState[] }>('/api/s/printers/state', REFRESH_SECONDS, onAuthLost)
  const now = useNow(30_000)
  const printers = data?.printers ?? []
  return (
    <main className="page">
      <SectionHead title="Printere" text="Status direkte fra printerne på jeres net. Dashboardet kan kun læse." />
      {error && <p className="problem">{error}</p>}
      <div className="printers">
        {printers.map((p) => <Printer key={p.id} p={p} now={now} />)}
      </div>
      {data && !printers.length && <p className="empty">Ingen printere sat op endnu. Det gøres under Admin → Opsætning.</p>}
    </main>
  )
}
