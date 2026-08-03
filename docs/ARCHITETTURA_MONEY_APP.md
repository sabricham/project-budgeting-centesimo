# Architettura — Money App

Documento di riferimento per il progetto di gestione finanziaria personale.
Copre: fondamenta tecniche, architettura delle funzionalità, piano implementativo, brief per agente AI.

---

## 0. Decisioni già confermate

| Area | Decisione |
|---|---|
| Deployment | Docker Compose, inizialmente sullo stesso PC del client Windows, in futuro su server separato |
| Accesso ai dati | Nessun client si collega direttamente al DB. Unico punto di accesso: API REST su HTTPS |
| Database | PostgreSQL |
| Backend API | Python 3.12 + FastAPI |
| Utenti | Singolo utente (tu) per ora, ma modello dati predisposto per estensione multi-utente futura |
| Rete fase 2 (remota) | VPN personale (Tailscale/WireGuard) invece di esporre l'API su internet pubblico |
| Client Windows | WPF/.NET nativo (Android sarà un progetto separato in futuro) |
| Investimenti | Tracking di portafoglio avanzato: ticker, quantità, prezzi di mercato in tempo reale |
| Budget | Limiti di spesa mensili per categoria, inclusi |
| Obiettivi di risparmio | Goal con target/scadenza, sovrapposti a un conto savings_goal |
| Debiti/Prestiti | Conti liability a modello snapshot, per un patrimonio netto reale |

Queste scelte sono **chiuse**: qualunque sviluppo, umano o AI, deve partire da qui senza rimetterle in discussione (vedi §4 per il perché questo conta).

---

## 1. Architettura delle fondamenta (contratto client-server)

Questa sezione è **machine-independent**: vale identica per il client Windows e per la futura app Android. Nessuno dei due deve avere logica diversa qui.

### 1.1 Autenticazione — come funziona, spiegata dall'inizio

Dato che sei l'unico utente non serve un sistema complesso, ma vale la pena farlo "giusto" da subito perché è la parte più delicata per la sicurezza.

**Flusso:**

1. Il client manda `POST /api/v1/auth/login` con `{username, password}`.
2. Il server verifica la password (confrontando con un hash **bcrypt/argon2** salvato nel DB — mai la password in chiaro) e risponde con due token:
   - **access_token** (JWT, durata breve: 15–60 minuti): è quello che il client allega a ogni richiesta successiva nell'header `Authorization: Bearer <access_token>`. Il server lo verifica firma+scadenza senza dover interrogare il DB ad ogni richiesta.
   - **refresh_token** (durata lunga: es. 30 giorni): usato solo per ottenere un nuovo access_token quando scade, via `POST /api/v1/auth/refresh`, senza dover reinserire la password ogni volta.
3. Il client salva il refresh_token in modo sicuro:
   - Windows: **Windows Credential Manager** (via API DPAPI), mai in un file di testo/JSON in chiaro.
   - Android: **Android Keystore**.
4. Se il refresh_token scade o viene revocato (es. logout, cambio password), il client torna alla schermata di login.

**Perché JWT e non semplice "API key fissa":** un JWT ha scadenza breve, quindi se mai venisse intercettato ha una finestra di validità limitata. Una chiave fissa valida per sempre è un rischio inutile.

**Cosa NON fare:** salvare la password in chiaro sul client per riautenticarsi automaticamente; passare token nella query string dell'URL (finiscono nei log); disattivare la verifica del certificato HTTPS "per comodità" in dev.

### 1.2 Design delle API REST

- Prefisso versionato: `/api/v1/...` — permette di introdurre `/api/v2/` in futuro senza rompere i client esistenti.
- Risorse principali: `/accounts`, `/categories`, `/transactions`, `/transfers`, `/recurring-transactions`, `/reports/*`.
- Verbi standard: `GET` (lista/dettaglio), `POST` (crea), `PATCH` (modifica parziale), `DELETE` (elimina, con soft-delete dove ha senso per non perdere storico).
- Filtri e paginazione via query string: `?account_id=&category_id=&date_from=&date_to=&limit=&offset=`.
- Errori in formato coerente: `{"error": {"code": "...", "message": "..."}}`.
- Documentazione **auto-generata** da FastAPI su `/docs` (Swagger UI) — utile sia per testare a mano sia come contratto di riferimento per chi scrive i client.

### 1.3 Contratto client (regole valide per Windows e Android)

- **La validazione che conta vive sul server.** Il client valida solo per UX immediata (feedback istantaneo), ma non deve mai fidarsi di sé stesso: il server ricontrolla sempre (es. importo positivo, categoria esistente, conto non archiviato).
- **Importi:** trasmessi come interi in centesimi (es. 1050 = 10,50€) oppure come stringhe decimali — mai come `float` nativo, per evitare errori di arrotondamento. Stessa convenzione lato server (colonna `NUMERIC` in Postgres, non `FLOAT`).
- **Date/orari:** sempre ISO 8601 in UTC sul filo; la conversione al fuso orario locale è responsabilità del client, solo per la visualizzazione.
- **Concorrenza:** dato l'uso singolo-utente non serve un sistema di risoluzione conflitti sofisticato. Basta un campo `updated_at` per rilevare modifiche concorrenti impreviste (es. stesso account loggato da due dispositivi contemporaneamente) e mostrare un avviso invece di sovrascrivere silenziosamente.
- **Caching locale:** non necessario per l'MVP (dataset piccolo, rete LAN/VPN veloce). Va tenuto in mente come possibile ottimizzazione futura per l'app Android in mobilità con connessione instabile, non a giorno 1.

### 1.4 Sicurezza di rete per fase

| Fase | Come esporre l'API |
|---|---|
| Ora (stesso PC) | `localhost`, certificato self-signed va bene, nessuna porta aperta verso l'esterno |
| Futuro (server separato, accesso da Android in mobilità) | VPN personale (Tailscale consigliato: zero config firewall, certificati HTTPS gestiti automaticamente tramite Tailscale Serve) — **mai** l'API esposta direttamente su IP pubblico |

---

## 2. Architettura delle funzionalità

### 2.1 Modello dati concettuale

```
User (1 per ora)
 └── Account (conto bancario, contanti, Satispay, investimento, risparmio, debito/prestito...)
      └── Transaction (entrata / uscita, legata a una Category)
      └── Transfer (movimento tra due Account — non è entrata né uscita)
      └── LiabilityUpdate (solo per conti liability: snapshot del residuo)
 Category (entrata/uscita, con eventuale sotto-categoria)
      └── Budget (limite di spesa mensile per categoria)
 RecurringTransaction (definizione di un abbonamento/bolletta ricorrente)
      └── genera → Transaction (quando l'occorrenza matura)
 Goal (obiettivo di risparmio, collegato a un Account savings_goal)
 DashboardWidget (configurazione dei widget nella home, per-utente)
```

### 2.2 Conti (Account)

Campi: `id, name, type, currency, initial_balance, icon, color, archived`.

`type` è un enum che copre i tuoi esempi più i debiti: `bank`, `cash`, `card`, `ewallet` (Satispay ecc.), `investment`, `savings_goal`, `liability` (mutuo, prestito, saldo carta di credito revolving).

Per i tipi `bank/cash/card/ewallet/investment/savings_goal` il saldo **non va salvato come campo aggiornato manualmente**: si calcola come `initial_balance + Σ transazioni + Σ trasferimenti in/out`. Per i conti `liability` il modello è diverso — vedi §2.10 — perché derivare il capitale residuo dai soli pagamenti richiederebbe un piano di ammortamento, complessità che reputo fuori scope per un tool personale.

### 2.3 Trasferimenti — un concetto che ti serve e non hai menzionato

Quando sposti soldi dal conto bancario a Satispay, o dal conto corrente a un conto "risparmio", **non è né un'entrata né un'uscita** in senso di budget: è denaro che resta tuo, solo spostato. Se lo registri come "spesa" dal conto bancario, i tuoi report di spesa mensile diventano falsati.

Serve quindi un'entità separata `Transfer`: `id, from_account_id, to_account_id, amount, date, description`. Non tocca le categorie, non entra nei report "spese per categoria", ma aggiorna comunque i saldi di entrambi i conti coinvolti.

Questo è anche il meccanismo con cui modelli "ho messo via 200€ di risparmio" o "ho investito 500€": un trasferimento dal conto corrente al conto `investment`/`savings_goal`.

### 2.4 Categorie

`id, name, type (income/expense), parent_category_id (nullable), icon, color`. Il `parent_category_id` ti dà sotto-categorie gratis (es. "Alimentari" → "Supermercato" / "Ristoranti") senza doverle aggiungere dopo.

### 2.5 Budget mensili per categoria

Un limite di spesa mensile legato a una categoria, per sapere quanto ti resta prima di sforare.

```
Budget:
  id, category_id (unique), amount_limit, active
```

Un solo budget "corrente" per categoria, non uno storico mese per mese: se lo modifichi, si applica da quel momento in poi. Per l'MVP basta così — uno storico dei limiti passati è un'aggiunta a costo quasi zero in futuro (basterebbe una tabella `BudgetHistory` con `valid_from`), non serve prevederla ora.

L'endpoint `GET /api/v1/budgets` non restituisce solo il limite ma anche il consumato: `spent_this_month` (somma delle transazioni della categoria nel mese corrente) e `remaining = amount_limit - spent_this_month`. Così il calcolo lo fa il server una volta sola, riusabile sia dal widget dashboard sia da eventuali notifiche future.

### 2.6 Transazioni

`id, account_id, category_id, type (income/expense), amount, date, description, source_recurring_id (nullable)`. Il campo `source_recurring_id` collega una transazione generata automaticamente al suo abbonamento di origine — utile per mostrare "questa spesa viene da Netflix" e per gestire modifiche/cancellazioni in blocco.

### 2.7 Abbonamenti / spese ricorrenti

Qui hai chiesto esplicitamente la possibilità di scegliere **più date a calendario** (non solo "ogni mese lo stesso giorno"). Modello proposto:

```
RecurringTransaction:
  id, account_id, category_id, amount, description
  frequency: weekly | monthly | yearly | custom_dates
  interval: int (ogni N settimane/mesi/anni, default 1)
  occurrence_days: JSON
     - monthly → [1, 15]           (es. due volte al mese: giorno 1 e 15)
     - weekly  → [0, 3]            (es. lunedì e giovedì, 0=lunedì)
     - yearly  → [{month:1,day:1}]
     - custom_dates → [date, date, ...]  (date esplicite, per casi irregolari)
  start_date, end_date (nullable = indefinito)
  active: bool
  auto_confirm: bool
```

**Generazione:** un job schedulato (dentro il container API, con `APScheduler` o simile) genera in anticipo le occorrenze future come `Transaction` con `status = projected`. Se `auto_confirm = true` diventano `confirmed` automaticamente alla data; altrimenti restano "in attesa di conferma" — utile per bollette a importo variabile (luce, gas) dove vuoi correggere l'importo prima che conti nel saldo.

Questo ti dà gratis anche una vista "prossime spese in arrivo questo mese" per il dashboard.

### 2.8 Investimenti / risparmi

Due casi distinti:

- **Risparmio passivo** ("soldi messi da parte"): basta il modello Account di tipo `savings_goal` + Transfer (§2.3). Nessuna complessità aggiuntiva.
- **Investimenti in azioni** (portafoglio avanzato — scelto): l'account `investment` non ha solo un saldo, ma tiene sia una **liquidità disponibile** (cash non ancora investito) sia un **elenco di posizioni** (azioni possedute). Modello:

```
Holding:
  id, account_id, ticker, quantity, avg_cost_basis (prezzo medio di carico), currency
StockTransaction:
  id, account_id, ticker, type (buy | sell | dividend)
  quantity (null per dividend), price_per_share (null per dividend)
  fees, amount (usato solo per dividend), date, notes
```

**Effetti sul saldo:**

- `buy`: liquidità del conto -= (quantity × price_per_share + fees); aggiorna `Holding.quantity` e ricalcola `avg_cost_basis` come media ponderata.
- `sell`: liquidità del conto += (quantity × price_per_share − fees); riduce `Holding.quantity`; calcola plusvalenza/minusvalenza realizzata = (price_per_share − avg_cost_basis) × quantity − fees.
- `dividend`: liquidità del conto += amount, nessun effetto su quantity.

**Prezzi di mercato:** servono da fonte esterna. Per un progetto personale consiglio **Twelve Data** o **Alpha Vantage** (piano gratuito, rate-limit basso ma sufficiente per un portafoglio personale aggiornato ogni tot minuti, non intraday). I prezzi vanno **cachati** in una tabella `PriceCache (ticker, price, currency, fetched_at)` aggiornata da un job schedulato (stesso meccanismo di APScheduler già previsto per le ricorrenze, §2.7) — mai chiamare l'API esterna ad ogni richiesta dell'utente, sia per i rate-limit sia per non far dipendere la UI dalla disponibilità di un servizio terzo.

**Valorizzazione portafoglio:** `valore_corrente = Σ (Holding.quantity × prezzo_cache)`, `plusvalenza_non_realizzata = valore_corrente − Σ (Holding.quantity × avg_cost_basis)`.

**Valute:** se un titolo è quotato in USD e la tua valuta base è EUR, per l'MVP conviene tenere gli importi nella valuta nativa del titolo a livello di `Holding`/`StockTransaction`, e fare la conversione **solo in fase di aggregazione/report** usando un tasso di cambio cachato giornalmente (stessa logica del `PriceCache`, tabella `FxRateCache`). Evita di dover convertire e "sporcare" i dati storici ogni volta che il cambio si muove.

Questa è la feature con più parti mobili (dipendenza da servizio esterno, job schedulati, conversione valuta) — nel piano a fasi (§3.4) la colloco volutamente dopo che il core (conti/transazioni/trasferimenti) è stabile e testato, non nel primo giro.

### 2.9 Obiettivi di risparmio (Goal)

Un obiettivo con importo target e (opzionalmente) scadenza, **sovrapposto** a un conto `savings_goal` esistente — niente contabilità parallela, si appoggia al saldo del conto collegato.

```
Goal:
  id, name, target_amount, target_date (nullable)
  linked_account_id (Account di tipo savings_goal)
  icon, color
```

`current_amount` non è un campo salvato: è semplicemente il saldo corrente del conto collegato (§2.2). `progress = current_amount / target_amount`. Con `target_date` impostata ottieni gratis anche "quanto dovresti accantonare ogni mese per arrivarci in tempo" — bel widget dashboard, zero lavoro aggiuntivo sul modello dati.

**Vincolo semplificativo:** un conto `savings_goal` è collegato a un solo Goal alla volta. Dividere un unico conto fra più obiettivi (es. "metà vacanze, metà auto") richiederebbe tracciare i contributi per obiettivo separatamente — lo lascio fuori scope: il caso d'uso più comune è un conto dedicato per obiettivo, che è anche la soluzione più pulita.

### 2.10 Debiti/Prestiti e patrimonio netto

I conti `liability` (§2.2) rappresentano ciò che devi, non ciò che possiedi: mutuo, prestito auto, saldo carta di credito revolving.

**Differenza chiave rispetto agli altri conti:** qui il saldo *non* si calcola sommando le transazioni — farlo correttamente richiederebbe un piano di ammortamento (separare quota capitale e quota interessi ad ogni rata), complessità che reputo fuori scope per un tool personale. Uso invece un modello a **snapshot**:

```
LiabilityUpdate:
  id, account_id, residual_amount, date, note
```

Registri periodicamente (es. quando arriva l'estratto conto) il capitale residuo: "Mutuo, al 1/8/2026: 144.500€". Il saldo del conto `liability` è semplicemente l'ultimo `residual_amount` registrato. Le rate pagate le registri normalmente come spesa dal conto bancario con categoria "Mutuo/Prestiti" (§2.4) — quella è la spesa reale che ti interessa nei report; l'aggiornamento del residuo è un dato separato, più occasionale.

**Patrimonio netto:**
`GET /api/v1/reports/net-worth` → `Σ saldo(conti bank/cash/card/ewallet/investment/savings_goal) − Σ saldo(conti liability)`.

Salvando uno snapshot periodico di questo valore (stesso job schedulato già previsto altrove) ottieni gratis anche un grafico "andamento patrimonio netto nel tempo", riusando lo stesso endpoint `/reports/timeseries` già previsto per gli altri widget (§2.11).

### 2.11 Dashboard — griglia di widget

`DashboardWidget: id, type, position (x, y, w, h), config (JSON)`.

`config` è JSON libero perché ogni tipo di widget ha impostazioni diverse (es. per un widget "saldo": quali conti selezionati, range temporale) senza dover fare una migrazione DB ogni volta che aggiungi un nuovo tipo di widget.

**Range temporale**, come da tua richiesta in stile broker: `day | week (da lunedì) | month (mese corrente) | year (anno corrente)`, con granularità dei dati che cambia di conseguenza:

| Range | Granularità punti dati |
|---|---|
| Day | lista movimenti del giorno + saldo cumulato |
| Week | un punto per giorno (lun→dom) |
| Month | un punto per giorno del mese |
| Year | un punto per mese |

Il backend espone un endpoint generico invece di uno specifico per widget:
`GET /api/v1/reports/timeseries?metric=balance|spending|income&account_ids=1,2&range=month`
così puoi aggiungere nuovi tipi di widget nel client senza toccare il backend, finché riusano le metriche esistenti. Con le aggiunte di questa iterazione, altri due widget naturali sono: "budget rimanente per categoria" (riusa `GET /budgets`, §2.5) e "andamento patrimonio netto" (riusa `/reports/timeseries?metric=net_worth`, §2.10).

**Nota implementativa onesta:** una griglia di widget riposizionabile via drag&drop è un pezzo di UI non banale su WPF (non c'è "gratis" come su web). Per l'MVP ti consiglio un layout a griglia fissa con 3–4 widget configurabili (scegli conti + range da un pannello impostazioni), e il drag&drop libero come miglioria di seconda iterazione.

### 2.12 Mappa delle pagine e flussi

```
Login
  └── Home (dashboard/widget grid)
        ├── → Conti (lista conti + saldo, inclusi debiti/prestiti) → Dettaglio conto (storico transazioni, + Aggiungi)
        ├── → Categorie e Budget (gestione CRUD categorie, limiti di spesa mensili)
        ├── → Abbonamenti (lista ricorrenze, calendario prossime occorrenze, conferma/modifica)
        ├── → Portafoglio (posizioni, buy/sell, plusvalenze, valore corrente)
        ├── → Obiettivi (goal di risparmio, progresso verso il target)
        └── → Report (grafici a tutto schermo, incluso patrimonio netto — stessa logica dei widget ma espansa)
```

---

## 3. Architettura implementativa (MVP testabile subito)

### 3.1 Stack tecnologico

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.0 (async), Alembic (migrazioni), Pydantic v2, `passlib[bcrypt]`, `python-jose` (JWT), driver `asyncpg`, `httpx` (chiamate all'API di prezzi di mercato).
- **Database:** PostgreSQL 16.
- **Scheduler:** APScheduler dentro il container API — genera le occorrenze ricorrenti (§2.7) e aggiorna `PriceCache`/`FxRateCache` (§2.8). Non serve un servizio separato per l'MVP.
- **Dati di mercato:** Twelve Data o Alpha Vantage (piano gratuito), chiave API salvata come secret Docker come per `db_password`/`jwt_secret`.
- **Client Windows:** WPF su .NET 8, token salvato in Windows Credential Manager (§1.1).

### 3.2 Struttura repo (monorepo)

```
money-app/
  api/
    app/
      main.py
      config.py
      db.py
      models.py          # SQLAlchemy models
      schemas.py         # Pydantic schemas
      auth/security.py   # hashing password, JWT
      routers/
        auth.py
        accounts.py
        categories.py
        transactions.py
        transfers.py
        recurring.py
        reports.py
    alembic/
    Dockerfile
    requirements.txt
  desktop/                # client Windows
  docker-compose.yml
  .env.example
  docs/
    ARCHITETTURA_MONEY_APP.md   (questo file)
    PROJECT_MEMORY.md           (vedi §4)
    API.md
```

### 3.3 Docker Compose (base)

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: money
      POSTGRES_USER: money_app
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
    volumes: [pgdata:/var/lib/postgresql/data]
    networks: [internal]
    secrets: [db_password]
  api:
    build: ./api
    environment:
      DATABASE_URL: postgresql+asyncpg://money_app@db:5432/money
      JWT_SECRET_FILE: /run/secrets/jwt_secret
    ports: ["8443:8443"]
    depends_on: [db]
    networks: [internal, external]
    secrets: [db_password, jwt_secret]
networks:
  internal:
  external:
volumes:
  pgdata:
secrets:
  db_password:
    file: ./secrets/db_password.txt
  jwt_secret:
    file: ./secrets/jwt_secret.txt
```

### 3.4 Piano di sviluppo a fasi (ognuna testabile prima di passare alla successiva)

1. **Scheletro:** `docker-compose up` → Postgres + API rispondono, endpoint `/health`.
2. **Auth:** utente seed nel DB, login funzionante, JWT emesso e verificato.
3. **Conti + Categorie + Budget:** CRUD completo, inclusi i limiti di spesa mensili per categoria, testabile da Swagger UI.
4. **Transazioni:** CRUD + calcolo saldo per conto.
5. **Milestone end-to-end:** client Windows minimo — login, lista conti con saldo, form "aggiungi transazione". **Qui hai la prima verifica reale che tutta la catena funziona.**
6. **Trasferimenti** tra conti.
7. **Obiettivi di risparmio (Goal)**, collegati ai conti `savings_goal`.
8. **Debiti/Prestiti:** conti `liability`, `LiabilityUpdate`, endpoint patrimonio netto.
9. **Ricorrenze/abbonamenti** + job di generazione.
10. **Report/timeseries** (endpoint aggregazione, incluso l'andamento del patrimonio netto).
11. **Dashboard a widget** nel client.
12. **Portafoglio investimenti:** `Holding`/`StockTransaction`, integrazione API prezzi + `PriceCache`/`FxRateCache`, pagina Portafoglio nel client. Deliberatamente verso la fine perché dipende da un servizio esterno e ha più parti mobili delle altre fasi.
13. **App Android** (stesso backend, nuovo client soltanto).

### 3.5 Client Windows — WPF/.NET nativo (confermato)

Scelto per la miglior esperienza nativa e il massimo controllo sulla UI, importante per la griglia di widget (§2.11) e per il portafoglio investimenti (§2.8), che hanno entrambi bisogno di grafici/layout non banali. L'app Android, quando arriverà, sarà un progetto client separato che consuma la stessa API — nessun codice condiviso col client Windows, ma nessun problema: il contratto è tutto in §1, machine-independent per definizione.

Nel repo: `desktop/` conterrà una soluzione .NET 8 con WPF, autenticazione via il flusso in §1.1 (token in Windows Credential Manager), e un client HTTP tipizzato generato/ispirato dallo schema OpenAPI esposto da FastAPI su `/openapi.json`.

---

## 4. Brief per l'agente AI (Claude Opus 5)

### 4.1 Perché serve una memoria persistente

Un agente che lavora a sessioni separate non ha memoria delle scelte fatte in sessioni precedenti. Senza un meccanismo esplicito rischia di: riproporre alternative già scartate (es. "colleghiamo il client direttamente al DB per semplicità"), reinventare convenzioni già stabilite (formati date/importi), perdere traccia di cosa è già stato implementato. La soluzione è un file di memoria che l'agente **deve leggere a inizio sessione e aggiornare a fine sessione**, come se fosse il suo diario di bordo del progetto.

### 4.2 Template — `docs/PROJECT_MEMORY.md`

Vedi il file reale: [PROJECT_MEMORY.md](PROJECT_MEMORY.md). Struttura: Stato attuale,
tabella Decisioni architetturali (log, non cancellare mai le righe vecchie), Schema dati,
Prossimi passi, Changelog.

### 4.3 Testo del brief da dare all'agente (da incollare come primo messaggio)

```
Stai implementando "Money App", un tool personale di gestione finanziaria.

REGOLE OBBLIGATORIE:

1. Prima di scrivere qualunque codice, leggi per intero docs/PROJECT_MEMORY.md e
   docs/ARCHITETTURA_MONEY_APP.md. Non proporre soluzioni già scartate lì elencate.
2. Le decisioni architetturali in ARCHITETTURA_MONEY_APP.md sono chiuse: non rimetterle
   in discussione (es. niente accesso diretto client→DB, niente SQLite, autenticazione
   JWT come descritta). Se pensi che una scelta vada cambiata, segnalalo esplicitamente
   e aspetta conferma, non procedere in autonomia.
3. Segui il piano a fasi in §3.4: una fase alla volta, ognuna deve essere testabile
   prima di passare alla successiva. Non saltare fasi.
4. Dopo OGNI modifica significativa (nuova feature, cambio schema, decisione presa),
   aggiorna docs/PROJECT_MEMORY.md PRIMA di considerare il task concluso:
   - aggiungi una riga alla tabella Decisioni se hai fatto una scelta non ovvia
   - aggiorna "Stato attuale"
   - aggiungi una voce al Changelog
5. Documenta ogni nuovo endpoint (mantieni aggiornato docs/API.md o rimanda
   esplicitamente a /docs generato da FastAPI).
6. Vai dritto al punto nell'implementazione: niente feature non richieste,
   niente over-engineering per scenari ipotetici futuri (es. multi-utente reale)
   finché non viene esplicitamente chiesto.

Obiettivo di questa sessione: [DA COMPILARE — es. "Fase 1: scheletro docker-compose
+ endpoint /health"]
```

---

## 5. Stato delle decisioni

Tutte le decisioni aperte sono state chiuse e riportate in §0:

- Investimenti → portafoglio avanzato (§2.8)
- Client Windows → WPF/.NET nativo (§3.5)
- Funzionalità aggiuntive → Budget (§2.5), Obiettivi di risparmio (§2.9), Debiti/Prestiti e patrimonio netto (§2.10)

Non ci sono decisioni bloccanti residue: si può passare alla Fase 1 del piano (§3.4) — scheletro Docker Compose + endpoint `/health`.

---

## Appendice A — Deroghe applicate in implementazione

Il documento sopra resta il riferimento. Queste sono le uniche differenze fra il testo e il
codice effettivo, decise esplicitamente e tracciate anche in
[PROJECT_MEMORY.md](PROJECT_MEMORY.md).

| Punto | Documento | Implementazione | Perché |
|---|---|---|---|
| §3.2 | cartelle `api/` e `desktop/` | **`server/` e `client/`** | richiesta esplicita di leggibilità: i nomi dicono subito quale metà è quale |
| §3.1, §3.5 | client su .NET 8 | **`net10.0-windows`** | sulla macchina di sviluppo è installato solo il runtime .NET 10; WPF è identico, nessuna perdita funzionale |
| §1.3 | importi come interi in centesimi **oppure** stringhe decimali | **stringhe decimali** | il documento lasciava la scelta; le stringhe sono leggibili in Swagger e nei log, e Pydantic v2 le produce già da `Decimal` |
| §1.2 | risorsa `/recurring-transactions` | **`/recurring`** | più corto da digitare; è l'unico nome di risorsa che si discosta |
| §2.8 | modello `StockTransaction` | aggiunti i campi calcolati **`realized_pnl`** e **`cash_delta`** | evitano di ricostruire l'effetto storico di ogni operazione ad ogni lettura |
| §2.8 | conversione valuta solo in aggregazione | vale per le **posizioni**; il **movimento di cassa** viene convertito alla registrazione | il contante uscito dal conto è un fatto storico e non va rivalutato |

Nessuna decisione di §0 è stata toccata.
