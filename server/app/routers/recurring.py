"""Abbonamenti e spese ricorrenti (§2.7).

    GET    /recurring                      elenco definizioni (+ prossima scadenza)
    POST   /recurring                      crea e genera subito le occorrenze
    PATCH  /recurring/{id}                 modifica
    DELETE /recurring/{id}                 disattiva (o elimina con ?hard=true)
    GET    /recurring/upcoming             occorrenze `projected` in arrivo
    POST   /recurring/generate             forza il job di generazione
    POST   /recurring/occurrences/{tx}/confirm   conferma (con importo corretto)
    POST   /recurring/occurrences/{tx}/skip      salta un'occorrenza
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from app import schemas
from app.auth.deps import CurrentUser, DbSession
from app.config import settings
from app.enums import AccountType, Frequency, TransactionStatus, TransactionType
from app.errors import Invalid
from app.models import Account, Category, RecurringTransaction, Transaction
from app.routers.common import Limit, Offset, apply_updates, check_concurrency, get_owned, paginate
from app.services import recurrence

router = APIRouter(prefix="/recurring", tags=["recurring"])


async def _validate_refs(
    session: DbSession, user_id: int, account_id: int, category_id: int, tx_type: TransactionType
) -> None:
    account = await get_owned(session, Account, account_id, user_id, label="Conto")
    if account.archived:
        raise Invalid("Il conto è archiviato")
    if account.type == AccountType.liability.value:
        raise Invalid("Le ricorrenze non si registrano sui conti `liability` (§2.10)")
    category = await get_owned(session, Category, category_id, user_id, label="Categoria")
    if category.type != tx_type.value:
        raise Invalid(
            f"La categoria '{category.name}' è di tipo {category.type}, "
            f"incompatibile con una ricorrenza {tx_type.value}"
        )


async def _serialize(session: DbSession, rows: list[RecurringTransaction]) -> list[dict]:
    if not rows:
        return []
    account_names = {
        r.id: r.name
        for r in await session.execute(
            select(Account.id, Account.name).where(Account.id.in_({r.account_id for r in rows}))
        )
    }
    category_names = {
        r.id: r.name
        for r in await session.execute(
            select(Category.id, Category.name).where(Category.id.in_({r.category_id for r in rows}))
        )
    }
    out = []
    for rec in rows:
        data = schemas.RecurringOut.model_validate(rec).model_dump()
        data["account_name"] = account_names.get(rec.account_id)
        data["category_name"] = category_names.get(rec.category_id)
        data["next_occurrence"] = recurrence.next_occurrence(
            frequency=rec.frequency,
            interval=rec.interval,
            occurrence_days=rec.occurrence_days,
            start_date=rec.start_date,
            end_date=rec.end_date,
        )
        out.append(data)
    return out


@router.get("", response_model=list[schemas.RecurringOut])
async def list_recurring(
    user: CurrentUser, session: DbSession, only_active: bool = True
) -> list[dict]:
    stmt = select(RecurringTransaction).where(RecurringTransaction.user_id == user.id)
    if only_active:
        stmt = stmt.where(RecurringTransaction.active.is_(True))
    rows = list(await session.scalars(stmt.order_by(RecurringTransaction.description)))
    return await _serialize(session, rows)


@router.post("", response_model=schemas.RecurringOut, status_code=status.HTTP_201_CREATED)
async def create_recurring(
    payload: schemas.RecurringCreate, user: CurrentUser, session: DbSession
) -> dict:
    await _validate_refs(
        session, user.id, payload.account_id, payload.category_id, payload.type
    )
    rec = RecurringTransaction(
        user_id=user.id,
        **{**payload.model_dump(), "type": payload.type.value, "frequency": payload.frequency.value},
    )
    session.add(rec)
    await session.commit()
    await session.refresh(rec)

    # genera subito, così l'utente vede immediatamente le prossime scadenze
    await recurrence.generate_occurrences(
        session, user_id=user.id, recurring_id=rec.id, horizon_days=settings.recurring_horizon_days
    )
    return (await _serialize(session, [rec]))[0]


@router.get("/upcoming", response_model=schemas.Page[schemas.TransactionOut])
async def upcoming(
    user: CurrentUser,
    session: DbSession,
    days: int = Query(default=30, ge=1, le=365),
    limit: Limit = 100,
    offset: Offset = 0,
) -> dict:
    """Occorrenze non ancora confermate nei prossimi `days` giorni.

    Include quelle già scadute ma mai confermate: sono proprio quelle da non dimenticare.
    """
    today = dt.date.today()
    stmt = (
        select(Transaction)
        .where(
            Transaction.user_id == user.id,
            Transaction.deleted_at.is_(None),
            Transaction.status == TransactionStatus.projected.value,
            Transaction.date <= today + dt.timedelta(days=days),
        )
        .order_by(Transaction.date, Transaction.id)
    )
    rows, total = await paginate(session, stmt, limit=limit, offset=offset)

    from app.routers.transactions import _serialize as serialize_tx

    return {
        "items": await serialize_tx(session, rows),
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/generate")
async def generate(
    user: CurrentUser,
    session: DbSession,
    horizon_days: int = Query(default=None, ge=1, le=730),
) -> dict[str, int]:
    """Esegue a richiesta lo stesso job dello scheduler (utile per testare)."""
    return await recurrence.generate_occurrences(
        session,
        user_id=user.id,
        horizon_days=horizon_days or settings.recurring_horizon_days,
    )


@router.get("/{recurring_id}", response_model=schemas.RecurringOut)
async def get_recurring(recurring_id: int, user: CurrentUser, session: DbSession) -> dict:
    rec = await get_owned(session, RecurringTransaction, recurring_id, user.id, label="Ricorrenza")
    return (await _serialize(session, [rec]))[0]


@router.patch("/{recurring_id}", response_model=schemas.RecurringOut)
async def update_recurring(
    recurring_id: int,
    payload: schemas.RecurringUpdate,
    user: CurrentUser,
    session: DbSession,
) -> dict:
    rec = await get_owned(session, RecurringTransaction, recurring_id, user.id, label="Ricorrenza")
    check_concurrency(rec, payload.expected_updated_at)

    fields = payload.model_dump(exclude_unset=True)
    if {"account_id", "category_id"} & fields.keys():
        await _validate_refs(
            session,
            user.id,
            fields.get("account_id", rec.account_id),
            fields.get("category_id", rec.category_id),
            TransactionType(rec.type),
        )
    if {"frequency", "occurrence_days"} & fields.keys():
        frequency = Frequency(fields.get("frequency", rec.frequency))
        recurrence.validate_occurrence_days(
            frequency, fields.get("occurrence_days", rec.occurrence_days)
        )
        rec.frequency = frequency.value

    apply_updates(rec, payload, skip={"frequency"})
    await session.commit()

    # Le occorrenze future non ancora confermate vanno rigenerate sulla nuova regola:
    # quelle già confermate restano storia e non si toccano.
    await session.execute(
        Transaction.__table__.delete().where(
            Transaction.source_recurring_id == rec.id,
            Transaction.status == TransactionStatus.projected.value,
            Transaction.date >= dt.date.today(),
        )
    )
    await session.commit()
    await recurrence.generate_occurrences(
        session, user_id=user.id, recurring_id=rec.id, horizon_days=settings.recurring_horizon_days
    )

    await session.refresh(rec)
    return (await _serialize(session, [rec]))[0]


@router.delete("/{recurring_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_recurring(
    recurring_id: int,
    user: CurrentUser,
    session: DbSession,
    hard: bool = Query(
        default=False, description="Elimina la definizione; le occorrenze future vengono rimosse"
    ),
) -> None:
    rec = await get_owned(session, RecurringTransaction, recurring_id, user.id, label="Ricorrenza")

    await session.execute(
        Transaction.__table__.delete().where(
            Transaction.source_recurring_id == rec.id,
            Transaction.status == TransactionStatus.projected.value,
        )
    )
    if hard:
        await session.delete(rec)
    else:
        rec.active = False
    await session.commit()


@router.post("/occurrences/{transaction_id}/confirm", response_model=schemas.TransactionOut)
async def confirm_occurrence(
    transaction_id: int,
    payload: schemas.ConfirmOccurrenceRequest,
    user: CurrentUser,
    session: DbSession,
) -> dict:
    """Conferma un'occorrenza, correggendo l'importo se serve (bolletta variabile)."""
    tx = await get_owned(session, Transaction, transaction_id, user.id, label="Occorrenza")
    if tx.status != TransactionStatus.projected.value:
        raise Invalid("L'occorrenza è già confermata")
    if payload.amount is not None:
        tx.amount = payload.amount
    if payload.date is not None:
        tx.date = payload.date
    tx.status = TransactionStatus.confirmed.value
    await session.commit()
    await session.refresh(tx)

    from app.routers.transactions import _serialize as serialize_tx

    return (await serialize_tx(session, [tx]))[0]


@router.post("/occurrences/{transaction_id}/skip", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def skip_occurrence(transaction_id: int, user: CurrentUser, session: DbSession) -> None:
    """Salta un'occorrenza (es. mese non addebitato).

    Soft-delete invece di cancellazione: così il job di generazione non la ricrea al giro
    successivo e resta traccia della decisione.
    """
    tx = await get_owned(session, Transaction, transaction_id, user.id, label="Occorrenza")
    if tx.status != TransactionStatus.projected.value:
        raise Invalid("Si possono saltare solo le occorrenze non ancora confermate")
    tx.deleted_at = dt.datetime.now(dt.timezone.utc)
    await session.commit()
