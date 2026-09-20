"""Schema iniziale: utenti, conti, catalogo categorie, entry.

Revision ID: 0001
Revises: 
Create Date: 2026-09-20 16:38:58.855464
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('categories',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name', name='uq_categories_name')
    )
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(length=64), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('display_name', sa.String(length=120), nullable=True),
    sa.Column('base_currency', sa.String(length=3), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('username')
    )
    op.create_table('accounts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('type', sa.String(length=32), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('initial_balance', sa.Numeric(precision=18, scale=2), nullable=False),
    sa.Column('color', sa.String(length=9), nullable=True),
    sa.Column('archived', sa.Boolean(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'name', name='uq_accounts_user_name')
    )
    op.create_index(op.f('ix_accounts_user_id'), 'accounts', ['user_id'], unique=False)
    op.create_table('refresh_tokens',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    op.create_index(op.f('ix_refresh_tokens_user_id'), 'refresh_tokens', ['user_id'], unique=False)
    op.create_table('subcategories',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('category_id', 'name', name='uq_subcategories_category_name')
    )
    op.create_index(op.f('ix_subcategories_category_id'), 'subcategories', ['category_id'], unique=False)
    op.create_table('entries',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('description', sa.String(length=255), nullable=False),
    sa.Column('amount', sa.Numeric(precision=18, scale=2), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('account_id', sa.Integer(), nullable=False),
    sa.Column('to_account_id', sa.Integer(), nullable=True),
    sa.Column('subcategory_id', sa.Integer(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(kind = 'investment' AND to_account_id IS NOT NULL  AND to_account_id <> account_id) OR (kind <> 'investment' AND to_account_id IS NULL)", name='ck_entries_destination_coherent'),
    sa.CheckConstraint("kind IN ('income', 'expense', 'investment')", name='ck_entries_kind'),
    sa.CheckConstraint('amount > 0', name='ck_entries_amount_positive'),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['subcategory_id'], ['subcategories.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['to_account_id'], ['accounts.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_entries_account_id'), 'entries', ['account_id'], unique=False)
    op.create_index(op.f('ix_entries_subcategory_id'), 'entries', ['subcategory_id'], unique=False)
    op.create_index(op.f('ix_entries_to_account_id'), 'entries', ['to_account_id'], unique=False)
    op.create_index('ix_entries_user_date', 'entries', ['user_id', 'date'], unique=False)
    op.create_index(op.f('ix_entries_user_id'), 'entries', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_entries_user_id'), table_name='entries')
    op.drop_index('ix_entries_user_date', table_name='entries')
    op.drop_index(op.f('ix_entries_to_account_id'), table_name='entries')
    op.drop_index(op.f('ix_entries_subcategory_id'), table_name='entries')
    op.drop_index(op.f('ix_entries_account_id'), table_name='entries')
    op.drop_table('entries')
    op.drop_index(op.f('ix_subcategories_category_id'), table_name='subcategories')
    op.drop_table('subcategories')
    op.drop_index(op.f('ix_refresh_tokens_user_id'), table_name='refresh_tokens')
    op.drop_table('refresh_tokens')
    op.drop_index(op.f('ix_accounts_user_id'), table_name='accounts')
    op.drop_table('accounts')
    op.drop_table('users')
    op.drop_table('categories')
