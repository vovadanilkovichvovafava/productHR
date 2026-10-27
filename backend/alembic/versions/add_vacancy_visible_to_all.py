"""Add visible_to_all column to vacancies table

Allows vacancy creators to mark a vacancy as visible to all members
of the organization, not just their department.

Revision ID: add_vacancy_visible_to_all
Revises: add_has_full_access
Create Date: 2026-03-12
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_vacancy_visible_to_all'
down_revision = 'add_has_full_access'
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
    if not column_exists('vacancies', 'visible_to_all'):
        op.add_column('vacancies', sa.Column(
            'visible_to_all',
            sa.Boolean(),
            server_default='false',
            nullable=False
        ))


def downgrade():
    if column_exists('vacancies', 'visible_to_all'):
        op.drop_column('vacancies', 'visible_to_all')
