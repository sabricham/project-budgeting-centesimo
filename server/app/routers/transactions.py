"""Transazioni: entrate e uscite (§2.6).

Validazione lato server (§1.3) — il client può anticiparla per la UX, ma qui è quella
che conta: importo > 0, conto e categoria esistenti e dell'utente, conto non archiviato,
tipo della transazione coerente con il tipo della categoria.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Query, status
from sqlalchemy import or_, select

from app import schemas
from app.auth.deps import CurrentUser, DbSession
from app.enums import AccountType, TransactionStatus, TransactionType
from app.errors import Invalid
from app.models import Account, Category, Transaction
from app.routers.common import Limit, Offset, apply_updates, check_concurrency, get_owned, paginate

router = APIRouter(prefix="/transactions", tags=["transactions"])


async def _validate_refs(
    session: DbSession,
    user_id: int,
    *,
    account_id: int,
    category_id: int,
    tx_type: TransactionType,
) -> None:
    account = await get_owned(session, Account, account_id, user_id, label="Conto")
    if account.archived:
        raise Invalid("Il conto è archiviato: riattivalo prima di registrarci movimenti")
    if account.type == AccountType.liability.value:
        raise Invalid(
            "Sui conti di tipo `liability` non si registrano transazioni: la rata è una spesa "
            "dal conto corrente, il residuo si aggiorna con POST /liabilities (§2.10)"
        )

    category = await get_owned(session, Category, category_id, user_id, label="Categoria")
    if category.type != tx_type.value:
        raise Invalid(
            f"La categoria '{category.name}' è di tipo {category.type}, "
            f"non compatibile con una transazione {tx_type.value}"
        )


async def _serialize(session: DbSession, rows: list[Transaction]) -> list[dict]:
    if not rows:
        return []
    account_names = {
        r.id: r.name
        for r in await session.execute(
            select(Account.id, Account.name).where(Account.id.in_({t.account_id for t in rows}))
        )
    }
    category_names = {
        r.id: r.name
        for r in await session.execute(
            select(Category.id, Category.name).where(Category.id.in_({t.category_id for t in rows}))
        )
    }
    out = []
    for tx in rows:
        data = schemas.TransactionOut.model_validate(tx).model_dump()
        data["account_name"] = account_names.get(tx.account_id)
        data["category_name"] = category_names.get(tx.category_id)
        out.append(data)
    return out


@router.get("", response_model=schemas.Page[schemas.TransactionOut])
async def list_transactions(
    user: CurrentUser,
    session: DbSession,
    account_id: int | None = None,
    category_id: int | None = None,
    type: TransactionType | None = None,
    status_filter: TransactionStatus | None = Query(default=None, alias="status"),
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    search: str | None = Query(default=None, description="Cerca nella descrizione"),
    include_deleted: bool = False,
    limit: Limit = 50,
    offset: Offset = 0,
) -> dict:
    stmt = select(Transaction).where(Transaction.user_id == user.id)
    if not include_deleted:
        stmt = stmt.where(Transaction.deleted_at.is_(None))
    if account_id is not None:
        stmt = stmt.where(Transaction.account_id == account_id)
    if category_id is not None:
        # include le sotto-categorie della categoria richiesta
        children = select(Category.id).where(Category.parent_category_id == category_id)
        stmt = stmt.where(
            or_(Transaction.category_id == category_id, Transaction.category_id.in_(children))
        )
    if type is not None:
        stmt = stmt.where(Transaction.type == type.value)
    if status_filter is not None:
        stmt = stmt.where(Transaction.status == status_filter.value)
    if date_from is not None:
        stmt = stmt.where(Transaction.date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Transaction.date <= date_to)
    if search:
        stmt = stmt.where(Transaction.description.ilike(f"%{search}%"))

    stmt = stmt.order_by(Transaction.date.desc(), Transaction.id.desc())
    rows, total = await paginate(session, stmt, limit=limit, offset=offset)
    return {
        "items": await _serialize(session, rows),
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("", response_model=schemas.TransactionOut, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    payload: schemas.TransactionCreate, user: CurrentUser, session: DbSession
) -> dict:
    await _validate_refs(
        session,
        user.id,
        account_id=payload.account_id,
        category_id=payload.category_id,
        tx_type=payload.type,
    )
    tx = Transaction(
        user_id=user.id,
        account_id=payload.account_id,
        category_id=payload.category_id,
        type=payload.type.value,
        amount=payload.amount,
        date=payload.date,
        description=payload.description,
        status=payload.status.value,
    )
    session.add(tx)
    await session.commit()
    await session.refresh(tx)
    return (await _serialize(session, [tx]))[0]


@router.get("/{transaction_id}", response_model=schemas.TransactionOut)
async def get_transaction(transaction_id: int, user: CurrentUser, session: DbSession) -> dict:
    tx = await get_owned(session, Transaction, transaction_id, user.id, label="Transazione")
    return (await _serialize(session, [tx]))[0]


@router.patch("/{transaction_id}", response_model=schemas.TransactionOut)
async def update_transaction(
    transaction_id: int,
    payload: schemas.TransactionUpdate,
    user: CurrentUser,
    session: DbSession,
) -> dict:
    tx = await get_owned(session, Transaction, transaction_id, user.id, label="Transazione")
    check_concurrency(tx, payload.expected_updated_at)

    fields = payload.model_dump(exclude_unset=True)
    if {"account_id", "category_id", "type"} & fields.keys():
        await _validate_refs(
            session,
            user.id,
            account_id=fields.get("account_id", tx.account_id),
            category_id=fields.get("category_id", tx.category_id),
            tx_type=TransactionType(fields.get("type", tx.type)),
        )

    for field in ("type", "status"):
        if field in fields and fields[field] is not None:
            setattr(tx, field, fields[field].value if hasattr(fields[field], "value") else fields[field])
    apply_updates(tx, payload, skip={"type", "status"})

    await session.commit()
    await session.refresh(tx)
    return (await _serialize(session, [tx]))[0]


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_transaction(
    transaction_id: int,
    user: CurrentUser,
    session: DbSession,
    hard: bool = Query(default=False, description="Elimina definitivamente invece di archiviare"),
) -> None:
    tx = await get_owned(session, Transaction, transaction_id, user.id, label="Transazione")
    if hard:
        await session.delete(tx)
    else:
        # soft-delete: sparisce da liste, saldi e report ma resta recuperabile
        tx.deleted_at = dt.datetime.now(dt.timezone.utc)
    await session.commit()


@router.post("/{transaction_id}/restore", response_model=schemas.TransactionOut)
async def restore_transaction(transaction_id: int, user: CurrentUser, session: DbSession) -> dict:
    tx = await get_owned(session, Transaction, transaction_id, user.id, label="Transazione")
    if tx.deleted_at is None:
        raise Invalid("La transazione non è eliminata")
    tx.deleted_at = None
    await session.commit()
    await session.refresh(tx)
    return (await _serialize(session, [tx]))[0]
