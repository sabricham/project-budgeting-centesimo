import { useState } from 'react'
import { ApiError } from '@/api/client'
import { auth } from '@/api/endpoints'
import styles from './LoginPage.module.css'

/**
 * Schermata di accesso.
 *
 * L'applicazione è raggiungibile da internet: questa è l'unica barriera davanti ai dati,
 * quindi il server limita i tentativi per indirizzo e qui ci limitiamo a mostrarne il
 * messaggio senza dare indizi su cosa fosse sbagliato fra utente e password.
 */
export function LoginPage({ onLoggedIn }: { onLoggedIn: () => void }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await auth.login(username.trim(), password)
      onLoggedIn()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Accesso non riuscito')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className={styles.page}>
      <form className={`card ${styles.box}`} onSubmit={submit}>
        <h1 className={styles.title}>Centesimo</h1>
        <p className="muted">Accedi per continuare.</p>

        <div className="field">
          <label htmlFor="username">Nome utente</label>
          <input
            id="username"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoFocus
            required
          />
        </div>

        <div className="field">
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>

        {error && <div className="error-box">{error}</div>}

        <button type="submit" className="btn btn-primary" disabled={busy}>
          {busy ? 'Accesso…' : 'Accedi'}
        </button>
      </form>
    </div>
  )
}
