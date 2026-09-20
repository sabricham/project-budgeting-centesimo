from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class AccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: str = Field(default="bank", max_length=32)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    initial_balance: Decimal = Decimal("0.00")
    color: str | None = Field(default=None, max_length=9)
    notes: str | None = None


class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    type: str | None = Field(default=None, max_length=32)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    initial_balance: Decimal | None = None
    color: str | None = Field(default=None, max_length=9)
    archived: bool | None = None
    notes: str | None = None


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: str
    currency: str
    initial_balance: Decimal
    color: str | None
    archived: bool
    notes: str | None
    #: saldo corrente, calcolato dai movimenti — non è una colonna del database
    balance: Decimal = Decimal("0.00")
