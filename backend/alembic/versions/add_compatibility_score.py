"""Add compatibility_score to vacancy_applications

Adds:
- compatibility_score: JSON column for AI-calculated candidate-vacancy compatibility

Revision ID: add_compatibility_score
Revises: add_feature_audit_logs
Create Date: 2026-01-13
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_compatibility_score'
down_revision = 'add_feature_audit_logs'
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
    """Add compatibility_score column to vacancy_applications."""
    if not column_exists('vacancy_applications', 'compatibility_score'):
        op.add_column(
            'vacancy_applications',
            sa.Column('compatibility_score', sa.JSON(), nullable=True)
        )


def downgrade():
    """Remove compatibility_score column from vacancy_applications."""
    if column_exists('vacancy_applications', 'compatibility_score'):
        op.drop_column('vacancy_applications', 'compatibility_score')
