"""Add 'hr' value to orgrole PostgreSQL enum

The Python OrgRole enum has 'hr' but the PostgreSQL enum was never updated.

Revision ID: add_hr_orgrole_001
Revises:
Create Date: 2026-04-13
"""
from alembic import op

revision = 'add_hr_orgrole_001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add 'hr' to the orgrole enum type in PostgreSQL
    op.execute("ALTER TYPE orgrole ADD VALUE IF NOT EXISTS 'hr'")


def downgrade() -> None:
    # Cannot remove enum values in PostgreSQL without recreating the type
    pass
