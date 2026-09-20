import type { ReactNode } from 'react'
import styles from './StatTiles.module.css'

/** Riga di valori chiave sopra il grafico. Generica: riceve le voci da mostrare. */
export interface Stat {
  label: string
  value: ReactNode
  color?: string
}

export function StatTiles({ stats }: { stats: Stat[] }) {
  return (
    <div className={styles.row}>
      {stats.map((stat) => (
        <div key={stat.label} className={styles.tile}>
          <span className={styles.label}>{stat.label}</span>
          <span className={`${styles.value} num`} style={stat.color ? { color: stat.color } : undefined}>
            {stat.value}
          </span>
        </div>
      ))}
    </div>
  )
}
