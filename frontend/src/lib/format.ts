/** Formattazione italiana: un solo posto, così importi e date sono identici ovunque. */

const money = new Intl.NumberFormat('it-IT', {
  style: 'currency',
  currency: 'EUR',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

const moneyNoSign = new Intl.NumberFormat('it-IT', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

/** Gli importi arrivano dall'API come **stringhe** decimali, mai come numeri:
 *  convertirli tardi e una volta sola evita gli errori di arrotondamento del float. */
export function toNumber(value: string | number | null | undefined): number {
  if (value === null || value === undefined) return 0
  return typeof value === 'number' ? value : Number(value)
}

export function formatMoney(value: string | number | null | undefined): string {
  return money.format(toNumber(value))
}

export function formatAmount(value: string | number | null | undefined): string {
  return moneyNoSign.format(toNumber(value))
}

/** Importo con segno esplicito, per la colonna della tabella Storico. */
export function formatSigned(value: string | number, negative: boolean): string {
  const n = Math.abs(toNumber(value))
  return `${negative ? '−' : '+'} ${moneyNoSign.format(n)} €`
}

const dateLong = new Intl.DateTimeFormat('it-IT', {
  weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
})
const dateShort = new Intl.DateTimeFormat('it-IT', { day: '2-digit', month: '2-digit', year: 'numeric' })

export function formatDateLong(date: Date): string {
  return dateLong.format(date)
}

export function formatDateISO(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number)
  return dateShort.format(new Date(y, m - 1, d))
}

export function formatTime(date: Date): string {
  return date.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

/**
 * Converte un importo scritto all'italiana nel formato che l'API si aspetta.
 *
 *   "1.250,80"  ->  "1250.80"      separatore delle migliaia tolto, virgola in punto
 *   "1 250,80"  ->  "1250.80"      spazi tolti
 *   "45.30"     ->  "45.30"        il punto decimale resta com'è
 *
 * La distinzione fra punto-migliaia e punto-decimale si fa contando le cifre che lo
 * seguono: tre cifre attaccate a fine gruppo sono migliaia, tutto il resto è decimale.
 * Usata da ogni campo importo dell'applicazione: sta qui perché ce ne sia una sola.
 */
export function parseAmount(raw: string): string {
  return raw
    .trim()
    .replace(/\s/g, '')
    .replace(/\.(?=\d{3}(\D|$))/g, '')
    .replace(',', '.')
}
