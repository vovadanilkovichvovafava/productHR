"""
Smart search, red flags и risk score кандидата. Воронки кандидата живут в
entity_vacancies.py, похожие и дубли — в duplicates.py (разрезано 20.10.2026).
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from .common import (
    logger, get_db, Entity, Chat, CallRecording, User, Vacancy, Message,
    get_current_user, get_user_org, check_entity_access, red_flags_service,
)

router = APIRouter()


# Умный поиск (GET /entities/search) удалён 20.10.2026: его не было ни на одной
# странице, а сам адрес перехватывался GET /entities/{entity_id} и отвечал 422.
# Поиск кандидатов — services/search_index.apply_text_search.

# === Red Flags & Risk ===

@router.get("/{entity_id}/red-flags")
async def get_entity_red_flags(
    entity_id: int,
    vacancy_id: Optional[int] = Query(None, description="Optional vacancy ID to compare against"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get red flags analysis for a candidate.

    Analyzes the candidate's profile and communications for potential red flags.
    Returns a list of detected red flags with severity levels and recommendations.
    """
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    # Fetch entity
    result = await db.execute(
        select(Entity).where(Entity.id == entity_id, Entity.org_id == org.id)
    )
    entity = result.scalar_one_or_none()

    if not entity:
        raise HTTPException(404, "Entity not found")

    # Check access
    has_access = await check_entity_access(entity, current_user, org.id, db, required_level=None)
    if not has_access:
        raise HTTPException(404, "Entity not found")

    # Fetch vacancy if provided
    vacancy = None
    if vacancy_id:
        vacancy_result = await db.execute(
            select(Vacancy).where(Vacancy.id == vacancy_id, Vacancy.org_id == org.id)
        )
        vacancy = vacancy_result.scalar_one_or_none()

    # Fetch linked chats with messages for AI analysis
    chats_result = await db.execute(
        select(Chat).where(Chat.entity_id == entity_id)
    )
    chats = list(chats_result.scalars().all())

    # Load messages for each chat (limit to avoid memory issues)
    for chat in chats:
        messages_result = await db.execute(
            select(Message)
            .where(Message.chat_id == chat.id)
            .order_by(Message.timestamp.desc())
            .limit(100)
        )
        chat.messages = list(messages_result.scalars().all())

    # Fetch linked calls with transcripts
    calls_result = await db.execute(
        select(CallRecording)
        .where(CallRecording.entity_id == entity_id)
        .order_by(CallRecording.created_at.desc())
        .limit(5)
    )
    calls = list(calls_result.scalars().all())

    # Run red flags analysis
    try:
        analysis = await red_flags_service.detect_red_flags(
            entity=entity,
            vacancy=vacancy,
            chats=chats,
            calls=calls
        )
        return analysis.to_dict()
    except Exception as e:
        logger.error(f"Red flags analysis failed for entity {entity_id}: {e}")
        raise HTTPException(500, f"Failed to analyze red flags: {str(e)}")


@router.get("/{entity_id}/risk-score")
async def get_entity_risk_score(
    entity_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get quick risk score for a candidate (0-100).

    This is a fast synchronous calculation based on available profile data.
    For full analysis with AI, use the /red-flags endpoint.
    """
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    result = await db.execute(
        select(Entity).where(Entity.id == entity_id, Entity.org_id == org.id)
    )
    entity = result.scalar_one_or_none()

    if not entity:
        raise HTTPException(404, "Entity not found")

    has_access = await check_entity_access(entity, current_user, org.id, db, required_level=None)
    if not has_access:
        raise HTTPException(404, "Entity not found")

    risk_score = red_flags_service.get_risk_score(entity)

    return {
        "entity_id": entity_id,
        "risk_score": risk_score,
        "risk_level": "high" if risk_score >= 60 else "medium" if risk_score >= 30 else "low"
    }
