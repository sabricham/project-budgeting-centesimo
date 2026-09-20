from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SubcategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category_id: int


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    subcategories: list[SubcategoryOut]
