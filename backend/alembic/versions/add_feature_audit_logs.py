"""Add feature_audit_logs table for tracking feature access changes

Creates:
- feature_audit_logs: Audit trail for feature access control changes

Revision ID: add_feature_audit_logs
Revises: fix_callsource_and_fk_constraints
Create Date: 2026-01-13
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_feature_audit_logs'
down_revision = 'add_refresh_tokens'
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
    """Create feature_audit_logs table."""

    if not table_exists('feature_audit_logs'):
        op.create_table(
            'feature_audit_logs',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('org_id', sa.Integer(), nullable=False),
            sa.Column('changed_by', sa.Integer(), nullable=True),
            sa.Column('feature_name', sa.String(50), nullable=False),
            sa.Column('action', sa.String(20), nullable=False),  # 'enable', 'disable', 'delete'
            sa.Column('department_id', sa.Integer(), nullable=True),
            sa.Column('old_value', sa.Boolean(), nullable=True),
            sa.Column('new_value', sa.Boolean(), nullable=True),
            sa.Column('details', sa.JSON(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['changed_by'], ['users.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['department_id'], ['departments.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_feature_audit_logs_org_id', 'feature_audit_logs', ['org_id'])
        op.create_index('ix_feature_audit_logs_changed_by', 'feature_audit_logs', ['changed_by'])
        op.create_index('ix_feature_audit_logs_created_at', 'feature_audit_logs', ['created_at'])
        op.create_index('ix_feature_audit_logs_lookup', 'feature_audit_logs', ['org_id', 'feature_name', 'created_at'])


def downgrade():
    """Remove feature_audit_logs table."""
    op.drop_table('feature_audit_logs')
