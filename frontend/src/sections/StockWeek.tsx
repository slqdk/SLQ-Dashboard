import { useState } from 'react'
import { shortDay, signed, whole } from '../core/format'
import type { StockWeek as Week } from '../core/types'
import { useWidth } from '../core/useWidth'

const HEIGHT = 170
const LEFT = 42
const RIGHT = 10
const TOP = 22
const BOTTOM = 20

const direction = (change: number) => (change < 0 ? 'down' : 'up')

/** One line: what today's holdings did over the week, in per cent of where it began.
 *  One series, so the title names it and there is no legend. */
function Chart({ week }: { week: Week }) {
  const { ref, width } = useWidth(320)
  const [hover, setHover] = useState<number | null>(null)
  const percent = week.total.map((v) => (v / week.total[0] - 1) * 100)
  const low = Math.min(0, ...percent)
  const high = Math.max(0, ...percent)
  const span = Math.max(0.5, high - low)
  const plot = Math.max(80, width - LEFT - RIGHT)
  const x = (i: number) => LEFT + (i / (percent.length - 1)) * plot
  const y = (v: number) => TOP + (1 - (v - low) / span) * (HEIGHT - TOP - BOTTOM)
  const line = percent.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join('')
  const at = hover ?? percent.length - 1
  const move = (e: React.MouseEvent<SVGSVGElement>) => {
    const box = e.currentTarget.getBoundingClientRect()
    setHover(Math.max(0, Math.min(percent.length - 1, Math.round(((e.clientX - box.left - LEFT) / plot) * (percent.length - 1)))))
  }
  return (
    <div ref={ref} className="week-chart">
      <svg width={width} height={HEIGHT} role="img" onMouseMove={move} onMouseLeave={() => setHover(null)}
        aria-label={`Din beholdning de seneste syv dage: ${signed(percent[percent.length - 1])} %`}>
        <line x1={LEFT} x2={LEFT + plot} y1={y(0)} y2={y(0)} className="week-zero" />
        <text x={LEFT - 6} y={y(high) + 4} textAnchor="end" className="week-tick">{signed(high)} %</text>
        {low < 0 && <text x={LEFT - 6} y={y(low) + 4} textAnchor="end" className="week-tick">{signed(low)} %</text>}
        {week.days.map((day, i) => (i % 2 === 1 || i === week.days.length - 1) && (
          <text key={day} x={x(i)} y={HEIGHT - 5} textAnchor="middle" className="week-tick">{shortDay(day).split(' ')[0]}</text>
        ))}
        {hover != null && <line x1={x(hover)} x2={x(hover)} y1={TOP} y2={HEIGHT - BOTTOM} className="week-cursor" />}
        <path d={line} className={`week-line ${direction(percent[percent.length - 1])}`} />
        <circle cx={x(at)} cy={y(percent[at])} r={4} className={`week-dot ${direction(percent[percent.length - 1])}`} />
        <text x={Math.max(LEFT, Math.min(x(at) - 60, LEFT + plot - 150))} y={12} className="week-value">
          {shortDay(week.days[at])}: {signed(percent[at])} %, {whole(week.total[at])} kr
        </text>
      </svg>
    </div>
  )
}

function Spark({ points, change }: { points: number[]; change: number }) {
  const low = Math.min(...points)
  const span = Math.max(...points) - low || 1
  const d = points.map((p, i) => `${i ? 'L' : 'M'}${((i / (points.length - 1)) * 62 + 1).toFixed(1)} ${(15 - ((p - low) / span) * 14).toFixed(1)}`).join('')
  return <svg className="spark" width={64} height={16} aria-hidden="true"><path d={d} className={`week-line ${direction(change)}`} /></svg>
}

/** The week: the holdings as one line, and each of them beside it. */
export function StockWeek({ week }: { week: Week }) {
  if (!week.items.length) return <p className="empty">Henter kurser.</p>
  return (
    <div className="week">
      <div>
        <p className="week-head">
          <strong>{whole(week.value ?? 0)} kr</strong>{' '}
          <span>{signed(week.change ?? 0)} % på en uge, {signed(week.changeKr ?? 0, 0)} kr</span>
        </p>
        <Chart week={week} />
      </div>
      <ul className="week-list">
        {week.items.map((item) => (
          <li key={item.isin} title={`${whole(item.value)} kr`}>
            <span className="week-name">{item.name}</span>
            <Spark points={item.points} change={item.change} />
            <span className="week-change">{signed(item.change)} %</span>
          </li>
        ))}
        {!!week.missing.length && (
          <li className="week-missing" title={week.missing.join(', ')}>{week.missing.length} uden kurs</li>
        )}
      </ul>
    </div>
  )
}
