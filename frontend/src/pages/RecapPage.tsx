import { useEffect, useState } from 'react'
import { reports } from '@/api/endpoints'
import type { NetWorthSeries, Summary } from '@/api/types'
import { FilterBar } from '@/components/FilterBar'
import { NetWorthChart } from '@/components/NetWorthChart'
import { StatTiles } from '@/components/StatTiles'
import { formatMoney } from '@/lib/format'
import { KINDS } from '@/lib/kinds'
import { resolvePeriod } from '@/lib/periods'
import { useAppData } from '@/state/AppData'
import { useFilters } from '@/state/Filters'

/** Pagina 1 — punto d'ingresso: andamento del patrimonio sul periodo selezionato. */
export function RecapPage() {
  const { accounts } = useAppData()
  const { period, setPeriod, accountId, setAccountId } = useFilters()
  const resolved = resolvePeriod(period)

  const [series, setSeries] = useState<NetWorthSeries | null>(null)
  const [summary, setSummary] = useState<Summary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    Promise.all([
      reports.netWorthSeries(resolved.from, resolved.to, accountId),
      reports.summary(resolved.from, resolved.to, accountId),
    ])
      .then(([seriesData, summaryData]) => {
        // La risposta di una richiesta superata da un cambio di periodo va scartata,
        // altrimenti può arrivare dopo e sovrascrivere quella giusta.
        if (cancelled) return
        setSeries(seriesData)
        setSummary(summaryData)
      })
      .catch(() => !cancelled && setError('Non è stato possibile caricare il riepilogo'))
      .finally(() => !cancelled && setLoading(false))

    return () => {
      cancelled = true
    }
  }, [resolved.from, resolved.to, accountId])

  const netChange = summary ? Number(summary.net_change) : 0

  return (
    <>
      <FilterBar
        accounts={accounts}
        period={period}
        onPeriodChange={setPeriod}
        accountId={accountId}
        onAccountChange={setAccountId}
      />

      {error && <div className="error-box">{error}</div>}

      {summary && (
        <StatTiles
          stats={[
            { label: 'Patrimonio a fine periodo', value: formatMoney(summary.closing_balance) },
            {
              label: 'Variazione nel periodo',
              value: `${netChange >= 0 ? '+' : '−'} ${formatMoney(Math.abs(netChange))}`,
              color: netChange >= 0 ? KINDS.income.color : KINDS.expense.color,
            },
            { label: 'Entrate', value: formatMoney(summary.income), color: KINDS.income.color },
            { label: 'Uscite', value: formatMoney(summary.expense), color: KINDS.expense.color },
            {
              label: 'Investimenti',
              value: formatMoney(summary.investment),
              color: KINDS.investment.color,
            },
          ]}
        />
      )}

      <section className="card">
        <h2>Andamento del patrimonio</h2>
        {loading && !series ? (
          <div className="empty">Caricamento…</div>
        ) : series ? (
          <NetWorthChart series={series} />
        ) : null}
      </section>
    </>
  )
}
