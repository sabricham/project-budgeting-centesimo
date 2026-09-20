from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.core.deps import DbSession
from app.modules.auth.deps import CurrentUser
from app.modules.categories.models import Category
from app.modules.categories.schemas import CategoryOut

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryOut])
async def list_categories(user: CurrentUser, session: DbSession) -> list[CategoryOut]:
    """Catalogo completo, categorie con le loro sottocategorie annidate.

    Una sola chiamata: il frontend lo carica all'avvio e popola entrambe le tendine
    del modulo di inserimento senza altri giri di rete.
    """
    rows = (
        (await session.execute(select(Category).order_by(Category.position, Category.name)))
        .scalars()
        .unique()
    )
    return [CategoryOut.model_validate(row) for row in rows]
