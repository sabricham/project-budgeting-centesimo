#!/bin/sh
set -e

CERT_DIR=/app/certs
CERT_FILE="$CERT_DIR/server.crt"
KEY_FILE="$CERT_DIR/server.key"

mkdir -p "$CERT_DIR"

# Certificato self-signed (§1.4).
# Non viene rigenerato ad ogni avvio: il client Windows ne pinna l'impronta,
# rigenerarlo ogni volta costringerebbe a riconfigurare il client.
#
# CERT_EXTRA_SAN aggiunge i nomi con cui il server è raggiunto dalla rete, in
# sintassi openssl e separati da virgola, es:
#     CERT_EXTRA_SAN="IP:192.168.1.104,DNS:office"
# Senza, il certificato varrebbe solo per localhost e ogni strumento che verifica
# davvero il nome (browser su Swagger, curl, futuro client Android) lo rifiuterebbe.
SAN="DNS:localhost,DNS:money-api,IP:127.0.0.1"
if [ -n "${CERT_EXTRA_SAN:-}" ]; then
    SAN="$SAN,$CERT_EXTRA_SAN"
fi

if [ ! -f "$CERT_FILE" ] || [ ! -f "$KEY_FILE" ]; then
    echo "[entrypoint] genero il certificato self-signed in $CERT_DIR (SAN: $SAN)"
    openssl req -x509 -nodes -newkey rsa:2048 \
        -days 3650 \
        -keyout "$KEY_FILE" \
        -out "$CERT_FILE" \
        -subj "/CN=${CERT_CN:-localhost}/O=Centesimo/C=IT" \
        -addext "subjectAltName=$SAN" \
        2>/dev/null
    chmod 600 "$KEY_FILE"
else
    echo "[entrypoint] certificato già presente in $CERT_DIR, lo riuso"
fi

echo "[entrypoint] applico le migrazioni Alembic"
alembic upgrade head

echo "[entrypoint] avvio uvicorn su https://0.0.0.0:8443"
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8443 \
    --ssl-certfile "$CERT_FILE" \
    --ssl-keyfile "$KEY_FILE" \
    --log-level "${LOG_LEVEL:-info}" \
    --proxy-headers
