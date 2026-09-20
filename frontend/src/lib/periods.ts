/**
 * Selettore di periodo.
 *
 * Tutta la logica dei periodi vive qui, in funzioni pure: il backend riceve soltanto
 * `date_from` e `date_to` e non sa nulla di «mese» o «ultimi 7 giorni». Aggiungere una
 * modalità significa aggiungere un caso in questo file, e nient'altro in tutto il progetto.
 *
 * Sei modalità:
 *   month | week | year   navigabili avanti e indietro con le frecce
 *   last7 | last30 | last365   finestre mobili che finiscono oggi, senza frecce
 */

export type PeriodMode = 'month' | 'week' | 'year' | 'last7' | 'last30' | 'last365'

export interface Period {
  mode: PeriodMode
  /** Giorno che identifica l'intervallo navigato. Ignorato dalle finestre mobili. */
  anchor: string
}

export interface ResolvedPeriod {
  from: string
  to: string
  label: string
  /** Le finestre mobili non si spostano: l'interfaccia nasconde le frecce. */
  navigable: boolean
}

export const PERIOD_MODES: { mode: PeriodMode; label: string }[] = [
  { mode: 'month', label: 'Mese' },
  { mode: 'week', label: 'Settimana' },
  { mode: 'year', label: 'Anno' },
  { mode: 'last7', label: 'Ultimi 7 giorni' },
  { mode: 'last30', label: 'Ultimi 30 giorni' },
  { mode: 'last365', label: 'Ultimi 365 giorni' },
]

const NAVIGABLE: PeriodMode[] = ['month', 'week', 'year']

/** Data in formato ISO `YYYY-MM-DD`, letta nel fuso locale e non in UTC. */
export function toISO(date: Date): string {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

/**
 * Costruisce una data locale da `YYYY-MM-DD`.
 * `new Date('2026-09-20')` la interpreterebbe come mezzanotte UTC e in Italia
 * diventerebbe il 20 alle 02:00 — innocuo di giorno, ma capace di far slittare un
 * confine di mese. Qui si passa per il costruttore a tre argomenti, sempre locale.
 */
export function fromISO(iso: string): Date {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d)
}

export function today(): string {
  return toISO(new Date())
}

/** Lunedì della settimana che contiene `date`. La settimana italiana inizia di lunedì. */
function startOfWeek(date: Date): Date {
  const out = new Date(date)
  const shift = (out.getDay() + 6) % 7 // domenica = 0 -> 6
  out.setDate(out.getDate() - shift)
  return out
}

function addDays(date: Date, days: number): Date {
  const out = new Date(date)
  out.setDate(out.getDate() + days)
  return out
}

export function defaultPeriod(): Period {
  return { mode: 'month', anchor: today() }
}

export function isNavigable(mode: PeriodMode): boolean {
  return NAVIGABLE.includes(mode)
}

const MESI = [
  'gennaio', 'febbraio', 'marzo', 'aprile', 'maggio', 'giugno',
  'luglio', 'agosto', 'settembre', 'ottobre', 'novembre', 'dicembre',
]

function shortDate(date: Date): string {
  return `${date.getDate()} ${MESI[date.getMonth()].slice(0, 3)}`
}

/** Traduce una modalità e la sua ancora nell'intervallo concreto da mandare all'API. */
export function resolvePeriod(period: Period): ResolvedPeriod {
  const anchor = fromISO(period.anchor)
  const now = new Date()

  switch (period.mode) {
    case 'month': {
      const from = new Date(anchor.getFullYear(), anchor.getMonth(), 1)
      const to = new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0)
      return {
        from: toISO(from),
        to: toISO(to),
        label: `${MESI[from.getMonth()]} ${from.getFullYear()}`,
        navigable: true,
      }
    }
    case 'week': {
      const from = startOfWeek(anchor)
      const to = addDays(from, 6)
      return {
        from: toISO(from),
        to: toISO(to),
        label: `${shortDate(from)} – ${shortDate(to)} ${to.getFullYear()}`,
        navigable: true,
      }
    }
    case 'year': {
      const from = new Date(anchor.getFullYear(), 0, 1)
      const to = new Date(anchor.getFullYear(), 11, 31)
      return { from: toISO(from), to: toISO(to), label: String(from.getFullYear()), navigable: true }
    }
    case 'last7':
      return { from: toISO(addDays(now, -6)), to: toISO(now), label: 'Ultimi 7 giorni', navigable: false }
    case 'last30':
      return { from: toISO(addDays(now, -29)), to: toISO(now), label: 'Ultimi 30 giorni', navigable: false }
    case 'last365':
      return { from: toISO(addDays(now, -364)), to: toISO(now), label: 'Ultimi 365 giorni', navigable: false }
  }
}

/** Sposta l'ancora di `step` intervalli (−1 indietro, +1 avanti). */
export function shiftPeriod(period: Period, step: number): Period {
  if (!isNavigable(period.mode)) return period
  const anchor = fromISO(period.anchor)

  switch (period.mode) {
    case 'week':
      return { ...period, anchor: toISO(addDays(anchor, step * 7)) }
    case 'year':
      return { ...period, anchor: toISO(new Date(anchor.getFullYear() + step, 0, 1)) }
    default:
      // Il giorno 1 evita il classico salto «31 gennaio + 1 mese = 3 marzo».
      return { ...period, anchor: toISO(new Date(anchor.getFullYear(), anchor.getMonth() + step, 1)) }
  }
}

/** Cambiando modalità l'ancora torna a oggi: è il comportamento che ci si aspetta. */
export function changeMode(mode: PeriodMode): Period {
  return { mode, anchor: today() }
}
