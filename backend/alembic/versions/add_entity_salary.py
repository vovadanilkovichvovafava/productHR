"""Add expected salary fields to entities table

Adds:
- expected_salary_min: Minimum expected salary
- expected_salary_max: Maximum expected salary
- expected_salary_currency: Currency code (default: RUB)

Revision ID: add_entity_salary
Revises: add_department_features
Create Date: 2026-01-13
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_entity_salary'
down_revision = 'add_department_features'
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
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
    """Add expected salary columns to entities table."""
    # Add expected_salary_min column
    if not column_exists('entities', 'expected_salary_min'):
        op.add_column(
            'entities',
            sa.Column('expected_salary_min', sa.Integer(), nullable=True)
        )

    # Add expected_salary_max column
    if not column_exists('entities', 'expected_salary_max'):
        op.add_column(
            'entities',
            sa.Column('expected_salary_max', sa.Integer(), nullable=True)
        )

    # Add expected_salary_currency column with default 'RUB'
    if not column_exists('entities', 'expected_salary_currency'):
        op.add_column(
            'entities',
            sa.Column('expected_salary_currency', sa.String(10), server_default='RUB', nullable=True)
        )


def downgrade():
    """Remove expected salary columns from entities table."""
    op.drop_column('entities', 'expected_salary_currency')
    op.drop_column('entities', 'expected_salary_max')
    op.drop_column('entities', 'expected_salary_min')
