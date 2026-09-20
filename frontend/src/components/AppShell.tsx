import { Outlet } from 'react-router-dom'
import { useAppData } from '@/state/AppData'
import { Clock } from './Clock'
import { NavTabs } from './NavTabs'
import styles from './AppShell.module.css'

/**
 * Intelaiatura comune a tutte le pagine: orologio in alto, pulsanti di navigazione
 * sotto, contenuto della pagina in fondo. Le pagine non ridisegnano nulla di tutto questo.
 */
export function AppShell() {
  const { user, logout } = useAppData()

  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        <Clock />
        <NavTabs />
        {user && (
          <button
            type="button"
            className={styles.logout}
            onClick={() => void logout()}
            title={`Esci da ${user.username}`}
          >
            Esci
          </button>
        )}
      </header>

      <main className={styles.main}>
        <Outlet />
      </main>
    </div>
  )
}
