/**
 * Client HTTP dell'API.
 *
 * Due responsabilità e basta: allegare l'access token e rinnovarlo quando scade.
 * L'indirizzo dell'API non è configurabile e non deve esserlo: nginx serve il sito e
 * l'API sotto la stessa origine, quindi `/api/v1/...` funziona identico in sviluppo
 * (grazie al proxy di Vite), in rete locale e da internet via Tailscale.
 */

const BASE = '/api/v1'

const ACCESS_KEY = 'centesimo.access_token'
const REFRESH_KEY = 'centesimo.refresh_token'

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
  ) {
    super(message)
  }
}

export const tokens = {
  get access() {
    return localStorage.getItem(ACCESS_KEY)
  },
  get refresh() {
    return localStorage.getItem(REFRESH_KEY)
  },
  save(access: string, refresh: string) {
    localStorage.setItem(ACCESS_KEY, access)
    localStorage.setItem(REFRESH_KEY, refresh)
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY)
    localStorage.removeItem(REFRESH_KEY)
  },
}

/** Chiamate in volo durante un rinnovo: le mettiamo in coda su una sola Promise,
 *  altrimenti tre richieste scadute insieme brucerebbero tre refresh token. */
let refreshing: Promise<boolean> | null = null

async function parseError(response: Response): Promise<ApiError> {
  let message = `Errore ${response.status}`
  let code = 'error'
  try {
    const body = await response.json()
    if (body?.error) {
      message = body.error.message ?? message
      code = body.error.code ?? code
    }
  } catch {
    /* risposta senza corpo JSON: teniamo il messaggio generico */
  }
  return new ApiError(message, response.status, code)
}

async function tryRefresh(): Promise<boolean> {
  const refresh_token = tokens.refresh
  if (!refresh_token) return false

  if (!refreshing) {
    refreshing = (async () => {
      try {
        const response = await fetch(`${BASE}/auth/refresh`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token }),
        })
        if (!response.ok) {
          tokens.clear()
          return false
        }
        const data = await response.json()
        tokens.save(data.access_token, data.refresh_token)
        return true
      } catch {
        return false
      } finally {
        refreshing = null
      }
    })()
  }
  return refreshing
}

interface RequestOptions {
  method?: string
  body?: unknown
  params?: Record<string, string | number | boolean | null | undefined>
  /** interno: evita il ciclo infinito se anche la chiamata dopo il refresh dà 401 */
  retried?: boolean
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, params, retried = false } = options

  const url = new URL(`${BASE}${path}`, window.location.origin)
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value !== null && value !== undefined && value !== '') {
      url.searchParams.set(key, String(value))
    }
  }

  const headers: Record<string, string> = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const access = tokens.access
  if (access) headers.Authorization = `Bearer ${access}`

  const response = await fetch(url.toString(), {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  if (response.status === 401 && !retried && tokens.refresh) {
    if (await tryRefresh()) {
      return request<T>(path, { ...options, retried: true })
    }
  }

  if (!response.ok) throw await parseError(response)
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}
