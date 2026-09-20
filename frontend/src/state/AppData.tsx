import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { accounts as accountsApi, auth, categories as categoriesApi } from '@/api/endpoints'
import { tokens } from '@/api/client'
import type { Account, Category, User } from '@/api/types'

/**
 * Dati che servono a più pagine: utente, conti, catalogo delle categorie.
 *
 * Si caricano una volta sola all'ingresso invece che ad ogni cambio pagina — sono dati
 * che cambiano di rado, e il modulo di inserimento ha bisogno di entrambi gli elenchi
 * per popolare le tendine senza attese.
 */
interface AppDataValue {
  user: User | null
  accounts: Account[]
  categories: Category[]
  loading: boolean
  error: string | null
  /** Da chiamare dopo aver inserito una entry: i saldi dei conti sono cambiati. */
  refreshAccounts: () => Promise<void>
  /** Inserisce un conto appena creato senza rifare il giro di rete. */
  addAccount: (account: Account) => void
  logout: () => Promise<void>
}

const AppDataContext = createContext<AppDataValue | null>(null)

export function AppDataProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [accounts, setAccounts] = useState<Account[]>([])
  const [categories, setCategories] = useState<Category[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refreshAccounts = useCallback(async () => {
    setAccounts(await accountsApi.list())
  }, [])

  const addAccount = useCallback((account: Account) => {
    setAccounts((prev) => [...prev, account].sort((a, b) => a.name.localeCompare(b.name, 'it')))
  }, [])

  const load = useCallback(async () => {
    if (!tokens.access) {
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const [me, accountList, categoryList] = await Promise.all([
        auth.me(),
        accountsApi.list(),
        categoriesApi.list(),
      ])
      setUser(me)
      setAccounts(accountList)
      setCategories(categoryList)
    } catch {
      // Token non più valido: si torna alla schermata di accesso.
      tokens.clear()
      setUser(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const logout = useCallback(async () => {
    await auth.logout()
    setUser(null)
    setAccounts([])
    setCategories([])
  }, [])

  const value = useMemo(
    () => ({ user, accounts, categories, loading, error, refreshAccounts, addAccount, logout }),
    [user, accounts, categories, loading, error, refreshAccounts, addAccount, logout],
  )

  return <AppDataContext.Provider value={value}>{children}</AppDataContext.Provider>
}

export function useAppData(): AppDataValue {
  const value = useContext(AppDataContext)
  if (!value) throw new Error('useAppData va usato dentro <AppDataProvider>')
  return value
}

/** Usata dalla schermata di accesso per ricaricare tutto dopo il login. */
export function useReload() {
  return () => window.location.reload()
}
