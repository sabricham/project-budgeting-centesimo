"""API dei conti.

Dipendenza fra moduli: il saldo di un conto è un'aggregazione sulle entry, quindi la
matematica vive in `entries/service.py` e qui viene solo usata. La direzione è sempre
questa — `entries` conosce `accounts` (ci punta con una foreign key), mai il contrario —
così non si creano import circolari.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, status
from sqlalchemy import select

from app.core.deps import DbSession
from app.core.errors import Invalid
from app.core.pagination import apply_updates, get_owned
from app.modules.accounts import service
from app.modules.accounts.models import ACCOUNT_TYPES, Account
from app.modules.accounts.schemas import AccountCreate, AccountOut, AccountUpdate
from app.modules.auth.deps import CurrentUser

router = APIRouter(prefix="/accounts", tags=["accounts"])


async def _with_balances(
    session: DbSession, user_id: int, rows: list[Account], as_of: dt.date | None = None
) -> list[AccountOut]:
    from app.modules.entries.service import balances_by_account

    balances = await balances_by_account(session, user_id, as_of=as_of)
    out = []
    for row in rows:
        item = AccountOut.model_validate(row)
        item.balance = balances.get(row.id, row.initial_balance)
        out.append(item)
    return out


@router.get("/types", response_model=list[str])
async def list_types() -> list[str]:
    """Tipi proposti dall'interfaccia. Non sono un vincolo del database."""
    return list(ACCOUNT_TYPES)


@router.get("", response_model=list[AccountOut])
async def list_accounts(
    user: CurrentUser,
    session: DbSession,
    include_archived: bool = False,
    as_of: dt.date | None = None,
) -> list[AccountOut]:
    stmt = select(Account).where(Account.user_id == user.id)
    if not include_archived:
        stmt = stmt.where(Account.archived.is_(False))
    rows = list((await session.execute(stmt.order_by(Account.name))).scalars())
    return await _with_balances(session, user.id, rows, as_of)


@router.post("", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
async def create_account(
    payload: AccountCreate, user: CurrentUser, session: DbSession
) -> AccountOut:
    await service.ensure_name_free(session, user.id, payload.name)
    account = Account(user_id=user.id, **payload.model_dump())
    session.add(account)
    await session.commit()
    await session.refresh(account)
    item = AccountOut.model_validate(account)
    item.balance = account.initial_balance
    return item


@router.get("/{account_id}", response_model=AccountOut)
async def get_account(account_id: int, user: CurrentUser, session: DbSession) -> AccountOut:
    account = await get_owned(session, Account, account_id, user.id, label="Conto")
    return (await _with_balances(session, user.id, [account]))[0]


@router.patch("/{account_id}", response_model=AccountOut)
async def update_account(
    account_id: int, payload: AccountUpdate, user: CurrentUser, session: DbSession
) -> AccountOut:
    account = await get_owned(session, Account, account_id, user.id, label="Conto")
    if payload.name is not None:
        await service.ensure_name_free(session, user.id, payload.name, exclude_id=account_id)
    apply_updates(account, payload)
    await session.commit()
    await session.refresh(account)
    return (await _with_balances(session, user.id, [account]))[0]


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_account(account_id: int, user: CurrentUser, session: DbSession) -> None:
    """Elimina il conto solo se non ha movimenti: altrimenti si archivia.

    Cancellare un conto con dei movimenti significherebbe riscrivere il passato, e il
    grafico del patrimonio diventerebbe incoerente. L'archiviazione lo toglie dalle tendine
    lasciando intatto lo storico.
    """
    account = await get_owned(session, Account, account_id, user.id, label="Conto")

    from app.modules.entries.service import count_for_account

    used = await count_for_account(session, user.id, account_id)
    if used:
        raise Invalid(
            f"Il conto «{account.name}» ha {used} movimenti: archivialo invece di eliminarlo."
        )
    await session.delete(account)
    await session.commit()
