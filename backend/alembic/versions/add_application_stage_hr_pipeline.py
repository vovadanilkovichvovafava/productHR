"""Add HR pipeline stages to applicationstage enum

Adds new enum values:
- new: Новый - just added to vacancy (replaces 'applied' as default)
- practice: Практика - practical task/test
- tech_practice: Тех-практика - technical practice
- is_interview: ИС - final interview

Revision ID: add_application_stage_hr_pipeline
Revises: add_entity_status_hr_stages
Create Date: 2026-01-15
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_application_stage_hr_pipeline'
down_revision = 'add_entity_status_hr_stages'
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
    """Add HR pipeline stages to applicationstage enum."""
    # Add 'new' value if not exists
    if not enum_value_exists('applicationstage', 'new'):
        op.execute("ALTER TYPE applicationstage ADD VALUE IF NOT EXISTS 'new'")

    # Add 'practice' value if not exists
    if not enum_value_exists('applicationstage', 'practice'):
        op.execute("ALTER TYPE applicationstage ADD VALUE IF NOT EXISTS 'practice'")

    # Add 'tech_practice' value if not exists
    if not enum_value_exists('applicationstage', 'tech_practice'):
        op.execute("ALTER TYPE applicationstage ADD VALUE IF NOT EXISTS 'tech_practice'")

    # Add 'is_interview' value if not exists
    if not enum_value_exists('applicationstage', 'is_interview'):
        op.execute("ALTER TYPE applicationstage ADD VALUE IF NOT EXISTS 'is_interview'")


def downgrade():
    """Cannot remove enum values in PostgreSQL without recreating the type."""
    # Note: PostgreSQL doesn't support removing enum values
    # To downgrade, you would need to:
    # 1. Create a new enum type without the values
    # 2. Update the column to use the new type
    # 3. Drop the old type
    # This is usually not worth the effort for backwards compatibility
    pass
