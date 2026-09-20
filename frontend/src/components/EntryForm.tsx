import { useEffect, useMemo, useState } from 'react'
import { entries as entriesApi } from '@/api/endpoints'
import { ApiError } from '@/api/client'
import type { Account, Category, Entry } from '@/api/types'
import { parseAmount } from '@/lib/format'
import { KIND_LIST, type EntryKind } from '@/lib/kinds'
import { today } from '@/lib/periods'
import { AccountSelector } from './AccountSelector'
import styles from './EntryForm.module.css'

/**
 * Modulo di inserimento di una entry.
 *
 * È **il** blocco riusabile del progetto: si presenta come un riquadro autonomo e va
 * usato identico ovunque si possa inserire un movimento — oggi la pagina «Aggiungi
 * entry», domani una finestra modale dallo Storico o un riquadro dentro il Recap.
 * Non conosce la pagina che lo ospita: riceve i dati di cui ha bisogno e comunica
 * l'esito con `onSaved`.
 *
 * Il conto di destinazione compare **solo** per i movimenti di tipo investimento,
 * perché solo lì ha significato: investire è spostare denaro fra due conti propri.
 */
export interface EntryFormProps {
  accounts: Account[]
  categories: Category[]
  /** Conto preselezionato: utile quando il modulo si apre dal dettaglio di un conto. */
  defaultAccountId?: number | null
  onSaved?: (entry: Entry) => void
  /** Testo del pulsante, per quando il modulo vive dentro una modale. */
  submitLabel?: string
}

const EMPTY = {
  date: today(),
  description: '',
  amount: '',
  kind: 'expense' as EntryKind,
  categoryId: null as number | null,
  subcategoryId: null as number | null,
  toAccountId: null as number | null,
}

export function EntryForm({
  accounts,
  categories,
  defaultAccountId = null,
  onSaved,
  submitLabel = 'Aggiungi entry',
}: EntryFormProps) {
  const usableAccounts = useMemo(() => accounts.filter((a) => !a.archived), [accounts])

  const [accountId, setAccountId] = useState<number | null>(
    defaultAccountId ?? usableAccounts[0]?.id ?? null,
  )
  // Quando il primo conto viene creato mentre questo modulo è già a schermo, o quando
  // il conto scelto viene archiviato, la selezione va riportata su un conto valido:
  // altrimenti resta su «Scegli un conto…» anche se la scelta è una sola.
  useEffect(() => {
    if (usableAccounts.length === 0) return
    if (accountId === null || !usableAccounts.some((a) => a.id === accountId)) {
      setAccountId(defaultAccountId ?? usableAccounts[0].id)
    }
  }, [usableAccounts, accountId, defaultAccountId])

  const [form, setForm] = useState(EMPTY)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)

  const subcategories = useMemo(
    () => categories.find((c) => c.id === form.categoryId)?.subcategories ?? [],
    [categories, form.categoryId],
  )

  const isInvestment = form.kind === 'investment'

  function set<K extends keyof typeof EMPTY>(key: K, value: (typeof EMPTY)[K]) {
    setForm((prev) => ({ ...prev, [key]: value }))
    setDone(null)
  }

  function validate(): string | null {
    if (accountId === null) return 'Scegli il conto'
    if (!form.date) return 'Scegli la data'
    const amount = Number(parseAmount(form.amount))
    if (!Number.isFinite(amount) || amount <= 0) return "Inserisci un importo maggiore di zero"
    if (form.subcategoryId === null) return 'Scegli categoria e sottocategoria'
    if (isInvestment && form.toAccountId === null) {
      return 'Un investimento ha bisogno del conto di destinazione'
    }
    if (isInvestment && form.toAccountId === accountId) {
      return 'Il conto di destinazione deve essere diverso da quello di partenza'
    }
    return null
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    const problem = validate()
    if (problem) {
      setError(problem)
      return
    }

    setSaving(true)
    setError(null)
    try {
      const saved = await entriesApi.create({
        date: form.date,
        description: form.description.trim(),
        amount: parseAmount(form.amount),
        kind: form.kind,
        account_id: accountId!,
        subcategory_id: form.subcategoryId!,
        to_account_id: isInvestment ? form.toAccountId : null,
      })
      // Data, tipo e conto restano: inserire più movimenti di fila è il caso normale.
      setForm((prev) => ({ ...prev, description: '', amount: '' }))
      setDone('Entry aggiunta.')
      onSaved?.(saved)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Non è stato possibile salvare la entry')
    } finally {
      setSaving(false)
    }
  }

  if (usableAccounts.length === 0) {
    return (
      <div className="empty">
        Non c'è ancora nessun conto. Creane uno per poter registrare dei movimenti.
      </div>
    )
  }

  return (
    <form className={styles.form} onSubmit={submit}>
      <div className={styles.kinds} role="group" aria-label="Tipo di movimento">
        {KIND_LIST.map((info) => (
          <button
            key={info.kind}
            type="button"
            className={form.kind === info.kind ? `${styles.kind} ${styles.kindOn}` : styles.kind}
            style={form.kind === info.kind ? { borderColor: info.color, color: info.color } : undefined}
            onClick={() => {
              set('kind', info.kind)
              if (info.kind !== 'investment') set('toAccountId', null)
            }}
          >
            {info.label}
          </button>
        ))}
      </div>

      <div className={styles.grid}>
        <div className="field">
          <label htmlFor="entry-account">{isInvestment ? 'Conto di partenza' : 'Conto'}</label>
          <AccountSelector
            accounts={usableAccounts}
            value={accountId}
            onChange={setAccountId}
            allowAll={false}
            layout="block"
          />
        </div>

        {isInvestment && (
          <div className="field">
            <label>Conto di destinazione</label>
            <AccountSelector
              accounts={usableAccounts.filter((a) => a.id !== accountId)}
              value={form.toAccountId}
              onChange={(value) => set('toAccountId', value)}
              allowAll={false}
              layout="block"
            />
          </div>
        )}

        <div className="field">
          <label htmlFor="entry-date">Data</label>
          <input
            id="entry-date"
            type="date"
            value={form.date}
            onChange={(e) => set('date', e.target.value)}
            required
          />
        </div>

        <div className="field">
          <label htmlFor="entry-amount">Importo</label>
          <input
            id="entry-amount"
            inputMode="decimal"
            placeholder="0,00"
            value={form.amount}
            onChange={(e) => set('amount', e.target.value)}
            required
          />
        </div>

        <div className="field">
          <label htmlFor="entry-category">Categoria</label>
          <select
            id="entry-category"
            value={form.categoryId ?? ''}
            onChange={(e) => {
              const id = e.target.value === '' ? null : Number(e.target.value)
              setForm((prev) => ({ ...prev, categoryId: id, subcategoryId: null }))
              setDone(null)
            }}
            required
          >
            <option value="">Scegli…</option>
            {categories.map((category) => (
              <option key={category.id} value={category.id}>
                {category.name}
              </option>
            ))}
          </select>
        </div>

        <div className="field">
          <label htmlFor="entry-subcategory">Sottocategoria</label>
          <select
            id="entry-subcategory"
            value={form.subcategoryId ?? ''}
            onChange={(e) => set('subcategoryId', e.target.value === '' ? null : Number(e.target.value))}
            disabled={form.categoryId === null}
            required
          >
            <option value="">{form.categoryId === null ? 'Scegli prima la categoria' : 'Scegli…'}</option>
            {subcategories.map((sub) => (
              <option key={sub.id} value={sub.id}>
                {sub.name}
              </option>
            ))}
          </select>
        </div>

        <div className={`field ${styles.wide}`}>
          <label htmlFor="entry-description">Descrizione</label>
          <input
            id="entry-description"
            value={form.description}
            onChange={(e) => set('description', e.target.value)}
            placeholder="Facoltativa"
            maxLength={255}
          />
        </div>
      </div>

      {error && <div className="error-box">{error}</div>}
      {done && <div className="ok-box">{done}</div>}

      <div className={styles.actions}>
        <button type="submit" className="btn btn-primary" disabled={saving}>
          {saving ? 'Salvataggio…' : submitLabel}
        </button>
      </div>
    </form>
  )
}
