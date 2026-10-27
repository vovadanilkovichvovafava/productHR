"""Add has_full_access column to org_members

This column allows admins to grant full database access to participants
without making them organization admins.

Revision ID: add_has_full_access
Revises: add_vacancy_sharing
Create Date: 2026-01-21
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_has_full_access'
down_revision = 'add_vacancy_sharing'
branch_labels = None
depends_on = None


def column_exists(table_name, column_name):
    """Check if a column exists in a table."""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_name = :table AND column_name = :column
        """
    ), {"table": table_name, "column": column_name})
    return result.fetchone() is not None


def upgrade():
    """Add has_full_access column to org_members."""

    if not column_exists('org_members', 'has_full_access'):
        op.add_column('org_members', sa.Column(
            'has_full_access',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('false')
        ))

        # Create index for fast lookups
        op.create_index(
            'ix_org_members_has_full_access',
            'org_members',
            ['has_full_access']
        )


def downgrade():
    """Remove has_full_access column."""

    op.drop_index('ix_org_members_has_full_access', table_name='org_members')
    op.drop_column('org_members', 'has_full_access')
