"""Helper condivisi dai router: ownership, concorrenza, paginazione."""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any, TypeVar

from fastapi import Query
from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import Conflict, NotFound

T = TypeVar("T")

Limit = Annotated[int, Query(ge=1, le=500)]
Offset = Annotated[int, Query(ge=0)]


async def get_owned(
    session: AsyncSession, model: type[T], obj_id: int, user_id: int, *, label: str = "Risorsa"
) -> T:
    """Carica una riga verificando che appartenga all'utente del token.

    Restituisce 404 (non 403) se appartiene a un altro utente: non si conferma
    nemmeno l'esistenza di un id altrui.
    """
    obj = await session.scalar(
        select(model).where(model.id == obj_id, model.user_id == user_id)  # type: ignore[attr-defined]
    )
    if obj is None:
        raise NotFound(f"{label} {obj_id} non trovata/o")
    return obj


def check_concurrency(obj: Any, expected_updated_at: dt.datetime | None) -> None:
    """Concorrenza ottimistica opzionale (§1.3)."""
    if expected_updated_at is None:
        return
    current: dt.datetime = obj.updated_at
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.timezone.utc)
    expected = expected_updated_at
    if expected.tzinfo is None:
        expected = expected.replace(tzinfo=dt.timezone.utc)
    # tolleranza di 1 ms: il roundtrip JSON può perdere precisione sui microsecondi
    if abs((current - expected).total_seconds()) > 0.001:
        raise Conflict(
            "La risorsa è stata modificata da un altro dispositivo: ricarica prima di salvare",
            code="stale_update",
        )


def apply_updates(obj: Any, payload: BaseModel, *, skip: set[str] | None = None) -> bool:
    """Applica i soli campi effettivamente presenti nella PATCH. True se qualcosa è cambiato."""
    skip = (skip or set()) | {"expected_updated_at"}
    changed = False
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field in skip:
            continue
        if getattr(obj, field) != value:
            setattr(obj, field, value)
            changed = True
    return changed


async def paginate(
    session: AsyncSession, stmt: Select, *, limit: int, offset: int
) -> tuple[list[Any], int]:
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = await session.execute(stmt.limit(limit).offset(offset))
    return list(rows.scalars().unique()), int(total)
