"""Regole di dominio dei conti. La CRUD pura sta nel router."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Invalid
from app.modules.accounts.models import Account


async def ensure_name_free(
    session: AsyncSession, user_id: int, name: str, *, exclude_id: int | None = None
) -> None:
    stmt = select(Account.id).where(Account.user_id == user_id, Account.name == name)
    if exclude_id is not None:
        stmt = stmt.where(Account.id != exclude_id)
    if await session.scalar(stmt) is not None:
        raise Invalid(f"Esiste già un conto chiamato «{name}»")


async def owned_ids(session: AsyncSession, user_id: int) -> list[int]:
    return [row[0] for row in await session.execute(
        select(Account.id).where(Account.user_id == user_id)
    )]
