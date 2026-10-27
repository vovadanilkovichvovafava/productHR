"""Add prometheus_review_cache table

Stores AI-generated Prometheus detailed reviews per contact (entity)
so that repeated visits to the Prometheus tab do not re-trigger
Claude AI generation.  Regeneration is done manually via force=true.

Revision ID: add_prometheus_review_cache
Revises: add_email_templates_analytics
Create Date: 2026-02-24
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_prometheus_review_cache'
down_revision = 'add_email_templates_analytics'
branch_labels = None
depends_on = None


def table_exists(table_name):
    """Check if a table exists."""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_name = :table
        """
    ), {"table": table_name})
    return result.fetchone() is not None


def upgrade():
    """Create prometheus_review_cache table."""
    if table_exists('prometheus_review_cache'):
        return

    op.create_table(
        'prometheus_review_cache',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('entity_id', sa.Integer(),
                  sa.ForeignKey('entities.id', ondelete='CASCADE'),
                  nullable=False, unique=True),
        sa.Column('review_data', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(),
                  onupdate=sa.func.now()),
    )

    op.create_index(
        'ix_prometheus_review_cache_entity_id',
        'prometheus_review_cache',
        ['entity_id'],
        unique=True,
    )


def downgrade():
    """Drop prometheus_review_cache table."""
    op.drop_index('ix_prometheus_review_cache_entity_id',
                  table_name='prometheus_review_cache')
    op.drop_table('prometheus_review_cache')
