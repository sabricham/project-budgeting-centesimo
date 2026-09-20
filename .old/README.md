# `.old/` — archivio della versione 1 di Centesimo

Qui dentro c'è **tutto il progetto come era il 2026-09-20**, prima della riscrittura v2.
Non è codice morto da ignorare: è un magazzino di pezzi funzionanti e già testati, da cui
ripescare quando una funzionalità verrà reintrodotta nella v2.

Niente qui viene compilato, eseguito o importato dalla v2. È materiale di consultazione.

## Perché è stato archiviato

La v1 era un backend FastAPI molto ampio (69 rotte, 16 tabelle, 3 job schedulati) più un
client desktop Windows in WPF. La v2 punta a un perimetro molto più stretto — conti, entry,
selettore di periodo, tre pagine web — con un'architettura modulare e **nessun client nativo**.
Invece di smontare la v1 pezzo per pezzo si è preferito ripartire da un albero pulito,
tenendo la v1 intera e consultabile.

Contesto utile: al momento dell'archiviazione il **database di produzione era vuoto**
(0 utenti, 0 conti, 0 categorie, 0 transazioni). Nessun dato reale è stato perso e non
esisteva nulla da migrare.

## Mappa dell'archivio

| Percorso | Cosa contiene |
|---|---|
| `.old/server/` | backend FastAPI completo (app, alembic, test, Dockerfile, entrypoint) |
| `.old/client/` | client desktop WPF / .NET 10, soluzione `Centesimo.sln` |
| `.old/docs/` | i 4 documenti della v1 — vedi sotto, il più prezioso è `PROJECT_MEMORY.md` |
| `.old/docker-compose.yml` | stack v1: Postgres + API su HTTPS 8443 con certificato self-signed |
| `.old/.env.example` | variabili della v1, incluse quelle del certificato e del provider prezzi |
| `.old/secrets/` | solo i file `.example`; i segreti veri non sono mai stati nel repository |
|  `.old/README-v1-originale.md` | il README originale del progetto (13 KB, panoramica completa della v1) |

### I documenti della v1 (`.old/docs/`)

- **`PROJECT_MEMORY.md`** — il più utile dei quattro. Contiene il **log storico delle
  decisioni architetturali** (38 righe con motivazione e alternative scartate) e un
  changelog molto dettagliato dei bug trovati e risolti. Da leggere prima di reintrodurre
  qualunque funzionalità: spiega *perché* le cose erano fatte in un certo modo.
- **`ARCHITETTURA_CENTESIMO.md`** — il documento di architettura della v1, 425 righe.
  Le sezioni sul modello dati restano valide come ragionamento anche se lo schema v2 è diverso.
- **`API.md`** — elenco degli endpoint v1.
- **`DEPLOY.md`** — procedura di deploy v1 (macchina Ubuntu, certificato self-signed, backup).

## Catalogo del backend v1

Legenda dell'ultima colonna: **↺** = già riportato nella v2, **☆** = candidato probabile per
una fase futura, **✕** = fuori dalla direzione attuale.

| Modulo | Cosa faceva | Tabelle | Endpoint | |
|---|---|---|---|---|
| `routers/auth.py` + `auth/` | login JWT, refresh token opachi revocabili e ruotati, cambio password | `users`, `refresh_tokens` | `/auth/login·token·refresh·logout·me·change-password` | ↺ |
| `routers/accounts.py` | CRUD conti con archiviazione e saldo calcolato | `accounts` | `/accounts` + `/{id}/unarchive` | ↺ |
| `routers/categories.py` | CRUD categorie con sotto-categorie via self-FK, max 2 livelli | `categories` | `/categories` | ↺ (rifatto: due tabelle distinte) |
| `routers/transactions.py` | CRUD entrate/uscite, soft-delete e ripristino, filtri e paginazione | `transactions` | `/transactions` + `/{id}/restore` | ↺ (diventa `entries`) |
| `routers/transfers.py` | movimenti fra due conti, esclusi dai report di spesa | `transfers` | `/transfers` | ↺ (assorbito dal tipo `investment`) |
| `routers/reports.py` | patrimonio netto, serie temporali, ripartizione per categoria | `net_worth_snapshots` | `/reports/net-worth·timeseries·by-category` | ↺ (parziale) |
| `routers/budgets.py` | limiti di spesa mensili per categoria, con speso e residuo calcolati dal server; il consumo di una categoria padre include le figlie | `budgets` | `/budgets` | ☆ |
| `routers/goals.py` | obiettivi di risparmio sovrapposti a un conto, con progresso e accantonamento mensile necessario | `goals` | `/goals` | ☆ |
| `routers/liabilities.py` | debiti e prestiti a modello snapshot: si registra il capitale residuo, non si somma le rate | `liability_updates` | `/liabilities` | ☆ |
| `routers/recurring.py` | abbonamenti e spese ricorrenti, incluse più date nello stesso periodo; generazione idempotente di occorrenze `projected` da confermare o saltare | `recurring_transactions` | `/recurring` + `/upcoming·generate·occurrences/{id}/confirm·skip` | ☆ |
| `routers/portfolio.py` + `services/portfolio.py` + `services/market_data.py` | **portafoglio investimenti completo**: posizioni con prezzo medio di carico, operazioni buy/sell/dividend, plusvalenze realizzate e non, prezzi di mercato da Alpha Vantage con cache e budget di richieste, conversione valute, ricostruzione storica del valore | `holdings`, `stock_transactions`, `price_cache`, `price_history`, `fx_rate_cache`, `api_budget` | `/portfolio/...` | ☆☆ (il pezzo più grosso e più probabile da recuperare) |
| `routers/dashboard.py` | widget della home a griglia fissa, con `config` JSONB libero per non migrare il DB ad ogni nuovo tipo di widget | `dashboard_widgets` | `/dashboard/widgets` | ☆ |
| `routers/settings.py` | provider dati di mercato configurabile a runtime, chiave API mascherata, azzeramento dei dati personali | `app_settings` | `/settings/market-data`, `/settings/reset-data` | ✕ |
| `scheduler.py` + `services/scheduler_jobs.py` | 3 job APScheduler nel container API: generazione ricorrenze, aggiornamento prezzi una volta al giorno, snapshot giornaliero del patrimonio | — | — | ☆ |
| `services/balances.py` | calcolo dei saldi dai movimenti, mai da una colonna | — | — | ↺ |
| `services/recurrence.py` | espansione delle regole di ricorrenza in date concrete | — | — | ☆ |
| `routers/common.py` | helper riusabili: `get_owned`, `paginate`, `apply_updates`, `check_concurrency` | — | — | ↺ |
| `errors.py` | eccezioni di dominio e handler per il formato d'errore uniforme | — | — | ↺ |
| `tests/` | 45 test pytest: 15 di logica pura + 30 di integrazione su un database `money_test` creato al volo | — | — | ↺ (approccio) |

## Catalogo del client WPF v1 (`.old/client/`)

Applicazione `Centesimo.Desktop`, .NET 10 su Windows, pattern MVVM. **Non verrà più
sviluppata**, ma le sue pagine documentano quali schermate erano state ritenute utili.

| Pagina | Logica che conteneva |
|---|---|
| `LoginWindow` | indirizzo del server modificabile e salvato solo dopo un login riuscito, refresh token nel Windows Credential Manager, certificato self-signed pinnato per impronta |
| `DashboardView` | home a griglia fissa di widget configurabili (saldo, budget residuo, patrimonio netto, prossime spese) |
| `AccountsView` | lista conti con saldo, dettaglio dei movimenti, trasferimenti, aggiornamento del residuo dei debiti |
| `CategoriesView` | gestione categorie e sotto-categorie insieme ai limiti di budget mensili |
| `RecurringView` | abbonamenti, calendario delle prossime occorrenze, conferma o salto della singola occorrenza |
| `PortfolioView` | posizioni e operazioni, selettore conto con «Tutti i conti», selettore di periodo da 1 mese a 5 anni, grafico del valore nel tempo, plus/minusvalenze in valore assoluto o percentuale |
| `GoalsView` | obiettivi di risparmio con barra di progresso verso il target |
| `ReportsView` | grafici a tutto schermo: patrimonio netto, andamento, ripartizione per categoria |
| `SettingsWindow` | dati dell'account, cambio password, riepilogo della connessione |

Pezzi non legati a WPF che restano interessanti come ragionamento:
`Controls/LineChart.cs` (grafico disegnato a mano su `Canvas`),
`Converters/Converters.cs` (formattazione italiana di importi, quantità e percentuali —
il changelog racconta perché la cultura del thread non basta in WPF),
`Services/CentesimoApi.cs` (client HTTP tipizzato sull'intera API v1).

## Come ripescare un pezzo

1. Leggi la riga corrispondente in `.old/docs/PROJECT_MEMORY.md`: dice *perché* era fatto così.
2. Guarda il servizio in `.old/server/app/services/` — è lì che sta la logica vera, i router
   sono quasi sempre solo validazione e serializzazione.
3. Porta il pezzo nella v2 come **nuovo modulo** sotto `backend/app/modules/`, non copiandolo
   com'è: la v1 aveva `models.py` e `schemas.py` unici e condivisi, la v2 tiene tutto dentro
   il modulo.
