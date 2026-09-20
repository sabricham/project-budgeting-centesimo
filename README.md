# Centesimo

Applicazione web di gestione finanziaria personale: conti, movimenti, andamento del
patrimonio. Backend e frontend separati, entrambi in Docker, raggiungibili dalla rete di
casa e da internet tramite Tailscale.

```
backend/     API FastAPI + PostgreSQL, organizzata a moduli indipendenti
frontend/    React + TypeScript + Vite, componenti riusabili
docs/        architettura e deploy
.old/        la versione precedente del progetto, archiviata e catalogata
```

## Avvio

```bash
cp .env.example .env
openssl rand -base64 32 > secrets/db_password.txt
openssl rand -base64 48 > secrets/jwt_secret.txt
chmod 600 secrets/*.txt
docker compose up -d --build
docker compose exec api python -m app.seed --username <nome> --password '<password lunga>'
```

Il sito risponde su `http://localhost:8080`. La documentazione interattiva dell'API
su `/docs`.

## Le tre pagine

| Pagina | Contenuto |
|---|---|
| **Recap** | grafico dell'andamento del patrimonio nel periodo, totali di entrate, uscite e investimenti |
| **Storico** | tutti i movimenti in tabella, ordinabile per data, importo, categoria, sottocategoria, conto e tipo |
| **Aggiungi entry** | inserimento di un movimento, più il riquadro dei conti da cui si creano i conti nuovi |

I conti si creano dal riquadro «Conti» della terza pagina: nome, tipo e saldo attuale.
Il modulo si apre da solo finché non esiste nessun conto, così da un'installazione nuova
si arriva al primo movimento senza passare da riga di comando.

In alto l'ora in tempo reale e la data di oggi, sotto i pulsanti di navigazione.
Su Recap e Storico c'è il selettore del periodo — mese, settimana e anno navigabili con
le frecce, più le finestre mobili a 7, 30 e 365 giorni — e il selettore del conto, con la
voce «Tutti i conti».

## I tre tipi di movimento

`Entrata` somma sul conto, `Uscita` sottrae, `Investimento` **sposta** l'importo da un
conto a un altro. Il terzo esiste perché investire non è spendere: il denaro resta tuo e
cambia soltanto forma, quindi il patrimonio complessivo non deve muoversi. Lo stesso
meccanismo copre anche lo spostamento fra due conti propri, per esempio da banca a Satispay.

## Categorie

Il catalogo — 11 categorie e 71 sottocategorie — sta in
`backend/app/modules/categories/data/categories.json` e viene allineato al database ad
ogni avvio. È preso alla lettera: sottocategorie con lo stesso nome sotto categorie
diverse restano voci distinte e indipendenti.

## Aggiungere qualcosa

**Un dominio nel backend:** crea una cartella sotto `backend/app/modules/` con
`models.py`, `schemas.py`, `service.py`, `router.py` e un `__init__.py` che esporta
`router`; aggiungi il nome a `MODULES` in `backend/app/modules/__init__.py`. Poi
`docker compose run --rm api alembic revision --autogenerate -m "..."`. Nessun altro file
va toccato.

**Una pagina nel frontend:** aggiungi il componente in `frontend/src/pages/`, una
`<Route>` in `src/App.tsx` e una voce in `TABS` dentro `src/components/NavTabs.tsx`.

**Un periodo:** un caso in `frontend/src/lib/periods.ts`. Il backend non va toccato:
riceve solo `date_from` e `date_to`.

## Test

```bash
docker compose exec api python -m pytest -q
```

Girano su un database separato, creato e distrutto al volo: non toccano mai i dati reali.

## Documentazione

- [docs/ARCHITETTURA.md](docs/ARCHITETTURA.md) — struttura, modello dati, scelte e alternative scartate
- [docs/DEPLOY.md](docs/DEPLOY.md) — avvio, Tailscale Funnel e i suoi limiti, backup
- [.old/README.md](.old/README.md) — catalogo della versione precedente, per ripescarne i pezzi
