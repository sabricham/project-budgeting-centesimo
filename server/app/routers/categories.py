"""Categorie di entrata/uscita, con sotto-categorie (§2.4)."""

from __future__ import annotations

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from app import schemas
from app.auth.deps import CurrentUser, DbSession
from app.enums import CategoryType
from app.errors import Conflict, Invalid
from app.models import Budget, Category, RecurringTransaction, Transaction
from app.routers.common import apply_updates, check_concurrency, get_owned

router = APIRouter(prefix="/categories", tags=["categories"])


async def _validate_parent(
    session: DbSession, user_id: int, parent_id: int | None, child_type: CategoryType, self_id: int | None = None
) -> None:
    if parent_id is None:
        return
    if parent_id == self_id:
        raise Invalid("Una categoria non può essere padre di sé stessa")
    parent = await get_owned(session, Category, parent_id, user_id, label="Categoria padre")
    if parent.type != child_type.value:
        raise Invalid("La sotto-categoria deve avere lo stesso tipo (income/expense) del padre")
    if parent.parent_category_id is not None:
        # Un solo livello di annidamento: due livelli bastano ai report e tengono la UI leggibile.
        raise Invalid("Sono ammessi al massimo due livelli di categorie")


@router.get("", response_model=list[schemas.CategoryOut])
async def list_categories(
    user: CurrentUser,
    session: DbSession,
    include_archived: bool = False,
    type: CategoryType | None = Query(default=None),
) -> list[Category]:
    stmt = select(Category).where(Category.user_id == user.id)
    if not include_archived:
        stmt = stmt.where(Category.archived.is_(False))
    if type is not None:
        stmt = stmt.where(Category.type == type.value)
    stmt = stmt.order_by(Category.type, Category.parent_category_id.nulls_first(), Category.name)
    return list(await session.scalars(stmt))


@router.post("", response_model=schemas.CategoryOut, status_code=status.HTTP_201_CREATED)
async def create_category(
    payload: schemas.CategoryCreate, user: CurrentUser, session: DbSession
) -> Category:
    await _validate_parent(session, user.id, payload.parent_category_id, payload.type)
    category = Category(
        user_id=user.id,
        name=payload.name,
        type=payload.type.value,
        parent_category_id=payload.parent_category_id,
        icon=payload.icon,
        color=payload.color,
    )
    session.add(category)
    await session.commit()
    await session.refresh(category)
    return category


@router.get("/{category_id}", response_model=schemas.CategoryOut)
async def get_category(category_id: int, user: CurrentUser, session: DbSession) -> Category:
    return await get_owned(session, Category, category_id, user.id, label="Categoria")


@router.patch("/{category_id}", response_model=schemas.CategoryOut)
async def update_category(
    category_id: int, payload: schemas.CategoryUpdate, user: CurrentUser, session: DbSession
) -> Category:
    category = await get_owned(session, Category, category_id, user.id, label="Categoria")
    check_concurrency(category, payload.expected_updated_at)
    if "parent_category_id" in payload.model_dump(exclude_unset=True):
        await _validate_parent(
            session, user.id, payload.parent_category_id, CategoryType(category.type), category.id
        )
    # Il tipo (income/expense) non è modificabile: cambierebbe il segno di tutto lo storico.
    apply_updates(category, payload)
    await session.commit()
    await session.refresh(category)
    return category


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_category(
    category_id: int,
    user: CurrentUser,
    session: DbSession,
    hard: bool = Query(default=False, description="Elimina la riga se non è mai stata usata"),
) -> None:
    category = await get_owned(session, Category, category_id, user.id, label="Categoria")

    if not hard:
        category.archived = True
        await session.commit()
        return

    for model, condition in (
        (Transaction, Transaction.category_id == category_id),
        (RecurringTransaction, RecurringTransaction.category_id == category_id),
        (Budget, Budget.category_id == category_id),
        (Category, Category.parent_category_id == category_id),
    ):
        exists = await session.scalar(select(model.id).where(condition).limit(1))
        if exists:
            raise Conflict(
                "Categoria in uso (transazioni, ricorrenze, budget o sotto-categorie): "
                "archiviala invece di eliminarla",
                code="category_in_use",
            )

    await session.delete(category)
    await session.commit()
