"""Debiti e prestiti: snapshot del capitale residuo (§2.10).

Qui NON si registrano le rate: quelle sono normali spese dal conto corrente con
categoria "Mutuo/Prestiti". Questo endpoint serve solo a dire "al 1/8/2026 il residuo è
144.500€", che è il dato che serve al patrimonio netto.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, status
from sqlalchemy import select

from app import schemas
from app.auth.deps import CurrentUser, DbSession
from app.enums import AccountType
from app.errors import Invalid
from app.models import Account, LiabilityUpdate
from app.routers.common import Limit, Offset, get_owned, paginate

router = APIRouter(prefix="/liabilities", tags=["liabilities"])


@router.get("", response_model=schemas.Page[schemas.LiabilityUpdateOut])
async def list_updates(
    user: CurrentUser,
    session: DbSession,
    account_id: int | None = None,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> dict:
    stmt = select(LiabilityUpdate).where(LiabilityUpdate.user_id == user.id)
    if account_id is not None:
        stmt = stmt.where(LiabilityUpdate.account_id == account_id)
    if date_from is not None:
        stmt = stmt.where(LiabilityUpdate.date >= date_from)
    if date_to is not None:
        stmt = stmt.where(LiabilityUpdate.date <= date_to)
    stmt = stmt.order_by(LiabilityUpdate.date.desc(), LiabilityUpdate.id.desc())

    rows, total = await paginate(session, stmt, limit=limit, offset=offset)
    return {"items": rows, "total": total, "limit": limit, "offset": offset}


@router.post("", response_model=schemas.LiabilityUpdateOut, status_code=status.HTTP_201_CREATED)
async def create_update(
    payload: schemas.LiabilityUpdateCreate, user: CurrentUser, session: DbSession
) -> LiabilityUpdate:
    account = await get_owned(session, Account, payload.account_id, user.id, label="Conto")
    if account.type != AccountType.liability.value:
        raise Invalid("Gli snapshot di residuo valgono solo per i conti di tipo `liability`")

    row = LiabilityUpdate(user_id=user.id, **payload.model_dump())
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


@router.delete("/{update_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_update(update_id: int, user: CurrentUser, session: DbSession) -> None:
    row = await get_owned(session, LiabilityUpdate, update_id, user.id, label="Aggiornamento")
    await session.delete(row)
    await session.commit()
