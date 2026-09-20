from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EntryKind = Literal["income", "expense", "investment"]


class EntryCreate(BaseModel):
    date: dt.date
    description: str = Field(default="", max_length=255)
    amount: Decimal = Field(gt=0)
    kind: EntryKind
    account_id: int
    subcategory_id: int
    #: obbligatorio se `kind = investment`, vietato altrimenti
    to_account_id: int | None = None


class EntryUpdate(BaseModel):
    date: dt.date | None = None
    description: str | None = Field(default=None, max_length=255)
    amount: Decimal | None = Field(default=None, gt=0)
    kind: EntryKind | None = None
    account_id: int | None = None
    subcategory_id: int | None = None
    to_account_id: int | None = None


class EntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: dt.date
    description: str
    amount: Decimal
    kind: EntryKind
    account_id: int
    to_account_id: int | None
    subcategory_id: int

    # Denormalizzati in lettura: la tabella dello Storico deve poter ordinare per
    # categoria senza che il frontend debba incrociare tre elenchi.
    account_name: str | None = None
    to_account_name: str | None = None
    category_id: int | None = None
    category_name: str | None = None
    subcategory_name: str | None = None
