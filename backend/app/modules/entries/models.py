"""Entry: un movimento registrato su un conto.

Campi richiesti: data, descrizione, categoria, sottocategoria, importo — più il conto e
il tipo di movimento.

Tre tipi, scelti **esplicitamente** dall'utente e mai dedotti dalla categoria:

  ``income``      entrata      il conto sale di `amount`
  ``expense``     uscita       il conto scende di `amount`
  ``investment``  investimento `account_id` scende di `amount` e `to_account_id` sale
                               dello stesso importo

Il terzo tipo è la ragione per cui il grafico del patrimonio resta onesto: investire 500 €
non è spendere 500 €, il denaro resta tuo e cambia soltanto conto. Sommando tutti i conti
un movimento `investment` vale zero. Lo stesso meccanismo copre anche il semplice
spostamento banca → Satispay.

`amount` è sempre **positivo**: il segno lo dà il tipo, non il numero. Così nessuna query
deve ricordarsi di gestire importi negativi.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin

MONEY = Numeric(18, 2)

KIND_INCOME = "income"
KIND_EXPENSE = "expense"
KIND_INVESTMENT = "investment"

ENTRY_KINDS: tuple[str, ...] = (KIND_INCOME, KIND_EXPENSE, KIND_INVESTMENT)


class Entry(TimestampMixin, Base):
    __tablename__ = "entries"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('income', 'expense', 'investment')", name="ck_entries_kind"
        ),
        CheckConstraint("amount > 0", name="ck_entries_amount_positive"),
        # Il conto di destinazione esiste se e solo se il movimento è un investimento,
        # e non può coincidere con quello di partenza. Garantito dal database, non solo
        # dalla validazione applicativa.
        CheckConstraint(
            "(kind = 'investment' AND to_account_id IS NOT NULL "
            " AND to_account_id <> account_id)"
            " OR (kind <> 'investment' AND to_account_id IS NULL)",
            name="ck_entries_destination_coherent",
        ),
        Index("ix_entries_user_date", "user_id", "date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)

    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    #: valorizzato solo per `kind = investment`: il conto che riceve il denaro
    to_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), index=True
    )
    subcategory_id: Mapped[int] = mapped_column(
        ForeignKey("subcategories.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    #: soft-delete: una entry cancellata sparisce da liste e saldi ma resta recuperabile
    deleted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
