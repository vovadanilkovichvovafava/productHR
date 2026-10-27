"""Add entity_type field to CriteriaPreset

Adds:
- entity_type: EntityType enum field for type-specific entity criteria presets

Revision ID: add_entity_type_criteria
Revises: add_entity_version
Create Date: 2025-01-14
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_entity_type_criteria'
down_revision = 'add_entity_version'
branch_labels = None
depends_on = None


def column_exists(table_name, column_name):
    """Check if a column exists in the table."""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns WHERE table_name = :table AND column_name = :column"
    ), {"table": table_name, "column": column_name})
    return result.fetchone() is not None


def index_exists(index_name):
    """Check if an index exists."""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM pg_indexes WHERE indexname = :index_name"
    ), {"index_name": index_name})
    return result.fetchone() is not None


def upgrade():
    # Add entity_type column to criteria_presets
    if not column_exists('criteria_presets', 'entity_type'):
        # First, ensure the entitytype enum exists
        conn = op.get_bind()
        result = conn.execute(sa.text(
            "SELECT 1 FROM pg_type WHERE typname = 'entitytype'"
        ))
        if result.fetchone() is None:
            # Create enum if it doesn't exist
            op.execute("CREATE TYPE entitytype AS ENUM ('candidate', 'client', 'contractor', 'lead', 'partner', 'custom')")

        # Add the column
        op.add_column('criteria_presets',
            sa.Column('entity_type',
                sa.Enum('candidate', 'client', 'contractor', 'lead', 'partner', 'custom', name='entitytype'),
                nullable=True
            )
        )

    # Add index for entity_type
    if not index_exists('ix_criteria_presets_entity_type'):
        op.create_index('ix_criteria_presets_entity_type', 'criteria_presets', ['entity_type'])


def downgrade():
    # Drop index
    op.drop_index('ix_criteria_presets_entity_type', table_name='criteria_presets')

    # Drop column
    op.drop_column('criteria_presets', 'entity_type')
