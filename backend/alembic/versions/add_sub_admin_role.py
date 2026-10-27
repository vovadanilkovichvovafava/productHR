"""Add SUB_ADMIN role to DeptRole enum

Revision ID: add_sub_admin_role
Revises: add_user_security_cols
Create Date: 2025-12-24

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_sub_admin_role'
down_revision = 'add_user_security_cols'
branch_labels = None
depends_on = None


def upgrade():
    """Add 'sub_admin' value to deptrole enum type."""
    # PostgreSQL ALTER TYPE ADD VALUE cannot run inside a transaction block
    # We need to use execute with proper connection handling
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE deptrole ADD VALUE IF NOT EXISTS 'sub_admin'")


def downgrade():
    """Downgrade is not supported for enum values in PostgreSQL.

    Removing enum values is complex and risky in PostgreSQL as it requires:
    1. Creating a new enum type without the value
    2. Updating all columns to use the new type
    3. Dropping the old type
    4. Renaming the new type

    This is generally not recommended in production. If downgrade is needed,
    manually update any department_members with role='sub_admin' to 'member',
    then follow the above steps.
    """
    # Downgrade not supported - enum value removal is complex in PostgreSQL
    pass
