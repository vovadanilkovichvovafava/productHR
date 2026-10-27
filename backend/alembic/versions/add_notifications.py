"""Add notifications table

Creates:
- notifications: In-app notifications for users

Revision ID: add_notifications
Revises: add_saturn_integration
Create Date: 2026-04-01
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_notifications'
down_revision = 'add_saturn_integration'
branch_labels = None
depends_on = None


def table_exists(table_name):
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables WHERE table_name = :table"
    ), {"table": table_name})
    return result.fetchone() is not None


def upgrade() -> None:
    if not table_exists("notifications"):
        op.create_table(
            "notifications",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("type", sa.String(50), nullable=False),
            sa.Column("title", sa.String(300), nullable=False),
            sa.Column("message", sa.Text(), nullable=True),
            sa.Column("link", sa.String(500), nullable=True),
            sa.Column("is_read", sa.Boolean(), server_default="false"),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        )


def downgrade() -> None:
    op.drop_table("notifications")
