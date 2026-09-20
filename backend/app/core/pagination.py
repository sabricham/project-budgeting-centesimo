"""Helper condivisi dai router di ogni modulo: ownership, paginazione, PATCH parziali."""

from __future__ import annotations

from typing import Annotated, Any, Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound

T = TypeVar("T")

Limit = Annotated[int, Query(ge=1, le=500)]
Offset = Annotated[int, Query(ge=0)]


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


async def get_owned(
    session: AsyncSession, model: type[T], obj_id: int, user_id: int, *, label: str = "Risorsa"
) -> T:
    """Carica una riga verificando che appartenga all'utente del token.

    Restituisce 404 e non 403: non si conferma nemmeno l'esistenza di un id altrui.
    """
    obj = await session.scalar(
        select(model).where(model.id == obj_id, model.user_id == user_id)  # type: ignore[attr-defined]
    )
    if obj is None:
        raise NotFound(f"{label} {obj_id} non trovata/o")
    return obj


def apply_updates(obj: Any, payload: BaseModel, *, skip: set[str] | None = None) -> bool:
    """Applica i soli campi presenti nella PATCH. True se qualcosa è davvero cambiato."""
    skip = skip or set()
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
