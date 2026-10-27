"""Add task_comments table for task comment threads

Revision ID: add_task_comments
Revises: add_projects_module
Create Date: 2026-03-31
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_task_comments'
down_revision = 'add_projects_module'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'task_comments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('task_id', sa.Integer(), sa.ForeignKey('project_tasks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('edited_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_task_comments_task_id', 'task_comments', ['task_id'])
    op.create_index('ix_task_comments_user_id', 'task_comments', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_task_comments_user_id', table_name='task_comments')
    op.drop_index('ix_task_comments_task_id', table_name='task_comments')
    op.drop_table('task_comments')
