"""
Recruiter Workspaces API — personal spaces for each recruiter.

Endpoints:
- GET /api/workspaces — list of recruiter workspaces (admin sees all, hr sees own)
- GET /api/workspaces/{recruiter_id} — workspace details for a specific recruiter
- GET /api/workspaces/{recruiter_id}/candidates — all candidates in recruiter's funnels
"""
import logging
from typing import Optional, List
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, and_, or_, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.database import get_db
from api.models.database import (
    User, UserRole, Organization, OrgMember, OrgRole,
    Vacancy, VacancyStatus, VacancyApplication, ApplicationStage,
    Entity,
)
from api.services.auth import get_current_user, get_user_org
from ..services.hr_stages import STAGE_LABELS

logger = logging.getLogger("hr-analyzer.workspaces")

router = APIRouter()


# --- Pydantic schemas ---

class WorkspaceSummary(BaseModel):
    recruiter_id: int
    name: str
    email: str
    org_role: str
    vacancy_count: int
    candidate_count: int
    active_applications: int  # applications in active stages (not rejected/hired/withdrawn)

    class Config:
        from_attributes = True


class WorkspaceVacancy(BaseModel):
    id: int
    title: str
    status: str
    candidate_count: int
    department_name: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class WorkspaceDetail(BaseModel):
    recruiter_id: int
    name: str
    email: str
    vacancies: List[WorkspaceVacancy]
    total_candidates: int
    active_candidates: int

    class Config:
        from_attributes = True


class WorkspaceCandidate(BaseModel):
    id: int
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    telegram: Optional[str] = None
    vacancy_title: str
    vacancy_id: int
    stage: str
    stage_label: str
    applied_at: Optional[datetime] = None
    source: Optional[str] = None

    class Config:
        from_attributes = True


# Подписи этапов — общий справочник (services/hr_stages.py).
APPLICATION_STAGE_LABELS = STAGE_LABELS

ACTIVE_STAGES = [
    ApplicationStage.applied, ApplicationStage.screening,
    ApplicationStage.phone_screen, ApplicationStage.interview,
    ApplicationStage.assessment, ApplicationStage.offer,
]


# --- Helpers ---

async def _get_org_hr_users(org_id: int, db: AsyncSession) -> List[User]:
    """Get all users with HR roles in the organization."""
    result = await db.execute(
        select(User)
        .join(OrgMember, OrgMember.user_id == User.id)
        .where(
            OrgMember.org_id == org_id,
            OrgMember.role.in_([OrgRole.owner, OrgRole.admin, OrgRole.hr]),
        )
        .order_by(User.name)
    )
    return list(result.scalars().all())


async def _get_user_org_role(user_id: int, org_id: int, db: AsyncSession) -> Optional[OrgRole]:
    """Get user's role in organization."""
    result = await db.execute(
        select(OrgMember.role).where(
            OrgMember.user_id == user_id,
            OrgMember.org_id == org_id,
        )
    )
    row = result.scalar_one_or_none()
    return row


async def _can_view_all_workspaces(user: User, org_id: int, db: AsyncSession) -> bool:
    """Check if user can see all recruiter workspaces (admin/owner/superadmin)."""
    if user.role == UserRole.superadmin:
        return True
    role = await _get_user_org_role(user.id, org_id, db)
    return role in (OrgRole.owner, OrgRole.admin)


# --- Routes ---

@router.get("", response_model=List[WorkspaceSummary])
async def list_workspaces(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List recruiter workspaces.
    - Admin/Owner/Superadmin: see all recruiters with stats
    - HR: see only own workspace
    """
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=403, detail="No organization found")

    can_view_all = await _can_view_all_workspaces(current_user, org.id, db)

    if can_view_all:
        recruiters = await _get_org_hr_users(org.id, db)
    else:
        recruiters = [current_user]

    # Build a map of recruiter_id -> org_role
    role_map = {}
    for recruiter in recruiters:
        role = await _get_user_org_role(recruiter.id, org.id, db)
        role_map[recruiter.id] = role.value if role else "member"

    workspaces = []
    for recruiter in recruiters:
        # Count vacancies created by this recruiter
        vac_count_q = await db.execute(
            select(func.count(Vacancy.id)).where(
                Vacancy.created_by == recruiter.id,
                Vacancy.org_id == org.id,
            )
        )
        vacancy_count = vac_count_q.scalar() or 0

        # Count unique candidates in this recruiter's vacancies
        cand_count_q = await db.execute(
            select(func.count(func.distinct(VacancyApplication.entity_id)))
            .join(Vacancy, VacancyApplication.vacancy_id == Vacancy.id)
            .where(Vacancy.created_by == recruiter.id, Vacancy.org_id == org.id)
        )
        candidate_count = cand_count_q.scalar() or 0

        # Count active applications (not rejected/hired/withdrawn)
        active_q = await db.execute(
            select(func.count(VacancyApplication.id))
            .join(Vacancy, VacancyApplication.vacancy_id == Vacancy.id)
            .where(
                Vacancy.created_by == recruiter.id,
                Vacancy.org_id == org.id,
                VacancyApplication.stage.in_(ACTIVE_STAGES),
            )
        )
        active_applications = active_q.scalar() or 0

        workspaces.append(WorkspaceSummary(
            recruiter_id=recruiter.id,
            name=recruiter.name or recruiter.email,
            email=recruiter.email,
            org_role=role_map.get(recruiter.id, "member"),
            vacancy_count=vacancy_count,
            candidate_count=candidate_count,
            active_applications=active_applications,
        ))

    return workspaces


@router.get("/{recruiter_id}", response_model=WorkspaceDetail)
async def get_workspace(
    recruiter_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get workspace details for a specific recruiter."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=403, detail="No organization found")

    # Access check: only self or admin
    can_view_all = await _can_view_all_workspaces(current_user, org.id, db)
    if not can_view_all and current_user.id != recruiter_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Get recruiter info
    recruiter = await db.get(User, recruiter_id)
    if not recruiter:
        raise HTTPException(status_code=404, detail="Recruiter not found")

    # Get vacancies
    vac_result = await db.execute(
        select(Vacancy)
        .where(
            Vacancy.created_by == recruiter_id,
            Vacancy.org_id == org.id,
        )
        .order_by(Vacancy.status, Vacancy.created_at.desc())
    )
    vacancies = vac_result.scalars().all()

    workspace_vacancies = []
    total_candidates = 0
    active_candidates = 0

    for v in vacancies:
        # Count candidates per vacancy
        count_q = await db.execute(
            select(func.count(VacancyApplication.id))
            .where(VacancyApplication.vacancy_id == v.id)
        )
        cand_count = count_q.scalar() or 0

        dept_name = None
        if v.department_id:
            from api.models.database import Department
            dept = await db.get(Department, v.department_id)
            dept_name = dept.name if dept else None

        workspace_vacancies.append(WorkspaceVacancy(
            id=v.id,
            title=v.title,
            status=v.status.value if v.status else "draft",
            candidate_count=cand_count,
            department_name=dept_name,
            created_at=v.created_at,
        ))
        total_candidates += cand_count

    # Count active candidates across all vacancies
    active_q = await db.execute(
        select(func.count(func.distinct(VacancyApplication.entity_id)))
        .join(Vacancy, VacancyApplication.vacancy_id == Vacancy.id)
        .where(
            Vacancy.created_by == recruiter_id,
            Vacancy.org_id == org.id,
            VacancyApplication.stage.in_(ACTIVE_STAGES),
        )
    )
    active_candidates = active_q.scalar() or 0

    return WorkspaceDetail(
        recruiter_id=recruiter.id,
        name=recruiter.name or recruiter.email,
        email=recruiter.email,
        vacancies=workspace_vacancies,
        total_candidates=total_candidates,
        active_candidates=active_candidates,
    )


@router.get("/{recruiter_id}/candidates")
async def get_workspace_candidates(
    recruiter_id: int,
    search: Optional[str] = None,
    vacancy_id: Optional[int] = None,
    stage: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all candidates in a recruiter's funnels."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=403, detail="No organization found")

    can_view_all = await _can_view_all_workspaces(current_user, org.id, db)
    if not can_view_all and current_user.id != recruiter_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Base query: candidates in recruiter's vacancies
    query = (
        select(
            Entity.id,
            Entity.name,
            Entity.email,
            Entity.phone,
            Entity.telegram_usernames,
            Vacancy.title.label("vacancy_title"),
            Vacancy.id.label("vacancy_id"),
            VacancyApplication.stage,
            VacancyApplication.applied_at,
            VacancyApplication.source,
        )
        .join(VacancyApplication, VacancyApplication.entity_id == Entity.id)
        .join(Vacancy, VacancyApplication.vacancy_id == Vacancy.id)
        .where(
            Vacancy.created_by == recruiter_id,
            Vacancy.org_id == org.id,
        )
    )

    # Filters
    if search:
        term = f"%{search}%"
        from ..services.search_index import name_search_conditions, ensure_pg_trgm_checked, contact_search_conditions
        await ensure_pg_trgm_checked(db)
        query = query.where(
            or_(
                *name_search_conditions(search),  # умный поиск по имени (транслит+порядок+опечатки)
                *contact_search_conditions(search),  # почта/телефон(норм.)/telegram + доп-списки
            )
        )

    if vacancy_id:
        query = query.where(Vacancy.id == vacancy_id)

    if stage:
        try:
            stage_enum = ApplicationStage(stage)
            query = query.where(VacancyApplication.stage == stage_enum)
        except ValueError:
            pass

    # Count total
    from sqlalchemy import text as sa_text
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    query = query.order_by(VacancyApplication.applied_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    rows = result.all()

    candidates = []
    for row in rows:
        telegram = None
        if row.telegram_usernames:
            if isinstance(row.telegram_usernames, list) and len(row.telegram_usernames) > 0:
                telegram = row.telegram_usernames[0]
            elif isinstance(row.telegram_usernames, str):
                telegram = row.telegram_usernames

        stage_val = row.stage.value if row.stage else "applied"

        candidates.append({
            "id": row.id,
            "name": row.name,
            "email": row.email,
            "phone": row.phone,
            "telegram": telegram,
            "vacancy_title": row.vacancy_title,
            "vacancy_id": row.vacancy_id,
            "stage": stage_val,
            "stage_label": APPLICATION_STAGE_LABELS.get(stage_val, stage_val),
            "applied_at": row.applied_at.isoformat() if row.applied_at else None,
            "source": row.source,
        })

    return {"items": candidates, "total": total, "skip": skip, "limit": limit}
