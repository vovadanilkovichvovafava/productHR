"""
AI Scoring Routes - Candidate-Vacancy Compatibility Scoring API.

Endpoints for calculating and retrieving AI-powered compatibility scores
between candidates (entities) and job vacancies.
"""
import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.database import (
    User, Entity, Vacancy, VacancyApplication,
    EntityType, VacancyStatus
)
from ..services.auth import get_current_user
from ..services.ai_scoring import ai_scoring_service, CompatibilityScore
from ..services.cache import scoring_cache

logger = logging.getLogger("hr-analyzer.routes.scoring")
router = APIRouter()


# ============================================================================
# Request/Response Schemas
# ============================================================================

class CalculateScoreRequest(BaseModel):
    """Request to calculate compatibility score."""
    entity_id: int = Field(..., description="Candidate (entity) ID")
    vacancy_id: int = Field(..., description="Vacancy ID")


class CompatibilityScoreResponse(BaseModel):
    """Response with compatibility score details."""
    overall_score: int = Field(..., ge=0, le=100)
    skills_match: int = Field(..., ge=0, le=100)
    experience_match: int = Field(..., ge=0, le=100)
    salary_match: int = Field(..., ge=0, le=100)
    culture_fit: int = Field(..., ge=0, le=100)
    strengths: List[str]
    weaknesses: List[str]
    recommendation: str
    summary: str
    key_factors: List[str]


class EntityScoreResult(BaseModel):
    """Score result for a single candidate."""
    entity_id: int
    entity_name: str
    score: CompatibilityScoreResponse


class VacancyScoreResult(BaseModel):
    """Score result for a single vacancy."""
    vacancy_id: int
    vacancy_title: str
    score: CompatibilityScoreResponse


class CalculateScoreResponse(BaseModel):
    """Response for single score calculation."""
    entity_id: int
    vacancy_id: int
    score: CompatibilityScoreResponse
    cached: bool = False


class BestMatchesRequest(BaseModel):
    """Request to find best matching candidates."""
    limit: int = Field(default=10, ge=1, le=50)
    min_score: int = Field(default=0, ge=0, le=100)
    status_filter: Optional[List[str]] = None


class BestMatchesResponse(BaseModel):
    """Response with best matching candidates."""
    vacancy_id: int
    vacancy_title: str
    matches: List[EntityScoreResult]
    total_evaluated: int


class MatchingVacanciesRequest(BaseModel):
    """Request to find matching vacancies for a candidate."""
    limit: int = Field(default=10, ge=1, le=50)
    min_score: int = Field(default=0, ge=0, le=100)


class MatchingVacanciesResponse(BaseModel):
    """Response with matching vacancies."""
    entity_id: int
    entity_name: str
    matches: List[VacancyScoreResult]
    total_evaluated: int


# ============================================================================
# Helper Functions
# ============================================================================

async def get_entity_with_permission(
    db: AsyncSession,
    entity_id: int,
    user: User
) -> Entity:
    """Get entity ensuring user has access."""
    result = await db.execute(
        select(Entity).where(Entity.id == entity_id)
    )
    entity = result.scalar_one_or_none()

    if not entity:
        raise HTTPException(status_code=404, detail="Кандидат не найден")

    # Check organization access (simplified - in production, add proper permissions)
    return entity


async def get_vacancy_with_permission(
    db: AsyncSession,
    vacancy_id: int,
    user: User
) -> Vacancy:
    """Get vacancy ensuring user has access."""
    result = await db.execute(
        select(Vacancy).where(Vacancy.id == vacancy_id)
    )
    vacancy = result.scalar_one_or_none()

    if not vacancy:
        raise HTTPException(status_code=404, detail="Вакансия не найдена")

    return vacancy


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/calculate", response_model=CalculateScoreResponse)
async def calculate_compatibility(
    request: CalculateScoreRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Calculate AI compatibility score between a candidate and vacancy.

    Returns detailed scoring including:
    - Overall compatibility score (0-100)
    - Skills match score
    - Experience match score
    - Salary match score
    - Culture fit score
    - List of strengths and weaknesses
    - Hiring recommendation (hire/maybe/reject)
    """
    # Get entities
    entity = await get_entity_with_permission(db, request.entity_id, current_user)
    vacancy = await get_vacancy_with_permission(db, request.vacancy_id, current_user)

    # Validate entity is a candidate
    if entity.type != EntityType.candidate:
        raise HTTPException(
            status_code=400,
            detail="Скоринг доступен только для кандидатов"
        )

    # Check for cached score in application
    result = await db.execute(
        select(VacancyApplication).where(
            VacancyApplication.entity_id == entity.id,
            VacancyApplication.vacancy_id == vacancy.id
        )
    )
    application = result.scalar_one_or_none()

    if application and application.compatibility_score:
        # Return cached score from application
        logger.info(f"Returning cached score from application for entity {entity.id} <-> vacancy {vacancy.id}")
        return CalculateScoreResponse(
            entity_id=entity.id,
            vacancy_id=vacancy.id,
            score=CompatibilityScoreResponse(**application.compatibility_score),
            cached=True
        )

    # Check for cached score in memory (when no application exists)
    if not application:
        cached_score = await scoring_cache.get_cached_score(entity.id, vacancy.id)
        if cached_score:
            logger.info(f"Returning cached score from memory for entity {entity.id} <-> vacancy {vacancy.id}")
            return CalculateScoreResponse(
                entity_id=entity.id,
                vacancy_id=vacancy.id,
                score=CompatibilityScoreResponse(**cached_score),
                cached=True
            )

    # Calculate new score
    score = await ai_scoring_service.calculate_compatibility(entity, vacancy)
    score_dict = score.to_dict()

    # Cache score in application if exists, otherwise cache in memory
    if application:
        application.compatibility_score = score_dict
        await db.commit()
    else:
        # Cache in memory with 1 hour TTL
        await scoring_cache.set_cached_score(entity.id, vacancy.id, score_dict)

    return CalculateScoreResponse(
        entity_id=entity.id,
        vacancy_id=vacancy.id,
        score=CompatibilityScoreResponse(**score_dict),
        cached=False
    )


@router.post("/vacancy/{vacancy_id}/matches", response_model=BestMatchesResponse)
async def find_best_matches_for_vacancy(
    vacancy_id: int,
    request: BestMatchesRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Find the best matching candidates for a vacancy.

    Evaluates all candidates and returns top matches sorted by compatibility score.
    """
    # Get vacancy
    vacancy = await get_vacancy_with_permission(db, vacancy_id, current_user)

    # Get candidates
    query = select(Entity).where(Entity.type == EntityType.candidate)

    # Filter by status if specified
    if request.status_filter:
        query = query.where(Entity.status.in_(request.status_filter))

    result = await db.execute(query)
    candidates = result.scalars().all()

    if not candidates:
        return BestMatchesResponse(
            vacancy_id=vacancy.id,
            vacancy_title=vacancy.title,
            matches=[],
            total_evaluated=0
        )

    # Score candidates
    matches = await ai_scoring_service.find_best_matches(
        vacancy=vacancy,
        candidates=list(candidates),
        limit=request.limit,
        min_score=request.min_score
    )

    return BestMatchesResponse(
        vacancy_id=vacancy.id,
        vacancy_title=vacancy.title,
        matches=[
            EntityScoreResult(
                entity_id=m["entity_id"],
                entity_name=m["entity_name"],
                score=CompatibilityScoreResponse(**m["score"])
            )
            for m in matches
        ],
        total_evaluated=len(candidates)
    )


@router.post("/entity/{entity_id}/vacancies", response_model=MatchingVacanciesResponse)
async def find_matching_vacancies_for_entity(
    entity_id: int,
    request: MatchingVacanciesRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Find matching vacancies for a candidate.

    Evaluates only vacancies accessible to the user and returns best matches
    sorted by compatibility score.

    SECURITY: Filters vacancies by user access rights - only shows vacancies
    the user created or has access to via department/sharing.
    """
    from ..services.permissions import PermissionService
    from ..services.auth import get_user_org

    # Get entity
    entity = await get_entity_with_permission(db, entity_id, current_user)

    if entity.type != EntityType.candidate:
        raise HTTPException(
            status_code=400,
            detail="Поиск вакансий доступен только для кандидатов"
        )

    # Get user's organization
    org = await get_user_org(current_user, db)
    org_id = org.id if org else None

    # SECURITY: Get accessible vacancy IDs to prevent data leak
    permissions = PermissionService(db)
    accessible_vacancy_ids = await permissions.get_accessible_ids(current_user, "vacancy", org_id) if org_id else set()

    # Get open vacancies filtered by access
    if not accessible_vacancy_ids:
        return MatchingVacanciesResponse(
            entity_id=entity.id,
            entity_name=entity.name,
            matches=[],
            total_evaluated=0
        )

    result = await db.execute(
        select(Vacancy).where(
            Vacancy.status == VacancyStatus.open,
            Vacancy.id.in_(accessible_vacancy_ids)
        )
    )
    vacancies = result.scalars().all()

    if not vacancies:
        return MatchingVacanciesResponse(
            entity_id=entity.id,
            entity_name=entity.name,
            matches=[],
            total_evaluated=0
        )

    # Score vacancies
    matches = await ai_scoring_service.find_matching_vacancies(
        entity=entity,
        vacancies=list(vacancies),
        limit=request.limit,
        min_score=request.min_score
    )

    return MatchingVacanciesResponse(
        entity_id=entity.id,
        entity_name=entity.name,
        matches=[
            VacancyScoreResult(
                vacancy_id=m["vacancy_id"],
                vacancy_title=m["vacancy_title"],
                score=CompatibilityScoreResponse(**m["score"])
            )
            for m in matches
        ],
        total_evaluated=len(vacancies)
    )


@router.post("/application/{application_id}/recalculate", response_model=CalculateScoreResponse)
async def recalculate_application_score(
    application_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Recalculate and update compatibility score for an existing application.

    Forces recalculation even if cached score exists.
    """
    # Get application with related data
    result = await db.execute(
        select(VacancyApplication).where(VacancyApplication.id == application_id)
    )
    application = result.scalar_one_or_none()

    if not application:
        raise HTTPException(status_code=404, detail="Отклик не найден")

    # Get entity and vacancy
    entity = await get_entity_with_permission(db, application.entity_id, current_user)
    vacancy = await get_vacancy_with_permission(db, application.vacancy_id, current_user)

    # Calculate new score
    score = await ai_scoring_service.calculate_compatibility(entity, vacancy)

    # Update cached score
    application.compatibility_score = score.to_dict()
    await db.commit()

    return CalculateScoreResponse(
        entity_id=entity.id,
        vacancy_id=vacancy.id,
        score=CompatibilityScoreResponse(**score.to_dict()),
        cached=False
    )


@router.get("/application/{application_id}", response_model=CalculateScoreResponse)
async def get_application_score(
    application_id: int,
    recalculate: bool = Query(False, description="Force recalculation of score"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get compatibility score for an application.

    If score is cached, returns cached version unless recalculate=true.
    If no cached score exists, calculates new score.
    """
    # Get application
    result = await db.execute(
        select(VacancyApplication).where(VacancyApplication.id == application_id)
    )
    application = result.scalar_one_or_none()

    if not application:
        raise HTTPException(status_code=404, detail="Отклик не найден")

    # Get entity and vacancy
    entity = await get_entity_with_permission(db, application.entity_id, current_user)
    vacancy = await get_vacancy_with_permission(db, application.vacancy_id, current_user)

    # Return cached if exists and not forcing recalculation
    if application.compatibility_score and not recalculate:
        return CalculateScoreResponse(
            entity_id=entity.id,
            vacancy_id=vacancy.id,
            score=CompatibilityScoreResponse(**application.compatibility_score),
            cached=True
        )

    # Calculate new score
    score = await ai_scoring_service.calculate_compatibility(entity, vacancy)

    # Update cached score
    application.compatibility_score = score.to_dict()
    await db.commit()

    return CalculateScoreResponse(
        entity_id=entity.id,
        vacancy_id=vacancy.id,
        score=CompatibilityScoreResponse(**score.to_dict()),
        cached=False
    )


@router.post("/bulk", response_model=List[EntityScoreResult])
async def bulk_calculate_scores(
    vacancy_id: int = Query(..., description="Vacancy ID"),
    entity_ids: List[int] = Query(..., description="List of entity IDs to score"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Bulk calculate compatibility scores for multiple candidates against a vacancy.
    """
    # Get vacancy
    vacancy = await get_vacancy_with_permission(db, vacancy_id, current_user)

    # Get entities
    result = await db.execute(
        select(Entity).where(
            Entity.id.in_(entity_ids),
            Entity.type == EntityType.candidate
        )
    )
    entities = result.scalars().all()

    if not entities:
        return []

    # Score all entities
    results = await ai_scoring_service.bulk_score(list(entities), vacancy)

    # Cache scores in applications
    for r in results:
        app_result = await db.execute(
            select(VacancyApplication).where(
                VacancyApplication.entity_id == r["entity_id"],
                VacancyApplication.vacancy_id == vacancy.id
            )
        )
        application = app_result.scalar_one_or_none()
        if application:
            application.compatibility_score = r["score"]

    await db.commit()

    return [
        EntityScoreResult(
            entity_id=r["entity_id"],
            entity_name=r["entity_name"],
            score=CompatibilityScoreResponse(**r["score"])
        )
        for r in results
    ]
