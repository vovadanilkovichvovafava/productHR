"""Add shadow users system

Adds support for hidden superadmin accounts (shadow users) with content isolation.

Creates:
- users.is_shadow (Boolean) - marks hidden superadmin accounts
- users.shadow_owner_id (FK to users.id) - who created this shadow user
- Index on is_shadow for fast filtering

Shadow users:
- Have full superadmin access to all org data
- Are completely hidden from user listings
- Have content isolation (main superadmin and shadow users don't see each other's content)

Revision ID: add_shadow_users
Revises: add_embeddings
Create Date: 2026-02-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = 'add_shadow_users'
down_revision = 'add_embeddings'
branch_labels = None
depends_on = None


def column_exists(table_name, column_name):
    """Check if a column exists in a table."""
    conn = op.get_bind()
    result = conn.execute(text(
        f"SELECT EXISTS (SELECT 1 FROM information_schema.columns "
        f"WHERE table_name = '{table_name}' AND column_name = '{column_name}')"
    ))
    return result.scalar()


def index_exists(index_name):
    """Check if an index exists."""
    conn = op.get_bind()
    result = conn.execute(text(
        f"SELECT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = '{index_name}')"
    ))
    return result.scalar()


def constraint_exists(constraint_name):
    """Check if a constraint exists."""
    conn = op.get_bind()
    result = conn.execute(text(
        f"SELECT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '{constraint_name}')"
    ))
    return result.scalar()


def upgrade():
    # Add is_shadow column (if not exists)
    if not column_exists('users', 'is_shadow'):
        op.add_column('users', sa.Column('is_shadow', sa.Boolean(), nullable=False, server_default='false'))
        op.alter_column('users', 'is_shadow', server_default=None)

    # Add shadow_owner_id column (if not exists)
    if not column_exists('users', 'shadow_owner_id'):
        op.add_column('users', sa.Column('shadow_owner_id', sa.Integer(), nullable=True))

    # Add foreign key constraint (if not exists)
    if not constraint_exists('fk_users_shadow_owner_id'):
        op.create_foreign_key(
            'fk_users_shadow_owner_id',
            'users', 'users',
            ['shadow_owner_id'], ['id'],
            ondelete='SET NULL'
        )

    # Add index for fast filtering of shadow users (if not exists)
    if not index_exists('ix_users_is_shadow'):
        op.create_index('ix_users_is_shadow', 'users', ['is_shadow'])


def downgrade():
    # Drop index (if exists)
    if index_exists('ix_users_is_shadow'):
        op.drop_index('ix_users_is_shadow', table_name='users')

    # Drop foreign key (if exists)
    if constraint_exists('fk_users_shadow_owner_id'):
        op.drop_constraint('fk_users_shadow_owner_id', 'users', type_='foreignkey')

    # Drop columns (if exist)
    if column_exists('users', 'shadow_owner_id'):
        op.drop_column('users', 'shadow_owner_id')
    if column_exists('users', 'is_shadow'):
        op.drop_column('users', 'is_shadow')
