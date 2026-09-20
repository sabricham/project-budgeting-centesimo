#!/bin/sh
set -e

echo "[entrypoint] attendo il database"
python - <<'PY'
import asyncio, sys
import asyncpg
from app.core.config import settings

async def wait():
    url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    for attempt in range(1, 31):
        try:
            conn = await asyncpg.connect(url)
            await conn.close()
            return
        except Exception as exc:
            print(f"[entrypoint]   tentativo {attempt}/30: {exc}")
            await asyncio.sleep(2)
    sys.exit("[entrypoint] database non raggiungibile")

asyncio.run(wait())
PY

echo "[entrypoint] applico le migrazioni"
alembic upgrade head

# --proxy-headers: davanti c'è nginx e, più avanti, Tailscale Funnel. Senza questo
# flag ogni richiesta sembrerebbe arrivare dall'IP del reverse proxy e il limitatore
# di tentativi sul login bloccherebbe tutti insieme invece del singolo chiamante.
echo "[entrypoint] avvio uvicorn su 0.0.0.0:8000"
exec uvicorn app.main:app \
    --host 0.0.0.0 --port 8000 \
    --proxy-headers --forwarded-allow-ips='*' \
    --log-level "${LOG_LEVEL:-info}"
