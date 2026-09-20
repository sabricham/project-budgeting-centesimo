import { useState } from 'react'
import { ApiError } from '@/api/client'
import { accounts as accountsApi } from '@/api/endpoints'
import type { Account } from '@/api/types'
import { parseAmount } from '@/lib/format'
import styles from './AccountForm.module.css'

/**
 * Modulo di creazione di un conto.
 *
 * Stesso principio di `EntryForm`: un blocco autonomo che non conosce la pagina che lo
 * ospita. Oggi vive dentro «Aggiungi entry», accanto ai saldi; se un giorno arriverà una
 * pagina dedicata ai conti si sposta lì senza modifiche.
 */
const TIPI: { value: string; label: string }[] = [
  { value: 'bank', label: 'Conto bancario' },
  { value: 'cash', label: 'Contanti' },
  { value: 'ewallet', label: 'Portafoglio elettronico' },
  { value: 'card', label: 'Carta' },
  { value: 'investment', label: 'Investimento' },
  { value: 'savings', label: 'Risparmio' },
  { value: 'other', label: 'Altro' },
]

export function AccountForm({
  onCreated,
  onCancel,
}: {
  onCreated: (account: Account) => void
  onCancel?: () => void
}) {
  const [name, setName] = useState('')
  const [type, setType] = useState('bank')
  const [initial, setInitial] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!name.trim()) {
      setError('Dai un nome al conto')
      return
    }

    const saldo = initial.trim() === '' ? '0' : parseAmount(initial)
    if (!Number.isFinite(Number(saldo))) {
      setError('Il saldo attuale non è un importo valido')
      return
    }

    setSaving(true)
    setError(null)
    try {
      const created = await accountsApi.create({
        name: name.trim(),
        type,
        // Il saldo di partenza è quello che il conto ha oggi, prima di registrare
        // qualunque movimento: senza, il patrimonio partirebbe da zero.
        initial_balance: saldo,
        currency: 'EUR',
      })
      setName('')
      setInitial('')
      onCreated(created)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Non è stato possibile creare il conto')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className={styles.form} onSubmit={submit}>
      <div className={styles.grid}>
        <div className="field">
          <label htmlFor="account-name">Nome</label>
          <input
            id="account-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Es. Intesa San Paolo"
            maxLength={120}
            autoFocus
            required
          />
        </div>

        <div className="field">
          <label htmlFor="account-type">Tipo</label>
          <select id="account-type" value={type} onChange={(e) => setType(e.target.value)}>
            {TIPI.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </div>

        <div className="field">
          <label htmlFor="account-initial">Saldo attuale</label>
          <input
            id="account-initial"
            inputMode="decimal"
            value={initial}
            onChange={(e) => setInitial(e.target.value)}
            placeholder="0,00"
          />
        </div>
      </div>

      {error && <div className="error-box">{error}</div>}

      <div className={styles.actions}>
        {onCancel && (
          <button type="button" className="btn" onClick={onCancel}>
            Annulla
          </button>
        )}
        <button type="submit" className="btn btn-primary" disabled={saving}>
          {saving ? 'Creazione…' : 'Crea conto'}
        </button>
      </div>
    </form>
  )
}
