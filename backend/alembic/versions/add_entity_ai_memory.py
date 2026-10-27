"""Add AI long-term memory fields to Entity

Adds:
- ai_summary: Auto-updated summary of all interactions
- ai_summary_updated_at: When summary was last updated
- key_events: JSON array of key milestones

Revision ID: add_entity_ai_memory
Revises: add_entity_multiple_ids
Create Date: 2025-12-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'add_entity_ai_memory'
down_revision = 'add_entity_multiple_ids'
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
    # Add AI long-term memory columns
    if not column_exists('entities', 'ai_summary'):
        op.add_column('entities', sa.Column('ai_summary', sa.Text(), nullable=True))
    if not column_exists('entities', 'ai_summary_updated_at'):
        op.add_column('entities', sa.Column('ai_summary_updated_at', sa.DateTime(), nullable=True))
    if not column_exists('entities', 'key_events'):
        op.add_column('entities', sa.Column('key_events', postgresql.JSON(astext_type=sa.Text()), nullable=True))

    # Set default empty array for key_events
    op.execute("UPDATE entities SET key_events = '[]'::jsonb WHERE key_events IS NULL")


def downgrade():
    op.drop_column('entities', 'key_events')
    op.drop_column('entities', 'ai_summary_updated_at')
    op.drop_column('entities', 'ai_summary')
