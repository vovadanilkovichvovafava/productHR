"""
PEN (Hiring Effectiveness Index) Dashboard routes.

Endpoints:
- GET /metrics — aggregate hiring metrics (practice, department, probation, 1 year)
- GET /recruiters — per-recruiter breakdown
- GET /salary-sheet — salary sheet (HRD/Lead only)
- POST /bonus — manual bonus entry (HRD/Lead only)
- GET /bonus-rates — default bonus rates per direction
"""
import csv
import io
import logging
from datetime import datetime, timedelta
from typing import Optional, List

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, func, and_, or_, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.database import get_db
from api.models.database import (
    Entity, EntityStatus, Employee, RecruiterBonus,
    User, Organization, OrgMember, OrgRole,
)
from api.services.auth import get_current_user, get_user_org

logger = logging.getLogger("hr-analyzer.pen")

router = APIRouter()

# ─── Bonus rate constants ──────────────────────────────────────
BONUS_RATES = {
    "traffic": {
        "department": 50,   # Practice → Department
        "probation": 100,   # Department → 3 months
        "total": 150,
    },
    "development": {
        "department": 25,
        "probation": 75,
        "total": 100,
    },
    "targeted": {
        "department": 175,   # avg of 150-200
        "probation": 275,    # avg of 250-300
        "total": 450,        # avg of 400-500
    },
}


# ─── Pydantic schemas ──────────────────────────────────────────

class DirectionMetrics(BaseModel):
    traffic: int = 0
    development: int = 0
    total: int = 0


class ConversionMetrics(BaseModel):
    practice_to_dept: Optional[float] = None
    dept_to_probation: Optional[float] = None


class PENMetricsResponse(BaseModel):
    started_practice: DirectionMetrics
    entered_department: DirectionMetrics
    passed_probation: DirectionMetrics
    working_1year: DirectionMetrics
    conversions: ConversionMetrics


class RecruiterMetrics(BaseModel):
    recruiter_id: int
    recruiter_name: str
    started_practice: int = 0
    entered_department: int = 0
    passed_probation: int = 0
    working_1year: int = 0
    total_bonus: int = 0


class SalarySheetCandidate(BaseModel):
    entity_id: Optional[int] = None
    entity_name: str
    direction: str
    stage: str
    amount: int


class SalarySheetEntry(BaseModel):
    recruiter_id: int
    recruiter_name: str
    candidates: List[SalarySheetCandidate]
    total_bonus: int


class BonusCreate(BaseModel):
    recruiter_id: int
    entity_id: Optional[int] = None
    direction: str  # traffic / development / targeted
    stage: str      # practice / department / probation
    amount: int
    notes: Optional[str] = None


class BonusResponse(BaseModel):
    id: int
    org_id: int
    recruiter_id: int
    entity_id: Optional[int] = None
    direction: str
    stage: str
    amount: int
    is_paid: bool
    paid_at: Optional[datetime] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ─── Helpers ────────────────────────────────────────────────────

async def _get_org_and_role(user: User, db: AsyncSession):
    """Get org and role; raise 403 if no org."""
    org = await get_user_org(user, db)
    if not org:
        raise HTTPException(status_code=403, detail="No organization")
    member = await db.execute(
        select(OrgMember).where(
            OrgMember.org_id == org.id,
            OrgMember.user_id == user.id,
        )
    )
    om = member.scalar_one_or_none()
    role = om.role if om else OrgRole.member
    return org, role


def _is_lead_or_above(user: User, role: OrgRole) -> bool:
    """Check if user is HRD/Lead or superadmin."""
    return user.role.value == "superadmin" or role in (OrgRole.owner, OrgRole.admin)


def _get_direction(entity: Entity) -> str:
    """Determine direction from entity extra_data or default."""
    if entity.extra_data and isinstance(entity.extra_data, dict):
        return entity.extra_data.get("direction", "traffic")
    return "traffic"


async def _get_entities_in_period(
    db: AsyncSession,
    org_id: int,
    period_from: Optional[datetime],
    period_to: Optional[datetime],
    recruiter_id: Optional[int] = None,
):
    """Get all entities in org, optionally filtered by period and recruiter."""
    query = select(Entity).where(Entity.org_id == org_id)
    if recruiter_id:
        query = query.where(Entity.created_by == recruiter_id)
    entities = (await db.execute(query)).scalars().all()
    return list(entities)


async def _get_employees_for_org(db: AsyncSession, org_id: int):
    """Get all employees in org with user relation loaded."""
    result = await db.execute(
        select(Employee)
        .options(selectinload(Employee.entity))
        .where(Employee.org_id == org_id)
    )
    return list(result.scalars().all())


def _in_period(dt: Optional[datetime], period_from: Optional[datetime], period_to: Optional[datetime]) -> bool:
    """Check if datetime falls within period."""
    if dt is None:
        return False
    if period_from and dt < period_from:
        return False
    if period_to and dt > period_to:
        return False
    return True


def _compute_metrics(
    entities: list,
    employees: list,
    period_from: Optional[datetime],
    period_to: Optional[datetime],
    direction_filter: Optional[str] = None,
    recruiter_id: Optional[int] = None,
) -> dict:
    """Compute PEN metrics from entities and employees."""
    # Build employee lookup by entity_id
    emp_by_entity = {}
    for emp in employees:
        if emp.entity_id:
            emp_by_entity[emp.entity_id] = emp

    now = datetime.utcnow()
    metrics = {
        "started_practice": {"traffic": 0, "development": 0},
        "entered_department": {"traffic": 0, "development": 0},
        "passed_probation": {"traffic": 0, "development": 0},
        "working_1year": {"traffic": 0, "development": 0},
    }

    for entity in entities:
        direction = _get_direction(entity)
        if direction_filter and direction_filter != "all" and direction != direction_filter:
            continue
        if recruiter_id and entity.created_by != recruiter_id:
            continue

        emp = emp_by_entity.get(entity.id)

        # Practice: entity status is practice/tech_practice, or employee has practice_start_date
        practice_date = None
        if emp and emp.practice_start_date:
            practice_date = emp.practice_start_date
        elif entity.status in (EntityStatus.practice, EntityStatus.tech_practice):
            practice_date = entity.updated_at or entity.created_at
        # Also entities that already passed practice (hired etc.)
        if emp and emp.practice_start_date:
            practice_date = emp.practice_start_date

        if practice_date and _in_period(practice_date, period_from, period_to):
            metrics["started_practice"][direction] += 1

        # Department: employee has department_start_date (= hired)
        dept_date = emp.department_start_date if emp else None
        if not dept_date and entity.status == EntityStatus.hired:
            dept_date = entity.updated_at or entity.created_at
        if dept_date and _in_period(dept_date, period_from, period_to):
            metrics["entered_department"][direction] += 1

        # Passed probation: hired + 3 months + still active
        if dept_date:
            probation_end = dept_date + relativedelta(months=3)
            if emp and emp.probation_end_date:
                probation_end = emp.probation_end_date
            is_active = emp.is_active if emp else (entity.status == EntityStatus.hired)
            if probation_end <= now and is_active and _in_period(probation_end, period_from, period_to):
                metrics["passed_probation"][direction] += 1

        # Working 1 year+: hired + 1 year + still active
        if dept_date:
            one_year = dept_date + relativedelta(years=1)
            if emp and emp.one_year_date:
                one_year = emp.one_year_date
            is_active = emp.is_active if emp else (entity.status == EntityStatus.hired)
            if one_year <= now and is_active and _in_period(one_year, period_from, period_to):
                metrics["working_1year"][direction] += 1

    return metrics


# ─── Routes ─────────────────────────────────────────────────────

@router.get("/metrics", response_model=PENMetricsResponse)
async def get_pen_metrics(
    period_from: Optional[datetime] = Query(None),
    period_to: Optional[datetime] = Query(None),
    recruiter_id: Optional[int] = Query(None),
    direction: Optional[str] = Query(None, description="traffic/development/all"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get aggregate PEN metrics for the organization."""
    org, role = await _get_org_and_role(user, db)

    # Recruiters can only see their own
    effective_recruiter = recruiter_id
    if not _is_lead_or_above(user, role):
        effective_recruiter = user.id

    entities = await _get_entities_in_period(db, org.id, period_from, period_to, effective_recruiter)
    employees = await _get_employees_for_org(db, org.id)

    raw = _compute_metrics(entities, employees, period_from, period_to, direction, effective_recruiter)

    def to_direction_metrics(d: dict) -> DirectionMetrics:
        return DirectionMetrics(
            traffic=d["traffic"],
            development=d["development"],
            total=d["traffic"] + d["development"],
        )

    sp = to_direction_metrics(raw["started_practice"])
    ed = to_direction_metrics(raw["entered_department"])
    pp = to_direction_metrics(raw["passed_probation"])
    w1 = to_direction_metrics(raw["working_1year"])

    # Conversions
    practice_to_dept = (ed.total / sp.total * 100) if sp.total > 0 else None
    dept_to_probation = (pp.total / ed.total * 100) if ed.total > 0 else None

    return PENMetricsResponse(
        started_practice=sp,
        entered_department=ed,
        passed_probation=pp,
        working_1year=w1,
        conversions=ConversionMetrics(
            practice_to_dept=round(practice_to_dept, 1) if practice_to_dept is not None else None,
            dept_to_probation=round(dept_to_probation, 1) if dept_to_probation is not None else None,
        ),
    )


@router.get("/recruiters", response_model=List[RecruiterMetrics])
async def get_pen_recruiters(
    period_from: Optional[datetime] = Query(None),
    period_to: Optional[datetime] = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get per-recruiter PEN breakdown. Lead/HRD only."""
    org, role = await _get_org_and_role(user, db)
    if not _is_lead_or_above(user, role):
        raise HTTPException(status_code=403, detail="Lead/HRD access required")

    entities = await _get_entities_in_period(db, org.id, period_from, period_to)
    employees = await _get_employees_for_org(db, org.id)

    # Get all recruiters (users who created entities)
    recruiter_ids = set(e.created_by for e in entities if e.created_by)
    recruiters = {}
    if recruiter_ids:
        result = await db.execute(
            select(User).where(User.id.in_(recruiter_ids))
        )
        for u in result.scalars().all():
            recruiters[u.id] = u

    # Get bonuses for the period
    bonus_query = select(RecruiterBonus).where(RecruiterBonus.org_id == org.id)
    if period_from:
        bonus_query = bonus_query.where(RecruiterBonus.created_at >= period_from)
    if period_to:
        bonus_query = bonus_query.where(RecruiterBonus.created_at <= period_to)
    bonuses_result = await db.execute(bonus_query)
    bonuses = list(bonuses_result.scalars().all())

    bonus_by_recruiter: dict[int, int] = {}
    for b in bonuses:
        bonus_by_recruiter[b.recruiter_id] = bonus_by_recruiter.get(b.recruiter_id, 0) + b.amount

    result_list = []
    for rid, ruser in recruiters.items():
        raw = _compute_metrics(entities, employees, period_from, period_to, None, rid)
        result_list.append(RecruiterMetrics(
            recruiter_id=rid,
            recruiter_name=ruser.name,
            started_practice=raw["started_practice"]["traffic"] + raw["started_practice"]["development"],
            entered_department=raw["entered_department"]["traffic"] + raw["entered_department"]["development"],
            passed_probation=raw["passed_probation"]["traffic"] + raw["passed_probation"]["development"],
            working_1year=raw["working_1year"]["traffic"] + raw["working_1year"]["development"],
            total_bonus=bonus_by_recruiter.get(rid, 0),
        ))

    # Sort by total bonus descending
    result_list.sort(key=lambda x: x.total_bonus, reverse=True)
    return result_list


@router.get("/salary-sheet")
async def get_salary_sheet(
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2020),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get salary sheet for a specific month. HRD/Lead only."""
    org, role = await _get_org_and_role(user, db)
    if not _is_lead_or_above(user, role):
        raise HTTPException(status_code=403, detail="Lead/HRD access required")

    period_from = datetime(year, month, 1)
    if month == 12:
        period_to = datetime(year + 1, 1, 1)
    else:
        period_to = datetime(year, month + 1, 1)

    # Get bonuses for the month
    result = await db.execute(
        select(RecruiterBonus)
        .options(selectinload(RecruiterBonus.entity))
        .where(
            RecruiterBonus.org_id == org.id,
            RecruiterBonus.created_at >= period_from,
            RecruiterBonus.created_at < period_to,
        )
        .order_by(RecruiterBonus.recruiter_id)
    )
    bonuses = list(result.scalars().all())

    # Group by recruiter
    by_recruiter: dict[int, list] = {}
    for b in bonuses:
        by_recruiter.setdefault(b.recruiter_id, []).append(b)

    # Get recruiter names
    recruiter_ids = list(by_recruiter.keys())
    recruiter_names = {}
    if recruiter_ids:
        users_result = await db.execute(
            select(User).where(User.id.in_(recruiter_ids))
        )
        for u in users_result.scalars().all():
            recruiter_names[u.id] = u.name

    entries = []
    for rid, bonus_list in by_recruiter.items():
        candidates = []
        total = 0
        for b in bonus_list:
            entity_name = b.entity.name if b.entity else f"ID:{b.entity_id}" if b.entity_id else "N/A"
            candidates.append(SalarySheetCandidate(
                entity_id=b.entity_id,
                entity_name=entity_name,
                direction=b.direction,
                stage=b.stage,
                amount=b.amount,
            ))
            total += b.amount
        entries.append(SalarySheetEntry(
            recruiter_id=rid,
            recruiter_name=recruiter_names.get(rid, f"User #{rid}"),
            candidates=candidates,
            total_bonus=total,
        ))

    entries.sort(key=lambda x: x.total_bonus, reverse=True)
    return entries


@router.get("/salary-sheet/csv")
async def export_salary_sheet_csv(
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2020),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export salary sheet as CSV. HRD/Lead only."""
    org, role = await _get_org_and_role(user, db)
    if not _is_lead_or_above(user, role):
        raise HTTPException(status_code=403, detail="Lead/HRD access required")

    period_from = datetime(year, month, 1)
    if month == 12:
        period_to = datetime(year + 1, 1, 1)
    else:
        period_to = datetime(year, month + 1, 1)

    result = await db.execute(
        select(RecruiterBonus)
        .options(selectinload(RecruiterBonus.entity))
        .where(
            RecruiterBonus.org_id == org.id,
            RecruiterBonus.created_at >= period_from,
            RecruiterBonus.created_at < period_to,
        )
        .order_by(RecruiterBonus.recruiter_id)
    )
    bonuses = list(result.scalars().all())

    # Get recruiter names
    recruiter_ids = list(set(b.recruiter_id for b in bonuses))
    recruiter_names = {}
    if recruiter_ids:
        users_result = await db.execute(select(User).where(User.id.in_(recruiter_ids)))
        for u in users_result.scalars().all():
            recruiter_names[u.id] = u.name

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Рекрутер", "Кандидат", "Направление", "Этап", "Сумма ($)", "Оплачено", "Примечание"])

    for b in bonuses:
        entity_name = b.entity.name if b.entity else f"ID:{b.entity_id}" if b.entity_id else "N/A"
        writer.writerow([
            recruiter_names.get(b.recruiter_id, f"User #{b.recruiter_id}"),
            entity_name,
            b.direction,
            b.stage,
            b.amount,
            "Да" if b.is_paid else "Нет",
            b.notes or "",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=pen_salary_{year}_{month:02d}.csv"},
    )


@router.post("/bonus", response_model=BonusResponse)
async def create_bonus(
    data: BonusCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manual bonus entry. HRD/Lead only — for targeted positions."""
    org, role = await _get_org_and_role(user, db)
    if not _is_lead_or_above(user, role):
        raise HTTPException(status_code=403, detail="Lead/HRD access required")

    if data.direction not in ("traffic", "development", "targeted"):
        raise HTTPException(status_code=400, detail="direction must be traffic, development, or targeted")
    if data.stage not in ("practice", "department", "probation"):
        raise HTTPException(status_code=400, detail="stage must be practice, department, or probation")

    bonus = RecruiterBonus(
        org_id=org.id,
        recruiter_id=data.recruiter_id,
        entity_id=data.entity_id,
        direction=data.direction,
        stage=data.stage,
        amount=data.amount,
        notes=data.notes,
    )
    db.add(bonus)
    await db.commit()
    await db.refresh(bonus)
    return bonus


@router.get("/bonus-rates")
async def get_bonus_rates(
    user: User = Depends(get_current_user),
):
    """Get default bonus rates per direction."""
    return BONUS_RATES
