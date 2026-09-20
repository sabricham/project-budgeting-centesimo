# Segreti

I file `*.txt` di questa cartella sono **fuori dal repository** (vedi `.gitignore`) e
vanno generati sulla macchina che esegue lo stack. Non si copiano da un'altra macchina:
un segreto che viaggia è un segreto in più da custodire.

```bash
openssl rand -base64 32 > secrets/db_password.txt
openssl rand -base64 48 > secrets/jwt_secret.txt
chmod 600 secrets/*.txt
```

Rigenerare `jwt_secret.txt` invalida tutte le sessioni aperte: si rifà il login e basta.
Rigenerare `db_password.txt` dopo il primo avvio **non** cambia la password dentro
Postgres, che è già stata impostata nel volume: andrebbe cambiata anche lì con `ALTER ROLE`.
