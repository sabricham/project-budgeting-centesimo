import {
  PERIOD_MODES,
  changeMode,
  resolvePeriod,
  shiftPeriod,
  type Period,
  type PeriodMode,
} from '@/lib/periods'
import styles from './PeriodSelector.module.css'

/**
 * Selettore del periodo, usato identico in Recap e Storico.
 *
 * Non sa nulla di date né di API: riceve un `Period`, ne restituisce uno nuovo.
 * Tutto il calcolo sta in `lib/periods.ts`, così il componente resta puro presentazione
 * e le regole dei periodi si possono provare senza montare nulla.
 */
export function PeriodSelector({
  period,
  onChange,
}: {
  period: Period
  onChange: (period: Period) => void
}) {
  const resolved = resolvePeriod(period)

  return (
    <div className={styles.wrap}>
      <select
        className={styles.mode}
        value={period.mode}
        onChange={(event) => onChange(changeMode(event.target.value as PeriodMode))}
        aria-label="Tipo di periodo"
      >
        {PERIOD_MODES.map((option) => (
          <option key={option.mode} value={option.mode}>
            {option.label}
          </option>
        ))}
      </select>

      <div className={styles.nav}>
        {resolved.navigable && (
          <button
            type="button"
            className="btn btn-icon"
            onClick={() => onChange(shiftPeriod(period, -1))}
            aria-label="Periodo precedente"
          >
            ‹
          </button>
        )}

        <span className={styles.label} title={`${resolved.from} → ${resolved.to}`}>
          {resolved.label}
        </span>

        {resolved.navigable && (
          <button
            type="button"
            className="btn btn-icon"
            onClick={() => onChange(shiftPeriod(period, 1))}
            aria-label="Periodo successivo"
          >
            ›
          </button>
        )}
      </div>
    </div>
  )
}
