# Architettura — Centesimo v2

Documento di riferimento. La versione precedente del progetto è archiviata in
[`.old/`](../.old/README.md), con il catalogo di cosa contiene.

---

## 1. Forma generale

Tre servizi, una sola porta esposta.

```
                     internet                    rete di casa
                        │                             │
              Tailscale Funnel                        │
           (HTTPS, certificato vero)                  │
                        │                             │
                        └──────────┬──────────────────┘
                                   ▼
                        ┌──────────────────────┐
                        │  web  (nginx :8080)  │   sito + inoltro /api
                        └──────────┬───────────┘
                                   ▼
                        ┌──────────────────────┐
                        │  api  (FastAPI :8000)│   HTTP, mai esposto
                        └──────────┬───────────┘
                                   ▼
                        ┌──────────────────────┐
                        │  db   (Postgres)     │   nessuna porta pubblicata
                        └──────────────────────┘
```

Frontend e API stanno **sotto la stessa origine**: nginx serve il sito e inoltra tutto
ciò che inizia con `/api/` al backend. Conseguenze volute: niente CORS da configurare,
nessun indirizzo dell'API da tenere aggiornato nel frontend, e lo stesso identico
pacchetto funziona da `localhost`, dalla rete di casa e da internet.

**Il TLS non è nell'applicazione.** Nella v1 l'API generava un certificato self-signed che
il client doveva "pinnare", ed è stata la fonte principale dei problemi di connessione.
Qui il certificato lo gestisce Tailscale, che ne emette uno vero di Let's Encrypt: il
browser lo accetta senza avvisi e non c'è niente da installare sui dispositivi.

---

## 2. Backend — monolite modulare

```
backend/app/
  main.py              monta i moduli in ciclo; non cresce quando cresce il progetto
  core/                ciò che è condiviso e non appartiene a nessun dominio
    config.py          variabili d'ambiente + segreti da file
    db.py              engine, sessione, Base, TimestampMixin
    errors.py          eccezioni di dominio e formato d'errore uniforme
    security.py        password e token: funzioni pure, nessun modello
    pagination.py      get_owned, paginate, apply_updates
    ratelimit.py       limitatore di tentativi sul login
    deps.py            DbSession
  modules/
    __init__.py        ← il registro: MODULES = (auth, accounts, categories, entries, reports)
    auth/              models · schemas · service · router · deps
    accounts/          models · schemas · service · router
    categories/        models · schemas · service · router · data/categories.json
    entries/           models · schemas · service · router
    reports/           schemas · service · router
```

### La regola del modulo

Un modulo è una cartella che contiene **tutto** di un dominio: le sue tabelle, i suoi
schemi, la sua logica, i suoi endpoint. Aggiungere un dominio significa creare una
cartella e aggiungere un nome a `MODULES`. Nessun file centrale va modificato:

- `main.py` monta i router scorrendo il registro;
- Alembic vede le nuove tabelle perché l'import nel registro le iscrive su `Base.metadata`.

Nella v1 c'erano un `models.py` di 563 righe e uno `schemas.py` di 651 condivisi da tutti:
ogni funzionalità toccava gli stessi tre file, e capire dove finiva una e cominciava
l'altra richiedeva di leggerli per intero.

### Direzione delle dipendenze

`entries` → `accounts`, `categories` → e basta. Il verso non si inverte mai: `accounts`
non importa `entries` a livello di modulo, e quando gli serve il saldo lo chiede con un
import locale dentro la funzione. Le foreign key sono dichiarate per nome di tabella
(`"accounts.id"`), quindi non creano dipendenze fra moduli Python.

**Perché non database separati per modulo:** la pagina Storico deve mostrare, in una
riga sola, la entry col nome del suo conto e della sua categoria. Con database distinti
quella join andrebbe rifatta a mano in Python, pagina per pagina, perdendo ordinamento e
paginazione lato server. La separazione che conta è **logica**, ed è garantita dalla
struttura a moduli.

---

## 3. Modello dati

| Tabella | Contenuto | Note |
|---|---|---|
| `users` | utente, hash bcrypt, valuta base | uno solo oggi, modello già multi-utente |
| `refresh_tokens` | SHA-256 del token, scadenza, `revoked_at` | consente la revoca reale |
| `categories` | nome, `position` | catalogo globale, non per-utente |
| `subcategories` | `category_id`, nome, `position` | tabella separata, niente self-FK |
| `accounts` | nome, tipo, valuta, `initial_balance`, `archived` | **nessuna colonna saldo** |
| `entries` | data, descrizione, importo, `kind`, conto, conto destinazione, sottocategoria, `deleted_at` | il cuore |

Denaro `NUMERIC(18,2)`, mai `FLOAT`. Istanti `TIMESTAMPTZ` in UTC, date contabili `DATE`.
Sul filo gli importi viaggiano come **stringhe decimali**.

### Categorie: il JSON alla lettera

Il catalogo in `backend/app/modules/categories/data/categories.json` è la fonte di verità:
11 categorie, 71 sottocategorie. Viene allineato al database ad ogni avvio, in modo
idempotente — aggiunge soltanto, non rinomina e non cancella, perché delle entry
potrebbero già puntare a una voce.

Due scelte esplicite, richieste dall'utente:

- **Sottocategorie omonime restano distinte.** «Regali» sotto *Acquisti* e «Regali» sotto
  *Entrata* sono due righe senza alcun legame, così come «Lotteria e gioco d'azzardo» e
  «Assegno di mantenimento». Una entry punta alla sottocategoria per id, e la categoria
  si ricava da lì: la coppia è sempre univoca.
- **Il tipo di movimento non si deduce dalla categoria.** Nessuna regola dice che la
  categoria «Entrata» implichi un'entrata. L'utente sceglie il tipo, e sceglie la
  categoria, e le due cose restano indipendenti.

### I tre tipi di movimento

| `kind` | Effetto sui saldi |
|---|---|
| `income` | `account_id` **+** importo |
| `expense` | `account_id` **−** importo |
| `investment` | `account_id` **−** importo, `to_account_id` **+** importo |

`amount` è sempre positivo: il segno lo dà il tipo, non il numero.

**Perché `investment` sposta denaro fra due conti.** Investire 500 € non è spendere 500 €:
il denaro resta tuo e cambia soltanto forma. Trattandolo come una spesa, il grafico del
patrimonio mostrerebbe un calo di 500 € che non è mai avvenuto. Modellandolo come
movimento fra conti, sommando tutti i conti vale zero — il patrimonio totale non si muove,
cambia solo la sua distribuzione. Lo stesso meccanismo copre gratis anche il semplice
spostamento da banca a Satispay, che avrebbe lo stesso identico problema.

Il database lo garantisce con un CHECK: il conto di destinazione esiste **se e solo se**
il movimento è un investimento, e non può coincidere con quello di partenza.

### Saldi

Il saldo non è mai una colonna. Si ricalcola sempre da `initial_balance` più i movimenti,
in `entries/service.py`. È la scelta che rende impossibile la deriva «saldo salvato
diverso dalla somma dei movimenti», che su un'app di contabilità è il difetto peggiore
perché è silenzioso.

---

## 4. Periodi — il backend non li conosce

Non esiste nessun enum `mese | settimana | anno` lato server. Il frontend calcola
`date_from` e `date_to` in `frontend/src/lib/periods.ts` e li manda; il backend riceve
due date e basta.

Le sei modalità richieste:

| Modalità | Comportamento |
|---|---|
| Mese, Settimana, Anno | navigabili avanti e indietro con le frecce |
| Ultimi 7 / 30 / 365 giorni | finestre mobili che finiscono oggi, senza frecce |

**Perché così.** Nella v1 il periodo era un enum lato server che significava sempre
«corrente»: non sapeva navigare, e aggiungerne uno richiedeva di toccare backend, schemi
e client. Ora aggiungere «ultimi 90 giorni» è un caso in più in un file solo, e il server
non se ne accorge nemmeno.

L'unica cosa che il server deduce è la **granularità** dei punti del grafico, perché
dipende solo dall'ampiezza dell'intervallo: fino a 62 giorni un punto al giorno, fino a
400 uno a settimana, oltre uno al mese. Trecentosessantacinque punti giornalieri su un
anno sono illeggibili.

La serie parte dal patrimonio posseduto **alla vigilia** del periodo (`opening_balance`),
non da zero: è quello che rende la linea il patrimonio reale e non la somma dei flussi.

---

## 5. Frontend — componenti riusabili

```
frontend/src/
  lib/periods.ts       le 6 modalità di periodo, funzioni pure
  lib/format.ts        formattazione italiana di importi, date, ore
  lib/kinds.ts         i tre tipi con etichette e colori
  api/client.ts        fetch + token + rinnovo automatico
  api/endpoints.ts     un punto solo in cui è scritto com'è fatta l'API
  state/AppData.tsx    utente, conti, categorie: caricati una volta
  state/Filters.tsx    periodo e conto, condivisi fra Recap e Storico
  components/          i blocchi riusabili
  pages/               le tre pagine, sottili
```

I componenti sono il punto del requisito «riutilizzare i moduli»:

| Componente | Dove si usa |
|---|---|
| **`EntryForm`** | il blocco chiave: pagina Aggiungi oggi, ovunque si inserisca una entry domani. Non conosce la pagina che lo ospita, riceve conti e categorie e segnala l'esito con `onSaved` |
| **`AccountForm`** | creazione di un conto. Vive nel riquadro «Conti» della pagina Aggiungi; se un giorno arriverà una pagina dedicata ai conti si sposta lì senza modifiche |
| `PeriodSelector` | Recap, Storico |
| `AccountSelector` | Recap, Storico, e due volte dentro `EntryForm` (partenza e destinazione) |
| `FilterBar` | Recap, Storico — periodo + conto insieme |
| `DataTable` | tabella ordinabile generica: riceve le colonne come dati, non conosce le entry |
| `NetWorthChart`, `StatTiles`, `Clock`, `NavTabs`, `AppShell` | intelaiatura comune |

Le pagine sono sottili di proposito: `AddEntryPage` è poco più di un `<EntryForm />`
circondato dai saldi.

**Ordinamento lato server.** `DataTable` non riordina: segnala su quale colonna si è
cliccato e chi la usa rifà la richiesta. Su dati paginati ordinare nel browser
riordinerebbe la pagina visibile, non l'insieme — un risultato sbagliato che sembra giusto.
La colonna «descrizione» semplicemente non ha una chiave di ordinamento, ed è così che
resta esclusa.

**Una regola sola per gli importi.** `parseAmount` in `lib/format.ts` traduce «1.250,80»
in «1250.80» ed è usata da ogni campo importo. Quando `AccountForm` ne aveva una copia
semplificata, accettava la virgola ma non il separatore delle migliaia: è il motivo per
cui una funzione del genere deve stare in un posto solo.

**Stili.** Tutti i colori e le spaziature stanno in `styles/tokens.css`. Nessun componente
scrive un colore letterale: si rifà il tema cambiando un file solo.

---

## 6. Sicurezza

L'applicazione è raggiungibile da internet, quindi il login è l'unica cosa fra un
estraneo e i dati.

- Password con hash **bcrypt**, mai in chiaro da nessuna parte.
- **Access token** JWT a vita breve, verificato su firma e scadenza senza toccare il database.
- **Refresh token** opaco a vita lunga, di cui nel database sta solo lo SHA-256: revocabile
  davvero (logout, cambio password) e illeggibile a chi accedesse al database. Ruotato ad
  ogni uso.
- **Limitatore di tentativi** sul login: 8 per indirizzo in 5 minuti, poi 429. È il motivo
  per cui uvicorn gira con `--proxy-headers` e nginx passa `X-Forwarded-For` — senza,
  tutte le richieste sembrerebbero venire da nginx e un blocco fermerebbe tutti insieme.
- Il messaggio d'errore del login è identico per utente inesistente e password sbagliata:
  non si rivela quali nomi utente esistono.
- Postgres non pubblica nessuna porta; l'API non è raggiungibile se non attraverso nginx.

---

## 7. Decisioni scartate, da non riproporre

| Scartata | Perché |
|---|---|
| Client desktop | il requisito è un sito raggiungibile ovunque; la v1 in WPF è in `.old/` |
| Certificato self-signed con pinning | lo fa Tailscale con un certificato vero |
| Database separati per modulo | romperebbe le join di Storico (§2) |
| Dedurre il tipo di movimento dalla categoria | scelta esplicita dell'utente (§3) |
| Fondere sottocategorie omonime | scelta esplicita dell'utente (§3) |
| Enum di periodo lato server | non sa navigare (§4) |
| Ordinamento nel browser | sbagliato su dati paginati (§5) |
| `investment` come terzo tipo su un conto solo | falserebbe il grafico del patrimonio (§3) |
