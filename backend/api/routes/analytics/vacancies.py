"""
Vacancy Analytics

Provides endpoints for vacancy-specific analytics:
- Individual vacancy metrics
- Comparison between vacancies
- Time-to-fill analytics
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, case, Float
from pydantic import BaseModel

from ...database import get_db
from ...models.database import (
    User, Vacancy, VacancyStatus, VacancyApplication,
    ApplicationStage, Entity, Department
)
from ...services.auth import get_current_user, get_user_org
from ...utils.logging import get_logger

logger = get_logger("analytics-vacancies")

router = APIRouter()


# Schemas
class VacancyAnalytics(BaseModel):
    vacancy_id: int
    title: str
    status: str
    department_name: Optional[str]

    # Counts
    total_applications: int
    applications_by_stage: Dict[str, int]

    # Scores
    avg_compatibility_score: Optional[float]
    score_distribution: Dict[str, int]

    # Time metrics
    days_open: int
    avg_days_in_stage: Dict[str, float]

    # Source breakdown
    source_breakdown: Dict[str, int]

    # Conversion
    conversion_to_screening: Optional[float]
    conversion_to_interview: Optional[float]
    conversion_to_offer: Optional[float]
    conversion_to_hire: Optional[float]


class VacancyComparisonItem(BaseModel):
    vacancy_id: int
    title: str
    status: str
    applications: int
    hires: int
    conversion_rate: float
    avg_time_to_hire_days: Optional[float]
    avg_score: Optional[float]


class TimeToFillAnalytics(BaseModel):
    period: str
    avg_days: float
    min_days: int
    max_days: int
    count: int


@router.get("/{vacancy_id}", response_model=VacancyAnalytics)
async def get_vacancy_analytics(
    vacancy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get detailed analytics for a specific vacancy."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Load vacancy
    result = await db.execute(
        select(Vacancy, Department.name.label("dept_name"))
        .outerjoin(Department, Vacancy.department_id == Department.id)
        .where(Vacancy.id == vacancy_id, Vacancy.org_id == org.id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Vacancy not found")

    vacancy = row[0]
    dept_name = row[1]

    # Applications by stage
    stage_counts_result = await db.execute(
        select(
            VacancyApplication.stage,
            func.count(VacancyApplication.id)
        )
        .where(VacancyApplication.vacancy_id == vacancy_id)
        .group_by(VacancyApplication.stage)
    )
    applications_by_stage = {
        row.stage.value: row[1]
        for row in stage_counts_result
    }
    total_applications = sum(applications_by_stage.values())

    # Average compatibility score
    avg_score_result = await db.execute(
        select(
            func.avg(
                func.cast(VacancyApplication.compatibility_score['overall_score'].astext, Float)
            )
        )
        .where(
            VacancyApplication.vacancy_id == vacancy_id,
            VacancyApplication.compatibility_score.isnot(None)
        )
    )
    avg_score = avg_score_result.scalar()

    # Score distribution
    score_dist_result = await db.execute(
        select(
            case(
                (func.cast(VacancyApplication.compatibility_score['overall_score'].astext, Float) >= 80, 'excellent'),
                (func.cast(VacancyApplication.compatibility_score['overall_score'].astext, Float) >= 60, 'good'),
                (func.cast(VacancyApplication.compatibility_score['overall_score'].astext, Float) >= 40, 'average'),
                else_='below_average'
            ).label("category"),
            func.count(VacancyApplication.id)
        )
        .where(
            VacancyApplication.vacancy_id == vacancy_id,
            VacancyApplication.compatibility_score.isnot(None)
        )
        .group_by("category")
    )
    score_distribution = {row[0]: row[1] for row in score_dist_result}

    # Source breakdown
    source_result = await db.execute(
        select(
            func.coalesce(VacancyApplication.source, 'Не указан'),
            func.count(VacancyApplication.id)
        )
        .where(VacancyApplication.vacancy_id == vacancy_id)
        .group_by(VacancyApplication.source)
    )
    source_breakdown = {row[0]: row[1] for row in source_result}

    # Days open
    days_open = 0
    if vacancy.published_at:
        if vacancy.status == VacancyStatus.closed:
            end_date = vacancy.updated_at or datetime.utcnow()
        else:
            end_date = datetime.utcnow()
        days_open = (end_date - vacancy.published_at).days

    # Conversion rates
    screening_count = applications_by_stage.get('screening', 0)
    interview_count = applications_by_stage.get('interview', 0)
    offer_count = applications_by_stage.get('offer', 0)
    hired_count = applications_by_stage.get('hired', 0)

    conversion_to_screening = None
    conversion_to_interview = None
    conversion_to_offer = None
    conversion_to_hire = None

    if total_applications > 0:
        # Count passed each stage (including later stages)
        passed_screening = screening_count + interview_count + offer_count + hired_count + applications_by_stage.get('phone_screen', 0) + applications_by_stage.get('assessment', 0)
        passed_interview = interview_count + applications_by_stage.get('assessment', 0) + offer_count + hired_count
        passed_offer = offer_count + hired_count

        conversion_to_screening = round(passed_screening / total_applications * 100, 1)
        if passed_screening > 0:
            conversion_to_interview = round(passed_interview / passed_screening * 100, 1)
        if passed_interview > 0:
            conversion_to_offer = round(passed_offer / passed_interview * 100, 1)
        if passed_offer > 0:
            conversion_to_hire = round(hired_count / passed_offer * 100, 1)

    return VacancyAnalytics(
        vacancy_id=vacancy.id,
        title=vacancy.title,
        status=vacancy.status.value,
        department_name=dept_name,
        total_applications=total_applications,
        applications_by_stage=applications_by_stage,
        avg_compatibility_score=round(avg_score, 1) if avg_score else None,
        score_distribution=score_distribution,
        days_open=days_open,
        avg_days_in_stage={},  # TODO: Calculate from stage change history
        source_breakdown=source_breakdown,
        conversion_to_screening=conversion_to_screening,
        conversion_to_interview=conversion_to_interview,
        conversion_to_offer=conversion_to_offer,
        conversion_to_hire=conversion_to_hire,
    )


@router.get("/compare/list", response_model=List[VacancyComparisonItem])
async def compare_vacancies(
    vacancy_ids: Optional[str] = None,  # Comma-separated IDs
    status: Optional[VacancyStatus] = None,
    department_id: Optional[int] = None,
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Compare multiple vacancies side by side."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Parse vacancy IDs if provided
    ids_filter = None
    if vacancy_ids:
        try:
            ids_filter = [int(id.strip()) for id in vacancy_ids.split(",")]
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid vacancy IDs format")

    # Subquery for application stats
    app_stats = (
        select(
            VacancyApplication.vacancy_id,
            func.count(VacancyApplication.id).label("applications"),
            func.sum(case((VacancyApplication.stage == 'hired', 1), else_=0)).label("hires"),
            func.avg(
                case(
                    (VacancyApplication.compatibility_score.isnot(None),
                     func.cast(VacancyApplication.compatibility_score['overall_score'].astext, Float)),
                    else_=None
                )
            ).label("avg_score"),
            func.avg(
                case(
                    (VacancyApplication.stage == 'hired',
                     func.extract('epoch', VacancyApplication.last_stage_change_at - VacancyApplication.applied_at) / 86400),
                    else_=None
                )
            ).label("avg_time_to_hire"),
        )
        .group_by(VacancyApplication.vacancy_id)
        .subquery()
    )

    query = (
        select(
            Vacancy.id,
            Vacancy.title,
            Vacancy.status,
            func.coalesce(app_stats.c.applications, 0).label("applications"),
            func.coalesce(app_stats.c.hires, 0).label("hires"),
            app_stats.c.avg_score,
            app_stats.c.avg_time_to_hire,
        )
        .outerjoin(app_stats, Vacancy.id == app_stats.c.vacancy_id)
        .where(Vacancy.org_id == org.id)
    )

    if ids_filter:
        query = query.where(Vacancy.id.in_(ids_filter))
    if status:
        query = query.where(Vacancy.status == status)
    if department_id:
        query = query.where(Vacancy.department_id == department_id)

    query = query.order_by(func.coalesce(app_stats.c.applications, 0).desc()).limit(limit)

    result = await db.execute(query)
    comparisons = []

    for row in result:
        applications = row.applications or 0
        hires = row.hires or 0
        conversion = round(hires / applications * 100, 1) if applications > 0 else 0

        comparisons.append(VacancyComparisonItem(
            vacancy_id=row.id,
            title=row.title,
            status=row.status.value,
            applications=applications,
            hires=hires,
            conversion_rate=conversion,
            avg_time_to_hire_days=round(row.avg_time_to_hire, 1) if row.avg_time_to_hire else None,
            avg_score=round(row.avg_score, 1) if row.avg_score else None,
        ))

    return comparisons


@router.get("/time-to-fill/summary", response_model=List[TimeToFillAnalytics])
async def get_time_to_fill_summary(
    group_by: str = Query("month", pattern="^(month|quarter|department)$"),
    department_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get time-to-fill analytics grouped by period or department."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Base query for filled vacancies (those with at least one hire)
    now = datetime.utcnow()
    year_ago = now - timedelta(days=365)

    if group_by == "department":
        # Group by department
        result = await db.execute(
            select(
                Department.name.label("period"),
                func.avg(
                    func.extract('epoch', Vacancy.updated_at - Vacancy.published_at) / 86400
                ).label("avg_days"),
                func.min(
                    func.extract('epoch', Vacancy.updated_at - Vacancy.published_at) / 86400
                ).label("min_days"),
                func.max(
                    func.extract('epoch', Vacancy.updated_at - Vacancy.published_at) / 86400
                ).label("max_days"),
                func.count(Vacancy.id).label("count"),
            )
            .join(Department, Vacancy.department_id == Department.id)
            .where(
                Vacancy.org_id == org.id,
                Vacancy.status == VacancyStatus.closed,
                Vacancy.published_at.isnot(None),
                Vacancy.updated_at >= year_ago
            )
            .group_by(Department.name)
            .order_by(Department.name)
        )
    else:
        # Group by time period
        if group_by == "quarter":
            date_trunc = func.date_trunc('quarter', Vacancy.updated_at)
        else:
            date_trunc = func.date_trunc('month', Vacancy.updated_at)

        query = (
            select(
                date_trunc.label("period"),
                func.avg(
                    func.extract('epoch', Vacancy.updated_at - Vacancy.published_at) / 86400
                ).label("avg_days"),
                func.min(
                    func.extract('epoch', Vacancy.updated_at - Vacancy.published_at) / 86400
                ).label("min_days"),
                func.max(
                    func.extract('epoch', Vacancy.updated_at - Vacancy.published_at) / 86400
                ).label("max_days"),
                func.count(Vacancy.id).label("count"),
            )
            .where(
                Vacancy.org_id == org.id,
                Vacancy.status == VacancyStatus.closed,
                Vacancy.published_at.isnot(None),
                Vacancy.updated_at >= year_ago
            )
            .group_by(date_trunc)
            .order_by(date_trunc)
        )

        if department_id:
            query = query.where(Vacancy.department_id == department_id)

        result = await db.execute(query)

    analytics = []
    for row in result:
        period_str = str(row.period) if row.period else "Unknown"
        if hasattr(row.period, 'strftime'):
            period_str = row.period.strftime("%Y-%m")

        analytics.append(TimeToFillAnalytics(
            period=period_str,
            avg_days=round(row.avg_days or 0, 1),
            min_days=int(row.min_days or 0),
            max_days=int(row.max_days or 0),
            count=row.count or 0,
        ))

    return analytics


@router.get("/sources/effectiveness", response_model=List[Dict[str, Any]])
async def get_source_effectiveness(
    days: int = Query(90, ge=30, le=365),
    department_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get candidate source effectiveness analytics."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    date_from = datetime.utcnow() - timedelta(days=days)

    query = (
        select(
            func.coalesce(VacancyApplication.source, 'Не указан').label("source"),
            func.count(VacancyApplication.id).label("total"),
            func.sum(case((VacancyApplication.stage == 'hired', 1), else_=0)).label("hired"),
            func.avg(
                case(
                    (VacancyApplication.compatibility_score.isnot(None),
                     func.cast(VacancyApplication.compatibility_score['overall_score'].astext, Float)),
                    else_=None
                )
            ).label("avg_score"),
        )
        .select_from(VacancyApplication)
        .join(Vacancy, VacancyApplication.vacancy_id == Vacancy.id)
        .where(
            Vacancy.org_id == org.id,
            VacancyApplication.applied_at >= date_from
        )
        .group_by(VacancyApplication.source)
        .order_by(func.count(VacancyApplication.id).desc())
    )

    if department_id:
        query = query.where(Vacancy.department_id == department_id)

    result = await db.execute(query)

    sources = []
    for row in result:
        total = row.total or 0
        hired = row.hired or 0
        conversion = round(hired / total * 100, 1) if total > 0 else 0

        sources.append({
            "source": row.source,
            "total_applications": total,
            "hires": hired,
            "conversion_rate": conversion,
            "avg_score": round(row.avg_score, 1) if row.avg_score else None,
        })

    return sources
