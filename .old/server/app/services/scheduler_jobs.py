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
from app.models import (
    Account,
    ApiBudget,
    FxRateCache,
    Holding,
    PriceCache,
    PriceHistory,
    User,
)
from app.services import app_settings, recurrence, reports
from app.services.market_data import get_provider

log = logging.getLogger(__name__)


async def _budget_left(session: AsyncSession, provider_name: str) -> int:
    """Richieste ancora spendibili oggi verso il provider."""
    today = dt.date.today()
    row = await session.get(ApiBudget, (today, provider_name))
    used = row.used if row else 0
    return max(0, settings.market_data_daily_budget - used)


async def _spend(session: AsyncSession, provider_name: str, amount: int = 1) -> None:
    today = dt.date.today()
    row = await session.get(ApiBudget, (today, provider_name))
    if row is None:
        row = ApiBudget(day=today, provider=provider_name, used=0)
        session.add(row)
    row.used += amount
    await session.flush()


async def refresh_market_data(session: AsyncSession, *, user_id: int | None = None) -> dict:
    """Aggiorna prezzi, storico giornaliero e cambi dal provider esterno.

    Strategia dettata dal piano gratuito di Alpha Vantage (25 richieste al giorno):

      * **una richiesta per ticker posseduto**, non di più. La serie giornaliera contiene
        già la quotazione di oggi, quindi non serve una seconda chiamata per il prezzo
        corrente;
      * i ticker già aggiornati oggi vengono saltati, così registrare dieci operazioni
        sullo stesso titolo non costa dieci richieste;
      * un contatore giornaliero (`ApiBudget`) impedisce di superare la quota: esaurita,
        si serve quello che c'è in archivio invece di restare ciechi fino a domani.

    Con provider `none` (nessuna API key) non fa nulla: i prezzi restano quelli inseriti
    a mano, e il portafoglio continua a funzionare.
    """
    provider_name, api_key, _ = await app_settings.market_data_config(session)
    provider = get_provider(provider_name, api_key)
    if provider.name == "none":
        return {"prices_updated": 0, "fx_updated": 0, "skipped": "nessun provider configurato"}

    holdings_q = select(Holding.ticker, Holding.currency, Account.currency).join(
        Account, Account.id == Holding.account_id
    ).where(Holding.quantity > 0)
    if user_id is not None:
        holdings_q = holdings_q.where(Holding.user_id == user_id)
    rows = list(await session.execute(holdings_q))

    now = dt.datetime.now(dt.timezone.utc)
    today = now.date()
    quotes: dict[str, tuple] = {}
    skipped_fresh = 0

    for ticker in sorted({r[0] for r in rows}):
        cached = await session.get(PriceCache, ticker)
        if cached is not None and cached.fetched_at.date() >= today and cached.source != "manual":
            skipped_fresh += 1
            quotes[ticker] = (cached.price, cached.currency)
            continue

        if await _budget_left(session, provider.name) <= 0:
            log.warning("budget giornaliero esaurito: %s non aggiornato", ticker)
            continue

        await _spend(session, provider.name)
        series = await provider.fetch_daily_series(
            ticker, hint=cached.asset_kind if cached else "unknown"
        )
        if series is None:
            continue

        kind, currency, closes = series
        for day, close in closes.items():
            row = await session.get(PriceHistory, (ticker, day))
            if row is None:
                session.add(
                    PriceHistory(
                        ticker=ticker, date=day, close=close,
                        currency=currency, source=provider.name,
                    )
                )
            else:
                row.close = close
                row.currency = currency
                row.source = provider.name

        latest_day = max(closes)
        quotes[ticker] = (closes[latest_day], currency)

        if cached is None:
            cached = PriceCache(ticker=ticker)
            session.add(cached)
        cached.price = closes[latest_day]
        cached.currency = currency
        cached.fetched_at = now
        cached.source = provider.name
        cached.asset_kind = kind

    # Cambi necessari: dalla valuta di quotazione a quella del conto, più la valuta base.
    pairs: set[tuple[str, str]] = set()
    for ticker, _holding_currency, account_currency in rows:
        quote_currency = quotes.get(ticker, (None, None))[1]
        for source_currency in {quote_currency, _holding_currency}:
            if source_currency and source_currency != account_currency:
                pairs.add((source_currency, account_currency))
            if source_currency and source_currency != settings.base_currency:
                pairs.add((source_currency, settings.base_currency))

    # Anche i cambi già aggiornati oggi si saltano, e comunque non si sfora il budget.
    needed: list[tuple[str, str]] = []
    for pair in sorted(pairs):
        existing = await session.get(FxRateCache, pair)
        if existing is not None and existing.fetched_at.date() >= today:
            continue
        needed.append(pair)

    affordable = needed[: await _budget_left(session, provider.name)]
    if len(affordable) < len(needed):
        log.warning("budget esaurito: %d cambi non aggiornati", len(needed) - len(affordable))

    fx = await provider.fetch_fx_rates(affordable) if affordable else {}
    if affordable:
        await _spend(session, provider.name, len(affordable))

    for (base, quote), rate in fx.items():
        row = await session.get(FxRateCache, (base, quote))
        if row is None:
            row = FxRateCache(base_currency=base, quote_currency=quote)
            session.add(row)
        row.rate = rate
        row.fetched_at = now
        row.source = provider.name

    await session.commit()
    return {
        "prices_updated": len(quotes) - skipped_fresh,
        "already_fresh": skipped_fresh,
        "fx_updated": len(fx),
        "budget_left": await _budget_left(session, provider.name),
    }


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
