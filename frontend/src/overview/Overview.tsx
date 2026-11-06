import { lazy, Suspense, useRef } from 'react'
import { ago, clock, dayName, kr, longDate, monthName, since, until, whole } from '../core/format'
import { hrefOf } from '../core/routes'
import { useNow, usePoll } from '../core/usePoll'
import type { Overview as Data, User } from '../core/types'
import { DayBand } from './DayBand'
import { CameraFrame } from '../sections/Cameras'
import { factWhen, MonologueList } from '../sections/LateNight'
import { finishesAt, PrinterLines } from '../sections/Printers'
import { StockWeek } from '../sections/StockWeek'

const LIVE_SECONDS = 30
const CAMERA_SECONDS = 30

function Block({ id, title, className, children }: {
  id: string; title: string; className?: string; children: React.ReactNode
}) {
  return (
    <section className={`block ${className ?? ''}`}>
      <h2><a href={hrefOf(id)}>{title}</a></h2>
      {children}
    </section>
  )
}

function digest(data: Data | null, now: Date): string {
  if (!data) return ''
  const b = data.blocks
  const parts: string[] = []
  const w = b.dklive?.weather
  if (w?.temp != null) parts.push(`${whole(w.temp)}° og ${w.text || 'ukendt vejr'}${b.dklive?.home ? ` i ${b.dklive.home}` : ''}.`)
  const next = b.calendar?.events.find((e) => !e.allDay && new Date(e.start) > now)
  if (next) parts.push(`Næste aftale er ${next.title}, ${dayName(next.day, now).toLowerCase()} kl. ${clock(next.start)}.`)
  const p = b.dklive?.power
  if (p) parts.push(`Strømmen koster ${kr(p.now)} kr og er billigst kl. ${clock(p.low.t)}.`)
  const f = b.f1?.next
  if (f && new Date(f.start).getTime() - now.getTime() < 48 * 3_600_000) {
    parts.push(`${f.name} til ${f.meeting.replace(' Grand Prix', ' GP')} ${dayName(f.start.slice(0, 10), now).toLowerCase()} kl. ${clock(f.start)}.`)
  }
  for (const printer of b.printers?.printers ?? []) {
    const done = finishesAt(printer, now)
    if (done) parts.push(`${printer.name} er færdig kl. ${clock(done)}.`)
  }
  return parts.join(' ')
}

// MapLibre is big, and only the overview uses it. A tab left open across an update asks
// for a file that is gone: the panels work without the map until it is reloaded.
const LiveMap = lazy(() => import('../map/LiveMap').catch(() => ({ default: () => null })))

const megawatt = (value: number | null | undefined) => (value != null ? `${whole(value)} MW` : '–')

export function Overview({ user, onAuthLost }: { user: User; onAuthLost: () => void }) {
  const now = useNow(1000)
  const free = useRef<HTMLDivElement>(null)
  const { data, error } = usePoll<Data>('/api/overview', LIVE_SECONDS, onAuthLost)
  const b = data?.blocks ?? {}
  const today = b.latenight?.exact ?? []
  const dlFacts = today.length ? today : b.latenight?.near ?? []

  return (
    <main className="overview">
      {b.dklive && <Suspense fallback={null}><LiveMap layers={b.dklive.layers} free={free} /></Suspense>}
      <div className="overlay">
        <header className="hero">
          <div className="hero-date">
            <h1>{longDate(now)}</h1>
            <p className="digest">{digest(data, now) || `Velkommen, ${user.name || user.username}.`}</p>
            {error && <p className="problem">{error}</p>}
          </div>
          <DayBand now={now} dk={b.dklive} calendar={b.calendar} f1={b.f1} />
          <p className="hero-clock">
            <time>{clock(now)}</time>
            <span>{String(now.getSeconds()).padStart(2, '0')}</span>
          </p>
        </header>

        <div className="middle">
          <div className="side">
            {b.latenight && (
              <Block id="latenight" title="SLQ DL" className="dl">
                {dlFacts.slice(0, 2).map((f) => (
                  <article key={f.id}>
                    <p className="dl-when">{factWhen(f, b.latenight?.date ?? '')}</p>
                    <p className="dl-title">{f.title}</p>
                    {f.body && <p className="dl-body">{f.body}</p>}
                  </article>
                ))}
                {!!b.latenight.monologues?.length && (
                  <div className="monologues">
                    <h3>Nyeste monologer</h3>
                    <MonologueList items={b.latenight.monologues} now={now} />
                  </div>
                )}
              </Block>
            )}

            {b.logmylife && (
              <Block id="logmylife" title="LogMyLife">
                {b.logmylife.onThisDay.length > 0 ? (
                  <ul className="life">
                    {b.logmylife.onThisDay.map((e) => (
                      <li key={e.id}>
                        <span className="meta">{now.getFullYear() - Number(e.day.slice(0, 4))} år siden</span>
                        <span>{e.title}</span>
                      </li>
                    ))}
                  </ul>
                ) : b.logmylife.latest.length > 0 ? (
                  <ul className="life">
                    {b.logmylife.latest.map((e) => (
                      <li key={e.id}><span className="meta">{e.day}</span><span>{e.title}</span></li>
                    ))}
                  </ul>
                ) : <p className="empty">Tidslinjen er tom. <a href={hrefOf('logmylife')}>Skriv det første indlæg</a>.</p>}
                {b.logmylife.total > 0 && <p className="note">{whole(b.logmylife.total)} begivenheder i alt</p>}
              </Block>
            )}
          </div>

          <div className="map-free" ref={free} />

          <div className="side">
            {b.dklive?.layers.includes('energy') && b.dklive.power && (
              <Block id="dklive" title={`Strøm ${b.dklive.power.area}`}>
                <dl className="mix">
                  <dt>Spotpris</dt><dd>{kr(b.dklive.power.now)} kr/kWh</dd>
                  <dt>Vind</dt><dd>{megawatt(b.dklive.power.wind)}</dd>
                  <dt>Sol</dt><dd>{megawatt(b.dklive.power.solar)}</dd>
                  <dt>Kraftværker</dt><dd>{megawatt(b.dklive.power.plants)}</dd>
                  <dt>CO₂</dt><dd>{b.dklive.power.co2 != null ? `${whole(b.dklive.power.co2)} g/kWh` : '–'}</dd>
                  <dt>{(b.dklive.power.exchange ?? 0) > 0 ? 'Import' : 'Eksport'}</dt><dd>{megawatt(Math.abs(b.dklive.power.exchange ?? 0))}</dd>
                </dl>
              </Block>
            )}

            {!!b.cameras?.cameras.length && (
              <Block id="cameras" title="Kameraer">
                <div className="cameras small">
                  {b.cameras.cameras.map((c) => (
                    <a key={c.id} className="cam" href={hrefOf('cameras')}>
                      <CameraFrame camera={c} seconds={CAMERA_SECONDS} />
                      <span>{c.name}</span>
                    </a>
                  ))}
                </div>
              </Block>
            )}

            {!!b.printers?.printers.length && (
              <Block id="printers" title="Printere">
                <PrinterLines printers={b.printers.printers} now={now} />
              </Block>
            )}

            {b.familylog && (
              <Block id="familylog" title="FamilyLog">
                {b.familylog.month ? (
                  <>
                    <p className="fl-spent">{whole(b.familylog.month.spent)} kr</p>
                    <p className="note">brugt i {monthName(now)}</p>
                  </>
                ) : (
                  <p className="empty">{b.familylog.connected ? 'Forbundet, kun læsning.' : 'Mangler læsenøgle.'}</p>
                )}
              </Block>
            )}

            {!!b.links?.pinned.length && (
              <Block id="links" title="Links">
                <ul className="pinned">
                  {b.links.pinned.map((l) => (
                    <li key={l.id}><a href={l.url} target="_blank" rel="noreferrer noopener">{l.title}</a></li>
                  ))}
                </ul>
              </Block>
            )}
          </div>
        </div>

        <div className="bottom">
          {b.news && (
            <Block id="news" title="Nyheder">
              {b.news.items.length ? (
                <ul className="headlines">
                  {b.news.items.map((n) => (
                    <li key={n.url}>
                      <a href={n.url} target="_blank" rel="noreferrer noopener">{n.title}</a>
                      <span className="meta">{n.source}{n.at ? `, ${ago(n.at, now.getTime())}` : ''}</span>
                    </li>
                  ))}
                </ul>
              ) : <p className="empty">Henter nyheder.</p>}
            </Block>
          )}

          {b.aktier && (
            <Block id="aktier" title="Aktier">
              {b.aktier.week ? <StockWeek week={b.aktier.week} /> : (
                <p className="empty">{b.aktier.mode === 'csv' ? 'Intet importeret endnu.' : 'Nordnet er ikke forbundet.'}</p>
              )}
              {b.aktier.importedAt && <p className="note">Beholdning importeret {since(b.aktier.importedAt, now.getTime())}</p>}
            </Block>
          )}

          {b.f1 && (
            <Block id="f1" title="Formel 1">
              {b.f1.next ? (
                <>
                  <p className="f1-meeting">{b.f1.meeting}</p>
                  <p className="f1-next">{b.f1.next.name} {until(b.f1.next.start, now.getTime())}</p>
                  <ul className="sessions">
                    {b.f1.weekend.map((s) => (
                      <li key={s.start} className={s.race ? 'race' : ''}>
                        <span>{s.name}</span>
                        <span className="meta">{dayName(s.start.slice(0, 10), now)} {clock(s.start)}</span>
                      </li>
                    ))}
                  </ul>
                </>
              ) : <p className="empty">Sæsonplanen er ikke hentet endnu.</p>}
            </Block>
          )}
        </div>
      </div>
    </main>
  )
}
