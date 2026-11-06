import { ago, clock, dayKey, dayName, kr, one, whole } from '../core/format'
import { useNow, usePoll } from '../core/usePoll'
import type { DkLive as Data, LiveUpdate, PricePoint } from '../core/types'
import { SectionHead } from './common'

const KIND = { '112': '112', politi: 'Politi', trafik: 'Trafik' } as const
const NEAR = 60

export function Updates({ items, now, limit, plain, empty }: {
  items: LiveUpdate[]; now: Date; limit?: number; plain?: boolean; empty?: string
}) {
  const shown = limit ? items.slice(0, limit) : items
  if (!shown.length) return <p className="empty">{empty ?? 'Ingen opdateringer lige nu.'}</p>
  return (
    <ul className={plain ? 'updates plain' : 'updates'}>
      {shown.map((u) => (
        <li key={u.id} className={u.km != null && u.km <= NEAR ? 'near' : ''}>
          {!plain && <span className={`kind kind-${u.kind}`}>{KIND[u.kind]}</span>}
          <span className="updates-title">{u.title}{u.detail ? `, ${u.detail}` : ''}</span>
          <span className="meta">
            {u.km != null ? `${whole(u.km)} km, ` : ''}{ago(u.at, now.getTime())}
          </span>
        </li>
      ))}
    </ul>
  )
}

/** The quarter-hour prices as hourly means, from this hour on. */
function hourly(series: PricePoint[], now: Date): PricePoint[] {
  const start = new Date(now).setMinutes(0, 0, 0)
  const hours = new Map<number, number[]>()
  for (const p of series) {
    const hour = new Date(p.t).setMinutes(0, 0, 0)
    if (hour >= start) hours.set(hour, [...(hours.get(hour) ?? []), p.dkk])
  }
  return [...hours].slice(0, 24).map(([hour, list]) => ({
    t: new Date(hour).toISOString(),
    dkk: list.reduce((a, b) => a + b, 0) / list.length,
  }))
}

export function DkLive({ onAuthLost }: { onAuthLost: () => void }) {
  const now = useNow(15_000)
  const { data, error } = usePoll<Data>('/api/s/dklive/state', 30, onAuthLost)
  if (!data) return <main className="page"><SectionHead title="DK live" />{error && <p className="problem">{error}</p>}</main>
  const p = data.power
  const w = data.weather
  const nextPrices = hourly(p?.series ?? [], now)
  const peak = Math.max(0.01, ...nextPrices.map((x) => x.dkk))
  return (
    <main className="page">
      <SectionHead title="DK live" text="Elpriser, trafik og opdateringer. Kortet ligger på overblikket." />
      {error && <p className="problem">{error}</p>}
      {data.error && <p className="problem">Ikke alle kilder svarer: {data.error}</p>}
      <div className="columns">
        <div>
          <h2>Opdateringer</h2>
          <Updates items={data.feed ?? []} now={now} />
        </div>
        <div>
          {p && (
            <>
              <h2>Elpris i timerne frem</h2>
              <p className="lead">Lige nu {kr(p.now)} kr/kWh. Spotpris {p.area} uden afgifter.</p>
              <table className="prices">
                <thead><tr><th scope="col">Time</th><th scope="col">kr/kWh</th><th scope="col"><span className="sr-only">Niveau</span></th></tr></thead>
                <tbody>
                  {nextPrices.map((x) => (
                    <tr key={x.t}>
                      <td>{new Date(x.t).getDate() === now.getDate() ? '' : `${dayName(dayKey(new Date(x.t)), now)} `}{clock(x.t)}</td>
                      <td>{kr(x.dkk)}</td>
                      <td><span className="price-bar" style={{ width: `${Math.max(2, (x.dkk / peak) * 100)}%` }} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
          {w && (
            <>
              <h2>Vejr{w.place ? ` i ${w.place}` : ''}</h2>
              <p className="lead">{w.temp != null ? `${one(w.temp)}°` : ''} og {w.text}. Vind {w.wind != null ? `${one(w.wind)} m/s` : 'ukendt'}.</p>
              <ul className="days">
                {w.daily.map((d) => (
                  <li key={d.day}>
                    <span>{dayName(d.day, now)}</span>
                    <span>{d.text}</span>
                    <span className="meta">{whole(d.min)}° til {whole(d.max)}°, {one(d.rain)} mm</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      </div>
    </main>
  )
}
