"""Add form templates and submissions tables

Creates:
- form_templates: Custom form templates created by recruiters
- form_submissions: Candidate submissions of forms

Revision ID: add_form_templates
Revises: 8e2df4526551
Create Date: 2026-04-03
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_form_templates'
down_revision = '8e2df4526551'
branch_labels = None
depends_on = None


def table_exists(table_name):
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables WHERE table_name = :table"
    ), {"table": table_name})
    return result.fetchone() is not None


def upgrade() -> None:
    if not table_exists("form_templates"):
        op.create_table(
            "form_templates",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("vacancy_id", sa.Integer(), sa.ForeignKey("vacancies.id", ondelete="SET NULL"), nullable=True, index=True),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("title", sa.String(300), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("slug", sa.String(100), unique=True, nullable=False),
            sa.Column("is_active", sa.Boolean(), server_default="true"),
            sa.Column("fields", sa.JSON(), server_default="[]"),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        )

    if not table_exists("form_submissions"):
        op.create_table(
            "form_submissions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("form_id", sa.Integer(), sa.ForeignKey("form_templates.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("entity_id", sa.Integer(), sa.ForeignKey("entities.id", ondelete="SET NULL"), nullable=True, index=True),
            sa.Column("data", sa.JSON(), nullable=False),
            sa.Column("submitted_at", sa.DateTime(), server_default=sa.func.now()),
        )


def downgrade() -> None:
    op.drop_table("form_submissions")
    op.drop_table("form_templates")
