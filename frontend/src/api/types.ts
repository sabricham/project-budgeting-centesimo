import type { EntryKind } from '@/lib/kinds'

/** Gli importi viaggiano come stringhe decimali: vedi `lib/format.ts`. */
export type Money = string

export interface User {
  id: number
  username: string
  display_name: string | null
  base_currency: string
}

export interface Account {
  id: number
  name: string
  type: string
  currency: string
  initial_balance: Money
  color: string | null
  archived: boolean
  notes: string | null
  balance: Money
}

export interface Subcategory {
  id: number
  name: string
  category_id: number
}

export interface Category {
  id: number
  name: string
  subcategories: Subcategory[]
}

export interface Entry {
  id: number
  date: string
  description: string
  amount: Money
  kind: EntryKind
  account_id: number
  to_account_id: number | null
  subcategory_id: number
  account_name: string | null
  to_account_name: string | null
  category_id: number | null
  category_name: string | null
  subcategory_name: string | null
}

export interface EntryCreate {
  date: string
  description: string
  amount: string
  kind: EntryKind
  account_id: number
  subcategory_id: number
  to_account_id?: number | null
}

export interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

export interface SeriesPoint {
  date: string
  value: Money
}

export interface NetWorthSeries {
  date_from: string
  date_to: string
  granularity: 'day' | 'week' | 'month'
  opening_balance: Money
  closing_balance: Money
  points: SeriesPoint[]
}

export interface Summary {
  date_from: string
  date_to: string
  income: Money
  expense: Money
  investment: Money
  net_change: Money
  closing_balance: Money
}

export type SortField = 'date' | 'amount' | 'category' | 'subcategory' | 'account' | 'kind'
