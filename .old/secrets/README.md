# secrets/

Contiene i segreti montati dai container come Docker secrets. **Nessuno di questi file
finisce nel repository** (vedi `.gitignore`): qui sono versionati solo i `.example`.

Genera i file reali prima del primo `docker compose up` (da PowerShell, nella root del repo):

```powershell
# password del database
[Convert]::ToBase64String((1..24 | ForEach-Object { Get-Random -Max 256 })) | Out-File -Encoding ascii -NoNewline secrets/db_password.txt

# segreto di firma dei JWT (§1.1)
[Convert]::ToBase64String((1..48 | ForEach-Object { Get-Random -Max 256 })) | Out-File -Encoding ascii -NoNewline secrets/jwt_secret.txt

# chiave API prezzi di mercato (§2.8) — lascia vuoto se non ne hai una:
# il portafoglio funziona lo stesso con i prezzi inseriti a mano
"" | Out-File -Encoding ascii -NoNewline secrets/market_data_api_key.txt
```

Note:
- i file devono essere **senza BOM e senza newline finale** (`-Encoding ascii -NoNewline`);
  l'API fa comunque `strip()` del contenuto letto;
- cambiare `jwt_secret.txt` invalida tutti gli access token emessi — è il modo più rapido
  per fare un "logout globale";
- cambiare `db_password.txt` dopo la prima inizializzazione **non** cambia la password
  dell'utente Postgres già creato nel volume `pgdata`: va cambiata anche nel DB (o si
  ricrea il volume).
