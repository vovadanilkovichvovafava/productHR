"""Add custom roles and permissions system

Revision ID: add_custom_roles
Revises: add_constraints_and_indexes
Create Date: 2025-12-27

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'add_custom_roles'
down_revision = 'add_constraints_and_indexes'
branch_labels = None
depends_on = None


def table_exists(table_name):
    """Check if table exists in database."""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables WHERE table_name = :table"
    ), {"table": table_name})
    return result.fetchone() is not None


def upgrade():
    """Create tables for custom roles and permissions system."""

    if table_exists('custom_roles'):
        return  # Already migrated

    # Create custom_roles table
    op.create_table(
        'custom_roles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(50), nullable=False),
        sa.Column('description', sa.String(255), nullable=True),
        sa.Column('base_role', sa.String(20), nullable=False),
        sa.Column('org_id', sa.Integer(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=True),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', 'org_id', name='uq_custom_role_name_org')
    )
    op.create_index('ix_custom_roles_org_id', 'custom_roles', ['org_id'])
    op.create_index('ix_custom_roles_base_role', 'custom_roles', ['base_role'])

    # Create role_permission_overrides table
    op.create_table(
        'role_permission_overrides',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('role_id', sa.Integer(), nullable=False),
        sa.Column('permission', sa.String(50), nullable=False),
        sa.Column('allowed', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['role_id'], ['custom_roles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('role_id', 'permission', name='uq_role_permission')
    )
    op.create_index('ix_role_permission_overrides_role_id', 'role_permission_overrides', ['role_id'])

    # Create permission_audit_logs table
    op.create_table(
        'permission_audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('changed_by', sa.Integer(), nullable=True),
        sa.Column('role_id', sa.Integer(), nullable=True),
        sa.Column('action', sa.String(20), nullable=False),
        sa.Column('permission', sa.String(50), nullable=True),
        sa.Column('old_value', sa.Boolean(), nullable=True),
        sa.Column('new_value', sa.Boolean(), nullable=True),
        sa.Column('details', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['changed_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['role_id'], ['custom_roles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_permission_audit_logs_changed_by', 'permission_audit_logs', ['changed_by'])
    op.create_index('ix_permission_audit_logs_created_at', 'permission_audit_logs', ['created_at'])

    # Create user_custom_roles table
    op.create_table(
        'user_custom_roles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('role_id', sa.Integer(), nullable=False),
        sa.Column('assigned_by', sa.Integer(), nullable=True),
        sa.Column('assigned_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['role_id'], ['custom_roles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['assigned_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'role_id', name='uq_user_custom_role')
    )
    op.create_index('ix_user_custom_roles_user_id', 'user_custom_roles', ['user_id'])
    op.create_index('ix_user_custom_roles_role_id', 'user_custom_roles', ['role_id'])


def downgrade():
    """Remove custom roles tables."""
    op.drop_table('user_custom_roles')
    op.drop_table('permission_audit_logs')
    op.drop_table('role_permission_overrides')
    op.drop_table('custom_roles')
