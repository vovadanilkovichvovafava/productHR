"""Add Saturn integration tables

Creates:
- saturn_projects: Synced projects from Saturn (Coolify)
- saturn_applications: Synced applications from Saturn
- saturn_sync_logs: Sync history and error tracking

Revision ID: add_saturn_integration
Revises: add_project_task_statuses
Create Date: 2026-03-31
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_saturn_integration'
down_revision = 'add_project_task_statuses'
branch_labels = None
depends_on = None


def table_exists(table_name):
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables WHERE table_name = :table"
    ), {"table": table_name})
    return result.fetchone() is not None


def upgrade() -> None:
    if not table_exists("saturn_projects"):
        op.create_table(
            "saturn_projects",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("saturn_uuid", sa.String(100), unique=True, nullable=False, index=True),
            sa.Column("saturn_id", sa.Integer(), nullable=True),
            sa.Column("name", sa.String(300), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("is_archived", sa.Boolean(), server_default="false"),
            sa.Column("enceladus_project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True),
            sa.Column("last_synced_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        )

    if not table_exists("saturn_applications"):
        op.create_table(
            "saturn_applications",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("saturn_uuid", sa.String(100), unique=True, nullable=False, index=True),
            sa.Column("saturn_project_id", sa.Integer(), sa.ForeignKey("saturn_projects.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("name", sa.String(300), nullable=False),
            sa.Column("fqdn", sa.String(500), nullable=True),
            sa.Column("status", sa.String(100), nullable=True),
            sa.Column("build_pack", sa.String(50), nullable=True),
            sa.Column("git_repository", sa.String(500), nullable=True),
            sa.Column("git_branch", sa.String(200), nullable=True),
            sa.Column("environment_name", sa.String(100), nullable=True),
            sa.Column("last_synced_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        )

    if not table_exists("saturn_sync_logs"):
        op.create_table(
            "saturn_sync_logs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("sync_type", sa.String(20), nullable=False),
            sa.Column("projects_synced", sa.Integer(), server_default="0"),
            sa.Column("apps_synced", sa.Integer(), server_default="0"),
            sa.Column("errors", sa.JSON(), server_default="[]"),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        )


def downgrade() -> None:
    op.drop_table("saturn_sync_logs")
    op.drop_table("saturn_applications")
    op.drop_table("saturn_projects")
