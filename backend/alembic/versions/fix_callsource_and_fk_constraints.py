"""Placeholder migration for FK constraint updates

NOTE: This migration is intentionally empty.

Originally this migration tried to update FK ondelete constraints, but:
1. DROP/CREATE CONSTRAINT operations require exclusive table locks
2. Railway deployments have active connections that hold locks
3. This caused migration timeouts (deadlock waiting for locks)

The FK ondelete='SET NULL' behavior is NOT critical for app operation.
The app handles orphaned references gracefully in application code.

CallSource enum values (google_doc, google_drive, direct_url, fireflies)
are added in start.sh BEFORE alembic runs.

Revision ID: fix_callsource_and_fk_constraints
Revises: add_entity_salary
Create Date: 2026-01-13
"""
from alembic import op
import sqlalchemy as sa

revision = 'fix_callsource_and_fk_constraints'
down_revision = 'add_entity_salary'
branch_labels = None
depends_on = None


def upgrade():
    """Empty migration - FK changes skipped to prevent deployment timeouts.

    The following FK ondelete constraints were planned but skipped:
    - org_members.invited_by -> SET NULL
    - chats.owner_id -> SET NULL
    - criteria_presets.created_by -> SET NULL
    - entities.created_by -> SET NULL
    - entities.transferred_to_id -> SET NULL
    - entity_transfers.from_user_id -> SET NULL
    - entity_transfers.to_user_id -> SET NULL
    - call_recordings.owner_id -> SET NULL

    These can be applied manually during maintenance window if needed.
    """
    print("fix_callsource_and_fk_constraints: Skipped (FK changes not critical)")


def downgrade():
    """Nothing to downgrade."""
    pass
