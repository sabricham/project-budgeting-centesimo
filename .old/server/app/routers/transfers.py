"""Trasferimenti fra conti propri (§2.3).

Non sono né entrate né uscite: spostano denaro che resta tuo. Non hanno categoria e sono
esclusi per costruzione dai report "spese per categoria" — è tutto il motivo per cui
esistono come entità separata invece che come coppia spesa+entrata.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Query, status
from sqlalchemy import or_, select

from app import schemas
from app.auth.deps import CurrentUser, DbSession
from app.enums import AccountType
from app.errors import Invalid
from app.models import Account, Transfer
from app.routers.common import Limit, Offset, apply_updates, check_concurrency, get_owned, paginate

router = APIRouter(prefix="/transfers", tags=["transfers"])


async def _validate_accounts(
    session: DbSession, user_id: int, from_id: int, to_id: int
) -> tuple[Account, Account]:
    if from_id == to_id:
        raise Invalid("Il conto di origine e quello di destinazione devono essere diversi")

    source = await get_owned(session, Account, from_id, user_id, label="Conto di origine")
    target = await get_owned(session, Account, to_id, user_id, label="Conto di destinazione")

    for account in (source, target):
        if account.archived:
            raise Invalid(f"Il conto '{account.name}' è archiviato")
        if account.type == AccountType.liability.value:
            raise Invalid(
                "I conti `liability` non partecipano ai trasferimenti: registra la rata come "
                "spesa dal conto corrente e aggiorna il residuo con POST /liabilities (§2.10)"
            )

    if source.currency != target.currency:
        # Un trasferimento cross-valuta richiederebbe un tasso di conversione per singola
        # operazione: fuori scope MVP, meglio un errore chiaro che un saldo sbagliato.
        raise Invalid(
            f"Trasferimento fra valute diverse ({source.currency} → {target.currency}) "
            "non supportato: registralo come uscita su un conto ed entrata sull'altro"
        )
    return source, target


async def _serialize(session: DbSession, rows: list[Transfer]) -> list[dict]:
    if not rows:
        return []
    ids = {t.from_account_id for t in rows} | {t.to_account_id for t in rows}
    names = {
        r.id: r.name
        for r in await session.execute(select(Account.id, Account.name).where(Account.id.in_(ids)))
    }
    out = []
    for transfer in rows:
        data = schemas.TransferOut.model_validate(transfer).model_dump()
        data["from_account_name"] = names.get(transfer.from_account_id)
        data["to_account_name"] = names.get(transfer.to_account_id)
        out.append(data)
    return out


@router.get("", response_model=schemas.Page[schemas.TransferOut])
async def list_transfers(
    user: CurrentUser,
    session: DbSession,
    account_id: int | None = Query(default=None, description="Origine o destinazione"),
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    include_deleted: bool = False,
    limit: Limit = 50,
    offset: Offset = 0,
) -> dict:
    stmt = select(Transfer).where(Transfer.user_id == user.id)
    if not include_deleted:
        stmt = stmt.where(Transfer.deleted_at.is_(None))
    if account_id is not None:
        stmt = stmt.where(
            or_(Transfer.from_account_id == account_id, Transfer.to_account_id == account_id)
        )
    if date_from is not None:
        stmt = stmt.where(Transfer.date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Transfer.date <= date_to)

    stmt = stmt.order_by(Transfer.date.desc(), Transfer.id.desc())
    rows, total = await paginate(session, stmt, limit=limit, offset=offset)
    return {
        "items": await _serialize(session, rows),
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("", response_model=schemas.TransferOut, status_code=status.HTTP_201_CREATED)
async def create_transfer(
    payload: schemas.TransferCreate, user: CurrentUser, session: DbSession
) -> dict:
    await _validate_accounts(session, user.id, payload.from_account_id, payload.to_account_id)
    transfer = Transfer(user_id=user.id, **payload.model_dump())
    session.add(transfer)
    await session.commit()
    await session.refresh(transfer)
    return (await _serialize(session, [transfer]))[0]


@router.get("/{transfer_id}", response_model=schemas.TransferOut)
async def get_transfer(transfer_id: int, user: CurrentUser, session: DbSession) -> dict:
    transfer = await get_owned(session, Transfer, transfer_id, user.id, label="Trasferimento")
    return (await _serialize(session, [transfer]))[0]


@router.patch("/{transfer_id}", response_model=schemas.TransferOut)
async def update_transfer(
    transfer_id: int, payload: schemas.TransferUpdate, user: CurrentUser, session: DbSession
) -> dict:
    transfer = await get_owned(session, Transfer, transfer_id, user.id, label="Trasferimento")
    check_concurrency(transfer, payload.expected_updated_at)

    fields = payload.model_dump(exclude_unset=True)
    if {"from_account_id", "to_account_id"} & fields.keys():
        await _validate_accounts(
            session,
            user.id,
            fields.get("from_account_id", transfer.from_account_id),
            fields.get("to_account_id", transfer.to_account_id),
        )
    apply_updates(transfer, payload)
    await session.commit()
    await session.refresh(transfer)
    return (await _serialize(session, [transfer]))[0]


@router.delete("/{transfer_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_transfer(
    transfer_id: int,
    user: CurrentUser,
    session: DbSession,
    hard: bool = Query(default=False),
) -> None:
    transfer = await get_owned(session, Transfer, transfer_id, user.id, label="Trasferimento")
    if hard:
        await session.delete(transfer)
    else:
        transfer.deleted_at = dt.datetime.now(dt.timezone.utc)
    await session.commit()
