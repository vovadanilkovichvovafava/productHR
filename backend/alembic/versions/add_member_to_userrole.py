"""Add MEMBER role to UserRole enum

Revision ID: add_member_to_userrole
Revises: add_custom_roles
Create Date: 2025-12-27

This migration adds the 'member' role to the UserRole enum.
Regular users should have this role instead of 'admin'.
Access is determined by OrgRole and DeptRole memberships.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_member_to_userrole'
down_revision = 'add_custom_roles'
branch_labels = None
depends_on = None


def upgrade():
    """Add 'member' value to userrole enum type."""
    # PostgreSQL ALTER TYPE ADD VALUE cannot run inside a transaction block
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'member'")


def downgrade():
    """Downgrade is not supported for enum values in PostgreSQL.

    Removing enum values is complex in PostgreSQL. If downgrade is needed,
    manually update users with role='member' to 'admin' first.
    """
    pass
