import type { Account } from '@/api/types'
import styles from './AccountSelector.module.css'

/**
 * Selettore del conto, con la voce «Tutti i conti».
 *
 * `null` significa *tutti*: è lo stesso valore che l'API interpreta come «nessun filtro»,
 * quindi non serve nessuna traduzione fra interfaccia e backend.
 *
 * Due disposizioni: `inline` per la barra dei filtri (etichetta a fianco, larghezza al
 * contenuto) e `block` per quando sta dentro una form, dove deve allinearsi in larghezza
 * agli altri campi.
 */
export function AccountSelector({
  accounts,
  value,
  onChange,
  allowAll = true,
  label,
  layout = 'inline',
}: {
  accounts: Account[]
  value: number | null
  onChange: (accountId: number | null) => void
  allowAll?: boolean
  label?: string
  layout?: 'inline' | 'block'
}) {
  return (
    <div className={layout === 'block' ? styles.block : styles.wrap}>
      {label && <label className={styles.label}>{label}</label>}
      <select
        value={value === null ? '' : String(value)}
        onChange={(event) => onChange(event.target.value === '' ? null : Number(event.target.value))}
        aria-label={label ?? 'Conto'}
      >
        {allowAll && <option value="">Tutti i conti</option>}
        {!allowAll && value === null && <option value="">Scegli un conto…</option>}
        {accounts.map((account) => (
          <option key={account.id} value={account.id}>
            {account.name}
          </option>
        ))}
      </select>
    </div>
  )
}
