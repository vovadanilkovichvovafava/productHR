"""Add impersonation logs table

Revision ID: add_impersonation_logs
Revises: add_entity_transfer_tracking
Create Date: 2024-12-24

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_impersonation_logs'
down_revision = 'add_entity_transfer'
branch_labels = None
depends_on = None


def table_exists(table_name):
    """Check if a table exists."""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables WHERE table_name = :table"
    ), {"table": table_name})
    return result.fetchone() is not None


def index_exists(index_name):
    """Check if an index exists."""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM pg_indexes WHERE indexname = :index_name"
    ), {"index_name": index_name})
    return result.fetchone() is not None


def upgrade():
    if not table_exists('impersonation_logs'):
        op.create_table(
            'impersonation_logs',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('superadmin_id', sa.Integer(), nullable=False),
            sa.Column('impersonated_user_id', sa.Integer(), nullable=False),
            sa.Column('started_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
            sa.Column('ended_at', sa.DateTime(), nullable=True),
            sa.Column('ip_address', sa.String(45), nullable=True),
            sa.Column('user_agent', sa.String(512), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['superadmin_id'], ['users.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['impersonated_user_id'], ['users.id'], ondelete='CASCADE')
        )
    if not index_exists('ix_impersonation_logs_superadmin_id'):
        op.create_index('ix_impersonation_logs_superadmin_id', 'impersonation_logs', ['superadmin_id'])
    if not index_exists('ix_impersonation_logs_impersonated_user_id'):
        op.create_index('ix_impersonation_logs_impersonated_user_id', 'impersonation_logs', ['impersonated_user_id'])


def downgrade():
    op.drop_index('ix_impersonation_logs_impersonated_user_id', 'impersonation_logs')
    op.drop_index('ix_impersonation_logs_superadmin_id', 'impersonation_logs')
    op.drop_table('impersonation_logs')
