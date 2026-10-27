"""Add SUB_ADMIN role to UserRole enum

Revision ID: add_sub_admin_to_userrole
Revises: add_sub_admin_role
Create Date: 2025-12-24

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_sub_admin_to_userrole'
down_revision = 'add_sub_admin_role'
branch_labels = None
depends_on = None


def upgrade():
    """Add 'sub_admin' value to userrole enum type."""
    # PostgreSQL ALTER TYPE ADD VALUE cannot run inside a transaction block
    # We need to use execute with proper connection handling
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'sub_admin'")


def downgrade():
    """Downgrade is not supported for enum values in PostgreSQL.

    Removing enum values is complex and risky in PostgreSQL as it requires:
    1. Creating a new enum type without the value
    2. Updating all columns to use the new type
    3. Dropping the old type
    4. Renaming the new type

    This is generally not recommended in production. If downgrade is needed,
    manually update any users with role='sub_admin' to 'admin',
    then follow the above steps.
    """
    # Downgrade not supported - enum value removal is complex in PostgreSQL
    pass
