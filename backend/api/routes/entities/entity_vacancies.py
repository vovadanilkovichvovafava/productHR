"""
Воронки кандидата: его заявки, лента активности по воронкам (/activity),
добавление в воронку, рекомендации вакансий (вынесено из search.py, 20.10.2026).
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel

from .common import (
    get_db, Entity, EntityType, User, Department, Vacancy, VacancyApplication,
    get_current_user, get_user_org, check_entity_access,
)
from ...models.database import StageTransition

router = APIRouter()


# === Vacancy Integration ===

class ActivityEventResponse(BaseModel):
    """Одно событие истории этапов в ленте активности."""
    id: int
    from_stage: Optional[str] = None
    to_stage: str
    comment: Optional[str] = None
    changed_by_name: Optional[str] = None
    created_at: datetime
    # Правка комментария к переводу: пометка «Изменено» + подсказка «кто и
    # когда правил». Автор и время написания в строке не меняются.
    edited_at: Optional[datetime] = None
    edited_by_name: Optional[str] = None

    class Config:
        from_attributes = True


class VacancyActivityBlockResponse(BaseModel):
    """Блок «вакансия + хронология этапов» в единой ленте кандидата."""
    application_id: int
    vacancy_id: int
    vacancy_title: str
    current_stage: str
    applied_at: datetime
    last_stage_change_at: datetime
    events: List[ActivityEventResponse] = []
    # Закреплённая запись этой воронки («e:<id>» / «n:<uuid>») — одна на блок.
    pinned_entry_key: Optional[str] = None
    # Кто ведёт кандидата в этой воронке (автор заявки, без автора — владелец
    # воронки; правило метки «HR: …»). Нужно окну «Забрать» (26.10.2026).
    owner_id: Optional[int] = None
    owner_name: Optional[str] = None

    class Config:
        from_attributes = True


class EntityVacancyApplicationResponse(BaseModel):
    """Response schema for vacancy application from entity perspective."""
    id: int
    vacancy_id: int
    vacancy_title: str
    vacancy_status: str
    stage: str
    rating: Optional[int] = None
    notes: Optional[str] = None
    source: Optional[str] = None
    applied_at: datetime
    last_stage_change_at: datetime
    department_name: Optional[str] = None

    class Config:
        from_attributes = True


@router.get("/{entity_id}/vacancies")
async def get_entity_vacancies(
    entity_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all vacancies a candidate/entity has applied to.
    """
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    # Get entity
    result = await db.execute(
        select(Entity).where(Entity.id == entity_id, Entity.org_id == org.id)
    )
    entity = result.scalar_one_or_none()

    if not entity:
        raise HTTPException(404, "Entity not found")

    # Check if user has access to view this entity
    has_access = await check_entity_access(entity, current_user, org.id, db, required_level=None)
    if not has_access:
        raise HTTPException(404, "Entity not found")

    # Get all vacancy applications for this entity
    apps_result = await db.execute(
        select(VacancyApplication)
        .where(VacancyApplication.entity_id == entity_id)
        .order_by(VacancyApplication.applied_at.desc())
    )
    applications = apps_result.scalars().all()

    if not applications:
        return []

    # Get vacancy IDs for batch query
    vacancy_ids = [app.vacancy_id for app in applications]

    # Batch fetch vacancies
    vacancies_result = await db.execute(
        select(Vacancy).where(Vacancy.id.in_(vacancy_ids))
    )
    vacancies_map = {v.id: v for v in vacancies_result.scalars().all()}

    # Get department names
    dept_ids = [v.department_id for v in vacancies_map.values() if v.department_id]
    dept_names = {}
    if dept_ids:
        depts_result = await db.execute(
            select(Department).where(Department.id.in_(dept_ids))
        )
        dept_names = {d.id: d.name for d in depts_result.scalars().all()}

    # Build response
    response = []
    for app in applications:
        vacancy = vacancies_map.get(app.vacancy_id)
        if vacancy:
            response.append(EntityVacancyApplicationResponse(
                id=app.id,
                vacancy_id=app.vacancy_id,
                vacancy_title=vacancy.title,
                vacancy_status=vacancy.status.value if vacancy.status else "unknown",
                stage=app.stage.value if app.stage else "applied",
                rating=app.rating,
                notes=app.notes,
                source=app.source,
                applied_at=app.applied_at,
                last_stage_change_at=app.last_stage_change_at,
                department_name=dept_names.get(vacancy.department_id) if vacancy.department_id else None
            ))

    return response


@router.get("/{entity_id}/activity", response_model=List[VacancyActivityBlockResponse])
async def get_entity_activity(
    entity_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Единая лента активности кандидата: по блоку на каждую заявку (вакансию)
    с полной историей этапов. Survivor после слияния показывает ВСЕ участия."""
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

    apps = (await db.execute(
        select(VacancyApplication)
        .where(VacancyApplication.entity_id == entity_id)
        .order_by(VacancyApplication.last_stage_change_at.desc())
    )).scalars().all()
    # Скоуп по воронкам (01.10.2026): кандидат может быть в двух воронках, а
    # человек допущен до одной. Сам кандидат ему открыт, но блок чужой воронки
    # (этап, переписка, история) — нет.
    from ...services.vacancy_scope import get_scope_vacancy_ids
    _scope_ids = await get_scope_vacancy_ids(current_user, db)
    if _scope_ids:
        apps = [a for a in apps if a.vacancy_id in _scope_ids]
    if not apps:
        return []

    app_ids = [a.id for a in apps]
    vacancy_ids = [a.vacancy_id for a in apps]
    vacancies_map = {
        v.id: v for v in (await db.execute(
            select(Vacancy).where(Vacancy.id.in_(vacancy_ids))
        )).scalars().all()
    }

    transitions = (await db.execute(
        select(StageTransition)
        .where(StageTransition.application_id.in_(app_ids))
        .order_by(StageTransition.created_at.desc())
    )).scalars().all()

    def _owner(a) -> Optional[int]:
        v = vacancies_map.get(a.vacancy_id)
        return a.created_by or (v.created_by if v else None)

    user_ids = list(
        {t.changed_by for t in transitions if t.changed_by}
        | {t.edited_by for t in transitions if t.edited_by}
        | {o for o in (_owner(a) for a in apps) if o}
    )
    user_names = {}
    if user_ids:
        user_names = {
            row[0]: row[1] for row in (await db.execute(
                select(User.id, User.name).where(User.id.in_(user_ids))
            )).all()
        }

    events_by_app: dict = {}
    for t in transitions:
        events_by_app.setdefault(t.application_id, []).append(
            ActivityEventResponse(
                id=t.id, from_stage=t.from_stage, to_stage=t.to_stage,
                comment=t.comment, changed_by_name=user_names.get(t.changed_by),
                created_at=t.created_at,
                edited_at=t.edited_at,
                edited_by_name=user_names.get(t.edited_by),
            )
        )

    blocks = []
    for a in apps:
        vac = vacancies_map.get(a.vacancy_id)
        blocks.append(VacancyActivityBlockResponse(
            application_id=a.id,
            vacancy_id=a.vacancy_id,
            vacancy_title=(vac.title if vac else f"Вакансия #{a.vacancy_id}"),
            current_stage=a.stage.value if a.stage else "applied",
            applied_at=a.applied_at,
            last_stage_change_at=a.last_stage_change_at,
            events=events_by_app.get(a.id, []),
            pinned_entry_key=a.pinned_entry_key,
            owner_id=_owner(a),
            owner_name=user_names.get(_owner(a)),
        ))
    return blocks


# POST /entities/{id}/apply-to-vacancy удалён 20.10.2026: из интерфейса не
# вызывался, а работал как ПЕРЕНОС — удалял все прежние заявки кандидата вместе с
# историей. Добавление в воронку — POST /vacancies/{id}/applications.


# === Vacancy Recommendations ===

class VacancyRecommendationResponse(BaseModel):
    """Response model for vacancy recommendation."""
    vacancy_id: int
    vacancy_title: str
    match_score: int
    match_reasons: List[str]
    missing_requirements: List[str]
    salary_compatible: bool
    location_match: bool = True
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: str = "RUB"
    location: Optional[str] = None
    employment_type: Optional[str] = None
    experience_level: Optional[str] = None
    department_name: Optional[str] = None
    applications_count: int = 0


@router.get("/{entity_id}/recommended-vacancies", response_model=List[VacancyRecommendationResponse])
async def get_recommended_vacancies(
    entity_id: int,
    limit: int = Query(5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get vacancy recommendations for a candidate.

    SECURITY: Results are filtered by user's accessible vacancies.
    Скоуп по воронкам: по чужому кандидату не отвечаем (01.10.2026).
    Users only see recommendations for vacancies they own, have shared access to,
    or are in their department (if lead/admin).
    """
    from ...services.vacancy_recommender import vacancy_recommender
    from ...services.permissions import PermissionService
    from ...services.vacancy_scope import ensure_entity_visible

    current_user = await db.merge(current_user)
    await ensure_entity_visible(entity_id, current_user, db)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    # Get the entity
    result = await db.execute(
        select(Entity).where(Entity.id == entity_id, Entity.org_id == org.id)
    )
    entity = result.scalar_one_or_none()

    if not entity:
        raise HTTPException(404, "Entity not found")

    if entity.type != EntityType.candidate:
        raise HTTPException(400, "Recommendations are only available for candidates")

    # SECURITY: Get accessible vacancy IDs to filter recommendations
    permissions = PermissionService(db)
    accessible_vacancy_ids = await permissions.get_accessible_ids(current_user, "vacancy", org.id)

    # Get recommendations (fetches all open vacancies in org)
    all_recommendations = await vacancy_recommender.get_recommendations(
        db=db,
        entity=entity,
        limit=limit * 3,  # Get more to filter, then limit
        org_id=org.id
    )

    # Filter by accessible vacancies
    recommendations = [
        rec for rec in all_recommendations
        if rec.vacancy_id in accessible_vacancy_ids
    ][:limit]

    return [
        VacancyRecommendationResponse(
            vacancy_id=rec.vacancy_id,
            vacancy_title=rec.vacancy_title,
            match_score=rec.match_score,
            match_reasons=rec.match_reasons,
            missing_requirements=rec.missing_requirements,
            salary_compatible=rec.salary_compatible,
            location_match=rec.location_match,
            salary_min=rec.salary_min,
            salary_max=rec.salary_max,
            salary_currency=rec.salary_currency,
            location=rec.location,
            employment_type=rec.employment_type,
            experience_level=rec.experience_level,
            department_name=rec.department_name,
            applications_count=rec.applications_count,
        )
        for rec in recommendations
    ]


@router.post("/{entity_id}/auto-apply/{vacancy_id}")
async def auto_apply_to_vacancy(
    entity_id: int,
    vacancy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Automatically apply a candidate to a vacancy.
    """
    from ...services.vacancy_recommender import vacancy_recommender

    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    # Get the entity
    entity_result = await db.execute(
        select(Entity).where(Entity.id == entity_id, Entity.org_id == org.id)
    )
    entity = entity_result.scalar_one_or_none()

    if not entity:
        raise HTTPException(404, "Entity not found")

    if entity.type != EntityType.candidate:
        raise HTTPException(400, "Only candidates can apply")

    # Get the vacancy
    vacancy_result = await db.execute(
        select(Vacancy).where(Vacancy.id == vacancy_id, Vacancy.org_id == org.id)
    )
    vacancy = vacancy_result.scalar_one_or_none()

    if not vacancy:
        raise HTTPException(404, "Vacancy not found")

    # Apply
    application = await vacancy_recommender.auto_apply(
        db=db,
        entity=entity,
        vacancy=vacancy,
        source="recommendation",
        created_by=current_user.id
    )

    if not application:
        raise HTTPException(400, "Candidate has already applied to this vacancy")

    return {
        "id": application.id,
        "vacancy_id": application.vacancy_id,
        "entity_id": application.entity_id,
        "stage": application.stage.value,
        "source": application.source,
        "applied_at": application.applied_at.isoformat() if application.applied_at else None,
        "message": "Application created successfully"
    }


