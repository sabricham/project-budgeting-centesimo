"""Logica del portafoglio investimenti (§2.8).

Punti fermi:

* La **liquidità** del conto `investment` è sempre espressa nella valuta del conto.
  Se un'operazione è in valuta diversa, l'importo di cassa viene convertito **al momento
  dell'operazione** con il cambio cachato: è ciò che è realmente uscito dal conto, e non
  va più ritoccato in futuro.
* Le **posizioni** restano invece nella valuta nativa del titolo (`Holding.currency`):
  la conversione avviene solo in fase di valorizzazione/aggregazione, così un movimento
  del cambio non riscrive lo storico.
* `avg_cost_basis` include le commissioni di acquisto: è il costo davvero sostenuto per
  azione, quindi la plusvalenza calcolata su di esso è già al netto dei costi.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import AccountType, StockTransactionType
from app.errors import Invalid, NotFound
from app.models import Account, FxRateCache, Holding, PriceCache, StockTransaction
from app.services.balances import ZERO, q2

PRICE_EXP = Decimal("0.000001")
QTY_EXP = Decimal("0.00000001")


def q6(value: Decimal) -> Decimal:
    return Decimal(value).quantize(PRICE_EXP)


def q8(value: Decimal) -> Decimal:
    return Decimal(value).quantize(QTY_EXP)


# --------------------------------------------------------------------------- #
#  Cambi
# --------------------------------------------------------------------------- #


async def get_fx_rate(session: AsyncSession, base: str, quote: str) -> Decimal | None:
    """1 `base` = ? `quote`, dalla cache. Prova anche il cambio inverso."""
    base, quote = base.upper(), quote.upper()
    if base == quote:
        return Decimal(1)

    row = await session.get(FxRateCache, (base, quote))
    if row is not None:
        return Decimal(row.rate)

    inverse = await session.get(FxRateCache, (quote, base))
    if inverse is not None and Decimal(inverse.rate) > 0:
        return Decimal(1) / Decimal(inverse.rate)
    return None


async def convert(
    session: AsyncSession, amount: Decimal, from_currency: str, to_currency: str
) -> Decimal | None:
    rate = await get_fx_rate(session, from_currency, to_currency)
    if rate is None:
        return None
    return q2(Decimal(amount) * rate)


# --------------------------------------------------------------------------- #
#  Valorizzazione
# --------------------------------------------------------------------------- #


async def _price_map(session: AsyncSession, tickers: list[str]) -> dict[str, PriceCache]:
    if not tickers:
        return {}
    rows = await session.scalars(select(PriceCache).where(PriceCache.ticker.in_(tickers)))
    return {row.ticker: row for row in rows}


async def holdings_value_by_account(
    session: AsyncSession, user_id: int, *, account_ids: list[int] | None = None
) -> dict[int, Decimal]:
    """Valore di mercato delle posizioni, per conto, nella valuta del conto.

    Se manca il prezzo di un titolo si usa il costo medio di carico: meglio un valore
    prudente che escludere silenziosamente la posizione dal patrimonio.
    """
    q = select(Holding).where(Holding.user_id == user_id, Holding.quantity > 0)
    if account_ids is not None:
        q = q.where(Holding.account_id.in_(account_ids))
    holdings = list(await session.scalars(q))
    if not holdings:
        return {}

    prices = await _price_map(session, [h.ticker for h in holdings])
    account_currency = {
        row.id: row.currency
        for row in await session.execute(
            select(Account.id, Account.currency).where(
                Account.id.in_({h.account_id for h in holdings})
            )
        )
    }

    totals: dict[int, Decimal] = {}
    for holding in holdings:
        price_row = prices.get(holding.ticker)
        unit_price = Decimal(price_row.price) if price_row else Decimal(holding.avg_cost_basis)
        currency = price_row.currency if price_row else holding.currency
        value = Decimal(holding.quantity) * unit_price

        target = account_currency.get(holding.account_id, currency)
        if currency != target:
            converted = await convert(session, value, currency, target)
            # Senza cambio disponibile si tiene il valore nativo: falsare l'ordine di
            # grandezza è peggio che avere due valute sommate, ed è segnalato in UI.
            value = converted if converted is not None else value

        totals[holding.account_id] = totals.get(holding.account_id, ZERO) + value

    return {k: q2(v) for k, v in totals.items()}


# --------------------------------------------------------------------------- #
#  Registrazione operazioni
# --------------------------------------------------------------------------- #


async def _get_investment_account(session: AsyncSession, user_id: int, account_id: int) -> Account:
    account = await session.scalar(
        select(Account).where(Account.id == account_id, Account.user_id == user_id)
    )
    if account is None:
        raise NotFound(f"Conto {account_id} non trovato")
    if account.type != AccountType.investment.value:
        raise Invalid("Le operazioni su titoli sono ammesse solo su conti di tipo `investment`")
    if account.archived:
        raise Invalid("Il conto è archiviato")
    return account


async def _to_account_currency(
    session: AsyncSession, amount: Decimal, from_currency: str, account: Account
) -> Decimal:
    if from_currency == account.currency:
        return q2(amount)
    converted = await convert(session, amount, from_currency, account.currency)
    if converted is None:
        raise Invalid(
            f"Manca il cambio {from_currency}/{account.currency}: impostalo con "
            f"PUT /portfolio/fx/{from_currency}/{account.currency} prima di registrare "
            "un'operazione in valuta diversa da quella del conto",
        )
    return converted


async def record_stock_transaction(
    session: AsyncSession,
    user_id: int,
    *,
    account_id: int,
    ticker: str,
    tx_type: StockTransactionType,
    quantity: Decimal | None,
    price_per_share: Decimal | None,
    fees: Decimal,
    amount: Decimal | None,
    currency: str,
    date: dt.date,
    notes: str | None,
) -> StockTransaction:
    """Registra buy/sell/dividend aggiornando `Holding` e la liquidità del conto."""
    account = await _get_investment_account(session, user_id, account_id)
    ticker = ticker.strip().upper()

    holding = await session.scalar(
        select(Holding).where(Holding.account_id == account_id, Holding.ticker == ticker)
    )
    realized_pnl: Decimal | None = None

    if tx_type is StockTransactionType.buy:
        gross = Decimal(quantity) * Decimal(price_per_share) + Decimal(fees)
        cash_delta = -(await _to_account_currency(session, gross, currency, account))

        if holding is None:
            holding = Holding(
                user_id=user_id,
                account_id=account_id,
                ticker=ticker,
                quantity=q8(Decimal(quantity)),
                avg_cost_basis=q6(gross / Decimal(quantity)),
                currency=currency,
            )
            session.add(holding)
        else:
            if holding.currency != currency:
                raise Invalid(
                    f"La posizione {ticker} è in {holding.currency}: non posso mescolare "
                    f"operazioni in {currency}"
                )
            old_cost = Decimal(holding.quantity) * Decimal(holding.avg_cost_basis)
            new_qty = Decimal(holding.quantity) + Decimal(quantity)
            holding.avg_cost_basis = q6((old_cost + gross) / new_qty)
            holding.quantity = q8(new_qty)

    elif tx_type is StockTransactionType.sell:
        if holding is None or Decimal(holding.quantity) < Decimal(quantity):
            owned = Decimal(holding.quantity) if holding else ZERO
            raise Invalid(f"Quantità insufficiente su {ticker}: possiedi {owned}")
        if holding.currency != currency:
            raise Invalid(
                f"La posizione {ticker} è in {holding.currency}: vendita in {currency} non ammessa"
            )
        gross = Decimal(quantity) * Decimal(price_per_share) - Decimal(fees)
        cash_delta = await _to_account_currency(session, gross, currency, account)
        realized_native = (
            Decimal(price_per_share) - Decimal(holding.avg_cost_basis)
        ) * Decimal(quantity) - Decimal(fees)
        realized_pnl = await _to_account_currency(session, realized_native, currency, account)

        remaining = Decimal(holding.quantity) - Decimal(quantity)
        if remaining <= 0:
            # Posizione chiusa: la riga sparisce, lo storico resta nelle StockTransaction.
            await session.delete(holding)
        else:
            holding.quantity = q8(remaining)

    else:  # dividend
        net = Decimal(amount) - Decimal(fees)
        cash_delta = await _to_account_currency(session, net, currency, account)

    stock_tx = StockTransaction(
        user_id=user_id,
        account_id=account_id,
        ticker=ticker,
        type=tx_type.value,
        quantity=q8(Decimal(quantity)) if quantity is not None else None,
        price_per_share=q6(Decimal(price_per_share)) if price_per_share is not None else None,
        fees=q2(fees),
        amount=q2(amount) if amount is not None else None,
        currency=currency,
        date=date,
        notes=notes,
        realized_pnl=realized_pnl,
        cash_delta=q2(cash_delta),
    )
    session.add(stock_tx)
    await session.flush()
    return stock_tx


# --------------------------------------------------------------------------- #
#  Riepilogo
# --------------------------------------------------------------------------- #


async def portfolio_summary(session: AsyncSession, user_id: int, account_id: int) -> dict:
    """Dati per `GET /portfolio/{account_id}` (schema `PortfolioSummary`)."""
    account = await _get_investment_account(session, user_id, account_id)

    from app.services.balances import cash_balances

    cash = (await cash_balances(session, user_id, account_ids=[account_id])).get(account_id, ZERO)

    holdings = list(
        await session.scalars(
            select(Holding)
            .where(Holding.account_id == account_id, Holding.quantity > 0)
            .order_by(Holding.ticker)
        )
    )
    prices = await _price_map(session, [h.ticker for h in holdings])

    items: list[dict] = []
    holdings_value = ZERO
    total_cost = ZERO
    missing: list[str] = []

    for holding in holdings:
        price_row = prices.get(holding.ticker)
        cost_value_native = Decimal(holding.quantity) * Decimal(holding.avg_cost_basis)
        if holding.currency == account.currency:
            cost_value = q2(cost_value_native)
        else:
            # In lettura non si solleva mai per un cambio mancante: si mostra il valore
            # nativo e il ticker finisce in `missing_prices`, così la UI può avvisare.
            converted_cost = await convert(
                session, cost_value_native, holding.currency, account.currency
            )
            cost_value = converted_cost if converted_cost is not None else q2(cost_value_native)

        market_value = None
        unrealized = None
        unrealized_pct = None
        if price_row is not None:
            native_value = Decimal(holding.quantity) * Decimal(price_row.price)
            converted = (
                q2(native_value)
                if price_row.currency == account.currency
                else await convert(session, native_value, price_row.currency, account.currency)
            )
            if converted is None:
                missing.append(holding.ticker)
            else:
                market_value = converted
                unrealized = q2(market_value - cost_value)
                unrealized_pct = float(unrealized / cost_value) if cost_value else None
        else:
            missing.append(holding.ticker)

        holdings_value += market_value if market_value is not None else cost_value
        total_cost += cost_value

        items.append(
            {
                "id": holding.id,
                "account_id": holding.account_id,
                "ticker": holding.ticker,
                "quantity": holding.quantity,
                "avg_cost_basis": holding.avg_cost_basis,
                "currency": holding.currency,
                "last_price": price_row.price if price_row else None,
                "price_fetched_at": price_row.fetched_at if price_row else None,
                "price_source": price_row.source if price_row else None,
                "market_value": market_value,
                "cost_value": cost_value,
                "unrealized_pnl": unrealized,
                "unrealized_pnl_pct": unrealized_pct,
            }
        )

    realized = await session.scalar(
        select(func.coalesce(func.sum(StockTransaction.realized_pnl), 0)).where(
            StockTransaction.account_id == account_id,
            StockTransaction.user_id == user_id,
        )
    )

    return {
        "account_id": account.id,
        "account_name": account.name,
        "currency": account.currency,
        "cash_balance": q2(cash),
        "holdings_value": q2(holdings_value),
        "total_value": q2(cash + holdings_value),
        "total_cost": q2(total_cost),
        "unrealized_pnl": q2(holdings_value - total_cost),
        "realized_pnl": q2(realized or 0),
        "holdings": items,
        "missing_prices": missing,
    }
