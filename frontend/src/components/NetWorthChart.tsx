import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { NetWorthSeries } from '@/api/types'
import { formatMoney, toNumber } from '@/lib/format'
import { fromISO } from '@/lib/periods'
import styles from './NetWorthChart.module.css'

/**
 * Andamento del patrimonio nel periodo.
 *
 * La linea parte dal patrimonio posseduto alla vigilia del periodo, non da zero: è il
 * server a calcolarlo (`opening_balance`) perché richiede tutti i movimenti precedenti.
 *
 * L'asse verticale **non parte da zero**: su un patrimonio che oscilla fra 10.000 e
 * 10.500 € una scala da zero appiattirebbe la linea fino a renderla inutile.
 */
function tickLabel(iso: string, granularity: NetWorthSeries['granularity']): string {
  const date = fromISO(iso)
  if (granularity === 'month') {
    return date.toLocaleDateString('it-IT', { month: 'short', year: '2-digit' })
  }
  return date.toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit' })
}

export function NetWorthChart({ series }: { series: NetWorthSeries }) {
  const data = series.points.map((point) => ({
    date: point.date,
    value: toNumber(point.value),
  }))

  if (data.length === 0) {
    return <div className="empty">Nessun dato nel periodo selezionato.</div>
  }

  const values = data.map((d) => d.value)
  const min = Math.min(...values)
  const max = Math.max(...values)
  // Un margine del 6% sopra e sotto: senza, la linea tocca i bordi del riquadro.
  const pad = Math.max((max - min) * 0.06, 1)

  return (
    <div className={styles.chart}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
          <defs>
            <linearGradient id="nw-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.35} />
              <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
            </linearGradient>
          </defs>

          <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />

          <XAxis
            dataKey="date"
            tickFormatter={(iso: string) => tickLabel(iso, series.granularity)}
            tick={{ fill: 'var(--text-faint)', fontSize: 12 }}
            axisLine={{ stroke: 'var(--border)' }}
            tickLine={false}
            minTickGap={28}
          />
          <YAxis
            domain={[min - pad, max + pad]}
            tick={{ fill: 'var(--text-faint)', fontSize: 12 }}
            axisLine={false}
            tickLine={false}
            width={78}
            tickFormatter={(value: number) =>
              new Intl.NumberFormat('it-IT', { notation: 'compact', maximumFractionDigits: 1 }).format(value)
            }
          />
          <Tooltip
            contentStyle={{
              background: 'var(--surface-2)',
              border: '1px solid var(--border-strong)',
              borderRadius: 'var(--radius-sm)',
              color: 'var(--text)',
            }}
            labelFormatter={(iso: string) =>
              fromISO(String(iso)).toLocaleDateString('it-IT', {
                day: '2-digit', month: 'long', year: 'numeric',
              })
            }
            formatter={(value: number) => [formatMoney(value), 'Patrimonio']}
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke="var(--accent)"
            strokeWidth={2}
            fill="url(#nw-fill)"
            dot={false}
            activeDot={{ r: 4 }}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
