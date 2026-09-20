import { useState } from 'react'
import type { Account, Entry } from '@/api/types'
import { AccountForm } from '@/components/AccountForm'
import { EntryForm } from '@/components/EntryForm'
import { formatAmount, formatDateISO, formatMoney } from '@/lib/format'
import { KINDS } from '@/lib/kinds'
import { useAppData } from '@/state/AppData'
import styles from './AddEntryPage.module.css'

/**
 * Pagina 3 — aggiungi entry.
 *
 * La pagina è quasi vuota di proposito: tutto il lavoro lo fa `<EntryForm />`, che è il
 * modulo riusabile. Qui si aggiunge solo il contesto attorno — i saldi dei conti e
 * l'elenco di ciò che si è appena inserito.
 */
export function AddEntryPage() {
  const { accounts, categories, refreshAccounts, addAccount } = useAppData()
  const [recent, setRecent] = useState<Entry[]>([])
  // Aperto da solo finché non esiste nessun conto: senza conti non si può fare nulla,
  // e lasciare l'utente davanti a un messaggio senza un modo per agire è inutile.
  const [creatingAccount, setCreatingAccount] = useState(false)
  const showAccountForm = creatingAccount || accounts.length === 0

  function handleAccountCreated(account: Account) {
    addAccount(account)
    setCreatingAccount(false)
  }

  async function handleSaved(entry: Entry) {
    setRecent((prev) => [entry, ...prev].slice(0, 8))
    // I saldi mostrati qui accanto sono appena cambiati.
    await refreshAccounts()
  }

  return (
    <>
      <section className="card">
        <h2 className={styles.title}>Nuova entry</h2>
        <EntryForm accounts={accounts} categories={categories} onSaved={handleSaved} />
      </section>

      <div className={styles.columns}>
        <section className="card">
          <div className={styles.head}>
            <h2 className={styles.title}>Conti</h2>
            {!showAccountForm && (
              <button type="button" className="btn" onClick={() => setCreatingAccount(true)}>
                + Nuovo conto
              </button>
            )}
          </div>

          {showAccountForm && (
            <AccountForm
              onCreated={handleAccountCreated}
              onCancel={accounts.length > 0 ? () => setCreatingAccount(false) : undefined}
            />
          )}

          {accounts.length === 0 ? (
            <div className="empty">Crea il primo conto per cominciare.</div>
          ) : (
            <ul className={styles.balances}>
              {accounts.map((account) => (
                <li key={account.id}>
                  <span>{account.name}</span>
                  <span className="num">{formatMoney(account.balance)}</span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="card">
          <h2 className={styles.title}>Appena inserite</h2>
          {recent.length === 0 ? (
            <div className="empty">Le entry aggiunte in questa sessione compaiono qui.</div>
          ) : (
            <ul className={styles.recent}>
              {recent.map((entry) => (
                <li key={entry.id}>
                  <span className="num muted">{formatDateISO(entry.date)}</span>
                  <span className={styles.what}>
                    {entry.description || entry.subcategory_name}
                  </span>
                  <span className="num" style={{ color: KINDS[entry.kind].color }}>
                    {KINDS[entry.kind].negative ? '−' : '+'} {formatAmount(entry.amount)} €
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </>
  )
}
