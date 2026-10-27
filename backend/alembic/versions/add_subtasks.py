"""Add subtasks support (parent_task_id) to project_tasks

Revision ID: add_subtasks
Revises: add_projects_module
Create Date: 2026-03-31
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_subtasks'
down_revision = 'add_projects_module'
branch_labels = None
depends_on = None


def column_exists(table_name, column_name):
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns WHERE table_name = :table AND column_name = :col"
    ), {"table": table_name, "col": column_name})
    return result.fetchone() is not None


def index_exists(index_name):
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM pg_indexes WHERE indexname = :idx"
    ), {"idx": index_name})
    return result.fetchone() is not None


def upgrade():
    if not column_exists("project_tasks", "parent_task_id"):
        op.add_column("project_tasks", sa.Column(
            "parent_task_id", sa.Integer(),
            sa.ForeignKey("project_tasks.id", ondelete="CASCADE"),
            nullable=True,
        ))

    if not index_exists("ix_task_parent"):
        op.create_index("ix_task_parent", "project_tasks", ["parent_task_id"])


def downgrade():
    if index_exists("ix_task_parent"):
        op.drop_index("ix_task_parent", table_name="project_tasks")
    if column_exists("project_tasks", "parent_task_id"):
        op.drop_column("project_tasks", "parent_task_id")
