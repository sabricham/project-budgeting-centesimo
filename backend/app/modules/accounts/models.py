"""Conti: banca, contanti, Satispay, PayPal, investimento, ...

Il saldo **non è una colonna**. Si ricalcola sempre da `initial_balance` più i movimenti
(vedi `app/modules/entries/service.py`): è la scelta che rende impossibile la classica
deriva "saldo salvato diverso dalla somma dei movimenti".
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin

MONEY = Numeric(18, 2)

#: Tipi proposti dall'interfaccia. Volutamente **non** un CHECK sul database: aggiungere
#: un tipo deve restare una riga di Python, non una migrazione. Il tipo è un'etichetta per
#: l'utente — nessuna logica di calcolo dipende da esso.
ACCOUNT_TYPES: tuple[str, ...] = (
    "bank",
    "cash",
    "ewallet",
    "card",
    "investment",
    "savings",
    "other",
)


class Account(TimestampMixin, Base):
    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_accounts_user_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False, default="bank")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    initial_balance: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=0)
    color: Mapped[str | None] = mapped_column(String(9))
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text)
