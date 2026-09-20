"""Conti (§2.2).

Il saldo restituito è sempre calcolato al volo dai movimenti: non esiste alcun campo
"saldo" modificabile dal client.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from app import schemas
from app.auth.deps import CurrentUser, DbSession
from app.enums import AccountType
from app.errors import Conflict, Invalid
from app.models import Account, Goal, Holding, LiabilityUpdate, Transaction, Transfer
from app.routers.common import apply_updates, check_concurrency, get_owned
from app.services import balances as balance_service
from app.services.portfolio import holdings_value_by_account

router = APIRouter(prefix="/accounts", tags=["accounts"])


async def _serialize(session, user_id: int, accounts: list[Account]) -> list[dict]:
    ids = [a.id for a in accounts]
    cash = await balance_service.cash_balances(session, user_id, account_ids=ids)
    liabilities = await balance_service.liability_balances(session, user_id, account_ids=ids)
    holdings = await holdings_value_by_account(session, user_id, account_ids=ids)

    out = []
    for account in accounts:
        data = schemas.AccountOut.model_validate(account).model_dump()
        if account.type == AccountType.liability.value:
            data["balance"] = liabilities.get(account.id, balance_service.ZERO)
        elif account.type == AccountType.investment.value:
            cash_balance = cash.get(account.id, balance_service.ZERO)
            holdings_value = holdings.get(account.id, balance_service.ZERO)
            data["balance"] = balance_service.q2(cash_balance + holdings_value)
            data["cash_balance"] = cash_balance
            data["holdings_value"] = holdings_value
        else:
            data["balance"] = cash.get(account.id, balance_service.ZERO)
        out.append(data)
    return out


@router.get("", response_model=list[schemas.AccountWithBalance])
async def list_accounts(
    user: CurrentUser,
    session: DbSession,
    include_archived: bool = False,
    type: AccountType | None = Query(default=None, description="Filtra per tipo di conto"),
) -> list[dict]:
    stmt = select(Account).where(Account.user_id == user.id)
    if not include_archived:
        stmt = stmt.where(Account.archived.is_(False))
    if type is not None:
        stmt = stmt.where(Account.type == type.value)
    accounts = list(await session.scalars(stmt.order_by(Account.type, Account.name)))
    return await _serialize(session, user.id, accounts)


@router.post("", response_model=schemas.AccountWithBalance, status_code=status.HTTP_201_CREATED)
async def create_account(
    payload: schemas.AccountCreate, user: CurrentUser, session: DbSession
) -> dict:
    account = Account(user_id=user.id, **payload.model_dump())
    account.type = payload.type.value
    session.add(account)
    await session.commit()
    await session.refresh(account)
    return (await _serialize(session, user.id, [account]))[0]


@router.get("/{account_id}", response_model=schemas.AccountWithBalance)
async def get_account(account_id: int, user: CurrentUser, session: DbSession) -> dict:
    account = await get_owned(session, Account, account_id, user.id, label="Conto")
    return (await _serialize(session, user.id, [account]))[0]


@router.patch("/{account_id}", response_model=schemas.AccountWithBalance)
async def update_account(
    account_id: int, payload: schemas.AccountUpdate, user: CurrentUser, session: DbSession
) -> dict:
    account = await get_owned(session, Account, account_id, user.id, label="Conto")
    check_concurrency(account, payload.expected_updated_at)
    # Il tipo di conto non è modificabile: cambiarlo cambierebbe retroattivamente il
    # significato di tutti i movimenti già registrati.
    apply_updates(account, payload)
    await session.commit()
    await session.refresh(account)
    return (await _serialize(session, user.id, [account]))[0]


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_account(
    account_id: int,
    user: CurrentUser,
    session: DbSession,
    hard: bool = Query(
        default=False,
        description="Elimina davvero la riga; consentito solo se il conto non ha movimenti",
    ),
) -> None:
    account = await get_owned(session, Account, account_id, user.id, label="Conto")

    if not hard:
        account.archived = True
        await session.commit()
        return

    for model, condition in (
        (Transaction, Transaction.account_id == account_id),
        (Transfer, (Transfer.from_account_id == account_id) | (Transfer.to_account_id == account_id)),
        (LiabilityUpdate, LiabilityUpdate.account_id == account_id),
        (Holding, Holding.account_id == account_id),
        (Goal, Goal.linked_account_id == account_id),
    ):
        exists = await session.scalar(select(model.id).where(condition).limit(1))
        if exists:
            raise Conflict(
                "Il conto ha movimenti o collegamenti: archivialo invece di eliminarlo "
                "(DELETE senza ?hard=true)",
                code="account_in_use",
            )

    await session.delete(account)
    await session.commit()


@router.post("/{account_id}/unarchive", response_model=schemas.AccountWithBalance)
async def unarchive_account(account_id: int, user: CurrentUser, session: DbSession) -> dict:
    account = await get_owned(session, Account, account_id, user.id, label="Conto")
    if not account.archived:
        raise Invalid("Il conto non è archiviato")
    account.archived = False
    await session.commit()
    await session.refresh(account)
    return (await _serialize(session, user.id, [account]))[0]
