import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { AppShell } from '@/components/AppShell'
import { AddEntryPage } from '@/pages/AddEntryPage'
import { HistoryPage } from '@/pages/HistoryPage'
import { LoginPage } from '@/pages/LoginPage'
import { RecapPage } from '@/pages/RecapPage'
import { AppDataProvider, useAppData } from '@/state/AppData'
import { FiltersProvider } from '@/state/Filters'

/**
 * Le rotte stanno tutte qui. Aggiungere una pagina significa aggiungere una `<Route>`
 * e una voce in `TABS` dentro `components/NavTabs.tsx` — nient'altro.
 */
function Routed() {
  const { user, loading } = useAppData()

  if (loading) return <div className="empty">Caricamento…</div>
  if (!user) return <LoginPage onLoggedIn={() => window.location.reload()} />

  return (
    <FiltersProvider>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<RecapPage />} />
          <Route path="storico" element={<HistoryPage />} />
          <Route path="aggiungi" element={<AddEntryPage />} />
          <Route path="*" element={<RecapPage />} />
        </Route>
      </Routes>
    </FiltersProvider>
  )
}

export function App() {
  return (
    <BrowserRouter>
      <AppDataProvider>
        <Routed />
      </AppDataProvider>
    </BrowserRouter>
  )
}
