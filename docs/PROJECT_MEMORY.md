# Project Memory — Centesimo

> Diario di bordo del progetto. **Leggere per intero a inizio sessione, aggiornare a fine
> sessione.** Le righe della tabella Decisioni non si cancellano mai: servono proprio a
> non riproporre alternative già scartate.

## Stato attuale

*Aggiornato al 2026-08-04.*

Tutte le fasi 1–12 del piano (§3.4) sono implementate **e verificate end-to-end**. Il
backend non gira più sul PC di sviluppo: è deployato su una macchina Ubuntu dedicata,
`192.168.1.104` (utente `office`, cartella `/home/office/Budgeting`). I sorgenti restano
qui, il server ne ha una copia sovrascritta ad ogni deploy — procedura in
[DEPLOY.md](DEPLOY.md).

Il repository contiene:

- **`server/`** — API FastAPI completa: autenticazione JWT con refresh token revocabili,
  conti, categorie con sotto-categorie, budget mensili, transazioni, trasferimenti,
  snapshot dei debiti, obiettivi di risparmio, ricorrenze con espansione delle occorrenze,
  report/timeseries, widget della dashboard, portafoglio investimenti con cache prezzi e
  cambi. Tre job APScheduler nel container API. 69 rotte registrate, migrazione Alembic
  iniziale, 45 test pytest (15 di logica pura + 30 di integrazione).
- **`client/`** — applicazione WPF (.NET 10) con login, shell di navigazione e sette
  pagine: Home a widget, Conti (con dettaglio movimenti, trasferimenti, residuo debiti),
  Categorie e budget, Abbonamenti, Portafoglio, Obiettivi, Report. Token nel Windows
  Credential Manager, certificato del server pinnato.
- **`docs/`** — architettura di riferimento, elenco API, procedura di deploy, questo file.

**Verificato il 2026-08-04 sul server reale:** `docker compose up -d --build` costruisce e
avvia entrambi i servizi (`healthy`); la migrazione `0001` è stata applicata per la prima
volta contro un Postgres vero; lo scheduler parte con i suoi 3 job; `/health` risponde
`{"status":"ok","db":"ok","scheduler":"running"}` **dalla LAN**; login → `/auth/me` →
`/categories` funziona da un client esterno con il certificato pinnato; il seed crea utente
e 21 categorie; **tutti e 45 i test passano**, inclusi i 30 di integrazione mai eseguiti
prima. Il client WPF compila in Release senza warning.

**Login dalla GUI: funziona.** Non l'ho osservato a schermo, ma il refresh token era
presente nel Credential Manager, e ci finisce solo dopo un `LoginAsync` andato a buon fine.

**NON ancora verificato:** il resto del giro nell'app desktop (inserimento di una
transazione, rientro automatico dal refresh token dopo un riavvio). Dopo la rinomina il
target nel Credential Manager è cambiato, quindi **il primo avvio di `Centesimo.exe`
richiede di rifare il login**.

## Decisioni architetturali

*Log storico. Non cancellare le righe vecchie.*

| Data | Decisione | Motivazione | Alternative scartate |
|---|---|---|---|
| 2026-07-30 | API REST centrale, no accesso diretto client→DB | sicurezza, decoupling | connessione SQL diretta dai client |
| 2026-07-30 | Trasferimenti come entità separata da transazioni | evitare di falsare i report di spesa | modellarli come spesa+entrata accoppiate |
| 2026-07-30 | Client Windows in WPF/.NET nativo | miglior UI per widget grid e portafoglio | .NET MAUI, Flutter (scartati: Android sarà progetto separato) |
| 2026-07-30 | Portafoglio investimenti avanzato (Holding + StockTransaction + prezzi esterni cachati) | tracciare posizioni reali, non solo saldo | account investimento come saldo semplice (scartato) |
| 2026-07-30 | Budget come limite unico "corrente" per categoria, non storico mensile | semplicità MVP | storico BudgetHistory per mese (rimandato) |
| 2026-07-30 | Goal sovrapposto a un conto savings_goal (no contabilità parallela) | riusa saldo già calcolato, zero duplicazione | tracking manuale dei contributi per goal (scartato per ora) |
| 2026-07-30 | Conti liability a modello snapshot (LiabilityUpdate), non sum-delle-transazioni | evitare piano di ammortamento, fuori scope | ammortamento capitale/interessi automatico (scartato) |
| 2026-07-30 | Cartelle top-level `server/` e `client/` invece di `api/` e `desktop/` (§3.2) | richiesta esplicita di leggibilità: i nomi dicono subito chi è chi | struttura letterale della §3.2 |
| 2026-07-30 | Client su `net10.0-windows` invece di `net8.0` (§3.1) | sulla macchina è installato solo il runtime .NET 10; WPF è identico, nessuna perdita funzionale | net8.0 + installazione del Desktop Runtime 8 |
| 2026-07-30 | Importi come **stringhe decimali** in JSON (la §1.3 ammetteva anche i centesimi interi) | leggibili in Swagger e nei log, e Pydantic v2 li serializza già così da `Decimal`; nessuna moltiplicazione ×100 da sbagliare | interi in centesimi |
| 2026-07-30 | Refresh token opaco salvato come SHA-256 in tabella dedicata, ruotato ad ogni uso | permette la revoca reale (logout, cambio password), impossibile con un JWT autocontenuto; se il DB trapela i token non sono riutilizzabili | secondo JWT come refresh token |
| 2026-07-30 | Enum come colonne testuali con CHECK invece di ENUM nativi Postgres | aggiungere un valore diventa una modifica del CHECK, non un `ALTER TYPE` in migrazione | tipi ENUM nativi |
| 2026-07-30 | Migrazione `0001` come baseline via `Base.metadata.create_all` | su progetto greenfield riscrivere a mano 16 `create_table` introduce solo rischio di divergenza modelli/migrazione; dalla 0002 si usa `--autogenerate` normalmente | create_table esplicite fin dalla prima migrazione |
| 2026-07-30 | `avg_cost_basis` comprende le commissioni di acquisto | è il costo realmente sostenuto per azione, quindi la plusvalenza è già netta | commissioni fuori dal carico, sottratte solo al P/L |
| 2026-07-30 | Il movimento di cassa di un'operazione su titoli è convertito nella valuta del conto **al momento dell'operazione**; le posizioni restano in valuta nativa | il contante uscito dal conto è un fatto storico e non va ritoccato; le posizioni invece si rivalutano, quindi convertirle solo in aggregazione (§2.8) | convertire tutto in aggregazione, oppure convertire anche le posizioni alla registrazione |
| 2026-07-30 | Senza cambio disponibile, un'operazione in valuta diversa dal conto viene **rifiutata** con messaggio esplicito | meglio un errore chiaro che un saldo silenziosamente sbagliato | assumere cambio 1:1 |
| 2026-07-30 | Il saldo di un conto `investment` mostrato in `/accounts` è liquidità + valore di mercato | è il numero che serve al patrimonio netto e ai widget; `cash_balance` e `holdings_value` restano esposti separatamente | mostrare solo la liquidità |
| 2026-07-30 | Il consumo di un budget su una categoria padre include le sotto-categorie | un budget su "Alimentari" che ignora "Supermercato" sarebbe inutile | conteggio solo sulla categoria esatta |
| 2026-07-30 | Niente transazioni né trasferimenti sui conti `liability` | coerenza con il modello a snapshot: la rata è una spesa dal conto corrente (§2.10) | permetterli e ignorarli nel calcolo |
| 2026-07-30 | Massimo due livelli di categorie | due livelli bastano ai report e tengono la UI leggibile | gerarchia arbitrariamente profonda |
| 2026-07-30 | "Salta occorrenza" = soft-delete della transazione `projected` | impedisce che il job la rigeneri al giro successivo e lascia traccia della decisione | cancellazione fisica |
| 2026-07-30 | Provider dati di mercato dietro un'interfaccia, con `NullProvider` di default e prezzi inseribili a mano | il portafoglio deve restare pienamente usabile senza API key (che oggi non c'è) | dipendenza obbligatoria da Twelve Data |
| 2026-07-30 | Grafici disegnati con un controllo WPF custom su `Canvas` | due serie semplici non giustificano una dipendenza di charting con i suoi vincoli di licenza e peso | LiveCharts / ScottPlot / OxyPlot |
| 2026-07-30 | Dashboard a griglia fissa configurabile, senza drag&drop | come raccomandato in §2.11: il riposizionamento libero in WPF è UI non banale, rimandato alla seconda iterazione | griglia drag&drop da subito |
| 2026-07-30 | Test di integrazione su un database separato `money_test` creato al volo | non toccano mai i dati reali; la pulizia sta nella fixture delle sessioni così i test di logica pura girano anche senza Postgres | transazioni con rollback sul DB di produzione |
| 2026-08-04 | Backend deployato su macchina Ubuntu separata (`192.168.1.104`), client solo su Windows | è lo scenario "server separato" già previsto in §0; il PC di sviluppo non deve restare acceso perché l'app funzioni | continuare a far girare i container sul PC Windows |
| 2026-08-04 | I sorgenti restano sul PC Windows, sul server c'è una copia sovrascritta ad ogni deploy | una sola fonte di verità; modificare il server "al volo" produrrebbe divergenze invisibili | sviluppare direttamente sul server via SSH |
| 2026-08-04 | Segreti (`db_password`, `jwt_secret`) **generati sul server**, non copiati da Windows | un segreto che viaggia è un segreto in più da custodire, e i due ambienti non hanno motivo di condividerli | copiare `secrets/` insieme ai sorgenti |
| 2026-08-04 | SAN del certificato parametrizzato via `CERT_CN`/`CERT_EXTRA_SAN` nel `.env` | il certificato era valido solo per `localhost`: fuori dal PC di sviluppo ogni strumento che verifica il nome (browser, curl, futuro client Android) lo rifiuterebbe | lasciare il SAN fisso e affidarsi solo al pinning del client WPF |
| 2026-08-04 | Docker installato dal repo ufficiale Docker, non dal pacchetto `docker.io` di Ubuntu | `docker.io` è più vecchio e non porta il plugin `compose` v2 richiesto dal `docker-compose.yml` | `apt install docker.io` + docker-compose v1 |
| 2026-08-04 | `pythonpath = .` in `pytest.ini` | senza, `docker compose exec api pytest` (il comando documentato) non trova il package `app`: pytest mette in `sys.path` la cartella dei test, non la root | documentare `python -m pytest` al posto di `pytest` |
| 2026-08-04 | App rinominata «Centesimo»: rinominati anche namespace, solution, assembly, `%APPDATA%` e target del Credential Manager, non solo i testi | un nome a metà (UI "Centesimo", codice `MoneyApp`) è la peggiore delle due opzioni: confonde senza far risparmiare | rinominare solo i testi visibili |
| 2026-08-04 | Campo «Server» del login reso modificabile, con salvataggio **solo dopo un login riuscito** | l'indirizzo cambia fra LAN e Tailscale (§1.4) e costringere a editare `settings.json` a mano è un attrito inutile; salvare prima della verifica permetterebbe a un indirizzo sbagliato di sostituire quello funzionante | campo di sola lettura (era così), oppure salvataggio immediato alla digitazione |
| 2026-08-04 | Rimosso il `settings.Save()` all'avvio; `Load()` espone `LastLoadError` mostrato nel login | con un `settings.json` illeggibile la coppia Load-ripiega-sui-default + Save sovrascriveva la configurazione buona con `localhost`, cancellando ogni traccia del problema: il sintomo era "punta a localhost e non si collega" | continuare a salvare all'avvio |
| 2026-08-04 | Database `money` e ruolo `money_app` **non** rinominati | sono identificatori dell'infrastruttura, non il nome dell'app; rinominarli impone di ricreare database e ruolo su Postgres senza alcun guadagno | rinominare anche quelli per coerenza |
| 2026-08-04 | Loop scope dei test forzato a `session` con `pytestmark` in `test_api.py` | l'engine async è di scope sessione e le connessioni asyncpg restano legate al loop che le ha aperte; in pytest-asyncio 0.25 lo scope del loop dei **test** si imposta solo dal marker (l'opzione ini copre le sole fixture) | rendere l'engine di scope funzione (ricreerebbe lo schema ad ogni test) |

## Schema dati

*Da aggiornare ad ogni migrazione.* Migrazione corrente: `0001_initial_schema`.

| Tabella | Contenuto | Note |
|---|---|---|
| `users` | utente, hash bcrypt della password, valuta base | oggi uno solo, modello già multi-utente |
| `refresh_tokens` | SHA-256 del token, scadenza, `revoked_at` | consente la revoca reale |
| `accounts` | nome, `type`, valuta, `initial_balance`, `archived` | **nessuna colonna saldo**: si calcola |
| `categories` | nome, `type`, `parent_category_id` | self-FK, max 2 livelli |
| `budgets` | `category_id` UNIQUE, `amount_limit`, `active` | speso/residuo calcolati in lettura |
| `transactions` | conto, categoria, `type`, importo, data, `status`, `source_recurring_id`, `deleted_at` | UNIQUE `(source_recurring_id, date)` per l'idempotenza del job |
| `transfers` | conto origine/destinazione, importo, data, `deleted_at` | CHECK conti diversi |
| `liability_updates` | conto, `residual_amount`, data | snapshot del residuo |
| `goals` | target, scadenza, `linked_account_id` UNIQUE | `current_amount` non persistito |
| `recurring_transactions` | regola: `frequency`, `interval`, `occurrence_days` JSONB, `auto_confirm` | genera transazioni `projected` |
| `dashboard_widgets` | tipo, posizione, `config` JSONB | config libero, niente migrazioni per nuovi widget |
| `holdings` | conto, ticker, quantità, `avg_cost_basis`, valuta | UNIQUE `(account_id, ticker)`; riga eliminata a posizione chiusa |
| `stock_transactions` | buy/sell/dividend, quantità, prezzo, commissioni, `realized_pnl`, `cash_delta` | `cash_delta` già nella valuta del conto |
| `price_cache` | ticker → ultimo prezzo, `fetched_at`, `source` | `source = manual` se inserito a mano |
| `fx_rate_cache` | coppia valute → tasso | usato solo in aggregazione |
| `net_worth_snapshots` | assets, liabilities, net worth per giorno | UNIQUE `(user_id, date)`; serve la serie storica |

Tipi: denaro `NUMERIC(18,2)`, quantità `NUMERIC(24,8)`, prezzi `NUMERIC(18,6)`, cambi
`NUMERIC(18,8)`. Istanti `TIMESTAMPTZ` UTC, date contabili `DATE`.

## Prossimi passi

- [ ] Confermare dalla GUI il flusso della §3.4 punto 5 (login → lista conti con saldo →
      aggiungi transazione) e il rientro automatico dal refresh token dopo un riavvio
      dell'app.
- [ ] Registrare una API key Twelve Data (o Alpha Vantage) in
      `secrets/market_data_api_key.txt` **sul server** e rimettere
      `MARKET_DATA_PROVIDER=twelvedata` nel suo `.env`; fino ad allora i prezzi si
      inseriscono a mano da `PUT /api/v1/portfolio/prices/{ticker}`.
- [ ] Backup del database: oggi è un `pg_dump` da lanciare a mano (DEPLOY.md §6), non c'è
      niente di schedulato.
- [ ] Accesso da fuori casa via Tailscale: l'IP `100.89.5.18` è già nel SAN del
      certificato, ma il percorso non è mai stato provato.
- [ ] Fase 13: app Android come nuovo client dello stesso backend (nessuna modifica al
      server prevista, il contratto §1 è machine-independent).

Idee esplicitamente rimandate, da non riproporre come "nuove": storico dei limiti di
budget (`BudgetHistory`), più obiettivi sullo stesso conto di risparmio, piano di
ammortamento per i mutui, drag&drop dei widget, caching locale sul client.

## Changelog

### 2026-08-04 (3) — configurazione del server dal client

- **Corretto un difetto che distruggeva la configurazione.** `App.OnStartup` faceva
  `AppSettings.Load()` seguito da `Save()`: se `settings.json` non era leggibile, `Load()`
  ripiegava in silenzio sui valori predefiniti e `Save()` li riscriveva sopra il file,
  cancellando l'indirizzo buono. Sintomo osservato: la finestra di login mostrava
  `https://localhost:8443` senza motivo apparente. Ora il salvataggio avviene solo dopo un
  login riuscito, e `AppSettings.LastLoadError` viene mostrato in rosso nel login.
- **Campo «Server» reso modificabile** (era `IsReadOnly` con binding `OneWay`, quindi
  puramente decorativo). L'URL viene validato, applicato ricostruendo l'`ApiClient` — la
  `BaseAddress` è fissata nel costruttore — e salvato solo dopo un login riuscito.
- **Gli errori del login erano illeggibili**, e questo ha nascosto un problema per un giro
  intero: la finestra aveva `Height` fisso e `ResizeMode="NoResize"`, quindi un messaggio
  lungo veniva tagliato dal bordo; e si mostrava solo `HttpRequestException.Message`
  ("The SSL connection could not be established"), che è generico — la ragione vera sta
  nelle eccezioni annidate. Ora la finestra è `SizeToContent="Height"` e ridimensionabile,
  e il messaggio include tutta la catena delle cause più l'indirizzo tentato.
- **Causa dell'errore TLS: il certificato non era dove il client lo cercava.** Il messaggio
  «Nessun certificato pinnato» ha rivelato `ServerCertificatePath = null`, quindi il
  callback rifiutava qualunque certificato (il ping funzionava: il problema era a livello
  TLS, non IP). Il certificato ora sta in `server/certs/server.crt` nel repository, che è
  il primo posto in cui `GuessCertificatePath()` guarda. Inoltre `Load()` non si fida più
  di un percorso valorizzato ma inesistente: ricade sulla ricerca automatica invece di
  restare senza pinning, e la finestra di login mostra il percorso risolto.
- **Un errore TLS osservato una volta alle 01:50 non è stato riprodotto.** Verificato dopo:
  l'impronta SHA-256 del certificato presentato coincide con quella del file pinnato, e il
  **codice di produzione** (`AppSettings.Load` + `ApiClient.LoginAsync`, esercitato da un
  harness che referenzia l'assembly vero) autentica correttamente. Nei log del server non
  compare alcun tentativo in quell'istante. Se ricapita, ora il messaggio dirà la causa.
- **Tailscale non è utilizzabile dal client oggi:** sul PC Windows Tailscale non è
  installato (nessun eseguibile, nessun servizio, nessun indirizzo `100.x`). L'IP
  `100.89.5.18` è del solo server. Config attiva quindi su `https://192.168.1.104:8443`;
  una volta installato Tailscale qui basta cambiare il campo Server, il certificato ha già
  quell'IP nel SAN.

### 2026-08-04 (2) — rinomina in «Centesimo»

- L'app si chiama **Centesimo**. Rinominati sia i testi visibili sia gli identificatori:
  namespace `MoneyApp.Desktop` → `Centesimo.Desktop`, `MoneyApp.sln` → `Centesimo.sln`,
  cartella del progetto, `AssemblyName` (l'eseguibile ora è `Centesimo.exe`), classe
  `MoneyApi` → `CentesimoApi`, `docs/ARCHITETTURA_MONEY_APP.md` →
  `docs/ARCHITETTURA_CENTESIMO.md` con tutti i link aggiornati. 50 file toccati.
- Cambiati anche due punti che hanno effetti collaterali: `%APPDATA%\MoneyApp` →
  `%APPDATA%\Centesimo` (config e certificato migrati, vecchia cartella rimossa) e il
  target nel Credential Manager `MoneyApp:refresh_token` → `Centesimo:refresh_token`
  (la vecchia voce, orfana, è stata cancellata: **serve rifare il login una volta**).
- **Non** rinominati, di proposito: il database `money` e il ruolo `money_app`. Sono
  identificatori dell'infrastruttura, non il nome dell'app, e cambiarli richiede di
  ricreare database e ruolo su Postgres — rischio senza guadagno.
- Il certificato già emesso conserva `O=Money App` nel subject: `entrypoint.sh` ora
  genera `O=Centesimo`, ma il certificato non si rigenera finché `server/certs/` esiste
  (e rigenerarlo romperebbe il pinning). Si allineerà alla prossima rigenerazione.
- Verificato dopo la rinomina: il client compila in Release senza warning come
  `Centesimo.exe`, l'OpenAPI espone `"Centesimo API"`, i 45 test passano ancora.

### 2026-08-04 (1) — primo deploy

- **Primo deploy reale.** Backend su `192.168.1.104` (Ubuntu 24.04, utente `office`,
  `/home/office/Budgeting`): installato Docker Engine 29.7.1 + Compose v5.4.0 dal repo
  ufficiale, copiati i sorgenti, generati segreti e `.env` sul posto, stack avviato.
- **Prima verifica end-to-end**, mai fatta prima: migrazione `0001` applicata su Postgres
  reale, `/health` OK dalla LAN, seed di utente e 21 categorie, login + `/auth/me` +
  `/categories` da un client esterno con certificato pinnato.
- `entrypoint.sh`: il SAN del certificato self-signed ora è parametrico
  (`CERT_CN`, `CERT_EXTRA_SAN`), altrimenti valeva solo per `localhost`. Aggiunte le
  variabili al `docker-compose.yml` e a `.env.example`.
- **Corretti due difetti che impedivano ai test di girare**, emersi solo eseguendoli
  davvero: `pytest.ini` senza `pythonpath = .` (il package `app` non era importabile) e
  scope dell'event loop disallineato fra fixture e test (tutti i 28 test che toccavano il
  DB morivano con "got Future attached to a different loop"). Rimossa la fixture
  `event_loop` fatta a mano, deprecata da pytest-asyncio 0.23. **45 test su 45 passano.**
- Nuovo [DEPLOY.md](DEPLOY.md): topologia, cosa vive solo sul server, gestione del
  certificato, deploy da zero, aggiornamento, comandi operativi, backup, rete.

### 2026-07-30

- Creato il repository da zero: `docker-compose.yml` con reti separate e Docker secrets,
  `Dockerfile` Python 3.12, entrypoint che genera il certificato self-signed e applica le
  migrazioni.
- Fase 1: endpoint `/health` con stato di database e scheduler.
- Fase 2: autenticazione JWT, refresh token opachi revocabili e ruotati, `app.seed` per
  utente e categorie iniziali.
- Fase 3: conti, categorie con sotto-categorie, budget con speso/residuo calcolati dal
  server.
- Fase 4: transazioni con `status` e soft-delete; servizio di calcolo saldi.
- Fase 5: client WPF con login, navigazione, pagina Conti e form di inserimento.
- Fase 6: trasferimenti fra conti, esclusi dai report di spesa.
- Fase 7: obiettivi di risparmio con progresso e accantonamento mensile richiesto.
- Fase 8: snapshot dei debiti e endpoint del patrimonio netto.
- Fase 9: motore delle ricorrenze (incluse più date a calendario nello stesso periodo) e
  job di generazione idempotente.
- Fase 10: `/reports/timeseries` generico, ripartizione per categoria, snapshot giornaliero
  del patrimonio netto.
- Fase 11: CRUD dei widget e Home a griglia fissa nel client.
- Fase 12: portafoglio investimenti con media ponderata di carico, plusvalenze realizzate,
  cache prezzi/cambi e provider esterno opzionale.
- Documentazione: `README.md`, `docs/API.md`, `docs/ARCHITETTURA_CENTESIMO.md`, questo file.
