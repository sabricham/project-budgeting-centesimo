import { createContext, useContext, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { defaultPeriod, type Period } from '@/lib/periods'

/**
 * Periodo e conto selezionati, condivisi fra Recap e Storico.
 *
 * Sta qui e non dentro le pagine per una ragione di uso concreto: se scegli «marzo 2026,
 * conto Satispay» nel Recap e passi allo Storico, ti aspetti di trovarci la stessa
 * selezione, non di doverla rifare.
 */
interface FiltersValue {
  period: Period
  setPeriod: (period: Period) => void
  /** `null` = tutti i conti */
  accountId: number | null
  setAccountId: (accountId: number | null) => void
}

const FiltersContext = createContext<FiltersValue | null>(null)

export function FiltersProvider({ children }: { children: ReactNode }) {
  const [period, setPeriod] = useState<Period>(defaultPeriod)
  const [accountId, setAccountId] = useState<number | null>(null)

  const value = useMemo(
    () => ({ period, setPeriod, accountId, setAccountId }),
    [period, accountId],
  )

  return <FiltersContext.Provider value={value}>{children}</FiltersContext.Provider>
}

export function useFilters(): FiltersValue {
  const value = useContext(FiltersContext)
  if (!value) throw new Error('useFilters va usato dentro <FiltersProvider>')
  return value
}
