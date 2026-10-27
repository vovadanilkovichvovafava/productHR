"""Add version field to Entity for optimistic locking

Adds:
- version: Integer field for optimistic locking (concurrent edit detection)

Revision ID: add_entity_version
Revises: add_entity_ai_memory
Create Date: 2025-01-14
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_entity_version'
down_revision = 'add_entity_ai_memory'
branch_labels = None
depends_on = None


def column_exists(table_name, column_name):
    """Check if a column exists in the table."""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns WHERE table_name = :table AND column_name = :column"
    ), {"table": table_name, "column": column_name})
    return result.fetchone() is not None


def upgrade():
    # Add version column for optimistic locking
    if not column_exists('entities', 'version'):
        op.add_column('entities', sa.Column('version', sa.Integer(), nullable=False, server_default='1'))

    # Set default value for existing rows
    op.execute("UPDATE entities SET version = 1 WHERE version IS NULL")


def downgrade():
    op.drop_column('entities', 'version')
