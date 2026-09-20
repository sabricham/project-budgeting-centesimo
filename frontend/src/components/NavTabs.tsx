import { NavLink } from 'react-router-dom'
import styles from './NavTabs.module.css'

/**
 * Navigazione a pulsanti.
 *
 * Le pagine stanno in un elenco, non scritte a mano nel markup: aggiungerne una
 * (ne arriveranno altre) è una riga sola.
 */
export interface Tab {
  to: string
  label: string
}

export const TABS: Tab[] = [
  { to: '/', label: 'Recap' },
  { to: '/storico', label: 'Storico' },
  { to: '/aggiungi', label: 'Aggiungi entry' },
]

export function NavTabs({ tabs = TABS }: { tabs?: Tab[] }) {
  return (
    <nav className={styles.tabs}>
      {tabs.map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          end={tab.to === '/'}
          className={({ isActive }) => (isActive ? `${styles.tab} ${styles.active}` : styles.tab)}
        >
          {tab.label}
        </NavLink>
      ))}
    </nav>
  )
}
