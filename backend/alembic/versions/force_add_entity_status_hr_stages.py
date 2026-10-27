"""Force add HR pipeline stages to entitystatus enum

This migration ensures the enum values are added even if previous
migration was marked as completed but didn't actually add them.

Revision ID: force_add_entity_status_hr
Revises: add_application_stage_hr_pipeline
Create Date: 2026-01-20
"""
from alembic import op
import sqlalchemy as sa

revision = 'force_add_entity_status_hr'
down_revision = 'add_application_stage_hr_pipeline'
branch_labels = None
depends_on = None


def enum_value_exists(enum_name: str, value: str) -> bool:
    """Check if a value exists in an enum type."""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        """
        SELECT 1 FROM pg_enum
        WHERE enumlabel = :value
        AND enumtypid = (SELECT oid FROM pg_type WHERE typname = :enum_name)
        """
    ), {"enum_name": enum_name, "value": value})
    return result.fetchone() is not None


def upgrade():
    """Force add HR pipeline stages to entitystatus enum."""
    # Use IF NOT EXISTS to make this idempotent
    # Add 'practice' value
    if not enum_value_exists('entitystatus', 'practice'):
        op.execute(sa.text("ALTER TYPE entitystatus ADD VALUE IF NOT EXISTS 'practice'"))

    # Add 'tech_practice' value
    if not enum_value_exists('entitystatus', 'tech_practice'):
        op.execute(sa.text("ALTER TYPE entitystatus ADD VALUE IF NOT EXISTS 'tech_practice'"))

    # Add 'is_interview' value
    if not enum_value_exists('entitystatus', 'is_interview'):
        op.execute(sa.text("ALTER TYPE entitystatus ADD VALUE IF NOT EXISTS 'is_interview'"))

    # Log what was done
    print("[force_add_entity_status_hr] Checked/added entitystatus enum values: practice, tech_practice, is_interview")


def downgrade():
    """Cannot remove enum values in PostgreSQL without recreating the type."""
    pass
