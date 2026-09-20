"""Centesimo — API.

Unico punto di accesso ai dati: il frontend parla solo con questa API, mai col database.
Tutti gli endpoint di dominio stanno sotto `/api/v1` e richiedono un access token; fanno
eccezione `/health` e `/api/v1/auth/login|refresh`.

**Il file non cresce quando cresce il progetto**: i router si montano in ciclo sul registro
in `app/modules/__init__.py`. Aggiungere un dominio non richiede di toccare questo file.

TLS: non se ne occupa questo processo. L'applicazione gira in HTTP dentro la rete Docker;
il certificato lo gestisce Tailscale davanti a nginx. Vedi docs/DEPLOY.md.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text

from app.core.config import settings
from app.core.db import SessionLocal, engine
from app.core.errors import register_error_handlers
from app.modules import MODULES
from app.modules.categories.service import sync_catalog

VERSION = "2.0.0"

logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s")
log = logging.getLogger("centesimo")


class HealthOut(BaseModel):
    status: str
    db: str
    version: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Il catalogo delle categorie è dato di riferimento, non dato dell'utente:
    # allinearlo all'avvio è idempotente e tiene il JSON come unica fonte di verità.
    try:
        async with SessionLocal() as session:
            added = await sync_catalog(session)
        if any(added):
            log.info("catalogo categorie: +%s categorie, +%s sottocategorie", *added)
    except Exception as exc:  # noqa: BLE001
        log.warning("catalogo categorie non allineato all'avvio: %s", exc)

    try:
        yield
    finally:
        await engine.dispose()


app = FastAPI(
    title="Centesimo API",
    version=VERSION,
    description="Gestione finanziaria personale. Importi come stringhe decimali, date ISO 8601.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url=None,
)

register_error_handlers(app)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

for module in MODULES:
    app.include_router(module.router, prefix=settings.api_prefix)


@app.get("/health", response_model=HealthOut, tags=["health"])
async def health() -> HealthOut:
    db_status = "ok"
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        log.warning("health: database non raggiungibile: %s", exc)
        db_status = "error"
    return HealthOut(status="ok" if db_status == "ok" else "degraded", db=db_status, version=VERSION)
