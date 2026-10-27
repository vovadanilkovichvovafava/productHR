"""
Service for recording stage/status transitions (audit log).
"""
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import StageTransition

logger = logging.getLogger("hr-analyzer.stage_transitions")


async def record_transition(
    db: AsyncSession,
    application_id: int,
    entity_id: int,
    from_stage: Optional[str],
    to_stage: str,
    changed_by_id: Optional[int],
    comment: Optional[str] = None,
) -> StageTransition:
    """Record a stage transition in the audit log.

    Args:
        db: Database session
        application_id: VacancyApplication.id
        entity_id: Entity.id (the candidate)
        from_stage: Previous stage value (None for initial creation)
        to_stage: New stage value
        changed_by_id: User.id who made the change
        comment: Optional comment about the transition

    Returns:
        The created StageTransition record
    """
    transition = StageTransition(
        application_id=application_id,
        entity_id=entity_id,
        from_stage=from_stage,
        to_stage=to_stage,
        changed_by=changed_by_id,
        comment=comment,
    )
    db.add(transition)

    logger.info(
        f"Stage transition: app={application_id} entity={entity_id} "
        f"{from_stage} -> {to_stage} by user={changed_by_id}"
    )

    return transition
