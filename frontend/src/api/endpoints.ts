/** Un punto solo in cui è scritto com'è fatta l'API. Le pagine chiamano queste funzioni. */

import { request, tokens } from './client'
import type {
  Account,
  Category,
  Entry,
  EntryCreate,
  NetWorthSeries,
  Page,
  SortField,
  Summary,
  User,
} from './types'

export const auth = {
  async login(username: string, password: string): Promise<void> {
    const data = await request<{ access_token: string; refresh_token: string }>('/auth/login', {
      method: 'POST',
      body: { username, password },
    })
    tokens.save(data.access_token, data.refresh_token)
  },
  me: () => request<User>('/auth/me'),
  async logout(): Promise<void> {
    const refresh_token = tokens.refresh
    if (refresh_token) {
      // Se la revoca fallisce (rete assente, token già scaduto) usciamo lo stesso:
      // lasciare l'utente dentro sarebbe la reazione sbagliata.
      await request('/auth/logout', { method: 'POST', body: { refresh_token } }).catch(() => {})
    }
    tokens.clear()
  },
}

export const accounts = {
  list: (includeArchived = false) =>
    request<Account[]>('/accounts', { params: { include_archived: includeArchived } }),
  types: () => request<string[]>('/accounts/types'),
  create: (body: Partial<Account>) => request<Account>('/accounts', { method: 'POST', body }),
  update: (id: number, body: Partial<Account>) =>
    request<Account>(`/accounts/${id}`, { method: 'PATCH', body }),
  remove: (id: number) => request<void>(`/accounts/${id}`, { method: 'DELETE' }),
}

export const categories = {
  list: () => request<Category[]>('/categories'),
}

export interface EntryQuery {
  date_from?: string
  date_to?: string
  account_id?: number | null
  kind?: string | null
  category_id?: number | null
  search?: string
  sort?: SortField
  order?: 'asc' | 'desc'
  limit?: number
  offset?: number
}

export const entries = {
  list: (query: EntryQuery) => request<Page<Entry>>('/entries', { params: { ...query } }),
  create: (body: EntryCreate) => request<Entry>('/entries', { method: 'POST', body }),
  update: (id: number, body: Partial<EntryCreate>) =>
    request<Entry>(`/entries/${id}`, { method: 'PATCH', body }),
  remove: (id: number) => request<void>(`/entries/${id}`, { method: 'DELETE' }),
}

export const reports = {
  netWorthSeries: (date_from: string, date_to: string, account_id?: number | null) =>
    request<NetWorthSeries>('/reports/net-worth-series', {
      params: { date_from, date_to, account_id },
    }),
  summary: (date_from: string, date_to: string, account_id?: number | null) =>
    request<Summary>('/reports/summary', { params: { date_from, date_to, account_id } }),
}
