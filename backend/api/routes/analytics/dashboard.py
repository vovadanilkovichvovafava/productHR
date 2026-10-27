"""
HR Analytics Dashboard

Provides endpoints for dashboard overview statistics:
- Key metrics (vacancies, candidates, hiring rate)
- Trends over time
- Quick stats
"""

from datetime import datetime, timedelta, date
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, case, distinct
from pydantic import BaseModel

from ...database import get_db
from ...models.database import (
    User, UserRole, Vacancy, VacancyStatus, VacancyApplication,
    ApplicationStage, Entity, EntityStatus, Department,
    OrgMember, OrgRole, DepartmentMember, DeptRole
)
from ...services.auth import get_current_user, get_user_org
from ...utils.logging import get_logger

logger = get_logger("analytics-dashboard")

router = APIRouter()


# ==================== ROLE-BASED FILTERING HELPERS ====================

async def get_user_analytics_scope(user: User, org_id: int, db: AsyncSession) -> dict:
    """
    Get user's analytics scope based on their role.

    Returns dict with:
    - scope: 'all' | 'department' | 'own'
    - department_ids: Set[int] - department IDs user can access (for department scope)
    - user_id: int - user ID (for own scope)
    """
    # Superadmin sees everything
    if user.role == UserRole.superadmin:
        return {"scope": "all", "department_ids": set(), "user_id": user.id}

    # Check org role
    org_member_result = await db.execute(
        select(OrgMember.role).where(
            OrgMember.org_id == org_id,
            OrgMember.user_id == user.id
        )
    )
    org_role = org_member_result.scalar_one_or_none()

    # Owner sees everything in org
    if org_role == OrgRole.owner:
        return {"scope": "all", "department_ids": set(), "user_id": user.id}

    # Check if user is lead or sub_admin in any department
    dept_result = await db.execute(
        select(DepartmentMember.department_id, DepartmentMember.role).where(
            DepartmentMember.user_id == user.id
        )
    )
    dept_memberships = dept_result.all()

    admin_dept_ids = set()
    for dept_id, role in dept_memberships:
        if role in [DeptRole.lead, DeptRole.sub_admin]:
            admin_dept_ids.add(dept_id)

    # Lead/Sub_admin sees their department(s) data
    if admin_dept_ids:
        return {"scope": "department", "department_ids": admin_dept_ids, "user_id": user.id}

    # Member sees only their own data
    return {"scope": "own", "department_ids": set(), "user_id": user.id}


# Schemas
class DashboardOverview(BaseModel):
    # Vacancies
    vacancies_total: int
    vacancies_open: int
    vacancies_draft: int
    vacancies_closed_this_month: int

    # Candidates
    candidates_total: int
    candidates_new_this_month: int
    candidates_in_pipeline: int

    # Applications
    applications_total: int
    applications_this_month: int

    # Hiring
    hires_this_month: int
    hires_this_quarter: int
    avg_time_to_hire_days: Optional[float]

    # Rejection
    rejections_this_month: int


class TrendDataPoint(BaseModel):
    date: str
    value: int


class DashboardTrends(BaseModel):
    applications_trend: List[TrendDataPoint]
    hires_trend: List[TrendDataPoint]
    vacancies_trend: List[TrendDataPoint]


class VacancyQuickStat(BaseModel):
    id: int
    title: str
    department_name: Optional[str]
    status: str
    applications_count: int
    days_open: int
    avg_score: Optional[float]


class TopPerformerStat(BaseModel):
    user_id: int
    user_name: str
    hires_count: int
    applications_processed: int


@router.get("/overview", response_model=DashboardOverview)
async def get_dashboard_overview(
    department_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get dashboard overview statistics based on user role."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    try:
        now = datetime.utcnow()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        quarter_start = now.replace(month=((now.month - 1) // 3) * 3 + 1, day=1, hour=0, minute=0, second=0, microsecond=0)

        # Get user's analytics scope based on role
        scope = await get_user_analytics_scope(current_user, org.id, db)

        # Base filters - always filter by org
        vacancy_filter = [Vacancy.org_id == org.id]
        entity_filter = [Entity.org_id == org.id]

        # Apply role-based filtering
        if scope["scope"] == "own":
            # Member sees only their own data
            vacancy_filter.append(Vacancy.created_by == current_user.id)
            entity_filter.append(Entity.created_by == current_user.id)
        elif scope["scope"] == "department":
            # Lead/Sub_admin sees their department(s) data
            if scope["department_ids"]:
                vacancy_filter.append(Vacancy.department_id.in_(scope["department_ids"]))
                entity_filter.append(Entity.department_id.in_(scope["department_ids"]))

        # Override with explicit department_id if provided (for drill-down)
        if department_id:
            # Only allow if user has access to this department
            if scope["scope"] == "all" or department_id in scope["department_ids"]:
                vacancy_filter = [Vacancy.org_id == org.id, Vacancy.department_id == department_id]
                entity_filter = [Entity.org_id == org.id, Entity.department_id == department_id]

        # Теневая база: архивные кандидаты не учитываются в статистике дашборда
        entity_filter.append(Entity.is_archived.is_not(True))

        # Vacancies stats
        vacancies_result = await db.execute(
            select(
                func.count(Vacancy.id).label("total"),
                func.sum(case((Vacancy.status == VacancyStatus.open, 1), else_=0)).label("open"),
                func.sum(case((Vacancy.status == VacancyStatus.draft, 1), else_=0)).label("draft"),
                func.sum(case(
                    (and_(Vacancy.status == VacancyStatus.closed, Vacancy.updated_at >= month_start), 1),
                    else_=0
                )).label("closed_this_month"),
            ).where(*vacancy_filter)
        )
        vac_row = vacancies_result.first()

        # Candidates stats - use string values for status comparison
        pipeline_statuses = ['new', 'screening', 'practice', 'tech_practice', 'is_interview', 'offer']
        candidates_result = await db.execute(
            select(
                func.count(Entity.id).label("total"),
                func.sum(case((Entity.created_at >= month_start, 1), else_=0)).label("new_this_month"),
                func.sum(case(
                    (Entity.status.in_(pipeline_statuses), 1),
                    else_=0
                )).label("in_pipeline"),
            ).where(
                *entity_filter,
                Entity.type == "candidate"
            )
        )
        cand_row = candidates_result.first()

        # Applications stats - apply same role-based filters via vacancy
        apps_query = (
            select(
                func.count(VacancyApplication.id).label("total"),
                func.sum(case((VacancyApplication.applied_at >= month_start, 1), else_=0)).label("this_month"),
            ).select_from(VacancyApplication)
            .join(Vacancy, VacancyApplication.vacancy_id == Vacancy.id)
            .where(*vacancy_filter)
        )
        apps_result = await db.execute(apps_query)
        apps_row = apps_result.first()

        # Hires stats - count both VacancyApplication hired AND Entity with hired status
        # 1. VacancyApplication hires (through vacancy pipeline)
        vacancy_hires_query = (
            select(
                func.sum(case((VacancyApplication.last_stage_change_at >= month_start, 1), else_=0)).label("this_month"),
                func.sum(case((VacancyApplication.last_stage_change_at >= quarter_start, 1), else_=0)).label("this_quarter"),
            ).select_from(VacancyApplication)
            .join(Vacancy, VacancyApplication.vacancy_id == Vacancy.id)
            .where(
                *vacancy_filter,
                VacancyApplication.stage == 'hired'
            )
        )
        vacancy_hires_result = await db.execute(vacancy_hires_query)
        vacancy_hires_row = vacancy_hires_result.first()

        # 2. Entity hires (candidates with hired status not in any vacancy)
        # Find entity IDs that have VacancyApplications with hired stage
        hired_via_vacancy_subq = (
            select(VacancyApplication.entity_id)
            .where(VacancyApplication.stage == 'hired')
            .distinct()
        )
        # Count entities with hired status that are NOT in the vacancy hired list
        entity_hires_query = (
            select(
                func.sum(case((Entity.updated_at >= month_start, 1), else_=0)).label("this_month"),
                func.sum(case((Entity.updated_at >= quarter_start, 1), else_=0)).label("this_quarter"),
            ).where(
                *entity_filter,
                Entity.type == "candidate",
                Entity.status == EntityStatus.hired,
                Entity.id.notin_(hired_via_vacancy_subq)
            )
        )
        entity_hires_result = await db.execute(entity_hires_query)
        entity_hires_row = entity_hires_result.first()

        # Combine both counts
        hires_this_month = (
            int(vacancy_hires_row.this_month or 0) +
            int(entity_hires_row.this_month or 0) if entity_hires_row else 0
        )
        hires_this_quarter = (
            int(vacancy_hires_row.this_quarter or 0) +
            int(entity_hires_row.this_quarter or 0) if entity_hires_row else 0
        )

        # Rejections this month - apply same role-based filters via vacancy
        rejections_result = await db.execute(
            select(func.count(VacancyApplication.id))
            .select_from(VacancyApplication)
            .join(Vacancy, VacancyApplication.vacancy_id == Vacancy.id)
            .where(
                *vacancy_filter,
                VacancyApplication.stage == 'rejected',
                VacancyApplication.last_stage_change_at >= month_start
            )
        )
        rejections_count = rejections_result.scalar() or 0

        # Average time to hire (for hires this quarter) - combines vacancy and entity data
        avg_time_to_hire = None
        try:
            # Time to hire from VacancyApplications
            vacancy_time_result = await db.execute(
                select(
                    func.avg(
                        func.extract('epoch', VacancyApplication.last_stage_change_at - VacancyApplication.applied_at) / 86400
                    )
                ).select_from(VacancyApplication)
                .join(Vacancy, VacancyApplication.vacancy_id == Vacancy.id)
                .where(
                    *vacancy_filter,
                    VacancyApplication.stage == 'hired',
                    VacancyApplication.last_stage_change_at >= quarter_start
                )
            )
            vacancy_avg = vacancy_time_result.scalar()

            # Time to hire from Entities (created_at to updated_at for hired status)
            entity_time_result = await db.execute(
                select(
                    func.avg(
                        func.extract('epoch', Entity.updated_at - Entity.created_at) / 86400
                    )
                ).where(
                    *entity_filter,
                    Entity.type == "candidate",
                    Entity.status == EntityStatus.hired,
                    Entity.updated_at >= quarter_start,
                    Entity.id.notin_(hired_via_vacancy_subq)
                )
            )
            entity_avg = entity_time_result.scalar()

            # Combine averages (weighted by count would be better, but simple average is ok)
            if vacancy_avg and entity_avg:
                avg_time_to_hire = (vacancy_avg + entity_avg) / 2
            else:
                avg_time_to_hire = vacancy_avg or entity_avg

        except Exception as e:
            logger.warning(f"Failed to calculate avg time to hire: {e}")

        return DashboardOverview(
            vacancies_total=int(vac_row.total or 0),
            vacancies_open=int(vac_row.open or 0),
            vacancies_draft=int(vac_row.draft or 0),
            vacancies_closed_this_month=int(vac_row.closed_this_month or 0),
            candidates_total=int(cand_row.total or 0),
            candidates_new_this_month=int(cand_row.new_this_month or 0),
            candidates_in_pipeline=int(cand_row.in_pipeline or 0),
            applications_total=int(apps_row.total or 0) if apps_row else 0,
            applications_this_month=int(apps_row.this_month or 0) if apps_row else 0,
            hires_this_month=hires_this_month,
            hires_this_quarter=hires_this_quarter,
            avg_time_to_hire_days=round(avg_time_to_hire, 1) if avg_time_to_hire else None,
            rejections_this_month=int(rejections_count),
        )
    except Exception as e:
        logger.error(f"Dashboard overview error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load analytics: {str(e)}")


@router.get("/trends", response_model=DashboardTrends)
async def get_dashboard_trends(
    days: int = Query(30, ge=7, le=90),
    department_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get trend data for dashboard charts based on user role."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    now = datetime.utcnow()
    start_date = (now - timedelta(days=days)).date()

    # Get user's analytics scope based on role
    scope = await get_user_analytics_scope(current_user, org.id, db)

    # Build role-based filters for vacancy
    vacancy_filters = [Vacancy.org_id == org.id]
    if scope["scope"] == "own":
        vacancy_filters.append(Vacancy.created_by == current_user.id)
    elif scope["scope"] == "department" and scope["department_ids"]:
        vacancy_filters.append(Vacancy.department_id.in_(scope["department_ids"]))

    # Override with explicit department_id if provided
    if department_id:
        if scope["scope"] == "all" or department_id in scope["department_ids"]:
            vacancy_filters = [Vacancy.org_id == org.id, Vacancy.department_id == department_id]

    # Applications trend by date
    apps_query = (
        select(
            func.date(VacancyApplication.applied_at).label("date"),
            func.count(VacancyApplication.id).label("count")
        )
        .select_from(VacancyApplication)
        .join(Vacancy, VacancyApplication.vacancy_id == Vacancy.id)
        .where(
            *vacancy_filters,
            VacancyApplication.applied_at >= start_date
        )
        .group_by(func.date(VacancyApplication.applied_at))
        .order_by(func.date(VacancyApplication.applied_at))
    )

    apps_result = await db.execute(apps_query)
    applications_trend = [
        TrendDataPoint(date=str(row.date), value=row.count)
        for row in apps_result
    ]

    # Hires trend by date
    hires_query = (
        select(
            func.date(VacancyApplication.last_stage_change_at).label("date"),
            func.count(VacancyApplication.id).label("count")
        )
        .select_from(VacancyApplication)
        .join(Vacancy, VacancyApplication.vacancy_id == Vacancy.id)
        .where(
            *vacancy_filters,
            VacancyApplication.stage == ApplicationStage.hired,
            VacancyApplication.last_stage_change_at >= start_date
        )
        .group_by(func.date(VacancyApplication.last_stage_change_at))
        .order_by(func.date(VacancyApplication.last_stage_change_at))
    )

    hires_result = await db.execute(hires_query)
    hires_trend = [
        TrendDataPoint(date=str(row.date), value=row.count)
        for row in hires_result
    ]

    # Vacancies opened trend
    vacancies_query = (
        select(
            func.date(Vacancy.published_at).label("date"),
            func.count(Vacancy.id).label("count")
        )
        .where(
            *vacancy_filters,
            Vacancy.published_at >= start_date,
            Vacancy.published_at.isnot(None)
        )
        .group_by(func.date(Vacancy.published_at))
        .order_by(func.date(Vacancy.published_at))
    )

    vacancies_result = await db.execute(vacancies_query)
    vacancies_trend = [
        TrendDataPoint(date=str(row.date), value=row.count)
        for row in vacancies_result
    ]

    return DashboardTrends(
        applications_trend=applications_trend,
        hires_trend=hires_trend,
        vacancies_trend=vacancies_trend,
    )


@router.get("/top-vacancies", response_model=List[VacancyQuickStat])
async def get_top_vacancies(
    limit: int = Query(5, ge=1, le=20),
    status: Optional[VacancyStatus] = VacancyStatus.open,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get top vacancies by application count based on user role."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Get user's analytics scope based on role
    scope = await get_user_analytics_scope(current_user, org.id, db)

    # Build role-based filters
    vacancy_filters = [Vacancy.org_id == org.id]
    if scope["scope"] == "own":
        vacancy_filters.append(Vacancy.created_by == current_user.id)
    elif scope["scope"] == "department" and scope["department_ids"]:
        vacancy_filters.append(Vacancy.department_id.in_(scope["department_ids"]))

    # Subquery for application count
    app_counts = (
        select(
            VacancyApplication.vacancy_id,
            func.count(VacancyApplication.id).label("app_count"),
            func.avg(
                case(
                    (VacancyApplication.compatibility_score.isnot(None),
                     func.cast(VacancyApplication.compatibility_score['overall_score'].astext, Float)),
                    else_=None
                )
            ).label("avg_score")
        )
        .group_by(VacancyApplication.vacancy_id)
        .subquery()
    )

    from sqlalchemy import Float

    query = (
        select(
            Vacancy.id,
            Vacancy.title,
            Vacancy.status,
            Vacancy.published_at,
            Department.name.label("department_name"),
            func.coalesce(app_counts.c.app_count, 0).label("applications_count"),
            app_counts.c.avg_score,
        )
        .outerjoin(app_counts, Vacancy.id == app_counts.c.vacancy_id)
        .outerjoin(Department, Vacancy.department_id == Department.id)
        .where(*vacancy_filters)
    )

    if status:
        query = query.where(Vacancy.status == status)

    query = query.order_by(func.coalesce(app_counts.c.app_count, 0).desc()).limit(limit)

    result = await db.execute(query)
    vacancies = []

    for row in result:
        days_open = 0
        if row.published_at:
            days_open = (datetime.utcnow() - row.published_at).days

        vacancies.append(VacancyQuickStat(
            id=row.id,
            title=row.title,
            department_name=row.department_name,
            status=row.status.value,
            applications_count=row.applications_count,
            days_open=days_open,
            avg_score=round(row.avg_score, 1) if row.avg_score else None,
        ))

    return vacancies


@router.get("/departments-summary", response_model=List[Dict[str, Any]])
async def get_departments_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get hiring summary by department based on user role."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Get user's analytics scope based on role
    scope = await get_user_analytics_scope(current_user, org.id, db)

    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Build department filter based on scope
    dept_filters = [Department.org_id == org.id]

    # For member scope, get user's departments only
    if scope["scope"] == "own":
        # Get departments where user is a member
        user_depts = await db.execute(
            select(DepartmentMember.department_id).where(
                DepartmentMember.user_id == current_user.id
            )
        )
        user_dept_ids = {row[0] for row in user_depts}
        if user_dept_ids:
            dept_filters.append(Department.id.in_(user_dept_ids))
        else:
            # User not in any department - return empty
            return []
    elif scope["scope"] == "department" and scope["department_ids"]:
        # Lead/sub_admin sees only their department(s)
        dept_filters.append(Department.id.in_(scope["department_ids"]))

    # Build vacancy filter for counting (also apply role-based filtering)
    vacancy_filters = [Vacancy.org_id == org.id]
    if scope["scope"] == "own":
        vacancy_filters.append(Vacancy.created_by == current_user.id)

    # Get stats by department
    result = await db.execute(
        select(
            Department.id,
            Department.name,
            func.count(distinct(Vacancy.id)).label("vacancies"),
            func.count(distinct(
                case((Vacancy.status == VacancyStatus.open, Vacancy.id), else_=None)
            )).label("open_vacancies"),
            func.count(distinct(VacancyApplication.id)).label("applications"),
            func.count(distinct(
                case((VacancyApplication.stage == ApplicationStage.hired, VacancyApplication.id), else_=None)
            )).label("hires"),
        )
        .select_from(Department)
        .outerjoin(Vacancy, and_(
            Department.id == Vacancy.department_id,
            *vacancy_filters
        ))
        .outerjoin(VacancyApplication, Vacancy.id == VacancyApplication.vacancy_id)
        .where(*dept_filters)
        .group_by(Department.id, Department.name)
        .order_by(Department.name)
    )

    departments = []
    for row in result:
        departments.append({
            "id": row.id,
            "name": row.name,
            "vacancies": row.vacancies or 0,
            "open_vacancies": row.open_vacancies or 0,
            "applications": row.applications or 0,
            "hires": row.hires or 0,
        })

    return departments
