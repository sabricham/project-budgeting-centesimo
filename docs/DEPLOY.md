# Deploy e accesso remoto

Lo stack gira su questa stessa macchina: nodo Tailscale **`office`**, `100.89.5.18`,
MagicDNS `office.tailfc4c52.ts.net`. Non c'è un PC di sviluppo separato.

## 1. Avvio da zero

```bash
cd /home/office/project-budgeting-centesimo
cp .env.example .env
openssl rand -base64 32 > secrets/db_password.txt
openssl rand -base64 48 > secrets/jwt_secret.txt
chmod 600 secrets/*.txt
docker compose up -d --build
docker compose exec api python -m app.seed --username <nome> --password '<password lunga>'
```

Il sito risponde su `http://<ip-del-server>:8080`. Le migrazioni si applicano da sole
all'avvio e il catalogo delle categorie si allinea al JSON.

## 2. Comandi operativi

```bash
docker compose ps                    # stato dei tre servizi
docker compose logs -f api           # log del backend
docker compose restart api           # riavvio senza ricostruire
docker compose up -d --build         # dopo una modifica al codice
docker compose exec api alembic upgrade head
```

Documentazione interattiva dell'API: `http://<host>:8080/docs`.

### Backup

```bash
docker compose exec -T db pg_dump -U centesimo centesimo | gzip > backup-$(date +%F).sql.gz
```

Oggi è **da lanciare a mano**: non c'è niente di schedulato.

---

## 3. Accesso da internet — Tailscale Funnel

### Cosa serve prima

Tre prerequisiti, tutti da sistemare **una sola volta** e tutti nel tuo account Tailscale.
Verificato il 2026-09-20: **nessuno dei tre è ancora attivo.**

1. **HTTPS nella tailnet.** Console di amministrazione → *DNS* → «Enable HTTPS».
   Senza, Tailscale non può emettere il certificato. (Oggi `CertDomains` è vuoto.)

2. **Permesso di Funnel sul nodo.** Console → *Access controls*, aggiungere alla policy:

   ```json
   "nodeAttrs": [
     { "target": ["autogroup:member"], "attr": ["funnel"] }
   ]
   ```

   (Oggi il nodo non ha la capability `funnel`.)

3. **Un `tailscale funnel` lanciato da root**, perché nessun utente è impostato come
   operator.

### Accendere

```bash
sudo tailscale funnel --bg 8080
```

Da quel momento il sito risponde su `https://office.tailfc4c52.ts.net`, con certificato
Let's Encrypt valido, da qualunque dispositivo al mondo.

Per spegnere:

```bash
sudo tailscale funnel --https=443 off
```

Per controllare: `tailscale funnel status`.

### Attenzione al conflitto sulla porta 443

Su questa macchina **Pi-hole occupa già `0.0.0.0:443`** (gira in rete host). Se Funnel
non riesce a prendere la 443, le uniche altre porte che ammette sono **8443 e 10000**:

```bash
sudo tailscale funnel --bg --https=8443 8080
```

L'indirizzo diventa `https://office.tailfc4c52.ts.net:8443` — più scomodo da digitare,
identico in tutto il resto. La 8443 si è liberata spegnendo il vecchio stack.

### Solo tailnet, senza esporre nulla

Se un giorno l'accesso pubblico non servisse più, `serve` al posto di `funnel` dà lo
stesso HTTPS con certificato valido ma **solo** ai dispositivi della tailnet:

```bash
sudo tailscale serve --bg 8080
```

---

## 4. Limiti del Funnel — da conoscere

Il Funnel risolve il problema «accedere da ovunque senza comprare un dominio», ma ha
confini precisi.

**È pubblico davvero, e l'indirizzo non è segreto.** Chiunque abbia l'URL arriva alla
pagina di accesso. Peggio: il certificato Let's Encrypt viene registrato nei log pubblici
di *Certificate Transparency*, quindi `office.tailfc4c52.ts.net` è **scopribile da
chiunque**, senza che nessuno te lo debba dire. Non esiste nessuna sicurezza per
oscurità: **la password è l'unica barriera**. Per questo il seed rifiuta password sotto i
10 caratteri e il login è limitato a 8 tentativi ogni 5 minuti.

**Solo tre porte, solo HTTPS.** Funnel accetta 443, 8443 e 10000 e nient'altro. Nessun
traffico che non sia HTTPS o TCP terminato da Tailscale.

**Il traffico passa dall'infrastruttura di Tailscale.** Le connessioni da internet non
arrivano dirette: transitano per i relay DERP. In pratica significa latenza più alta di
una connessione diretta e una banda soggetta alle condizioni di uso corretto del servizio.
Per un'app di budgeting usata da una persona è del tutto irrilevante; per trasferire file
grossi no.

**Nessuna protezione applicativa davanti.** Niente WAF, niente mitigazione DDoS, nessun
filtro per paese o indirizzo. Quello che arriva alla porta 8080 è quello che nginx riceve.

**Dipende dal demone Tailscale.** Se `tailscaled` si ferma o il nodo perde la connessione
al coordinatore, il sito sparisce da internet — pur continuando a funzionare in rete locale.

**Il certificato è legato al nome della tailnet.** Se rinomini la tailnet, l'indirizzo
cambia. Non è un dominio tuo e non è portabile altrove.

**Come stringere la sicurezza, se in futuro servisse:** comprare un dominio e metterci
davanti un reverse proxy con Let's Encrypt e filtro sugli indirizzi; oppure tenere
`serve` invece di `funnel` e installare Tailscale su ogni dispositivo da cui accedi —
è la modalità più sicura, al prezzo di non poter usare un PC qualsiasi.

---

## 5. Accesso dalla rete di casa

Sempre disponibile e indipendente dal Funnel: `http://192.168.1.104:8080`
(o l'indirizzo Tailscale `http://100.89.5.18:8080` da un dispositivo della tailnet).
In HTTP, perché dentro la propria rete non c'è nulla da terminare.

---

## 6. Il vecchio stack

La v1 girava da `/home/office/Budgeting` sulla porta 8443, con un database separato.
È stata spenta. Il codice è archiviato in [`.old/`](../.old/README.md); la cartella
`/home/office/Budgeting` con il suo volume Postgres può essere rimossa quando vuoi:

```bash
cd /home/office/Budgeting && docker compose down -v
```
