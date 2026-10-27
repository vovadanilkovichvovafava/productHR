"""
API routes for global search (Command Palette).
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from pydantic import BaseModel
import logging

logger = logging.getLogger("hr-analyzer.search")

from ..database import get_db
from ..models.database import (
    Entity, EntityType, EntityStatus, User, Organization,
    Vacancy, VacancyStatus
)
from ..services.auth import get_current_user, get_user_org

router = APIRouter()


# === Pydantic Schemas ===

class GlobalSearchCandidate(BaseModel):
    """Search result for a candidate."""
    id: int
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    position: Optional[str] = None
    company: Optional[str] = None
    status: str
    relevance_score: float = 0.0


class GlobalSearchVacancy(BaseModel):
    """Search result for a vacancy."""
    id: int
    title: str
    status: str
    location: Optional[str] = None
    department_name: Optional[str] = None
    relevance_score: float = 0.0


class GlobalSearchResponse(BaseModel):
    """Response from global search."""
    candidates: List[GlobalSearchCandidate] = []
    vacancies: List[GlobalSearchVacancy] = []
    total: int = 0


# === Helper Functions ===

def calculate_relevance_score(text: str, query: str) -> float:
    """
    Calculate relevance score based on match position and type.

    Score factors:
    - Exact match at start: 100
    - Exact match anywhere: 80
    - Word boundary match: 60
    - Partial match: 40
    """
    if not text or not query:
        return 0.0

    text_lower = text.lower()
    query_lower = query.lower()

    # Exact match at start
    if text_lower.startswith(query_lower):
        return 100.0

    # Exact word match
    words = text_lower.split()
    for word in words:
        if word == query_lower:
            return 80.0
        if word.startswith(query_lower):
            return 70.0

    # Contains match
    if query_lower in text_lower:
        return 50.0

    return 0.0


# === Routes ===

@router.get("/global", response_model=GlobalSearchResponse)
async def global_search(
    query: str = Query(..., min_length=1, max_length=100, description="Search query"),
    limit: int = Query(5, ge=1, le=20, description="Max results per category"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> GlobalSearchResponse:
    """
    Global search across candidates and vacancies.

    Used by the Command Palette (Cmd+K) for quick navigation.

    Features:
    - Searches candidates by name, email, phone, position
    - Searches vacancies by title
    - Results sorted by relevance score
    - Respects organization boundaries

    Args:
        query: Search query string (min 1 char)
        limit: Maximum results per category (default: 5, max: 20)

    Returns:
        GlobalSearchResponse with candidates and vacancies lists
    """
    org = await get_user_org(current_user, db)
    if not org:
        return GlobalSearchResponse()

    query_lower = query.lower().strip()

    # Умный матч по имени — тот же, что в «Все кандидаты» (транслит + любой порядок
    # слов + опечатки через pg_trgm; при отсутствии pg_trgm — транслит-ILIKE).
    from ..services.search_index import name_search_conditions, ensure_pg_trgm_checked, contact_search_conditions
    await ensure_pg_trgm_checked(db)

    candidates: List[GlobalSearchCandidate] = []
    vacancies: List[GlobalSearchVacancy] = []

    # Search candidates (entities with type=candidate)
    try:
        entity_query = (
            select(Entity)
            .where(
                Entity.org_id == org.id,
                Entity.type == EntityType.candidate,
                or_(
                    # pg_trgm (транслит + любой порядок слов + опечатки) + транслит-ILIKE + Ё≡Е
                    *name_search_conditions(query),
                    *contact_search_conditions(query),  # почта/телефон(норм.)/telegram + доп-списки
                    func.lower(Entity.position).contains(query_lower),
                    func.lower(Entity.company).contains(query_lower),
                )
            )
            .limit(limit * 2)  # Get more to sort by relevance
        )
        result = await db.execute(entity_query)
        entity_rows = result.scalars().all()

        # Calculate relevance and sort
        scored_candidates = []
        for entity in entity_rows:
            # Calculate score based on multiple fields
            scores = [
                calculate_relevance_score(entity.name, query_lower) * 1.5,  # Name has higher weight
                calculate_relevance_score(entity.email or '', query_lower),
                calculate_relevance_score(entity.phone or '', query_lower),
                calculate_relevance_score(entity.position or '', query_lower),
                calculate_relevance_score(entity.company or '', query_lower),
            ]
            max_score = max(scores) if scores else 0

            scored_candidates.append((entity, max_score))

        # Sort by score and take top results
        scored_candidates.sort(key=lambda x: x[1], reverse=True)

        for entity, score in scored_candidates[:limit]:
            candidates.append(GlobalSearchCandidate(
                id=entity.id,
                name=entity.name,
                email=entity.email,
                phone=entity.phone,
                position=entity.position,
                company=entity.company,
                status=entity.status.value if entity.status else 'new',
                relevance_score=score
            ))
    except Exception as e:
        logger.warning(f"Candidate search error: {e}")

    # Search vacancies
    try:
        vacancy_query = (
            select(Vacancy)
            .where(
                Vacancy.org_id == org.id,
                Vacancy.status.in_([VacancyStatus.open, VacancyStatus.paused, VacancyStatus.draft]),
                func.lower(Vacancy.title).contains(query_lower)
            )
            .limit(limit * 2)
        )
        result = await db.execute(vacancy_query)
        vacancy_rows = result.scalars().all()

        # Calculate relevance and sort
        scored_vacancies = []
        for vacancy in vacancy_rows:
            score = calculate_relevance_score(vacancy.title, query_lower)
            scored_vacancies.append((vacancy, score))

        scored_vacancies.sort(key=lambda x: x[1], reverse=True)

        for vacancy, score in scored_vacancies[:limit]:
            # Get department name if available
            dept_name = None
            if vacancy.department_id:
                from ..models.database import Department
                dept_result = await db.execute(
                    select(Department.name).where(Department.id == vacancy.department_id)
                )
                dept_row = dept_result.scalar_one_or_none()
                if dept_row:
                    dept_name = dept_row

            vacancies.append(GlobalSearchVacancy(
                id=vacancy.id,
                title=vacancy.title,
                status=vacancy.status.value if vacancy.status else 'draft',
                location=vacancy.location,
                department_name=dept_name,
                relevance_score=score
            ))
    except Exception as e:
        logger.warning(f"Vacancy search error: {e}")

    total = len(candidates) + len(vacancies)

    return GlobalSearchResponse(
        candidates=candidates,
        vacancies=vacancies,
        total=total
    )
