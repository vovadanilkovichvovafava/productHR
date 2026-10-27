"""Add project task statuses table

Creates:
- project_task_statuses: Custom task status definitions per project

Revision ID: add_project_task_statuses
Revises: add_projects_module
Create Date: 2026-03-31
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_project_task_statuses'
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
    if not table_exists('project_task_statuses'):
        op.create_table(
            'project_task_statuses',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
            sa.Column('name', sa.String(100), nullable=False),
            sa.Column('slug', sa.String(100), nullable=False),
            sa.Column('color', sa.String(20), server_default='#6366f1'),
            sa.Column('sort_order', sa.Integer(), server_default='0'),
            sa.Column('is_done', sa.Boolean(), server_default='false'),
            sa.Column('is_default', sa.Boolean(), server_default='false'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.UniqueConstraint('project_id', 'slug', name='uq_project_status_slug'),
        )
        op.create_index('ix_pts_project_id', 'project_task_statuses', ['project_id'])
        op.create_index('ix_pts_project_sort', 'project_task_statuses', ['project_id', 'sort_order'])


def downgrade():
    op.drop_table('project_task_statuses')
