"""Money App — API REST (§1.2).

Unico punto di accesso ai dati: nessun client parla direttamente col database.
Tutti gli endpoint di dominio stanno sotto `/api/v1` e richiedono un access token;
fanno eccezione `/health` e `/api/v1/auth/login|refresh`.

Documentazione interattiva: https://localhost:8443/docs
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.config import settings
from app.db import engine
from app.errors import register_error_handlers
from app.routers import (
    accounts,
    auth,
    budgets,
    categories,
    dashboard,
    goals,
    liabilities,
    portfolio,
    recurring,
    reports,
    transactions,
    transfers,
)
from app.scheduler import scheduler_status, shutdown_scheduler, start_scheduler
from app.schemas import HealthOut

VERSION = "1.0.0"

logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    try:
        yield
    finally:
        shutdown_scheduler()
        await engine.dispose()


app = FastAPI(
    title="Money App API",
    version=VERSION,
    description=(
        "API di gestione finanziaria personale. Importi come stringhe decimali, "
        "date in ISO 8601 UTC. Vedi docs/ARCHITETTURA_MONEY_APP.md."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url=None,
    openapi_url="/openapi.json",
)

register_error_handlers(app)

for router in (
    auth.router,
    accounts.router,
    categories.router,
    budgets.router,
    transactions.router,
    transfers.router,
    liabilities.router,
    goals.router,
    recurring.router,
    reports.router,
    dashboard.router,
    portfolio.router,
):
    app.include_router(router, prefix=settings.api_prefix)


@app.get("/health", response_model=HealthOut, tags=["health"])
async def health() -> HealthOut:
    """Stato del servizio: usato dall'healthcheck Docker e dal client all'avvio."""
    db_status = "ok"
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        logging.getLogger(__name__).warning("health: DB non raggiungibile: %s", exc)
        db_status = "error"

    return HealthOut(
        status="ok" if db_status == "ok" else "degraded",
        db=db_status,
        version=VERSION,
        scheduler=scheduler_status(),
    )
