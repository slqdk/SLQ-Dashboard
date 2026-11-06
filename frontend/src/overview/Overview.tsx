import { ago, clock, dayName, kr, longDate, monthName, one, until, whole } from '../core/format'
import { hrefOf } from '../core/routes'
import { useNow, usePoll } from '../core/usePoll'
import type { DkLive, LifeEvent, LiveUpdate, Overview as Data, User } from '../core/types'
import { DayBand } from './DayBand'
import { CameraFrame } from '../sections/Cameras'
import { Updates } from '../sections/DkLive'
import { factWhen, MonologueList } from '../sections/LateNight'
import { finishesAt, PrinterLines } from '../sections/Printers'

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

function CalendarList({ events, now }: { events: LifeEvent[]; now: Date }) {
  const days = new Map<string, LifeEvent[]>()
  for (const e of events.slice(0, 9)) days.set(e.day, [...(days.get(e.day) ?? []), e])
  return (
    <div className="agenda">
      {[...days].map(([day, list]) => (
        <div key={day} className="agenda-day">
          <h3>{dayName(day, now)}</h3>
          <ul>
            {list.map((e) => (
              <li key={e.id}>
                <span className="agenda-time">{e.allDay ? 'Hele dagen' : clock(e.start)}</span>
                <span>{e.title}</span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  )
}

function PowerSummary({ dk }: { dk: DkLive }) {
  const p = dk.power
  if (!p) return null
  return (
    <div className="power">
      <p className="power-now">{kr(p.now)} <span>kr/kWh</span></p>
      <dl>
        <dt>Billigst</dt><dd>{kr(p.low.dkk)} kl. {clock(p.low.t)}</dd>
        <dt>Dyrest</dt><dd>{kr(p.high.dkk)} kl. {clock(p.high.t)}</dd>
      </dl>
      <p className="note">Spotpris {p.area} uden afgifter</p>
    </div>
  )
}

function updatedText(iso: string, now: Date): string {
  const text = ago(iso, now.getTime())
  return text === 'lige nu' ? 'Opdateret lige nu' : `Opdateret for ${text} siden`
}

function LiveBlock({ dk, now }: { dk?: DkLive; now: Date }) {
  if (!dk) return null
  if (!dk.configured) return <p className="empty">Sæt adressen til dk-live under Admin → Opsætning.</p>
  const updates: LiveUpdate[] = dk.feed ?? []
  const road = dk.traffic
  return (
    <div className="live">
      <PowerSummary dk={dk} />
      <div>
        <h3>Trafik{road ? `, ${road.near} tæt på` : ''}</h3>
        <Updates items={road?.items.slice(0, 5) ?? []} now={now} plain empty="Ingen hændelser lige nu." />
      </div>
      <div>
        <h3>Opdateringer</h3>
        <Updates items={updates} now={now} limit={6} />
      </div>
      {dk.updated && (
        <p className="live-stamp">
          <span className={`dot dot-${dk.ok ? 'good' : 'slow'}`} aria-hidden="true" />
          {dk.ok ? updatedText(dk.updated, now) : 'Viser seneste data, dk-live svarer ikke helt'}
        </p>
      )}
    </div>
  )
}

export function Overview({ user, onAuthLost }: { user: User; onAuthLost: () => void }) {
  const now = useNow(1000)
  const { data, error } = usePoll<Data>('/api/overview', LIVE_SECONDS, onAuthLost)
  const b = data?.blocks ?? {}
  const today = b.latenight?.exact ?? []
  const dlFacts = today.length ? today : b.latenight?.near ?? []

  return (
    <main className="overview">
      <header className="hero">
        <div>
          <h1>{longDate(now)}</h1>
          <p className="digest">{digest(data, now) || `Velkommen, ${user.name || user.username}.`}</p>
        </div>
        <p className="hero-clock">
          <time>{clock(now)}</time>
          <span>{String(now.getSeconds()).padStart(2, '0')}</span>
        </p>
      </header>

      {error && <p className="problem">{error}</p>}

      <DayBand now={now} dk={b.dklive} calendar={b.calendar} f1={b.f1} />

      <div className="blocks">
        {b.calendar && (
          <Block id="calendar" title="Kalender" className="w4">
            {!b.calendar.connected ? (
              <p className="empty">Din Google-kalender er ikke forbundet.{' '}
                <a href={hrefOf('calendar')}>Forbind den her</a>.</p>
            ) : b.calendar.events.length ? (
              <CalendarList events={b.calendar.events} now={now} />
            ) : <p className="empty">Intet de næste 10 dage.</p>}
          </Block>
        )}

        {b.dklive && (
          <Block id="dklive" title="DK live" className="w8">
            <LiveBlock dk={b.dklive} now={now} />
          </Block>
        )}

        {b.news && (
          <Block id="news" title="Nyheder" className="w5">
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

        {b.latenight && (
          <Block id="latenight" title="SLQ DL" className="w4 dl">
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

        {b.f1 && (
          <Block id="f1" title="Formel 1" className="w3">
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

        {b.logmylife && (
          <Block id="logmylife" title="LogMyLife" className="w5">
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

        {b.links && (
          <Block id="links" title="Links" className="w3">
            {b.links.pinned.length ? (
              <ul className="pinned">
                {b.links.pinned.map((l) => (
                  <li key={l.id}><a href={l.url} target="_blank" rel="noreferrer noopener">{l.title}</a></li>
                ))}
              </ul>
            ) : <p className="empty">{b.links.total ? 'Fastgør et link, så står det her.' : 'Ingen links endnu.'}</p>}
          </Block>
        )}

        {b.aktier && (
          <Block id="aktier" title="Aktier" className="w2">
            <p className="empty">Nordnet er ikke forbundet.</p>
          </Block>
        )}

        {b.familylog && (
          <Block id="familylog" title="FamilyLog" className="w2">
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

        {!!b.cameras?.cameras.length && (
          <Block id="cameras" title="Kameraer" className="w8">
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
          <Block id="printers" title="Printere" className="w4">
            <PrinterLines printers={b.printers.printers} now={now} />
          </Block>
        )}
      </div>

      {data?.blocks.dklive?.weather?.temp != null && (
        <p className="sr-only">{one(data.blocks.dklive.weather.temp)} grader</p>
      )}
    </main>
  )
}
