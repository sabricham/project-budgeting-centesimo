import type { ReactNode } from 'react'
import styles from './DataTable.module.css'

/**
 * Tabella ordinabile generica.
 *
 * Non conosce le entry: riceve le colonne come dati. L'ordinamento **non** avviene qui —
 * il componente segnala soltanto su quale colonna si è cliccato, e chi lo usa rifà la
 * richiesta al server. Ordinare lato client sarebbe sbagliato su dati paginati: si
 * riordinerebbe la pagina visibile, non l'insieme.
 *
 * Una colonna con `sortKey` assente è semplicemente non ordinabile — è così che la
 * colonna «descrizione» resta fuori dall'ordinamento.
 */
export interface Column<Row, SortKey extends string = string> {
  key: string
  header: string
  sortKey?: SortKey
  render: (row: Row) => ReactNode
  align?: 'left' | 'right' | 'center'
  /** nasconde la colonna sugli schermi stretti */
  secondary?: boolean
}

export interface DataTableProps<Row, SortKey extends string = string> {
  columns: Column<Row, SortKey>[]
  rows: Row[]
  rowKey: (row: Row) => string | number
  sort?: SortKey
  order?: 'asc' | 'desc'
  onSort?: (key: SortKey) => void
  empty?: ReactNode
}

export function DataTable<Row, SortKey extends string = string>({
  columns,
  rows,
  rowKey,
  sort,
  order = 'desc',
  onSort,
  empty = 'Nessun risultato.',
}: DataTableProps<Row, SortKey>) {
  if (rows.length === 0) return <div className="empty">{empty}</div>

  return (
    <div className={styles.scroll}>
      <table className={styles.table}>
        <thead>
          <tr>
            {columns.map((column) => {
              const sortable = Boolean(column.sortKey && onSort)
              const active = column.sortKey && column.sortKey === sort
              return (
                <th
                  key={column.key}
                  className={[
                    column.align === 'right' ? styles.right : '',
                    column.align === 'center' ? styles.center : '',
                    column.secondary ? styles.secondary : '',
                  ].join(' ')}
                  aria-sort={active ? (order === 'asc' ? 'ascending' : 'descending') : undefined}
                >
                  {sortable ? (
                    // Un <button> e non un <th> cliccabile: così l'intestazione si
                    // raggiunge col tabulatore e si attiva da tastiera, e i lettori di
                    // schermo la annunciano come comando invece che come testo.
                    <button
                      type="button"
                      className={styles.sortable}
                      onClick={() => onSort!(column.sortKey!)}
                    >
                      {column.header}
                      <span className={active ? styles.arrowOn : styles.arrow}>
                        {active ? (order === 'asc' ? '▲' : '▼') : '▾'}
                      </span>
                    </button>
                  ) : (
                    column.header
                  )}
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)}>
              {columns.map((column) => (
                <td
                  key={column.key}
                  className={[
                    column.align === 'right' ? styles.right : '',
                    column.align === 'center' ? styles.center : '',
                    column.secondary ? styles.secondary : '',
                  ].join(' ')}
                >
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
