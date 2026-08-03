"""Budget mensili per categoria (§2.5).

`GET /budgets` non restituisce solo il limite ma anche `spent_this_month` e `remaining`:
il calcolo lo fa il server una volta sola, riusabile dal widget dashboard e da eventuali
notifiche future senza duplicare la logica nei client.

Il consumo di una categoria **padre** include anche le sue sotto-categorie: un budget su
"Alimentari" deve contare pure "Supermercato" e "Ristoranti".
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Query, status
from sqlalchemy import func, select

from app import schemas
from app.auth.deps import CurrentUser, DbSession
from app.enums import CategoryType, TransactionStatus, TransactionType
from app.errors import Conflict, Invalid
from app.models import Budget, Category, Transaction
from app.routers.common import apply_updates, check_concurrency, get_owned
from app.services.balances import ZERO, q2

router = APIRouter(prefix="/budgets", tags=["budgets"])


def month_bounds(today: dt.date | None = None) -> tuple[dt.date, dt.date]:
    today = today or dt.date.today()
    first = today.replace(day=1)
    last = (first + dt.timedelta(days=32)).replace(day=1) - dt.timedelta(days=1)
    return first, last


async def _spent_by_category(
    session: DbSession, user_id: int, month: dt.date | None = None
) -> dict[int, "object"]:
    """Speso per categoria nel mese, già aggregato includendo le sotto-categorie."""
    date_from, date_to = month_bounds(month)

    rows = await session.execute(
        select(
            Transaction.category_id,
            func.coalesce(func.sum(Transaction.amount), 0),
        )
        .where(
            Transaction.user_id == user_id,
            Transaction.deleted_at.is_(None),
            Transaction.status == TransactionStatus.confirmed.value,
            Transaction.type == TransactionType.expense.value,
            Transaction.date >= date_from,
            Transaction.date <= date_to,
        )
        .group_by(Transaction.category_id)
    )
    direct = {category_id: total for category_id, total in rows}

    parents = {
        row.id: row.parent_category_id
        for row in await session.execute(
            select(Category.id, Category.parent_category_id).where(Category.user_id == user_id)
        )
    }

    rolled: dict[int, object] = {}
    for category_id, total in direct.items():
        rolled[category_id] = rolled.get(category_id, ZERO) + total
        parent_id = parents.get(category_id)
        if parent_id:
            rolled[parent_id] = rolled.get(parent_id, ZERO) + total
    return rolled


async def _serialize(session: DbSession, user_id: int, budgets: list[Budget]) -> list[dict]:
    if not budgets:
        return []
    spent_map = await _spent_by_category(session, user_id)
    names = {
        row.id: row.name
        for row in await session.execute(
            select(Category.id, Category.name).where(
                Category.id.in_([b.category_id for b in budgets])
            )
        )
    }

    out = []
    for budget in budgets:
        spent = q2(spent_map.get(budget.category_id, ZERO))
        limit = q2(budget.amount_limit)
        out.append(
            {
                "id": budget.id,
                "category_id": budget.category_id,
                "category_name": names.get(budget.category_id, "?"),
                "amount_limit": limit,
                "active": budget.active,
                "spent_this_month": spent,
                "remaining": q2(limit - spent),
                "usage_ratio": float(spent / limit) if limit else 0.0,
                "created_at": budget.created_at,
                "updated_at": budget.updated_at,
            }
        )
    return out


@router.get("", response_model=list[schemas.BudgetOut])
async def list_budgets(
    user: CurrentUser,
    session: DbSession,
    only_active: bool = Query(default=True),
) -> list[dict]:
    stmt = select(Budget).where(Budget.user_id == user.id)
    if only_active:
        stmt = stmt.where(Budget.active.is_(True))
    budgets = list(await session.scalars(stmt.order_by(Budget.id)))
    return await _serialize(session, user.id, budgets)


@router.post("", response_model=schemas.BudgetOut, status_code=status.HTTP_201_CREATED)
async def create_budget(
    payload: schemas.BudgetCreate, user: CurrentUser, session: DbSession
) -> dict:
    category = await get_owned(session, Category, payload.category_id, user.id, label="Categoria")
    if category.type != CategoryType.expense.value:
        raise Invalid("Un budget ha senso solo su una categoria di spesa")

    existing = await session.scalar(select(Budget).where(Budget.category_id == category.id))
    if existing is not None:
        raise Conflict(
            "Esiste già un budget per questa categoria: modificalo invece di crearne un altro",
            code="budget_exists",
        )

    budget = Budget(user_id=user.id, **payload.model_dump())
    session.add(budget)
    await session.commit()
    await session.refresh(budget)
    return (await _serialize(session, user.id, [budget]))[0]


@router.patch("/{budget_id}", response_model=schemas.BudgetOut)
async def update_budget(
    budget_id: int, payload: schemas.BudgetUpdate, user: CurrentUser, session: DbSession
) -> dict:
    budget = await get_owned(session, Budget, budget_id, user.id, label="Budget")
    check_concurrency(budget, payload.expected_updated_at)
    apply_updates(budget, payload)
    await session.commit()
    await session.refresh(budget)
    return (await _serialize(session, user.id, [budget]))[0]


@router.delete("/{budget_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_budget(budget_id: int, user: CurrentUser, session: DbSession) -> None:
    budget = await get_owned(session, Budget, budget_id, user.id, label="Budget")
    await session.delete(budget)
    await session.commit()
