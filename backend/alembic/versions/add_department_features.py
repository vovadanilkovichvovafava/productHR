"""Add department_features table for feature access control

Creates:
- department_features: Controls which features are available to which departments

Revision ID: add_department_features
Revises: add_vacancies
Create Date: 2026-01-13
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_department_features'
down_revision = 'add_entity_files'  # Fixed: was add_vacancies, now follows add_entity_files
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
    """Create department_features table."""

    # Create department_features table
    if not table_exists('department_features'):
        op.create_table(
            'department_features',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('org_id', sa.Integer(), nullable=False),
            sa.Column('department_id', sa.Integer(), nullable=True),
            sa.Column('feature_name', sa.String(50), nullable=False),
            sa.Column('enabled', sa.Boolean(), server_default='true'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['department_id'], ['departments.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('org_id', 'department_id', 'feature_name', name='uq_dept_feature')
        )
        op.create_index('ix_department_features_org_id', 'department_features', ['org_id'])
        op.create_index('ix_department_features_department_id', 'department_features', ['department_id'])
        op.create_index('ix_department_features_lookup', 'department_features', ['org_id', 'feature_name'])


def downgrade():
    """Remove department_features table."""
    op.drop_table('department_features')
