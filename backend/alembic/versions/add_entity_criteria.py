"""Add entity_criteria table

Adds entity_criteria table for storing evaluation criteria per entity.

Revision ID: add_entity_criteria
Revises: add_performance_indexes
Create Date: 2025-12-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'add_entity_criteria'
down_revision = 'add_performance_indexes'  # Fixed: was add_member_to_userrole, merged with performance_indexes branch
branch_labels = None
depends_on = None


def table_exists(table_name):
    """Check if a table exists."""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables WHERE table_name = :table"
    ), {"table": table_name})
    return result.fetchone() is not None


def upgrade():
    # Create entity_criteria table if not exists
    if not table_exists('entity_criteria'):
        op.create_table(
            'entity_criteria',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('entity_id', sa.Integer(), nullable=False),
            sa.Column('criteria', postgresql.JSON(astext_type=sa.Text()), nullable=False),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
            sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('entity_id')
        )
        op.create_index(op.f('ix_entity_criteria_entity_id'), 'entity_criteria', ['entity_id'], unique=True)


def downgrade():
    op.drop_index(op.f('ix_entity_criteria_entity_id'), table_name='entity_criteria')
    op.drop_table('entity_criteria')
