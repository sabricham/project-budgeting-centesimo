import type { Account } from '@/api/types'
import type { Period } from '@/lib/periods'
import { AccountSelector } from './AccountSelector'
import { PeriodSelector } from './PeriodSelector'
import styles from './FilterBar.module.css'

/**
 * Barra in alto con selettore di periodo e selettore del conto.
 *
 * Richiesta identica in Recap e Storico, quindi è un blocco solo usato due volte
 * invece della stessa riga copiata in due pagine.
 */
export function FilterBar({
  accounts,
  period,
  onPeriodChange,
  accountId,
  onAccountChange,
}: {
  accounts: Account[]
  period: Period
  onPeriodChange: (period: Period) => void
  accountId: number | null
  onAccountChange: (accountId: number | null) => void
}) {
  return (
    <div className={styles.bar}>
      <PeriodSelector period={period} onChange={onPeriodChange} />
      <AccountSelector
        accounts={accounts}
        value={accountId}
        onChange={onAccountChange}
        label="Conto"
      />
    </div>
  )
}
