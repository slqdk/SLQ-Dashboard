import { useState } from 'react'
import { api } from '../core/api'
import { fullDate, kr, localDate, signed, units, whole } from '../core/format'
import type { StockWeek as Week } from '../core/types'
import { usePoll } from '../core/usePoll'
import { Dialog, FileImport, SectionHead } from './common'
import { StockWeek } from './StockWeek'

const API = '/api/s/aktier'

interface Position {
  name: string
  isin: string
  depot: string
  quantity: number
  cost: number | null
  currency: string
}

interface Year {
  year: string
  currency: string
  dividends: number
  result: number
}

interface State {
  mode: string
  rows: number
  first: string | null
  last: string | null
  importedAt: string | null
  positions: Position[]
  years: Year[]
  week: Week | null
}

function Holdings({ positions, week }: { positions: Position[]; week: Week | null }) {
  const depots = new Set(positions.map((p) => p.depot)).size > 1
  const priced = new Map(week?.items.map((i) => [i.isin, i]))
  return (
    <div className="table-wrap">
      <table className="holdings">
        <thead>
          <tr>
            <th scope="col">Værdipapir</th>
            {depots && <th scope="col">Depot</th>}
            <th scope="col">Antal</th>
            <th scope="col">Snitkurs</th>
            <th scope="col">Købsværdi</th>
            <th scope="col">Værdi</th>
            <th scope="col">Uge</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((p) => {
            const now = priced.get(p.isin)
            return (
            <tr key={`${p.depot}${p.isin}`}>
              <th scope="row">{p.name}</th>
              {depots && <td>…{p.depot}</td>}
              <td>{units(p.quantity)}</td>
              <td>{p.cost == null ? 'Ukendt' : kr(p.cost / p.quantity)}</td>
              <td>{p.cost == null ? 'Ukendt' : `${kr(p.cost)} ${p.currency}`}</td>
              <td>{now ? `${whole(now.value)} kr` : 'Ingen kurs'}</td>
              <td>{now ? `${signed(now.change)} %` : ''}</td>
            </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function Years({ years }: { years: Year[] }) {
  return (
    <div className="table-wrap">
      <table className="holdings">
        <thead>
          <tr><th scope="col">År</th><th scope="col">Udbytte efter skat</th><th scope="col">Realiseret resultat</th></tr>
        </thead>
        <tbody>
          {years.map((y) => (
            <tr key={`${y.year}${y.currency}`}>
              <th scope="row">{y.year}</th>
              <td>{y.dividends ? `${kr(y.dividends)} ${y.currency}` : ''}</td>
              <td>{y.result ? `${kr(y.result)} ${y.currency}` : ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function Aktier({ onAuthLost }: { onAuthLost: () => void }) {
  // Prices arrive a little after an import, so the page keeps asking.
  const { data, error, reload } = usePoll<State>(`${API}/state`, 15, onAuthLost)
  const [importing, setImporting] = useState(false)
  const [clearing, setClearing] = useState(false)

  if (!data) return <main className="page">{error && <p className="problem">{error}</p>}</main>

  const clear = async () => {
    await api(`${API}/rows`, { method: 'DELETE' })
    setClearing(false)
    void reload()
  }

  if (data.mode !== 'csv') {
    return (
      <main className="page narrow">
        <SectionHead title="Aktier" text="Din Nordnet-konto." />
        <p className="lead">Nordnet er ikke forbundet.</p>
        <p>Slå <strong>Importeret udtræk</strong> til under Admin → Opsætning → Nordnet.</p>
      </main>
    )
  }

  const summary = data.rows
    ? `Beholdningen er fra dit udtræk, til og med ${fullDate(localDate(data.last ?? ''))}. Kurserne er fra Yahoo Finance.`
    : 'Din beholdning, fra et udtræk fra Nordnet.'

  return (
    <main className="page">
      <SectionHead title="Aktier" text={summary}>
        <button className="primary" onClick={() => setImporting(true)}>Importér fra Nordnet</button>
      </SectionHead>
      {error && <p className="problem">{error}</p>}

      {!data.rows && <p className="empty">Intet importeret endnu.</p>}
      {data.week && <section className="aktier-week"><h2>Ugen</h2><StockWeek week={data.week} /></section>}
      {!!data.positions.length && <Holdings positions={data.positions} week={data.week} />}
      {!!data.years.length && (
        <section>
          <h2>År for år</h2>
          <Years years={data.years} />
        </section>
      )}
      {!!data.rows && (
        <p className="note aktier-foot">
          {data.rows} rækker i alt, fra {fullDate(localDate(data.first ?? ''))}.{' '}
          <button className="link" onClick={() => setClearing(true)}>Slet det importerede</button>
        </p>
      )}

      {importing && (
        <FileImport title="Importér fra Nordnet" url={`${API}/import`} label="CSV-fil fra Nordnet" accept=".csv,text/csv"
          onClose={() => setImporting(false)} onDone={() => void reload()}>
          <ol className="steps">
            <li>Gå til Transaktioner og notaer på Nordnet.</li>
            <li>Vælg hele perioden, fra du åbnede kontoen. Et værdipapir uden rækker i perioden kommer ikke med.</li>
            <li>Hent CSV-filen, og vælg den her. Importerer du igen senere, kommer kun det nye til.</li>
          </ol>
        </FileImport>
      )}
      {clearing && (
        <Dialog title="Slet det importerede" onClose={() => setClearing(false)}>
          <p>Dine {data.rows} rækker fra Nordnet slettes fra dashboardet. Du kan importere filen igen bagefter.</p>
          <div className="dialog-actions">
            <button onClick={() => setClearing(false)}>Annullér</button>
            <button className="danger" onClick={() => void clear()}>Slet</button>
          </div>
        </Dialog>
      )}
    </main>
  )
}
