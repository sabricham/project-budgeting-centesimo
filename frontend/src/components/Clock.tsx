import { useEffect, useState } from 'react'
import { formatDateLong, formatTime } from '@/lib/format'
import styles from './Clock.module.css'

/**
 * Orologio in tempo reale con la data di oggi.
 *
 * Si riallinea al secondo esatto invece di usare un intervallo fisso di 1000 ms:
 * con `setInterval` secco la deriva accumulata fa saltare visibilmente un secondo
 * ogni tanto.
 */
export function Clock() {
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    let timer: number
    const tick = () => {
      const current = new Date()
      setNow(current)
      timer = window.setTimeout(tick, 1000 - current.getMilliseconds())
    }
    timer = window.setTimeout(tick, 1000 - now.getMilliseconds())
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className={styles.clock}>
      <time className={styles.time} dateTime={now.toISOString()}>
        {formatTime(now)}
      </time>
      <span className={styles.date}>{formatDateLong(now)}</span>
    </div>
  )
}
