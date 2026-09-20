"""Calcolo dei saldi (§2.2, §2.10).

Il saldo **non è mai una colonna**: si ricalcola sempre dai movimenti. È la scelta che
rende impossibile la classica deriva "saldo salvato ≠ somma dei movimenti".

Composizione del saldo per tipo di conto:

  bank / cash / card / ewallet / savings_goal
      initial_balance + Σ entrate − Σ uscite + Σ trasferimenti in − Σ trasferimenti out
      (solo transazioni `confirmed`: le `projected` sono previsioni, §2.7)

  investment
      come sopra, più l'effetto delle operazioni su titoli sulla liquidità
      (`cash_balance`), più il valore di mercato delle posizioni (§2.8)

  liability
      ultimo `LiabilityUpdate.residual_amount` registrato — nessuna somma di
      transazioni, per non dover ricostruire un piano di ammortamento (§2.10)
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Sequence
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import ASSET_ACCOUNT_TYPES, AccountType, TransactionStatus, TransactionType
from app.models import Account, LiabilityUpdate, StockTransaction, Transaction, Transfer

ZERO = Decimal("0.00")


def q2(value: Decimal | int | float | None) -> Decimal:
    """Arrotonda a 2 decimali restando in Decimal (mai float, §1.3)."""
    if value is None:
        return ZERO
    return Decimal(value).quantize(Decimal("0.01"))


async def cash_balances(
    session: AsyncSession,
    user_id: int,
    *,
    account_ids: Sequence[int] | None = None,
    as_of: dt.date | None = None,
) -> dict[int, Decimal]:
    """Liquidità dei conti asset: initial_balance + movimenti di cassa.

    Per un conto `investment` questo è il contante non investito, non il valore totale.
    """
    accounts_q = select(Account.id, Account.initial_balance).where(
        Account.user_id == user_id, Account.type.in_(ASSET_ACCOUNT_TYPES)
    )
    if account_ids is not None:
        accounts_q = accounts_q.where(Account.id.in_(account_ids))

    balances: dict[int, Decimal] = {
        row.id: Decimal(row.initial_balance) for row in await session.execute(accounts_q)
    }
    if not balances:
        return {}

    ids = list(balances)

    # --- transazioni confermate -------------------------------------------------
    # Raggruppo per (conto, tipo) e applico il segno in Python: più leggibile di una
    # CASE inline e con lo stesso numero di query.
    tx_q = (
        select(
            Transaction.account_id,
            Transaction.type,
            func.coalesce(func.sum(Transaction.amount), 0).label("total"),
        )
        .where(
            Transaction.user_id == user_id,
            Transaction.account_id.in_(ids),
            Transaction.deleted_at.is_(None),
            Transaction.status == TransactionStatus.confirmed.value,
        )
        .group_by(Transaction.account_id, Transaction.type)
    )
    if as_of is not None:
        tx_q = tx_q.where(Transaction.date <= as_of)

    for account_id, tx_type, total in await session.execute(tx_q):
        delta = Decimal(total)
        if tx_type == TransactionType.expense.value:
            delta = -delta
        balances[account_id] += delta

    # --- trasferimenti (§2.3): escono da un conto ed entrano nell'altro ---------
    for column, sign in ((Transfer.to_account_id, 1), (Transfer.from_account_id, -1)):
        tr_q = (
            select(column, func.coalesce(func.sum(Transfer.amount), 0))
            .where(
                Transfer.user_id == user_id,
                column.in_(ids),
                Transfer.deleted_at.is_(None),
            )
            .group_by(column)
        )
        if as_of is not None:
            tr_q = tr_q.where(Transfer.date <= as_of)
        for account_id, total in await session.execute(tr_q):
            balances[account_id] += Decimal(total) * sign

    # --- operazioni su titoli: muovono la liquidità del conto investment (§2.8) --
    st_q = (
        select(StockTransaction.account_id, func.coalesce(func.sum(StockTransaction.cash_delta), 0))
        .where(StockTransaction.user_id == user_id, StockTransaction.account_id.in_(ids))
        .group_by(StockTransaction.account_id)
    )
    if as_of is not None:
        st_q = st_q.where(StockTransaction.date <= as_of)
    for account_id, total in await session.execute(st_q):
        balances[account_id] += Decimal(total)

    return {k: q2(v) for k, v in balances.items()}


async def liability_balances(
    session: AsyncSession,
    user_id: int,
    *,
    account_ids: Sequence[int] | None = None,
    as_of: dt.date | None = None,
) -> dict[int, Decimal]:
    """Residuo dei conti `liability`: l'ultimo snapshot registrato (§2.10).

    A parità di data vince l'id più alto (lo snapshot inserito per ultimo).
    """
    accounts_q = select(Account.id).where(
        Account.user_id == user_id, Account.type == AccountType.liability.value
    )
    if account_ids is not None:
        accounts_q = accounts_q.where(Account.id.in_(account_ids))
    ids = [row[0] for row in await session.execute(accounts_q)]
    if not ids:
        return {}

    balances: dict[int, Decimal] = {account_id: ZERO for account_id in ids}

    latest = select(
        LiabilityUpdate.account_id,
        LiabilityUpdate.residual_amount,
        func.row_number()
        .over(
            partition_by=LiabilityUpdate.account_id,
            order_by=(LiabilityUpdate.date.desc(), LiabilityUpdate.id.desc()),
        )
        .label("rn"),
    ).where(LiabilityUpdate.user_id == user_id, LiabilityUpdate.account_id.in_(ids))
    if as_of is not None:
        latest = latest.where(LiabilityUpdate.date <= as_of)
    ranked = latest.subquery()

    rows = await session.execute(
        select(ranked.c.account_id, ranked.c.residual_amount).where(ranked.c.rn == 1)
    )
    for account_id, residual in rows:
        balances[account_id] = Decimal(residual)

    return {k: q2(v) for k, v in balances.items()}


async def account_balances(
    session: AsyncSession,
    user_id: int,
    *,
    account_ids: Sequence[int] | None = None,
    as_of: dt.date | None = None,
    include_holdings: bool = True,
) -> dict[int, Decimal]:
    """Saldo "pieno" di ogni conto dell'utente, liability inclusi (valore positivo).

    Per i conti `investment` somma la liquidità e il valore di mercato delle posizioni:
    è il valore che serve al patrimonio netto e ai widget di saldo.
    """
    balances = await cash_balances(session, user_id, account_ids=account_ids, as_of=as_of)
    balances.update(
        await liability_balances(session, user_id, account_ids=account_ids, as_of=as_of)
    )

    if include_holdings:
        # import locale: portfolio importa a sua volta questo modulo
        from app.services.portfolio import holdings_value_by_account

        for account_id, value in (await holdings_value_by_account(session, user_id)).items():
            if account_ids is None or account_id in set(account_ids):
                balances[account_id] = q2(balances.get(account_id, ZERO) + value)

    return balances


async def net_worth(
    session: AsyncSession, user_id: int, *, as_of: dt.date | None = None
) -> tuple[Decimal, Decimal, Decimal]:
    """(assets, liabilities, net_worth) — §2.10."""
    assets_map = await cash_balances(session, user_id, as_of=as_of)
    from app.services.portfolio import holdings_value_by_account

    for account_id, value in (await holdings_value_by_account(session, user_id)).items():
        assets_map[account_id] = assets_map.get(account_id, ZERO) + value

    liabilities_map = await liability_balances(session, user_id, as_of=as_of)

    assets = q2(sum(assets_map.values(), ZERO))
    liabilities = q2(sum(liabilities_map.values(), ZERO))
    return assets, liabilities, q2(assets - liabilities)


def only(balances: dict[int, Decimal], ids: Iterable[int]) -> Decimal:
    return q2(sum((balances.get(i, ZERO) for i in ids), ZERO))
