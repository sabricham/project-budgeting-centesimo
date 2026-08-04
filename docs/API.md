# API — Centesimo

**Fonte autoritativa:** l'OpenAPI generato da FastAPI su <https://localhost:8443/docs>
(schema grezzo su `/openapi.json`). Questo file è l'indice leggibile: se un giorno
divergesse, fa fede `/docs`.

Tutti gli endpoint sotto `/api/v1` richiedono `Authorization: Bearer <access_token>`,
tranne `login` e `refresh`. `/health` è pubblico.

## Convenzioni

| | |
|---|---|
| Importi | stringhe decimali: `"1250.00"` — mai float |
| Date | `"2026-07-30"`; istanti in ISO 8601 UTC |
| Liste | `?limit=&offset=` → `{"items": [...], "total": n, "limit": n, "offset": n}` |
| Errori | `{"error": {"code": "not_found", "message": "…"}}` |
| Concorrenza | nelle PATCH, campo opzionale `expected_updated_at` → `409 stale_update` |
| Eliminazioni | `DELETE` archivia/soft-delete; `?hard=true` elimina davvero quando è lecito |

Codici d'errore ricorrenti: `invalid_credentials`, `invalid_token`,
`invalid_refresh_token`, `session_expired`, `not_found`, `invalid`, `validation_error`,
`conflict`, `stale_update`, `account_in_use`, `category_in_use`, `budget_exists`,
`account_already_linked`.

---

## Servizio

| Metodo | Percorso | Descrizione |
|---|---|---|
| `GET` | `/health` | Stato di API, database e scheduler. Usato dall'healthcheck Docker |

## Autenticazione (§1.1)

| Metodo | Percorso | Descrizione |
|---|---|---|
| `POST` | `/api/v1/auth/login` | `{username, password}` → access token + refresh token |
| `POST` | `/api/v1/auth/refresh` | Nuovo access token; il refresh token viene **ruotato** |
| `POST` | `/api/v1/auth/logout` | Revoca il refresh token indicato |
| `GET` | `/api/v1/auth/me` | Profilo dell'utente autenticato |
| `POST` | `/api/v1/auth/change-password` | Cambia password e revoca **tutte** le sessioni |

## Conti (§2.2)

| Metodo | Percorso | Descrizione |
|---|---|---|
| `GET` | `/api/v1/accounts` | Elenco con saldo calcolato. `?include_archived=&type=` |
| `POST` | `/api/v1/accounts` | Crea un conto |
| `GET` | `/api/v1/accounts/{id}` | Dettaglio con saldo |
| `PATCH` | `/api/v1/accounts/{id}` | Modifica (il `type` non è modificabile) |
| `DELETE` | `/api/v1/accounts/{id}` | Archivia; `?hard=true` elimina solo se senza movimenti |
| `POST` | `/api/v1/accounts/{id}/unarchive` | Riattiva un conto archiviato |

Tipi: `bank`, `cash`, `card`, `ewallet`, `investment`, `savings_goal`, `liability`.
Per i conti `investment` la risposta include anche `cash_balance` e `holdings_value`.

## Categorie (§2.4)

| Metodo | Percorso | Descrizione |
|---|---|---|
| `GET` | `/api/v1/categories` | `?include_archived=&type=income|expense` |
| `POST` | `/api/v1/categories` | Crea; con `parent_category_id` diventa sotto-categoria |
| `GET` | `/api/v1/categories/{id}` | Dettaglio |
| `PATCH` | `/api/v1/categories/{id}` | Modifica (il `type` non è modificabile) |
| `DELETE` | `/api/v1/categories/{id}` | Archivia; `?hard=true` solo se mai usata |

Massimo due livelli di annidamento.

## Budget (§2.5)

| Metodo | Percorso | Descrizione |
|---|---|---|
| `GET` | `/api/v1/budgets` | Limite **più** `spent_this_month`, `remaining`, `usage_ratio` |
| `POST` | `/api/v1/budgets` | Un solo budget per categoria (di spesa) |
| `PATCH` | `/api/v1/budgets/{id}` | Cambia limite o lo disattiva |
| `DELETE` | `/api/v1/budgets/{id}` | Elimina |

Il consumo di una categoria padre include le sue sotto-categorie.

## Transazioni (§2.6)

| Metodo | Percorso | Descrizione |
|---|---|---|
| `GET` | `/api/v1/transactions` | `?account_id=&category_id=&type=&status=&date_from=&date_to=&search=&include_deleted=&limit=&offset=` |
| `POST` | `/api/v1/transactions` | Crea (default `status=confirmed`) |
| `GET` | `/api/v1/transactions/{id}` | Dettaglio |
| `PATCH` | `/api/v1/transactions/{id}` | Modifica |
| `DELETE` | `/api/v1/transactions/{id}` | Soft-delete; `?hard=true` elimina |
| `POST` | `/api/v1/transactions/{id}/restore` | Annulla il soft-delete |

Solo le transazioni `confirmed` entrano nei saldi e nei report. Il filtro
`category_id` include automaticamente le sotto-categorie.

## Trasferimenti (§2.3)

| Metodo | Percorso | Descrizione |
|---|---|---|
| `GET` | `/api/v1/transfers` | `?account_id=` (origine o destinazione) |
| `POST` | `/api/v1/transfers` | Sposta denaro fra due conti propri |
| `GET` | `/api/v1/transfers/{id}` | Dettaglio |
| `PATCH` | `/api/v1/transfers/{id}` | Modifica |
| `DELETE` | `/api/v1/transfers/{id}` | Soft-delete |

Mai categorizzati, mai nei report di spesa. Non ammessi su conti `liability` né fra valute
diverse.

## Debiti e prestiti (§2.10)

| Metodo | Percorso | Descrizione |
|---|---|---|
| `GET` | `/api/v1/liabilities` | Storico degli snapshot. `?account_id=&date_from=&date_to=` |
| `POST` | `/api/v1/liabilities` | Registra il capitale residuo a una data |
| `DELETE` | `/api/v1/liabilities/{id}` | Elimina uno snapshot |

Il saldo di un conto `liability` è l'ultimo `residual_amount` registrato. Le rate pagate
si registrano come normali spese dal conto corrente.

## Obiettivi di risparmio (§2.9)

| Metodo | Percorso | Descrizione |
|---|---|---|
| `GET` | `/api/v1/goals` | Con `current_amount`, `progress`, `monthly_required` |
| `POST` | `/api/v1/goals` | Collegato a un conto `savings_goal` non ancora usato |
| `GET` | `/api/v1/goals/{id}` | Dettaglio |
| `PATCH` | `/api/v1/goals/{id}` | Modifica (il conto collegato non si cambia) |
| `DELETE` | `/api/v1/goals/{id}` | Elimina l'obiettivo, non il conto |

## Ricorrenze (§2.7)

| Metodo | Percorso | Descrizione |
|---|---|---|
| `GET` | `/api/v1/recurring` | Definizioni + `next_occurrence` |
| `POST` | `/api/v1/recurring` | Crea e genera subito le occorrenze |
| `GET` | `/api/v1/recurring/{id}` | Dettaglio |
| `PATCH` | `/api/v1/recurring/{id}` | Modifica e rigenera le occorrenze future non confermate |
| `DELETE` | `/api/v1/recurring/{id}` | Disattiva; `?hard=true` elimina la definizione |
| `GET` | `/api/v1/recurring/upcoming` | Occorrenze da confermare. `?days=30` |
| `POST` | `/api/v1/recurring/generate` | Esegue a richiesta il job di generazione |
| `POST` | `/api/v1/recurring/occurrences/{tx_id}/confirm` | Conferma, con `amount` opzionale |
| `POST` | `/api/v1/recurring/occurrences/{tx_id}/skip` | Salta l'occorrenza |

Forma di `occurrence_days` per frequenza:

```jsonc
"monthly"      : [1, 15]                      // giorni del mese; il 31 slitta a fine mese
"weekly"       : [0, 3]                       // 0 = lunedì
"yearly"       : [{"month": 1, "day": 1}]
"custom_dates" : ["2026-03-01", "2026-09-15"]
```

`interval` = ogni N periodi. Con `occurrence_days` vuoto la cadenza si deduce da
`start_date`.

## Report (§2.10, §2.11)

| Metodo | Percorso | Descrizione |
|---|---|---|
| `GET` | `/api/v1/reports/net-worth` | Σ asset − Σ liability. `?as_of=` |
| `GET` | `/api/v1/reports/timeseries` | `?metric=balance\|spending\|income\|net_worth&range=day\|week\|month\|year&account_ids=1,2` |
| `GET` | `/api/v1/reports/by-category` | `?type=expense\|income&range=` oppure `date_from`/`date_to` |
| `POST` | `/api/v1/reports/net-worth/snapshot` | Forza lo snapshot di oggi |

Granularità: `day` → un punto; `week`/`month` → un punto per giorno; `year` → un punto per
mese. `timeseries` è volutamente generico: nuovi widget nel client non richiedono nuovi
endpoint.

## Dashboard (§2.11)

| Metodo | Percorso | Descrizione |
|---|---|---|
| `GET` | `/api/v1/dashboard/widgets` | Configurazione dei widget |
| `POST` | `/api/v1/dashboard/widgets` | Crea (`type`, posizione, `config` JSON libero) |
| `PATCH` | `/api/v1/dashboard/widgets/{id}` | Modifica |
| `DELETE` | `/api/v1/dashboard/widgets/{id}` | Elimina |

`config` è JSON libero: un nuovo tipo di widget non richiede migrazioni.

## Portafoglio (§2.8)

| Metodo | Percorso | Descrizione |
|---|---|---|
| `GET` | `/api/v1/portfolio/{account_id}` | Liquidità, posizioni, valore, P/L realizzato e non |
| `GET` | `/api/v1/portfolio/{account_id}/transactions` | Storico operazioni. `?ticker=` |
| `POST` | `/api/v1/portfolio/transactions` | `buy` / `sell` / `dividend` |
| `GET` | `/api/v1/portfolio/prices` | Contenuto della cache prezzi |
| `PUT` | `/api/v1/portfolio/prices/{ticker}` | Prezzo manuale (funziona senza API key) |
| `GET` | `/api/v1/portfolio/fx` | Cambi in cache |
| `PUT` | `/api/v1/portfolio/fx/{base}/{quote}` | Cambio manuale: 1 `base` = `rate` `quote` |
| `POST` | `/api/v1/portfolio/refresh-prices` | Forza l'aggiornamento dal provider esterno |

Effetti di un'operazione:

- **buy** — liquidità `−(quantità × prezzo + commissioni)`; ricalcolo della media ponderata
  di carico, commissioni incluse;
- **sell** — liquidità `+(quantità × prezzo − commissioni)`; salva la plusvalenza
  realizzata `(prezzo − carico medio) × quantità − commissioni`;
- **dividend** — liquidità `+ importo`, nessun effetto sulla quantità.

Le posizioni restano nella valuta nativa del titolo; la conversione avviene solo in
valorizzazione. Il movimento di cassa viene invece convertito nella valuta del conto al
momento dell'operazione: se manca il cambio, l'operazione è rifiutata con un messaggio che
indica quale cambio impostare.
