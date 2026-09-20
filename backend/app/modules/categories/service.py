"""Caricamento del catalogo dal JSON.

Idempotente: rilanciarlo non duplica nulla e non tocca le righe già presenti, così può
girare ad ogni avvio senza conseguenze.
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.categories.models import Category, Subcategory

CATALOG_PATH = Path(__file__).parent / "data" / "categories.json"


def load_catalog() -> dict[str, list[str]]:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


async def sync_catalog(session: AsyncSession) -> tuple[int, int]:
    """Allinea il database al JSON. Restituisce (categorie aggiunte, sottocategorie aggiunte).

    Aggiunge soltanto: non rinomina e non cancella. Togliere una voce dal JSON non la
    rimuove dal database, perché delle entry potrebbero già puntarci.
    """
    catalog = load_catalog()

    existing_categories = {
        row.name: row for row in (await session.execute(select(Category))).scalars()
    }
    added_categories = 0
    added_subcategories = 0

    for cat_position, (cat_name, sub_names) in enumerate(catalog.items()):
        category = existing_categories.get(cat_name)
        if category is None:
            category = Category(name=cat_name, position=cat_position)
            session.add(category)
            await session.flush()
            added_categories += 1

        existing_subs = {
            row[0]
            for row in await session.execute(
                select(Subcategory.name).where(Subcategory.category_id == category.id)
            )
        }
        for sub_position, sub_name in enumerate(sub_names):
            if sub_name in existing_subs:
                continue
            session.add(
                Subcategory(category_id=category.id, name=sub_name, position=sub_position)
            )
            added_subcategories += 1

    await session.commit()
    return added_categories, added_subcategories
