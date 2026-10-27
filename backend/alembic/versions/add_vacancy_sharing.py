"""Add vacancy sharing support to shared_access

Adds:
- vacancy_id column to shared_access table
- vacancy to resourcetype enum

Revision ID: add_vacancy_sharing
Revises: force_add_entity_status_hr
Create Date: 2026-01-21
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_vacancy_sharing'
down_revision = 'force_add_entity_status_hr'
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


def enum_value_exists(enum_name, value):
    """Check if a value exists in an enum."""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        """
        SELECT 1 FROM pg_enum e
        JOIN pg_type t ON e.enumtypid = t.oid
        WHERE t.typname = :enum_name AND e.enumlabel = :value
        """
    ), {"enum_name": enum_name, "value": value})
    return result.fetchone() is not None


def upgrade():
    """Add vacancy sharing support."""

    # Add 'vacancy' to resourcetype enum if not exists
    if not enum_value_exists('resourcetype', 'vacancy'):
        op.execute("ALTER TYPE resourcetype ADD VALUE IF NOT EXISTS 'vacancy'")

    # Add vacancy_id column to shared_access if not exists
    if not column_exists('shared_access', 'vacancy_id'):
        op.add_column('shared_access', sa.Column(
            'vacancy_id',
            sa.Integer(),
            sa.ForeignKey('vacancies.id', ondelete='CASCADE'),
            nullable=True
        ))

        # Create index for vacancy_id
        op.create_index(
            'ix_shared_access_vacancy_id',
            'shared_access',
            ['vacancy_id']
        )


def downgrade():
    """Remove vacancy sharing support."""

    # Drop index
    op.drop_index('ix_shared_access_vacancy_id', table_name='shared_access')

    # Drop column
    op.drop_column('shared_access', 'vacancy_id')

    # Note: Cannot remove enum value easily, leaving it
