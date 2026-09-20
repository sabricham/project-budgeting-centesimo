"""Catalogo di categorie e sottocategorie.

Due tabelle distinte, non una self-FK: il catalogo in `data/categories.json` è preso
**alla lettera**. Una sottocategoria appartiene a una sola categoria, e sottocategorie
omonime di categorie diverse — «Regali» sotto *Acquisti* e «Regali» sotto *Entrata*,
«Lotteria e gioco d'azzardo» sotto *Vita e intrattenimento* e sotto *Entrata* — sono
righe **separate e senza alcun legame fra loro**. Scelta esplicita dell'utente: nessuna
deduzione automatica, nessuna fusione di omonimi.

Il catalogo è **globale**, non per-utente: è un elenco di riferimento condiviso. Se un
giorno servisse personalizzarlo per utente, basterà aggiungere una colonna `user_id`
nullable senza toccare le entry, che puntano alla sottocategoria per id.

Il tipo di movimento (entrata / uscita / investimento) **non** si deduce da qui: è un
campo esplicito della entry. Vedi `app/modules/entries/models.py`.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("name", name="uq_categories_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    #: ordine di presentazione: quello del JSON, così le tendine non si riordinano da sole
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    subcategories: Mapped[list["Subcategory"]] = relationship(
        back_populates="category",
        order_by="Subcategory.position",
        lazy="selectin",
        cascade="all, delete-orphan",
    )


class Subcategory(Base):
    __tablename__ = "subcategories"
    __table_args__ = (
        UniqueConstraint("category_id", "name", name="uq_subcategories_category_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    category: Mapped[Category] = relationship(back_populates="subcategories")
