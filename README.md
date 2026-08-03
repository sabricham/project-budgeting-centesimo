# Money App

Tool personale di gestione finanziaria: conti, transazioni, trasferimenti, budget,
obiettivi di risparmio, debiti/prestiti, abbonamenti ricorrenti, portafoglio investimenti
e patrimonio netto.

Architettura in due parti nettamente separate:

| Cartella | Cos'è | Tecnologia |
|---|---|---|
| [`server/`](server) | **Unico** punto di accesso ai dati: API REST su HTTPS | Python 3.12, FastAPI, SQLAlchemy 2.0 async, PostgreSQL 16 |
| [`client/`](client) | Client Windows nativo che consuma l'API | .NET, WPF, MVVM |

Nessun client parla mai direttamente col database — è una decisione chiusa
(vedi [docs/ARCHITETTURA_MONEY_APP.md](docs/ARCHITETTURA_MONEY_APP.md) §0). Una futura app
Android sarà semplicemente un altro client dello stesso backend.

---

## Indice

- [Prerequisiti](#prerequisiti)
- [Avvio rapido](#avvio-rapido)
- [Struttura del repository](#struttura-del-repository)
- [Concetti chiave del modello](#concetti-chiave-del-modello)
- [Convenzioni del contratto API](#convenzioni-del-contratto-api)
- [Sicurezza](#sicurezza)
- [Job schedulati](#job-schedulati)
- [Test](#test)
- [Comandi utili](#comandi-utili)
- [Problemi frequenti](#problemi-frequenti)
- [Documentazione](#documentazione)

---

## Prerequisiti

- **Docker Desktop** per Windows (server + database).
- **.NET SDK 10** per compilare il client (`dotnet --list-sdks`).
- Facoltativo: una API key gratuita [Twelve Data](https://twelvedata.com) o
  [Alpha Vantage](https://www.alphavantage.co) per i prezzi di mercato. Senza chiave il
  portafoglio funziona lo stesso, con i prezzi inseriti a mano.

## Avvio rapido

### 1. Segreti

```powershell
Copy-Item .env.example .env
[Convert]::ToBase64String((1..24 | ForEach-Object { Get-Random -Max 256 })) | Out-File -Encoding ascii -NoNewline secrets/db_password.txt
[Convert]::ToBase64String((1..48 | ForEach-Object { Get-Random -Max 256 })) | Out-File -Encoding ascii -NoNewline secrets/jwt_secret.txt
"" | Out-File -Encoding ascii -NoNewline secrets/market_data_api_key.txt
```

Dettagli in [`secrets/README.md`](secrets/README.md).

### 2. Avvio dello stack

```bash
docker compose up -d --build
```

All'avvio il container `api`:
1. genera un certificato TLS self-signed in `server/certs/` (solo la prima volta);
2. applica le migrazioni Alembic;
3. espone l'API su `https://localhost:8443`.

Verifica:

```bash
curl -k https://localhost:8443/health
```

Attesa: `{"status":"ok","db":"ok","version":"1.0.0","scheduler":"running"}`.

### 3. Utente iniziale

```bash
docker compose exec api python -m app.seed --username sabri --password 'scegli-una-password'
```

Crea l'utente e un set di categorie italiane di partenza. Aggiungi `--demo` per creare
anche un conto per ogni tipo, utile per provare subito l'app.

### 4. Swagger

Apri <https://localhost:8443/docs> (il browser avvisa del certificato self-signed:
è atteso, vedi [Sicurezza](#sicurezza)). Premi **Authorize**, inserisci utente e password,
e puoi esercitare tutta l'API a mano.

### 5. Client Windows

```bash
dotnet run --project client/MoneyApp.Desktop
```

Al primo avvio compare il login; dalle volte successive l'app rientra da sola usando il
refresh token salvato nel Windows Credential Manager.

---

## Struttura del repository

```
Budgeting/
├─ docker-compose.yml        stack db + api
├─ .env.example              variabili non sensibili
├─ secrets/                  password e chiavi (mai versionate)
├─ docs/
│   ├─ ARCHITETTURA_MONEY_APP.md   documento di riferimento — decisioni chiuse
│   ├─ PROJECT_MEMORY.md           diario di bordo: stato, decisioni, changelog
│   └─ API.md                      elenco endpoint
├─ server/
│   ├─ Dockerfile · entrypoint.sh · requirements.txt · alembic.ini
│   ├─ alembic/versions/           migrazioni
│   ├─ app/
│   │   ├─ main.py                 app FastAPI, /health, montaggio router
│   │   ├─ config.py               env + segreti da file
│   │   ├─ db.py · models.py · schemas.py · enums.py · errors.py
│   │   ├─ scheduler.py            job APScheduler
│   │   ├─ seed.py                 utente e categorie iniziali
│   │   ├─ auth/                   hashing password, JWT, dipendenze
│   │   ├─ routers/                un file per risorsa REST
│   │   └─ services/               logica di dominio (saldi, ricorrenze, report,
│   │                              portafoglio, dati di mercato)
│   └─ tests/                      pytest
└─ client/
    ├─ MoneyApp.sln
    └─ MoneyApp.Desktop/
        ├─ Services/               ApiClient, MoneyApi, TokenStore, AppSettings
        ├─ Models/                 DTO speculari agli schemi del server
        ├─ ViewModels/             uno per pagina (MVVM)
        ├─ Views/                  XAML
        ├─ Controls/               grafico a linea disegnato a mano
        └─ Styles/                 tema
```

## Concetti chiave del modello

**I saldi non si salvano mai.** Il saldo di un conto è ricalcolato ad ogni lettura come
`saldo iniziale + entrate − uscite + trasferimenti in − trasferimenti out (+ operazioni su
titoli)`. È l'unico modo per rendere impossibile la deriva "saldo memorizzato ≠ somma dei
movimenti". Vedi [`server/app/services/balances.py`](server/app/services/balances.py).

**I trasferimenti non sono spese.** Spostare denaro dal conto corrente a Satispay o al
fondo risparmio non è né entrata né uscita: esiste l'entità `Transfer`, che muove i saldi
di entrambi i conti ma non compare nei report per categoria. Registrarli come spese
falserebbe ogni report mensile.

**I debiti usano gli snapshot, non le somme.** Per un mutuo il saldo è l'ultimo
`residual_amount` registrato, non la somma delle rate: derivarlo dai pagamenti
richiederebbe un piano di ammortamento (separare quota capitale e interessi), complessità
fuori scope. Le rate si registrano come normali spese dal conto corrente.

**Le occorrenze ricorrenti nascono "previste".** Un job genera in anticipo le occorrenze
come transazioni con `status = projected`: si vedono nel widget "in arrivo" ma **non**
entrano nei saldi finché non vengono confermate. Con `auto_confirm` si confermano da sole
alla data; senza, restano in attesa — comodo per le bollette a importo variabile.

**Gli obiettivi non hanno contabilità propria.** Un `Goal` è un'etichetta sopra un conto
`savings_goal`: il progresso è il saldo di quel conto. Per farlo crescere si fa un
trasferimento, non si "versa nell'obiettivo".

**Il portafoglio tiene liquidità e posizioni separate.** Un conto `investment` ha del
contante non investito e un elenco di posizioni; il saldo mostrato è la somma dei due. Il
costo medio di carico include le commissioni di acquisto, quindi la plusvalenza è già al
netto dei costi.

## Convenzioni del contratto API

Valgono identiche per il client Windows e per qualsiasi client futuro.

| Aspetto | Regola |
|---|---|
| Prefisso | `/api/v1/...` (una `/api/v2/` futura non romperà i client esistenti) |
| Importi | `NUMERIC(18,2)` nel DB, **stringhe decimali** in JSON (`"10.50"`), `decimal` in C#. Mai float |
| Date | `DATE` per la data contabile, ISO 8601 UTC per gli istanti; la conversione al fuso locale è del client |
| Errori | `{"error": {"code": "...", "message": "..."}}` — il client si basa su `code` |
| Liste | `?limit=&offset=&date_from=&date_to=&account_id=&category_id=` → `{items, total, limit, offset}` |
| Concorrenza | ogni risorsa ha `updated_at`; le PATCH accettano `expected_updated_at` e restituiscono `409 stale_update` invece di sovrascrivere in silenzio |
| Cancellazioni | soft-delete dove serve (`archived` sui conti/categorie, `deleted_at` su transazioni/trasferimenti) |
| Validazione | quella che conta è **sempre** lato server; il client valida solo per dare feedback immediato |

Il contratto completo e sempre aggiornato è l'OpenAPI generato da FastAPI:
<https://localhost:8443/openapi.json>. Elenco leggibile in [docs/API.md](docs/API.md).

## Sicurezza

**Autenticazione a due token.** Il login restituisce un *access token* (JWT HS256, 30
minuti) da mettere nell'header `Authorization: Bearer …`, e un *refresh token* opaco (30
giorni) usato solo per rinnovare l'access token. Del refresh token il database conserva
solo lo SHA-256: serve a poterlo **revocare** davvero (logout, cambio password), cosa
impossibile con un JWT autocontenuto. Ad ogni uso il refresh token viene ruotato e il
precedente revocato.

**Dove finiscono i segreti.** La password non viene mai salvata sul client, in nessuna
forma. Il refresh token va nel **Windows Credential Manager**, cifrato con DPAPI
sull'account Windows dell'utente — mai in un file di testo o JSON.

**TLS.** In sviluppo il certificato è self-signed. Il client non disattiva la verifica:
accetta quel certificato solo se corrisponde esattamente a quello pinnato
(`server/certs/server.crt`), altrimenti pretende una catena valida. Il browser mostrerà
comunque un avviso su `/docs`: è normale per un self-signed.

**Rete.** Il container `db` sta su una rete Docker interna senza porte pubblicate: è
raggiungibile solo dall'API. Quando il server si sposterà su un'altra macchina, l'accesso
passerà da una VPN personale (Tailscale/WireGuard), **mai** esponendo l'API su IP pubblico.

## Job schedulati

APScheduler gira dentro il container API (un servizio separato non serve: tre job brevi e
idempotenti). Con `RUN_SCHEDULER=false` l'API parte senza.

| Quando | Cosa |
|---|---|
| 00:10 UTC | genera le occorrenze delle ricorrenze fino a 90 giorni avanti |
| ogni 30 min | aggiorna `price_cache` e `fx_rate_cache` dal provider esterno |
| 23:50 UTC | salva lo snapshot del patrimonio netto (serve la serie storica) |

L'API di mercato non viene **mai** chiamata durante una richiesta dell'utente: né i
rate-limit del piano gratuito né un disservizio del provider devono poter bloccare la UI.
Ognuno dei job è richiamabile a mano (`POST /recurring/generate`,
`POST /portfolio/refresh-prices`, `POST /reports/net-worth/snapshot`).

## Test

```bash
# integrazione + unità, su un database `money_test` creato al volo
docker compose exec api pytest

# solo la logica pura delle ricorrenze, senza database
docker compose exec api pytest tests/test_recurrence.py
```

I test coprono le invarianti che costano care se si rompono: autenticazione e rotazione
dei refresh token, calcolo dei saldi, esclusione dei trasferimenti dai report di spesa,
budget con sotto-categorie, patrimonio netto con debiti, generazione idempotente delle
ricorrenze, media ponderata di carico e plusvalenze del portafoglio, controllo di
concorrenza.

## Comandi utili

```bash
docker compose logs -f api
```

```bash
docker compose exec api alembic revision --autogenerate -m "descrizione"
```

```bash
docker compose exec db psql -U money_app -d money
```

```bash
dotnet build client/MoneyApp.sln
```

## Problemi frequenti

**`docker compose up` fallisce sui segreti** — mancano i file in `secrets/`: sono
gitignorati, vanno generati come nell'[avvio rapido](#1-segreti).

**Il client dice "Server non raggiungibile"** — controlla `docker compose ps` e
`curl -k https://localhost:8443/health`. Se l'API risponde ma il client no, il problema è
il certificato: verifica che `server/certs/server.crt` esista e, se hai cambiato macchina
o percorso, correggi `ServerCertificatePath` in `%APPDATA%\MoneyApp\settings.json`.

**Il login funziona ma al riavvio ricompare** — il refresh token è stato revocato (logout,
cambio password) o `secrets/jwt_secret.txt` è cambiato. Basta rifare il login.

**Il portafoglio mostra "prezzo non disponibile"** — non c'è una API key configurata
oppure il job non è ancora passato. Inserisci il prezzo a mano dalla pagina Portafoglio
(`PUT /api/v1/portfolio/prices/{ticker}`): le posizioni senza prezzo sono valorizzate al
costo di carico.

**Titolo in valuta diversa dal conto** — imposta prima il cambio con
`PUT /api/v1/portfolio/fx/USD/EUR`, altrimenti l'operazione viene rifiutata con un
messaggio esplicito: meglio un errore chiaro che un saldo sbagliato.

## Documentazione

- [docs/ARCHITETTURA_MONEY_APP.md](docs/ARCHITETTURA_MONEY_APP.md) — documento di
  riferimento con le decisioni **chiuse**. Da leggere prima di modificare l'architettura.
- [docs/PROJECT_MEMORY.md](docs/PROJECT_MEMORY.md) — stato attuale, log delle decisioni
  con motivazioni e alternative scartate, schema dati, prossimi passi, changelog.
  **Va letto a inizio sessione e aggiornato a fine sessione.**
- [docs/API.md](docs/API.md) — elenco degli endpoint; lo schema autoritativo resta
  `/docs` generato da FastAPI.
