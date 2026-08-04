"""Portafoglio investimenti (§2.8).

    GET  /portfolio/{account_id}                riepilogo: liquidità, posizioni, P/L
    GET  /portfolio/{account_id}/transactions   storico operazioni
    POST /portfolio/transactions                registra buy / sell / dividend
    GET  /portfolio/prices                      contenuto del PriceCache
    PUT  /portfolio/prices/{ticker}             prezzo manuale (funziona senza API key)
    PUT  /portfolio/fx/{base}/{quote}           cambio manuale
    POST /portfolio/refresh-prices              forza il job di aggiornamento prezzi
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from app import schemas
from app.auth.deps import CurrentUser, DbSession
from app.models import FxRateCache, PriceCache, StockTransaction
from app.routers.common import Limit, Offset, paginate
from app.services import portfolio as portfolio_service
from app.services.market_data import get_provider

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.post(
    "/transactions", response_model=schemas.StockTransactionOut, status_code=status.HTTP_201_CREATED
)
async def create_stock_transaction(
    payload: schemas.StockTransactionCreate, user: CurrentUser, session: DbSession
) -> StockTransaction:
    stock_tx = await portfolio_service.record_stock_transaction(
        session,
        user.id,
        account_id=payload.account_id,
        ticker=payload.ticker,
        tx_type=payload.type,
        quantity=payload.quantity,
        price_per_share=payload.price_per_share,
        fees=payload.fees,
        amount=payload.amount,
        currency=payload.currency,
        date=payload.date,
        notes=payload.notes,
    )
    await session.commit()
    await session.refresh(stock_tx)
    return stock_tx


@router.get("/history", response_model=schemas.PortfolioHistoryOut)
async def value_history(
    user: CurrentUser,
    session: DbSession,
    account_id: int | None = Query(default=None, description="assente = tutti i conti investimento"),
    days: int = Query(default=180, ge=7, le=1825),
    interval_days: int = Query(default=1, ge=1, le=30, description="distanza fra due campioni"),
) -> dict:
    """Serie storica del valore delle posizioni, letta solo dall'archivio locale.

    Non chiama mai il provider: i dati arrivano da `price_history`, popolata una volta al
    giorno dal job. Cambiare intervallo o periodo costa quindi zero richieste API.
    """
    return await portfolio_service.value_history(
        session, user.id, account_id=account_id, days=days, interval_days=interval_days
    )


@router.get("/prices", response_model=list[schemas.PriceOut])
async def list_prices(user: CurrentUser, session: DbSession) -> list[PriceCache]:
    return list(await session.scalars(select(PriceCache).order_by(PriceCache.ticker)))


@router.put("/prices/{ticker}", response_model=schemas.PriceOut)
async def set_price(
    ticker: str, payload: schemas.PriceIn, user: CurrentUser, session: DbSession
) -> PriceCache:
    """Inserimento manuale del prezzo.

    È la via prevista quando non c'è una API key configurata: il portafoglio resta
    pienamente utilizzabile aggiornando i prezzi a mano quando serve.
    """
    ticker = ticker.strip().upper()
    row = await session.get(PriceCache, ticker)
    if row is None:
        row = PriceCache(ticker=ticker)
        session.add(row)
    row.price = payload.price
    row.currency = payload.currency
    row.fetched_at = dt.datetime.now(dt.timezone.utc)
    row.source = "manual"
    await session.commit()
    await session.refresh(row)
    return row


@router.put("/fx/{base}/{quote}", response_model=schemas.FxRateOut)
async def set_fx_rate(
    base: str, quote: str, payload: schemas.FxRateIn, user: CurrentUser, session: DbSession
) -> FxRateCache:
    """Imposta 1 `base` = `rate` `quote` (es. USD→EUR)."""
    base, quote = base.upper(), quote.upper()
    row = await session.get(FxRateCache, (base, quote))
    if row is None:
        row = FxRateCache(base_currency=base, quote_currency=quote)
        session.add(row)
    row.rate = payload.rate
    row.fetched_at = dt.datetime.now(dt.timezone.utc)
    row.source = "manual"
    await session.commit()
    await session.refresh(row)
    return row


@router.get("/fx", response_model=list[schemas.FxRateOut])
async def list_fx(user: CurrentUser, session: DbSession) -> list[FxRateCache]:
    return list(await session.scalars(select(FxRateCache)))


@router.post("/refresh-prices")
async def refresh_prices(user: CurrentUser, session: DbSession) -> dict:
    """Forza l'aggiornamento dei prezzi dal provider esterno.

    Normalmente lo fa il job schedulato; qui è esposto per poterlo provare a mano.
    Con `MARKET_DATA_PROVIDER=none` (o senza chiave) non fa nulla e lo dichiara.
    """
    from app.services.scheduler_jobs import refresh_market_data

    provider = get_provider()
    result = await refresh_market_data(session, user_id=user.id)
    return {"provider": provider.name, **result}


@router.get("/{account_id}", response_model=schemas.PortfolioSummary)
async def get_portfolio(account_id: int, user: CurrentUser, session: DbSession) -> dict:
    return await portfolio_service.portfolio_summary(session, user.id, account_id)


@router.get("/{account_id}/transactions", response_model=schemas.Page[schemas.StockTransactionOut])
async def list_stock_transactions(
    account_id: int,
    user: CurrentUser,
    session: DbSession,
    ticker: str | None = Query(default=None),
    limit: Limit = 50,
    offset: Offset = 0,
) -> dict:
    stmt = select(StockTransaction).where(
        StockTransaction.user_id == user.id, StockTransaction.account_id == account_id
    )
    if ticker:
        stmt = stmt.where(StockTransaction.ticker == ticker.strip().upper())
    stmt = stmt.order_by(StockTransaction.date.desc(), StockTransaction.id.desc())

    rows, total = await paginate(session, stmt, limit=limit, offset=offset)
    return {"items": rows, "total": total, "limit": limit, "offset": offset}
