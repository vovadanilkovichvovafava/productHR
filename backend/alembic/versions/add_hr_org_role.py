"""Add 'hr' value to orgrole enum

Revision ID: b5e2a1d3c908
Revises: a3f7c9e1b204
Create Date: 2026-04-06
"""
from alembic import op

revision = 'b5e2a1d3c908'
down_revision = 'a3f7c9e1b204'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add 'hr' to the orgrole PostgreSQL enum type
    op.execute("ALTER TYPE orgrole ADD VALUE IF NOT EXISTS 'hr' AFTER 'admin'")


def downgrade() -> None:
    # PostgreSQL doesn't support removing enum values easily
    # Would need to recreate the type which is complex and risky
    pass
