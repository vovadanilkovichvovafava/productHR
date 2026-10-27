"""
Hiring Funnel Analytics

Provides endpoints for:
- Funnel visualization data
- Stage conversion metrics
- Pipeline health
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, case
from pydantic import BaseModel

from ...database import get_db
from ...models.database import (
    User, Vacancy, VacancyStatus, VacancyApplication,
    ApplicationStage, Department
)
from ...services.auth import get_current_user, get_user_org
from ...utils.logging import get_logger
from ...services.hr_stages import STAGE_LABELS  # общий справочник этапов

logger = get_logger("analytics-funnel")

router = APIRouter()



# Ordered stages for funnel
FUNNEL_STAGES = ["applied", "screening", "phone_screen", "interview", "assessment", "offer", "hired"]


# Schemas
class FunnelStage(BaseModel):
    stage: str
    label: str
    count: int
    percentage: float
    conversion_from_previous: Optional[float]


class FunnelData(BaseModel):
    stages: List[FunnelStage]
    total_applications: int
    total_hires: int
    overall_conversion: float
    rejected_count: int
    withdrawn_count: int


class StageConversionMetrics(BaseModel):
    from_stage: str
    to_stage: str
    from_label: str
    to_label: str
    count: int
    converted: int
    conversion_rate: float
    avg_days_to_convert: Optional[float]


class PipelineHealthMetrics(BaseModel):
    total_in_pipeline: int
    stuck_candidates: int  # No activity for > 14 days
    high_score_waiting: int  # Score > 70 but not moved
    urgent_vacancies_without_candidates: int
    stages_health: Dict[str, Dict[str, Any]]


@router.get("/overview", response_model=FunnelData)
async def get_funnel_overview(
    vacancy_id: Optional[int] = None,
    department_id: Optional[int] = None,
    days: int = Query(90, ge=7, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get hiring funnel overview with stage counts and conversions."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    date_from = datetime.utcnow() - timedelta(days=days)

    # Build query for stage counts
    query = (
        select(
            VacancyApplication.stage,
            func.count(VacancyApplication.id).label("count")
        )
        .select_from(VacancyApplication)
        .join(Vacancy, VacancyApplication.vacancy_id == Vacancy.id)
        .where(
            Vacancy.org_id == org.id,
            VacancyApplication.applied_at >= date_from
        )
        .group_by(VacancyApplication.stage)
    )

    if vacancy_id:
        query = query.where(VacancyApplication.vacancy_id == vacancy_id)
    if department_id:
        query = query.where(Vacancy.department_id == department_id)

    result = await db.execute(query)
    stage_counts = {(row.stage.value if hasattr(row.stage, 'value') else str(row.stage)): row.count for row in result}

    # Build funnel stages
    stages = []
    total = sum(stage_counts.get(s, 0) for s in FUNNEL_STAGES)
    previous_count = None

    for stage in FUNNEL_STAGES:
        count = stage_counts.get(stage, 0)
        percentage = round(count / total * 100, 1) if total > 0 else 0

        conversion = None
        if previous_count is not None and previous_count > 0:
            conversion = round(count / previous_count * 100, 1)

        stages.append(FunnelStage(
            stage=stage,
            label=STAGE_LABELS.get(stage, stage),
            count=count,
            percentage=percentage,
            conversion_from_previous=conversion,
        ))

        previous_count = count

    total_hires = stage_counts.get("hired", 0)
    rejected = stage_counts.get("rejected", 0)
    withdrawn = stage_counts.get("withdrawn", 0)

    overall_conversion = round(total_hires / total * 100, 1) if total > 0 else 0

    return FunnelData(
        stages=stages,
        total_applications=total,
        total_hires=total_hires,
        overall_conversion=overall_conversion,
        rejected_count=rejected,
        withdrawn_count=withdrawn,
    )


@router.get("/conversions", response_model=List[StageConversionMetrics])
async def get_stage_conversions(
    vacancy_id: Optional[int] = None,
    department_id: Optional[int] = None,
    days: int = Query(90, ge=7, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get detailed conversion metrics between stages."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    date_from = datetime.utcnow() - timedelta(days=days)

    # Get stage counts
    query = (
        select(
            VacancyApplication.stage,
            func.count(VacancyApplication.id).label("count")
        )
        .select_from(VacancyApplication)
        .join(Vacancy, VacancyApplication.vacancy_id == Vacancy.id)
        .where(
            Vacancy.org_id == org.id,
            VacancyApplication.applied_at >= date_from
        )
        .group_by(VacancyApplication.stage)
    )

    if vacancy_id:
        query = query.where(VacancyApplication.vacancy_id == vacancy_id)
    if department_id:
        query = query.where(Vacancy.department_id == department_id)

    result = await db.execute(query)
    stage_counts = {(row.stage.value if hasattr(row.stage, 'value') else str(row.stage)): row.count for row in result}

    # Calculate conversions between consecutive stages
    conversions = []

    for i in range(len(FUNNEL_STAGES) - 1):
        from_stage = FUNNEL_STAGES[i]
        to_stage = FUNNEL_STAGES[i + 1]

        from_count = stage_counts.get(from_stage, 0)
        # Count everyone who reached to_stage or later
        to_count = sum(stage_counts.get(s, 0) for s in FUNNEL_STAGES[i + 1:])

        conversion_rate = round(to_count / from_count * 100, 1) if from_count > 0 else 0

        conversions.append(StageConversionMetrics(
            from_stage=from_stage,
            to_stage=to_stage,
            from_label=STAGE_LABELS.get(from_stage, from_stage),
            to_label=STAGE_LABELS.get(to_stage, to_stage),
            count=from_count,
            converted=to_count,
            conversion_rate=conversion_rate,
            avg_days_to_convert=None,  # TODO: Calculate from history
        ))

    return conversions


@router.get("/health", response_model=PipelineHealthMetrics)
async def get_pipeline_health(
    department_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get pipeline health metrics to identify bottlenecks."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    now = datetime.utcnow()
    stuck_threshold = now - timedelta(days=14)

    # Active pipeline stages (not hired/rejected/withdrawn) - use strings for DB comparison
    active_stages = ['applied', 'screening', 'phone_screen', 'interview', 'assessment', 'offer']

    # Base query for active applications
    base_filter = [Vacancy.org_id == org.id]
    if department_id:
        base_filter.append(Vacancy.department_id == department_id)

    # Total in pipeline
    total_result = await db.execute(
        select(func.count(VacancyApplication.id))
        .select_from(VacancyApplication)
        .join(Vacancy, VacancyApplication.vacancy_id == Vacancy.id)
        .where(
            *base_filter,
            VacancyApplication.stage.in_(active_stages)
        )
    )
    total_in_pipeline = total_result.scalar() or 0

    # Stuck candidates (no activity for > 14 days)
    stuck_result = await db.execute(
        select(func.count(VacancyApplication.id))
        .select_from(VacancyApplication)
        .join(Vacancy, VacancyApplication.vacancy_id == Vacancy.id)
        .where(
            *base_filter,
            VacancyApplication.stage.in_(active_stages),
            VacancyApplication.updated_at < stuck_threshold
        )
    )
    stuck_candidates = stuck_result.scalar() or 0

    # High score waiting (score > 70 in early stages)
    from sqlalchemy import Float

    high_score_result = await db.execute(
        select(func.count(VacancyApplication.id))
        .select_from(VacancyApplication)
        .join(Vacancy, VacancyApplication.vacancy_id == Vacancy.id)
        .where(
            *base_filter,
            VacancyApplication.stage.in_(['applied', 'screening']),
            VacancyApplication.compatibility_score.isnot(None),
            func.cast(VacancyApplication.compatibility_score['overall_score'].astext, Float) >= 70
        )
    )
    high_score_waiting = high_score_result.scalar() or 0

    # Urgent vacancies without candidates
    urgent_result = await db.execute(
        select(func.count(Vacancy.id))
        .select_from(Vacancy)
        .outerjoin(VacancyApplication, and_(
            VacancyApplication.vacancy_id == Vacancy.id,
            VacancyApplication.stage.in_(active_stages)
        ))
        .where(
            *base_filter,
            Vacancy.status == VacancyStatus.open,
            Vacancy.priority >= 2  # Urgent
        )
        .group_by(Vacancy.id)
        .having(func.count(VacancyApplication.id) == 0)
    )
    urgent_without = len(urgent_result.all())

    # Stage health - count and avg days in each stage
    stages_health = {}
    for stage in active_stages:
        stage_result = await db.execute(
            select(
                func.count(VacancyApplication.id).label("count"),
                func.avg(
                    func.extract('epoch', now - VacancyApplication.last_stage_change_at) / 86400
                ).label("avg_days")
            )
            .select_from(VacancyApplication)
            .join(Vacancy, VacancyApplication.vacancy_id == Vacancy.id)
            .where(
                *base_filter,
                VacancyApplication.stage == stage
            )
        )
        row = stage_result.first()
        stages_health[stage] = {
            "label": STAGE_LABELS.get(stage, stage),
            "count": row.count or 0,
            "avg_days_in_stage": round(row.avg_days or 0, 1),
            "is_bottleneck": (row.avg_days or 0) > 7  # More than 7 days = potential bottleneck
        }

    return PipelineHealthMetrics(
        total_in_pipeline=total_in_pipeline,
        stuck_candidates=stuck_candidates,
        high_score_waiting=high_score_waiting,
        urgent_vacancies_without_candidates=urgent_without,
        stages_health=stages_health,
    )


@router.get("/weekly-report", response_model=Dict[str, Any])
async def get_weekly_report(
    department_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get weekly hiring report summary."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)

    base_filter = [Vacancy.org_id == org.id]
    if department_id:
        base_filter.append(Vacancy.department_id == department_id)

    # This week metrics
    this_week_result = await db.execute(
        select(
            func.count(VacancyApplication.id).label("total"),
            func.sum(case((VacancyApplication.stage == 'hired', 1), else_=0)).label("hired"),
            func.sum(case((VacancyApplication.stage == 'rejected', 1), else_=0)).label("rejected"),
        )
        .select_from(VacancyApplication)
        .join(Vacancy, VacancyApplication.vacancy_id == Vacancy.id)
        .where(
            *base_filter,
            VacancyApplication.applied_at >= week_ago
        )
    )
    this_week = this_week_result.first()

    # Last week metrics (for comparison)
    last_week_result = await db.execute(
        select(
            func.count(VacancyApplication.id).label("total"),
            func.sum(case((VacancyApplication.stage == ApplicationStage.hired, 1), else_=0)).label("hired"),
        )
        .select_from(VacancyApplication)
        .join(Vacancy, VacancyApplication.vacancy_id == Vacancy.id)
        .where(
            *base_filter,
            VacancyApplication.applied_at >= two_weeks_ago,
            VacancyApplication.applied_at < week_ago
        )
    )
    last_week = last_week_result.first()

    # Vacancies opened/closed this week
    vacancies_result = await db.execute(
        select(
            func.sum(case((Vacancy.published_at >= week_ago, 1), else_=0)).label("opened"),
            func.sum(case(
                (and_(Vacancy.status == VacancyStatus.closed, Vacancy.updated_at >= week_ago), 1),
                else_=0
            )).label("closed"),
        )
        .where(*base_filter)
    )
    vacancies = vacancies_result.first()

    # Calculate changes
    this_week_total = this_week.total or 0
    last_week_total = last_week.total or 0
    applications_change = this_week_total - last_week_total
    applications_change_pct = round((applications_change / last_week_total * 100), 1) if last_week_total > 0 else 0

    return {
        "period": f"{week_ago.strftime('%d.%m')} - {now.strftime('%d.%m.%Y')}",
        "applications": {
            "total": this_week_total,
            "change": applications_change,
            "change_percent": applications_change_pct,
        },
        "hires": {
            "total": this_week.hired or 0,
            "last_week": last_week.hired or 0,
        },
        "rejections": this_week.rejected or 0,
        "vacancies": {
            "opened": vacancies.opened or 0,
            "closed": vacancies.closed or 0,
        },
        "generated_at": now.isoformat(),
    }
