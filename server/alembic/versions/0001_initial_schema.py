"""Schema iniziale — tutte le tabelle di dominio.

Revision ID: 0001
Revises:
Create Date: 2026-07-30

Nota implementativa: questa prima migrazione è una **baseline** e crea lo schema
direttamente da `Base.metadata`. È una scelta deliberata: su un progetto greenfield
riscrivere a mano ~16 `create_table` introduce solo il rischio che la migrazione e i
modelli divergano al primo giorno di vita. Dalla 0002 in poi si procede normalmente
con `alembic revision --autogenerate`, che confronta i modelli con il DB reale.
"""

from typing import Sequence, Union

from alembic import op

from app.db import Base
from app import models  # noqa: F401  (registra i modelli su Base.metadata)

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
