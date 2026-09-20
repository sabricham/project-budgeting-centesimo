"""Storico prezzi giornaliero e budget delle richieste API.

Generata con `--autogenerate` e poi corretta a mano su un punto: `price_cache.asset_kind`
è NOT NULL, e senza `server_default` la migrazione fallirebbe su una tabella già popolata.

Le due tabelle servono a stare dentro le 25 richieste al giorno del piano gratuito:
`price_history` è l'archivio locale (una richiesta per ticker al giorno copre insieme
quotazione corrente e storico), `api_budget` è il contatore che impedisce di sforare.

Revision ID: 0002
Revises: 0001
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "price_history",
        sa.Column("ticker", sa.String(length=24), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("close", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("source", sa.String(length=24), nullable=False, server_default="manual"),
        sa.PrimaryKeyConstraint("ticker", "date"),
    )

    op.create_table(
        "api_budget",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("provider", sa.String(length=24), nullable=False),
        sa.Column("used", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("day", "provider"),
    )

    op.add_column(
        "price_cache",
        sa.Column("asset_kind", sa.String(length=8), nullable=False, server_default="unknown"),
    )


def downgrade() -> None:
    op.drop_column("price_cache", "asset_kind")
    op.drop_table("api_budget")
    op.drop_table("price_history")
