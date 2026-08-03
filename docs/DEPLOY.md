# Deploy — Money App

Come è fatto il deploy del backend e come rifarlo/aggiornarlo. Il documento descrive la
situazione reale, non un ideale: se cambi qualcosa sul server, cambia anche questo file.

---

## 1. Topologia

```
   ┌──────────────────────────────┐            ┌───────────────────────────────────┐
   │  PC Windows (sviluppo)       │            │  192.168.1.104  "office"          │
   │  C:\...\Projects\Budgeting   │            │  Ubuntu 24.04 · utente `office`   │
   │                              │            │                                   │
   │  server/   ← SORGENTI        │  deploy    │  /home/office/Budgeting           │
   │  client/   ← app WPF ────────┼───────────▶│    server/            (copia)     │
   │  docs/                       │   scp      │    docker-compose.yml             │
   │                              │            │    .env      (solo qui)           │
   │  app desktop ────────────────┼───HTTPS───▶│    secrets/  (solo qui)           │
   └──────────────────────────────┘   :8443    │                                   │
                                               │  docker compose:                  │
                                               │    api  → 0.0.0.0:8443 (pubblica) │
                                               │    db   → rete `internal`, chiusa │
                                               └───────────────────────────────────┘
```

**La macchina Windows resta la fonte di verità dei sorgenti.** Sul server c'è una copia
di `server/` che viene sovrascritta ad ogni deploy: non modificare i file direttamente
là, andrebbero persi al deploy successivo.

Il `client/` non viene mai copiato sul server: gira solo su Windows.

| | |
|---|---|
| Host | `192.168.1.104` (anche Tailscale `100.89.5.18`, hostname `office`) |
| SO | Ubuntu 24.04.4 LTS |
| Utente | `office` (nel gruppo `sudo` e `docker`) |
| Cartella | `/home/office/Budgeting` |
| Docker | Engine 29.7.1, Compose v5.4.0, dal repo ufficiale Docker |
| API | `https://192.168.1.104:8443` — Swagger su `/docs` |

---

## 2. Cosa vive solo sul server e non è nel repository

Tre cose non vengono mai copiate da Windows, e questo è voluto:

| File | Perché sta solo là |
|---|---|
| `secrets/db_password.txt` | generato sul server con `openssl rand -hex 16`. Un segreto che viaggia è un segreto in più da custodire |
| `secrets/jwt_secret.txt` | idem, `openssl rand -hex 32`. Cambiarlo invalida tutti i token emessi |
| `secrets/market_data_api_key.txt` | **vuoto**: nessuna API key registrata. Con il file vuoto il provider diventa `NullProvider` e il portafoglio resta usabile inserendo i prezzi a mano |
| `.env` | contiene la configurazione del deploy, incluso il SAN del certificato |
| `server/certs/` | certificato self-signed generato al primo avvio. **Non va rigenerato**: il client ne pinna i byte |

Sono tutti in `.gitignore`. Il modello è `.env.example`, che invece è versionato.

---

## 3. Il certificato — il punto che rompe le cose se lo si ignora

Il client Windows **pinna** il certificato (§1.1 dell'architettura): non disattiva la
verifica TLS, confronta i byte del certificato presentato con quelli di una copia locale.
Ne discendono due conseguenze pratiche:

1. **Il certificato deve elencare l'indirizzo con cui il server viene raggiunto.**
   L'entrypoint lo genera per `localhost` più i nomi in `CERT_EXTRA_SAN`. Sul deploy
   attuale il `.env` contiene:

   ```
   CERT_CN=192.168.1.104
   CERT_EXTRA_SAN=IP:192.168.1.104,DNS:office,DNS:office.local,IP:100.89.5.18
   ```

2. **Se rigeneri il certificato devi ridistribuirlo al client**, altrimenti il pinning
   fallisce e l'app non si collega più. L'entrypoint apposta non lo rigenera finché
   `server/certs/server.crt` e `server.key` esistono: cambiare `CERT_EXTRA_SAN` a
   posteriori non ha alcun effetto da solo.

Per rigenerarlo davvero (es. hai aggiunto un indirizzo):

```bash
ssh office@192.168.1.104 "cd ~/Budgeting && docker compose down && rm -rf server/certs && docker compose up -d"
```

...e poi rifare il passo 5.2 (riscaricare il `.crt` sul client).

---

## 4. Deploy da zero su una macchina nuova

### 4.1 Docker

Dal repo ufficiale Docker (non `docker.io` di Ubuntu, che è più vecchio e senza il
plugin `compose`):

```bash
sudo apt-get update && sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list
sudo apt-get update && sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```

L'ultima riga evita il `sudo` davanti ad ogni comando docker. **Serve riaprire la
sessione SSH** perché il nuovo gruppo venga applicato.

### 4.2 Sorgenti

Da Windows, nella root del progetto (Git Bash o WSL):

```bash
tar --exclude='__pycache__' --exclude='*.pyc' --exclude='.pytest_cache' --exclude='certs' -czf /tmp/money-server.tar.gz server docker-compose.yml .env.example
scp /tmp/money-server.tar.gz office@192.168.1.104:~/Budgeting/
ssh office@192.168.1.104 "cd ~/Budgeting && tar -xzf money-server.tar.gz && rm money-server.tar.gz"
```

`client/` è escluso di proposito: sul server non serve.

### 4.3 Segreti e configurazione

Sul server, una volta sola:

```bash
cd ~/Budgeting && mkdir -p secrets && chmod 700 secrets
openssl rand -hex 16 | tr -d '\n' > secrets/db_password.txt
openssl rand -hex 32 | tr -d '\n' > secrets/jwt_secret.txt
: > secrets/market_data_api_key.txt
chmod 600 secrets/*.txt
cp .env.example .env && chmod 600 .env
```

Poi in `.env` va messo l'indirizzo reale del server in `CERT_CN` / `CERT_EXTRA_SAN`
(vedi §3) e `MARKET_DATA_PROVIDER=none` finché non c'è una API key.

### 4.4 Avvio

```bash
cd ~/Budgeting && docker compose up -d --build
```

L'entrypoint genera il certificato e applica le migrazioni Alembic da solo.

### 4.5 Utente applicativo

```bash
docker compose exec api python -m app.seed --username sabri
```

Stampa una password generata **una volta sola**. Con `--password 'xxx'` la scegli tu,
con `--demo` crea anche dei conti di esempio. È idempotente: rilanciarlo non duplica
nulla e non cambia la password di un utente esistente.

---

## 5. Aggiornare un deploy esistente

### 5.1 Ho cambiato il codice del server

Da Windows:

```bash
tar --exclude='__pycache__' --exclude='*.pyc' --exclude='.pytest_cache' --exclude='certs' -czf /tmp/money-server.tar.gz server docker-compose.yml
scp /tmp/money-server.tar.gz office@192.168.1.104:~/Budgeting/
ssh office@192.168.1.104 "cd ~/Budgeting && tar -xzf money-server.tar.gz && rm money-server.tar.gz && docker compose up -d --build"
```

Il `Dockerfile` fa `COPY . .`: l'immagine va **ricostruita**, non basta riavviare il
container. Le migrazioni nuove vengono applicate dall'entrypoint all'avvio.

> Attenzione a `scp` con più file verso una cartella: finiscono tutti allo stesso
> livello, ignorando la sottocartella di origine. Per file singoli dentro `server/tests/`
> indica il percorso completo di destinazione.

### 5.2 Riportare il certificato sul client Windows

```bash
scp office@192.168.1.104:~/Budgeting/server/certs/server.crt "$APPDATA/MoneyApp/server.crt"
```

---

## 6. Comandi operativi

Tutti da eseguire in `~/Budgeting` sul server.

| Cosa | Comando |
|---|---|
| Stato | `docker compose ps` |
| Log dell'API | `docker compose logs -f api` |
| Riavvio | `docker compose restart api` |
| Stop | `docker compose down` (i dati restano nel volume `budgeting_pgdata`) |
| Test | `docker compose exec api pytest -q` |
| Shell nel container | `docker compose exec api bash` |
| psql | `docker compose exec db psql -U money_app -d money` |
| Health | `curl -sk https://192.168.1.104:8443/health` |

I container hanno `restart: unless-stopped`: **ripartono da soli al riavvio del server**,
non serve nulla in systemd.

### Backup

Il dato vive tutto nel volume Docker `budgeting_pgdata`. Un dump logico:

```bash
docker compose exec -T db pg_dump -U money_app money | gzip > ~/backup-money-$(date +%F).sql.gz
```

Ripristino su un database vuoto:

```bash
gunzip -c backup-money-2026-08-04.sql.gz | docker compose exec -T db psql -U money_app -d money
```

Non c'è ancora niente di schedulato: per ora è un comando da lanciare a mano.

---

## 7. Rete e sicurezza

- Il servizio `db` **non pubblica porte**: sta sulla rete Docker `internal` (che ha
  `internal: true`, quindi nemmeno accesso a internet). Postgres non è raggiungibile
  dalla LAN, solo dal container `api`.
- L'unica porta esposta è `8443/tcp` dell'API.
- Il certificato è self-signed: va bene finché il consumo è LAN + Tailscale con pinning
  lato client. **Non esporre `8443` su internet con un port forward.** L'accesso da fuori
  casa è previsto via Tailscale (l'IP `100.89.5.18` è già nel SAN del certificato), come
  da §1.4 dell'architettura.
- I segreti sono file montati in `/run/secrets`, mai variabili d'ambiente in chiaro.

---

## 8. Client Windows

Configurazione in `%APPDATA%\MoneyApp\settings.json` (creato a mano o dall'app):

```json
{
  "ApiBaseUrl": "https://192.168.1.104:8443",
  "ServerCertificatePath": "C:\\Users\\sabri\\AppData\\Roaming\\MoneyApp\\server.crt"
}
```

Il refresh token **non** sta qui: è nel Windows Credential Manager (§1.1).

Build ed avvio:

```bash
dotnet build client/MoneyApp.sln -c Release
```

L'eseguibile è `client/MoneyApp.Desktop/bin/Release/net10.0-windows/MoneyApp.exe`.
