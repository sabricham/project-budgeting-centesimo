"""API delle entry.

L'ordinamento è **lato server**: la pagina Storico è paginata, e ordinare solo la pagina
corrente darebbe un risultato sbagliato appena i movimenti superano il limite.
Ordinabile per data, importo, categoria, sottocategoria, conto e tipo — non per
descrizione, come richiesto.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Query, status
from sqlalchemy import Select, or_, select
from sqlalchemy.orm import aliased

from app.core.deps import DbSession
from app.core.errors import Invalid
from app.core.pagination import Limit, Offset, Page, apply_updates, get_owned, paginate
from app.core.security import utcnow
from app.modules.accounts.models import Account
from app.modules.auth.deps import CurrentUser
from app.modules.categories.models import Category, Subcategory
from app.modules.entries import service
from app.modules.entries.models import ENTRY_KINDS, Entry
from app.modules.entries.schemas import EntryCreate, EntryOut, EntryUpdate

router = APIRouter(prefix="/entries", tags=["entries"])

#: colonne ammesse per l'ordinamento -> espressione da usare nell'ORDER BY
SORTABLE = ("date", "amount", "category", "subcategory", "account", "kind")


async def _serialize(session: DbSession, rows: list[Entry]) -> list[EntryOut]:
    """Arricchisce le entry con i nomi di conto, categoria e sottocategoria.

    Due sole query in più per l'intera pagina, invece di una per riga.
    """
    if not rows:
        return []

    account_ids = {r.account_id for r in rows} | {
        r.to_account_id for r in rows if r.to_account_id is not None
    }
    names = {
        row.id: row.name
        for row in await session.execute(select(Account.id, Account.name).where(Account.id.in_(account_ids)))
    }

    sub_rows = await session.execute(
        select(Subcategory.id, Subcategory.name, Category.id, Category.name)
        .join(Category, Category.id == Subcategory.category_id)
        .where(Subcategory.id.in_({r.subcategory_id for r in rows}))
    )
    subs = {row[0]: (row[1], row[2], row[3]) for row in sub_rows}

    out = []
    for row in rows:
        item = EntryOut.model_validate(row)
        item.account_name = names.get(row.account_id)
        item.to_account_name = names.get(row.to_account_id) if row.to_account_id else None
        sub = subs.get(row.subcategory_id)
        if sub:
            item.subcategory_name, item.category_id, item.category_name = sub
        out.append(item)
    return out


def _apply_sort(stmt: Select, sort: str, order: str) -> Select:
    """Aggiunge ORDER BY, con i join necessari per ordinare sui nomi."""
    descending = order.lower() == "desc"

    if sort in ("category", "subcategory"):
        stmt = stmt.join(Subcategory, Subcategory.id == Entry.subcategory_id)
        if sort == "category":
            stmt = stmt.join(Category, Category.id == Subcategory.category_id)
            column = Category.name
        else:
            column = Subcategory.name
    elif sort == "account":
        source = aliased(Account)
        stmt = stmt.join(source, source.id == Entry.account_id)
        column = source.name
    elif sort == "amount":
        column = Entry.amount
    elif sort == "kind":
        column = Entry.kind
    else:
        column = Entry.date

    stmt = stmt.order_by(column.desc() if descending else column.asc())
    # Secondo criterio stabile: senza, due righe con la stessa data possono scambiarsi
    # di posto fra una pagina e l'altra.
    return stmt.order_by(Entry.id.desc())


@router.get("/kinds", response_model=list[str])
async def list_kinds() -> list[str]:
    return list(ENTRY_KINDS)


@router.get("", response_model=Page[EntryOut])
async def list_entries(
    user: CurrentUser,
    session: DbSession,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    account_id: int | None = Query(default=None, description="Conto; considera anche i movimenti ricevuti"),
    kind: str | None = None,
    category_id: int | None = None,
    subcategory_id: int | None = None,
    search: str | None = Query(default=None, description="Cerca nella descrizione"),
    sort: str = Query(default="date", description=f"Uno di: {', '.join(SORTABLE)}"),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: Limit = 100,
    offset: Offset = 0,
) -> Page[EntryOut]:
    if sort not in SORTABLE:
        raise Invalid(f"Ordinamento «{sort}» non ammesso. Usa uno di: {', '.join(SORTABLE)}")

    stmt = select(Entry).where(Entry.user_id == user.id, Entry.deleted_at.is_(None))

    if date_from is not None:
        stmt = stmt.where(Entry.date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Entry.date <= date_to)
    if account_id is not None:
        # Un investimento compare nello storico di entrambi i conti coinvolti.
        stmt = stmt.where(or_(Entry.account_id == account_id, Entry.to_account_id == account_id))
    if kind is not None:
        stmt = stmt.where(Entry.kind == kind)
    if subcategory_id is not None:
        stmt = stmt.where(Entry.subcategory_id == subcategory_id)
    if category_id is not None:
        stmt = stmt.where(
            Entry.subcategory_id.in_(
                select(Subcategory.id).where(Subcategory.category_id == category_id)
            )
        )
    if search:
        stmt = stmt.where(Entry.description.ilike(f"%{search}%"))

    rows, total = await paginate(session, _apply_sort(stmt, sort, order), limit=limit, offset=offset)
    return Page(items=await _serialize(session, rows), total=total, limit=limit, offset=offset)


@router.post("", response_model=EntryOut, status_code=status.HTTP_201_CREATED)
async def create_entry(payload: EntryCreate, user: CurrentUser, session: DbSession) -> EntryOut:
    await service.validate_refs(
        session,
        user.id,
        kind=payload.kind,
        account_id=payload.account_id,
        to_account_id=payload.to_account_id,
        subcategory_id=payload.subcategory_id,
    )
    entry = Entry(user_id=user.id, **payload.model_dump())
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return (await _serialize(session, [entry]))[0]


@router.get("/{entry_id}", response_model=EntryOut)
async def get_entry(entry_id: int, user: CurrentUser, session: DbSession) -> EntryOut:
    entry = await get_owned(session, Entry, entry_id, user.id, label="Movimento")
    return (await _serialize(session, [entry]))[0]


@router.patch("/{entry_id}", response_model=EntryOut)
async def update_entry(
    entry_id: int, payload: EntryUpdate, user: CurrentUser, session: DbSession
) -> EntryOut:
    entry = await get_owned(session, Entry, entry_id, user.id, label="Movimento")
    apply_updates(entry, payload)
    # Rivalidato sullo stato risultante, non sul solo payload: cambiare il tipo senza
    # toccare il conto di destinazione deve comunque essere respinto.
    await service.validate_refs(
        session,
        user.id,
        kind=entry.kind,
        account_id=entry.account_id,
        to_account_id=entry.to_account_id,
        subcategory_id=entry.subcategory_id,
    )
    await session.commit()
    await session.refresh(entry)
    return (await _serialize(session, [entry]))[0]


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_entry(entry_id: int, user: CurrentUser, session: DbSession) -> None:
    """Soft-delete: la riga resta, esce da liste e saldi ed è ripristinabile."""
    entry = await get_owned(session, Entry, entry_id, user.id, label="Movimento")
    if entry.deleted_at is None:
        entry.deleted_at = utcnow()
        await session.commit()


@router.post("/{entry_id}/restore", response_model=EntryOut)
async def restore_entry(entry_id: int, user: CurrentUser, session: DbSession) -> EntryOut:
    entry = await get_owned(session, Entry, entry_id, user.id, label="Movimento")
    entry.deleted_at = None
    await session.commit()
    await session.refresh(entry)
    return (await _serialize(session, [entry]))[0]
