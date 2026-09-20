/** I tre tipi di movimento, con le etichette e i colori usati ovunque nell'interfaccia. */

export type EntryKind = 'income' | 'expense' | 'investment'

export interface KindInfo {
  kind: EntryKind
  label: string
  /** true se il movimento fa scendere il conto di partenza */
  negative: boolean
  color: string
}

export const KINDS: Record<EntryKind, KindInfo> = {
  income: { kind: 'income', label: 'Entrata', negative: false, color: 'var(--income)' },
  expense: { kind: 'expense', label: 'Uscita', negative: true, color: 'var(--expense)' },
  investment: { kind: 'investment', label: 'Investimento', negative: true, color: 'var(--investment)' },
}

export const KIND_LIST: KindInfo[] = [KINDS.income, KINDS.expense, KINDS.investment]
