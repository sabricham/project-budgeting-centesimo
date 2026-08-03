"""Lavoro svolto dai job schedulati (§2.7, §2.8, §2.10).

Le funzioni qui dentro sono normali coroutine con una `AsyncSession`: possono essere
richiamate sia dallo scheduler sia da un endpoint (utile per testarle a mano) sia dai test.
"""

from __future__ import annotations

import datetime as dt
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import SessionLocal
from app.models import Account, FxRateCache, Holding, PriceCache, User
from app.services import recurrence, reports
from app.services.market_data import get_provider

log = logging.getLogger(__name__)


async def refresh_market_data(session: AsyncSession, *, user_id: int | None = None) -> dict:
    """Aggiorna `PriceCache` e `FxRateCache` dal provider esterno.

    Con provider `none` (nessuna API key) non fa nulla: i prezzi restano quelli inseriti
    a mano, e il portafoglio continua a funzionare.
    """
    provider = get_provider()
    if provider.name == "none":
        return {"prices_updated": 0, "fx_updated": 0, "skipped": "nessun provider configurato"}

    holdings_q = select(Holding.ticker, Holding.currency, Account.currency).join(
        Account, Account.id == Holding.account_id
    ).where(Holding.quantity > 0)
    if user_id is not None:
        holdings_q = holdings_q.where(Holding.user_id == user_id)
    rows = list(await session.execute(holdings_q))

    tickers = sorted({r[0] for r in rows})
    quotes = await provider.fetch_quotes(tickers) if tickers else {}

    now = dt.datetime.now(dt.timezone.utc)
    for ticker, (price, currency) in quotes.items():
        row = await session.get(PriceCache, ticker)
        if row is None:
            row = PriceCache(ticker=ticker)
            session.add(row)
        row.price = price
        row.currency = currency
        row.fetched_at = now
        row.source = provider.name

    # Cambi necessari: dalla valuta di quotazione a quella del conto, più la valuta base.
    pairs: set[tuple[str, str]] = set()
    for ticker, _holding_currency, account_currency in rows:
        quote_currency = quotes.get(ticker, (None, None))[1]
        for source_currency in {quote_currency, _holding_currency}:
            if source_currency and source_currency != account_currency:
                pairs.add((source_currency, account_currency))
            if source_currency and source_currency != settings.base_currency:
                pairs.add((source_currency, settings.base_currency))

    fx = await provider.fetch_fx_rates(sorted(pairs)) if pairs else {}
    for (base, quote), rate in fx.items():
        row = await session.get(FxRateCache, (base, quote))
        if row is None:
            row = FxRateCache(base_currency=base, quote_currency=quote)
            session.add(row)
        row.rate = rate
        row.fetched_at = now
        row.source = provider.name

    await session.commit()
    return {"prices_updated": len(quotes), "fx_updated": len(fx)}


# --------------------------------------------------------------------------- #
#  Wrapper usati dallo scheduler: aprono e chiudono la propria sessione
# --------------------------------------------------------------------------- #


async def job_generate_recurring() -> None:
    async with SessionLocal() as session:
        result = await recurrence.generate_occurrences(
            session, horizon_days=settings.recurring_horizon_days
        )
        if result["created"] or result["confirmed"]:
            log.info("ricorrenze: %s", result)


async def job_refresh_market_data() -> None:
    async with SessionLocal() as session:
        try:
            result = await refresh_market_data(session)
        except Exception:  # noqa: BLE001 — un provider giù non deve fermare lo scheduler
            log.exception("aggiornamento prezzi fallito")
            return
        if result.get("prices_updated"):
            log.info("prezzi aggiornati: %s", result)


async def job_net_worth_snapshot() -> None:
    async with SessionLocal() as session:
        for user_id in await session.scalars(select(User.id).where(User.is_active.is_(True))):
            await reports.save_net_worth_snapshot(session, user_id)
        log.info("snapshot patrimonio netto salvato")
