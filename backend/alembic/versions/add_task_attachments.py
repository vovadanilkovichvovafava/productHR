"""Add task attachments table

Creates:
- task_attachments: File attachments on project tasks

Revision ID: add_task_attachments
Revises: add_projects_module
Create Date: 2026-03-31
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_task_attachments'
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
    if not table_exists('task_attachments'):
        op.create_table(
            'task_attachments',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('task_id', sa.Integer(), sa.ForeignKey('project_tasks.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('filename', sa.String(500), nullable=False),
            sa.Column('original_filename', sa.String(500), nullable=False),
            sa.Column('file_size', sa.Integer(), nullable=False),
            sa.Column('content_type', sa.String(200), nullable=True),
            sa.Column('storage_path', sa.String(1000), nullable=False),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        )


def downgrade():
    if table_exists('task_attachments'):
        op.drop_table('task_attachments')
