"""Add form_dispatches table and form_submissions.dispatch_id

Revision ID: add_form_dispatches
Revises: merge_heads_2026_06_17
Create Date: 2026-06-17
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_form_dispatches'
down_revision = 'merge_heads_2026_06_17'
branch_labels = None
depends_on = None


def table_exists(name):
    conn = op.get_bind()
    r = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables WHERE table_name = :t"), {"t": name})
    return r.fetchone() is not None


def column_exists(table, column):
    conn = op.get_bind()
    r = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns WHERE table_name = :t AND column_name = :c"),
        {"t": table, "c": column})
    return r.fetchone() is not None


def upgrade() -> None:
    if not table_exists("form_dispatches"):
        op.create_table(
            "form_dispatches",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("form_id", sa.Integer(), sa.ForeignKey("form_templates.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("entity_id", sa.Integer(), sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("token", sa.String(64), unique=True, nullable=False, index=True),
            sa.Column("status", sa.String(20), server_default="sent"),
            sa.Column("submission_id", sa.Integer(), sa.ForeignKey("form_submissions.id", ondelete="SET NULL", use_alter=True), nullable=True),
            sa.Column("seen_by_recruiter", sa.Boolean(), server_default="false"),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("opened_at", sa.DateTime(), nullable=True),
            sa.Column("submitted_at", sa.DateTime(), nullable=True),
        )
    if not column_exists("form_submissions", "dispatch_id"):
        op.add_column("form_submissions", sa.Column("dispatch_id", sa.Integer(),
                      sa.ForeignKey("form_dispatches.id", ondelete="SET NULL"), nullable=True))


def downgrade() -> None:
    if column_exists("form_submissions", "dispatch_id"):
        op.drop_column("form_submissions", "dispatch_id")
    if table_exists("form_dispatches"):
        op.drop_table("form_dispatches")
