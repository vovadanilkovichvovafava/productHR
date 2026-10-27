"""Add project prefix and task sequential numbers

Adds:
- projects.prefix (short code like "PM", "HR")
- projects.task_counter (auto-increment for task numbers)
- project_tasks.task_number (sequential number within project)

Revision ID: add_task_keys
Revises: add_projects_module
Create Date: 2026-03-31
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_task_keys'
down_revision = 'add_projects_module'
branch_labels = None
depends_on = None


def column_exists(table, column):
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns WHERE table_name = :table AND column_name = :column"
    ), {"table": table, "column": column})
    return result.fetchone() is not None


def upgrade():
    if not column_exists('projects', 'prefix'):
        op.add_column('projects', sa.Column('prefix', sa.String(10), nullable=True))
    if not column_exists('projects', 'task_counter'):
        op.add_column('projects', sa.Column('task_counter', sa.Integer(), server_default='0'))
    if not column_exists('project_tasks', 'task_number'):
        op.add_column('project_tasks', sa.Column('task_number', sa.Integer(), nullable=True))


def downgrade():
    op.drop_column('project_tasks', 'task_number')
    op.drop_column('projects', 'task_counter')
    op.drop_column('projects', 'prefix')
