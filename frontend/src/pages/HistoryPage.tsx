import { useEffect, useState } from 'react'
import { entries as entriesApi } from '@/api/endpoints'
import type { Entry, SortField } from '@/api/types'
import { DataTable, type Column } from '@/components/DataTable'
import { FilterBar } from '@/components/FilterBar'
import { formatAmount, formatDateISO } from '@/lib/format'
import { KINDS } from '@/lib/kinds'
import { resolvePeriod } from '@/lib/periods'
import { useAppData } from '@/state/AppData'
import { useFilters } from '@/state/Filters'
import styles from './HistoryPage.module.css'

const PAGE_SIZE = 100

/**
 * Pagina 2 — storico dettagliato.
 *
 * Ordinabile per data, importo, categoria, sottocategoria, conto e tipo. La descrizione
 * non è ordinabile: è testo libero, ordinarla alfabeticamente non direbbe nulla.
 */
export function HistoryPage() {
  const { accounts } = useAppData()
  const { period, setPeriod, accountId, setAccountId } = useFilters()
  const resolved = resolvePeriod(period)

  const [rows, setRows] = useState<Entry[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [sort, setSort] = useState<SortField>('date')
  const [order, setOrder] = useState<'asc' | 'desc'>('desc')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Cambiare filtro o ordinamento riporta alla prima pagina: restare alla pagina 4 di
  // un elenco appena ricostruito mostrerebbe righe arbitrarie.
  useEffect(() => {
    setOffset(0)
  }, [resolved.from, resolved.to, accountId, sort, order])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    entriesApi
      .list({
        date_from: resolved.from,
        date_to: resolved.to,
        account_id: accountId,
        sort,
        order,
        limit: PAGE_SIZE,
        offset,
      })
      .then((page) => {
        if (cancelled) return
        setRows(page.items)
        setTotal(page.total)
      })
      .catch(() => !cancelled && setError('Non è stato possibile caricare i movimenti'))
      .finally(() => !cancelled && setLoading(false))

    return () => {
      cancelled = true
    }
  }, [resolved.from, resolved.to, accountId, sort, order, offset])

  function toggleSort(key: SortField) {
    if (key === sort) {
      setOrder((prev) => (prev === 'asc' ? 'desc' : 'asc'))
    } else {
      setSort(key)
      setOrder(key === 'date' || key === 'amount' ? 'desc' : 'asc')
    }
  }

  const columns: Column<Entry, SortField>[] = [
    {
      key: 'date',
      header: 'Data',
      sortKey: 'date',
      render: (row) => <span className="num">{formatDateISO(row.date)}</span>,
    },
    {
      key: 'kind',
      header: 'Tipo',
      sortKey: 'kind',
      render: (row) => (
        <span className={styles.badge} style={{ color: KINDS[row.kind].color }}>
          {KINDS[row.kind].label}
        </span>
      ),
    },
    {
      key: 'account',
      header: 'Conto',
      sortKey: 'account',
      render: (row) =>
        row.to_account_name ? (
          <span>
            {row.account_name} <span className="muted">→ {row.to_account_name}</span>
          </span>
        ) : (
          row.account_name
        ),
    },
    { key: 'category', header: 'Categoria', sortKey: 'category', render: (row) => row.category_name },
    {
      key: 'subcategory',
      header: 'Sottocategoria',
      sortKey: 'subcategory',
      secondary: true,
      render: (row) => <span className="muted">{row.subcategory_name}</span>,
    },
    {
      key: 'description',
      header: 'Descrizione',
      secondary: true,
      render: (row) => <span className={styles.description}>{row.description || '—'}</span>,
    },
    {
      key: 'amount',
      header: 'Importo',
      sortKey: 'amount',
      align: 'right',
      render: (row) => (
        <span className="num" style={{ color: KINDS[row.kind].color, fontWeight: 600 }}>
          {KINDS[row.kind].negative ? '−' : '+'} {formatAmount(row.amount)} €
        </span>
      ),
    },
  ]

  const pageEnd = Math.min(offset + PAGE_SIZE, total)

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

      <section className="card">
        <div className={styles.head}>
          <h2>Movimenti</h2>
          <span className="muted">
            {total === 0 ? 'nessun movimento' : `${offset + 1}–${pageEnd} di ${total}`}
          </span>
        </div>

        {loading && rows.length === 0 ? (
          <div className="empty">Caricamento…</div>
        ) : (
          <DataTable
            columns={columns}
            rows={rows}
            rowKey={(row) => row.id}
            sort={sort}
            order={order}
            onSort={toggleSort}
            empty="Nessun movimento nel periodo selezionato."
          />
        )}

        {total > PAGE_SIZE && (
          <div className={styles.pager}>
            <button
              type="button"
              className="btn"
              disabled={offset === 0}
              onClick={() => setOffset((value) => Math.max(0, value - PAGE_SIZE))}
            >
              ‹ Precedenti
            </button>
            <button
              type="button"
              className="btn"
              disabled={pageEnd >= total}
              onClick={() => setOffset((value) => value + PAGE_SIZE)}
            >
              Successivi ›
            </button>
          </div>
        )}
      </section>
    </>
  )
}
