"""Add project_status_defs table for custom project statuses per organization

Revision ID: add_project_status_defs
Revises: add_projects_module
Create Date: 2026-04-01
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_project_status_defs'
down_revision = 'add_projects_module'
branch_labels = None
depends_on = None


def table_exists(table_name):
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables WHERE table_name = :table"
    ), {"table": table_name})
    return result.fetchone() is not None


def upgrade():
    if not table_exists('project_status_defs'):
        op.create_table(
            'project_status_defs',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('org_id', sa.Integer(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
            sa.Column('name', sa.String(100), nullable=False),
            sa.Column('slug', sa.String(100), nullable=False),
            sa.Column('color', sa.String(20), server_default='#6366f1'),
            sa.Column('sort_order', sa.Integer(), server_default='0'),
            sa.Column('is_done', sa.Boolean(), server_default='false'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.UniqueConstraint('org_id', 'slug', name='uq_project_status_def_slug'),
            sa.Index('ix_psd_org_sort', 'org_id', 'sort_order'),
        )
        op.create_index('ix_project_status_defs_org_id', 'project_status_defs', ['org_id'])


def downgrade():
    if table_exists('project_status_defs'):
        op.drop_table('project_status_defs')
