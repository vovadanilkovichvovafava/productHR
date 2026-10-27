"""Sync Entity.status from VacancyApplication.stage

This migration fixes data inconsistency where Entity.status was out of sync
with VacancyApplication.stage. The root cause was bidirectional sync that
updated ALL applications when Entity.status changed.

The fix:
1. Entity.status no longer syncs TO VacancyApplication.stage
2. VacancyApplication.stage still syncs TO Entity.status (Kanban is source of truth)
3. This migration syncs existing data: sets Entity.status based on the "best" stage
   from all VacancyApplications (highest progress that isn't rejected)

Revision ID: sync_entity_status_001
Revises:
Create Date: 2026-01-18

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session
from datetime import datetime


# revision identifiers, used by Alembic.
revision = 'sync_entity_status_001'
down_revision = ('add_has_full_access', 'add_transfer_cancel_fields')  # Merge two branches
branch_labels = None
depends_on = None


# Stage to status mapping (same as in database.py STAGE_SYNC_MAP)
STAGE_TO_STATUS = {
    'applied': 'new',
    'screening': 'screening',
    'phone_screen': 'practice',
    'interview': 'tech_practice',
    'assessment': 'is_interview',
    'offer': 'offer',
    'hired': 'hired',
    'rejected': 'rejected',
    'withdrawn': 'rejected',  # Map withdrawn to rejected for entity status
}

# Stage priority (higher = more progress)
STAGE_PRIORITY = {
    'applied': 1,
    'screening': 2,
    'phone_screen': 3,
    'interview': 4,
    'assessment': 5,
    'offer': 6,
    'hired': 7,
    'rejected': 0,  # Lowest priority so non-rejected stages win
    'withdrawn': 0,
}


def upgrade() -> None:
    """Sync Entity.status from VacancyApplication.stage.

    For each entity with vacancy applications:
    - If hired in ANY vacancy: status = hired
    - Else if offer in ANY vacancy: status = offer
    - Else: use highest priority non-rejected stage
    - If ALL applications are rejected: status = rejected
    """
    bind = op.get_bind()
    session = Session(bind=bind)

    try:
        # Get all entities that have vacancy applications
        result = session.execute(sa.text("""
            SELECT DISTINCT e.id, e.status as current_status
            FROM entities e
            INNER JOIN vacancy_applications va ON va.entity_id = e.id
            WHERE e.type = 'candidate'
        """))

        entities_to_update = list(result.fetchall())
        print(f"Found {len(entities_to_update)} entities with vacancy applications")

        for entity_id, current_status in entities_to_update:
            # Get all stages for this entity
            stages_result = session.execute(sa.text("""
                SELECT stage FROM vacancy_applications
                WHERE entity_id = :entity_id
            """), {"entity_id": entity_id})

            stages = [row[0] for row in stages_result.fetchall()]

            if not stages:
                continue

            # Determine best status
            # Priority: hired > offer > highest non-rejected stage > rejected
            if 'hired' in stages:
                new_status = 'hired'
            elif 'offer' in stages:
                new_status = 'offer'
            else:
                # Find highest priority non-rejected stage
                non_rejected = [s for s in stages if s not in ('rejected', 'withdrawn')]
                if non_rejected:
                    best_stage = max(non_rejected, key=lambda s: STAGE_PRIORITY.get(s, 0))
                    new_status = STAGE_TO_STATUS.get(best_stage, 'new')
                else:
                    # All rejected
                    new_status = 'rejected'

            # Update if different
            if new_status != current_status:
                session.execute(sa.text("""
                    UPDATE entities
                    SET status = :new_status, updated_at = :now
                    WHERE id = :entity_id
                """), {
                    "entity_id": entity_id,
                    "new_status": new_status,
                    "now": datetime.utcnow()
                })
                print(f"  Entity {entity_id}: {current_status} -> {new_status}")

        session.commit()
        print(f"Sync complete!")

    except Exception as e:
        session.rollback()
        print(f"Error during sync: {e}")
        raise


def downgrade() -> None:
    """No downgrade - this is a data sync operation."""
    pass
