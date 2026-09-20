"""Logica delle entry: validazione, saldi, aggregazioni.

Questo modulo è il proprietario della matematica dei saldi. Gli altri moduli
(`accounts`, `reports`) la importano da qui invece di riscriverla: c'è un solo posto
in cui è definito cosa significa «entrata», «uscita» e «investimento» per un saldo.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Invalid, NotFound
from app.modules.accounts.models import Account
from app.modules.categories.models import Subcategory
from app.modules.entries.models import KIND_EXPENSE, KIND_INCOME, KIND_INVESTMENT, Entry

ZERO = Decimal("0.00")


def q2(value: Decimal | int | None) -> Decimal:
    """Arrotonda a 2 decimali restando in Decimal — mai float sul denaro."""
    return ZERO if value is None else Decimal(value).quantize(Decimal("0.01"))


# --------------------------------------------------------------------------- #
#  Validazione
# --------------------------------------------------------------------------- #


async def validate_refs(
    session: AsyncSession,
    user_id: int,
    *,
    kind: str,
    account_id: int,
    to_account_id: int | None,
    subcategory_id: int,
) -> None:
    """Controlli che non possono stare in Pydantic perché richiedono il database."""
    account = await _owned_account(session, user_id, account_id, "Conto")
    if account.archived:
        raise Invalid(
            f"Il conto «{account.name}» è archiviato: riattivalo prima di registrarci movimenti"
        )

    if kind == KIND_INVESTMENT:
        if to_account_id is None:
            raise Invalid(
                "Un movimento di tipo investimento ha bisogno del conto di destinazione: "
                "il denaro si sposta da un conto all'altro, non sparisce"
            )
        if to_account_id == account_id:
            raise Invalid("Il conto di destinazione deve essere diverso da quello di partenza")
        destination = await _owned_account(session, user_id, to_account_id, "Conto di destinazione")
        if destination.archived:
            raise Invalid(f"Il conto «{destination.name}» è archiviato")
    elif to_account_id is not None:
        raise Invalid(
            "Il conto di destinazione ha senso solo per i movimenti di tipo investimento"
        )

    if await session.scalar(select(Subcategory.id).where(Subcategory.id == subcategory_id)) is None:
        raise NotFound(f"Sottocategoria {subcategory_id} non trovata")


async def _owned_account(
    session: AsyncSession, user_id: int, account_id: int, label: str
) -> Account:
    account = await session.scalar(
        select(Account).where(Account.id == account_id, Account.user_id == user_id)
    )
    if account is None:
        raise NotFound(f"{label} {account_id} non trovato")
    return account


# --------------------------------------------------------------------------- #
#  Saldi
# --------------------------------------------------------------------------- #


async def balances_by_account(
    session: AsyncSession,
    user_id: int,
    *,
    as_of: dt.date | None = None,
) -> dict[int, Decimal]:
    """Saldo di ogni conto dell'utente: `initial_balance` più i movimenti fino a `as_of`.

    Tre contributi, uno per verso:
      * entrate           -> + sul conto
      * uscite            -> − sul conto
      * investimenti      -> − sul conto di partenza, + su quello di destinazione
    """
    balances: dict[int, Decimal] = {
        row.id: Decimal(row.initial_balance)
        for row in await session.execute(
            select(Account.id, Account.initial_balance).where(Account.user_id == user_id)
        )
    }
    if not balances:
        return {}

    def bounded(stmt):
        stmt = stmt.where(Entry.user_id == user_id, Entry.deleted_at.is_(None))
        return stmt if as_of is None else stmt.where(Entry.date <= as_of)

    # Lato conto di partenza: le entrate sommano, uscite e investimenti sottraggono.
    outgoing = bounded(
        select(Entry.account_id, Entry.kind, func.coalesce(func.sum(Entry.amount), 0))
    ).group_by(Entry.account_id, Entry.kind)
    for account_id, kind, total in await session.execute(outgoing):
        if account_id in balances:
            amount = Decimal(total)
            balances[account_id] += amount if kind == KIND_INCOME else -amount

    # Lato conto di destinazione: esiste solo sugli investimenti, e somma sempre.
    incoming = bounded(
        select(Entry.to_account_id, func.coalesce(func.sum(Entry.amount), 0))
    ).where(Entry.to_account_id.is_not(None)).group_by(Entry.to_account_id)
    for account_id, total in await session.execute(incoming):
        if account_id in balances:
            balances[account_id] += Decimal(total)

    return {k: q2(v) for k, v in balances.items()}


async def net_worth(
    session: AsyncSession, user_id: int, *, as_of: dt.date | None = None
) -> Decimal:
    return q2(sum((await balances_by_account(session, user_id, as_of=as_of)).values(), ZERO))


async def daily_deltas(
    session: AsyncSession,
    user_id: int,
    date_from: dt.date,
    date_to: dt.date,
    *,
    account_ids: list[int] | None = None,
) -> dict[dt.date, Decimal]:
    """Variazione del saldo giorno per giorno, per i conti indicati (tutti se `None`).

    Con tutti i conti un investimento si annulla (−X e +X nello stesso giorno), com'è
    giusto: il patrimonio complessivo non cambia. Filtrando su un conto solo, invece,
    l'investimento si vede come uscita o entrata di quel conto.
    """
    deltas: dict[dt.date, Decimal] = defaultdict(lambda: ZERO)

    outgoing = select(Entry.date, Entry.kind, func.sum(Entry.amount)).where(
        Entry.user_id == user_id,
        Entry.deleted_at.is_(None),
        Entry.date >= date_from,
        Entry.date <= date_to,
    )
    if account_ids is not None:
        outgoing = outgoing.where(Entry.account_id.in_(account_ids))
    for day, kind, total in await session.execute(outgoing.group_by(Entry.date, Entry.kind)):
        amount = Decimal(total)
        deltas[day] += amount if kind == KIND_INCOME else -amount

    incoming = select(Entry.date, func.sum(Entry.amount)).where(
        Entry.user_id == user_id,
        Entry.deleted_at.is_(None),
        Entry.to_account_id.is_not(None),
        Entry.date >= date_from,
        Entry.date <= date_to,
    )
    if account_ids is not None:
        incoming = incoming.where(Entry.to_account_id.in_(account_ids))
    for day, total in await session.execute(incoming.group_by(Entry.date)):
        deltas[day] += Decimal(total)

    return dict(deltas)


async def totals_by_kind(
    session: AsyncSession,
    user_id: int,
    date_from: dt.date,
    date_to: dt.date,
    *,
    account_ids: list[int] | None = None,
) -> dict[str, Decimal]:
    """Totale di entrate, uscite e investimenti nel periodo (valori positivi)."""
    stmt = select(Entry.kind, func.sum(Entry.amount)).where(
        Entry.user_id == user_id,
        Entry.deleted_at.is_(None),
        Entry.date >= date_from,
        Entry.date <= date_to,
    )
    if account_ids is not None:
        stmt = stmt.where(Entry.account_id.in_(account_ids))

    out = {KIND_INCOME: ZERO, KIND_EXPENSE: ZERO, KIND_INVESTMENT: ZERO}
    for kind, total in await session.execute(stmt.group_by(Entry.kind)):
        out[kind] = q2(total)
    return out


async def count_for_account(session: AsyncSession, user_id: int, account_id: int) -> int:
    """Quanti movimenti toccano il conto, da una parte o dall'altra."""
    return int(
        await session.scalar(
            select(func.count())
            .select_from(Entry)
            .where(
                Entry.user_id == user_id,
                (Entry.account_id == account_id) | (Entry.to_account_id == account_id),
            )
        )
        or 0
    )
