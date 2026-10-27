"""
Huntflow-style HR Reports Center

Reports:
1. Time to Fill (Время закрытия позиций) — avg close time, avg delay, closed positions, avg time per stage
2. Funnel by Recruiter (Воронка по рекрутерам) — funnel + rejections split by recruiter
3. Rejections (Отказы) — rejection reasons by stage
4. Sources (Источники резюме) — where candidates come from
5. Candidate Movement (Движение кандидатов) — how many moved between stages
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, case, extract, text, cast, String
from pydantic import BaseModel

from ...database import get_db
from ...models.database import (
    User, UserRole, Vacancy, VacancyStatus, VacancyApplication,
    ApplicationStage, Entity, EntityType, StageTransition,
    OrgMember, OrgRole, EntityTag, entity_tag_association,
)
from ...services.auth import get_current_user, get_user_org
from ...utils.logging import get_logger
from ...services.hr_stages import STAGE_LABELS  # общий справочник этапов

logger = get_logger("analytics-reports")

router = APIRouter()

# Stage ordering for funnel
FUNNEL_STAGES = [
    "applied", "screening", "phone_screen", "interview",
    "assessment", "offer", "hired",
]


LEGACY_STAGE_ALIASES = {
    "new": "applied",
}


def _normalize_stage(stage: Optional[str]) -> Optional[str]:
    if not stage:
        return stage
    value = stage.value if hasattr(stage, "value") else str(stage)
    return LEGACY_STAGE_ALIASES.get(value, value)


def _stage_values(stage: str) -> List[str]:
    aliases = [key for key, value in LEGACY_STAGE_ALIASES.items() if value == stage]
    return [stage, *aliases]


# ========== SCHEMAS ==========

class TimeToFillSummary(BaseModel):
    avg_days_to_close: Optional[float]
    avg_delay_days: Optional[float]
    closed_positions: int
    total_positions: int


class StageTimingItem(BaseModel):
    stage: str
    label: str
    avg_days: float


class LastClosing(BaseModel):
    candidate_name: str
    vacancy_title: str
    recruiter_name: Optional[str]
    closed_date: Optional[str]
    days_to_close: Optional[int]
    start_date: Optional[str]


class TimeToFillReport(BaseModel):
    summary: TimeToFillSummary
    stage_timings: List[StageTimingItem]
    last_closings: List[LastClosing]


class FunnelStageData(BaseModel):
    stage: str
    label: str
    candidate_count: int
    rejection_count: int


class SourceBreakdown(BaseModel):
    source: str
    count: int


class RejectionReasonItem(BaseModel):
    reason: str
    count: int


class FunnelReport(BaseModel):
    stages: List[FunnelStageData]
    total_candidates: int
    total_rejections: int
    sources: List[SourceBreakdown]
    rejection_reasons: List[RejectionReasonItem]


class RecruiterFunnelItem(BaseModel):
    recruiter_id: int
    recruiter_name: str
    stages: List[FunnelStageData]
    total_candidates: int
    total_rejections: int


class FunnelByRecruiterReport(BaseModel):
    summary: FunnelReport
    by_recruiter: List[RecruiterFunnelItem]


class RejectionsByStage(BaseModel):
    stage: str
    label: str
    count: int
    reasons: List[RejectionReasonItem]


class RejectionsReport(BaseModel):
    total_rejections: int
    by_stage: List[RejectionsByStage]
    top_reasons: List[RejectionReasonItem]


class SourceReport(BaseModel):
    total_candidates: int
    sources: List[SourceBreakdown]
    by_stage: Dict[str, List[SourceBreakdown]]


class StageMovementItem(BaseModel):
    from_stage: str
    from_label: str
    to_stage: str
    to_label: str
    count: int


class MovementReport(BaseModel):
    total_movements: int
    movements: List[StageMovementItem]


class SourcerStat(BaseModel):
    tag_id: int
    name: str
    color: str
    archived: bool
    brought: int
    in_work: int
    reached_offer: int
    hired: int
    rejected: int
    conversion: float


class SourcersReport(BaseModel):
    items: List[SourcerStat]
    total_brought: int
    total_hired: int


# ========== HELPERS ==========

def _get_date_filter(period: str, date_from_str: Optional[str] = None, date_to_str: Optional[str] = None):
    """Parse period filter into (date_from, date_to) tuple.

    For preset periods: returns (date_from, None).
    For custom range: returns (date_from, date_to).
    """
    if period == "custom" and date_from_str:
        try:
            df = datetime.fromisoformat(date_from_str)
        except ValueError:
            df = None
        dt = None
        if date_to_str:
            try:
                dt = datetime.fromisoformat(date_to_str)
                # Include the full end day
                dt = dt.replace(hour=23, minute=59, second=59)
            except ValueError:
                pass
        return df, dt

    now = datetime.utcnow()
    if period == "current":
        return None, None
    elif period == "month":
        return now - timedelta(days=30), None
    elif period == "quarter":
        return now - timedelta(days=90), None
    elif period == "half_year":
        return now - timedelta(days=180), None
    elif period == "year":
        return now - timedelta(days=365), None
    return None, None


async def _is_admin_analytics(user: User, org_id: int, db: AsyncSession) -> bool:
    """Видит общую аналитику по всей организации: superadmin/owner/admin.
    hr (ограниченный рекрутёр) и member видят только свои данные.
    """
    if user.role == UserRole.superadmin:
        return True
    res = await db.execute(
        select(OrgMember.role).where(
            OrgMember.user_id == user.id,
            OrgMember.org_id == org_id,
        )
    )
    role = res.scalar_one_or_none()
    return role in (OrgRole.owner, OrgRole.admin)


async def _scope_recruiter_id(
    recruiter_id: Optional[int],
    current_user: User,
    org_id: int,
    db: AsyncSession,
) -> Optional[int]:
    """Если юзер не админ-уровня — фильтр всегда current_user.id (любой
    переданный recruiter_id игнорируется). Админ может смотреть кого угодно."""
    if await _is_admin_analytics(current_user, org_id, db):
        return recruiter_id
    return current_user.id


# ========== ENDPOINTS ==========

@router.get("/time-to-fill", response_model=TimeToFillReport)
async def get_time_to_fill(
    period: str = Query("current", description="current|month|quarter|half_year|year|custom"),
    recruiter_id: Optional[int] = None,
    department_id: Optional[int] = None,
    vacancy_status: str = Query("all", description="all|open|closed"),
    date_from: Optional[str] = Query(None, description="Custom range start (ISO date)"),
    date_to: Optional[str] = Query(None, description="Custom range end (ISO date)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Time to Fill report — Huntflow-style 'Время закрытия позиций'."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(404, "Organization not found")

    recruiter_id = await _scope_recruiter_id(recruiter_id, current_user, org.id, db)
    date_from_dt, date_to_dt = _get_date_filter(period, date_from, date_to)

    # --- Closed positions (hired applications) ---
    hired_query = (
        select(
            VacancyApplication.id,
            VacancyApplication.vacancy_id,
            VacancyApplication.entity_id,
            VacancyApplication.applied_at,
            VacancyApplication.last_stage_change_at,
            Vacancy.title.label("vacancy_title"),
            Vacancy.created_by.label("recruiter_id"),
            Entity.name.label("candidate_name"),
        )
        .join(Vacancy, VacancyApplication.vacancy_id == Vacancy.id)
        .join(Entity, VacancyApplication.entity_id == Entity.id)
        .where(
            Vacancy.org_id == org.id,
            VacancyApplication.stage == ApplicationStage.hired,
        )
    )

    if date_from_dt:
        hired_query = hired_query.where(VacancyApplication.last_stage_change_at >= date_from_dt)
    if date_to_dt:
        hired_query = hired_query.where(VacancyApplication.last_stage_change_at <= date_to_dt)
    if recruiter_id:
        hired_query = hired_query.where(Vacancy.created_by == recruiter_id)
    if department_id:
        hired_query = hired_query.where(Vacancy.department_id == department_id)

    hired_result = await db.execute(hired_query.order_by(VacancyApplication.last_stage_change_at.desc()))
    hired_rows = hired_result.all()

    # Calculate avg days to close
    days_list = []
    last_closings = []
    for row in hired_rows:
        if row.applied_at and row.last_stage_change_at:
            days = (row.last_stage_change_at - row.applied_at).days
            days_list.append(days)

            # Get recruiter name
            recruiter = await db.get(User, row.recruiter_id) if row.recruiter_id else None

            last_closings.append(LastClosing(
                candidate_name=row.candidate_name or "—",
                vacancy_title=row.vacancy_title or "—",
                recruiter_name=recruiter.name if recruiter else None,
                closed_date=row.last_stage_change_at.strftime("%d %B %Y") if row.last_stage_change_at else None,
                days_to_close=days,
                start_date=row.applied_at.strftime("%d %B %Y") if row.applied_at else None,
            ))

    avg_days = round(sum(days_list) / len(days_list), 1) if days_list else None

    # Total positions count
    total_q = select(func.count(Vacancy.id)).where(Vacancy.org_id == org.id)
    if department_id:
        total_q = total_q.where(Vacancy.department_id == department_id)
    if vacancy_status == "open":
        total_q = total_q.where(Vacancy.status == VacancyStatus.open)
    elif vacancy_status == "closed":
        total_q = total_q.where(Vacancy.status == VacancyStatus.closed)
    total_result = await db.execute(total_q)
    total_positions = total_result.scalar() or 0

    # --- Average time per stage (from StageTransition) ---
    stage_timings = []
    for stage in FUNNEL_STAGES[:-1]:  # Exclude "hired" — it's the end
        next_idx = FUNNEL_STAGES.index(stage) + 1
        if next_idx < len(FUNNEL_STAGES):
            next_stage = FUNNEL_STAGES[next_idx]

            # Find transitions from this stage to next
            trans_q = (
                select(
                    func.avg(
                        extract('epoch', StageTransition.created_at) -
                        extract('epoch', VacancyApplication.applied_at)
                    )
                )
                .select_from(StageTransition)
                .join(VacancyApplication, StageTransition.application_id == VacancyApplication.id)
                .join(Vacancy, VacancyApplication.vacancy_id == Vacancy.id)
                .where(
                    Vacancy.org_id == org.id,
                    StageTransition.to_stage == next_stage,
                    StageTransition.from_stage == stage,
                )
            )
            if date_from_dt:
                trans_q = trans_q.where(StageTransition.created_at >= date_from_dt)
            if date_to_dt:
                trans_q = trans_q.where(StageTransition.created_at <= date_to_dt)
            if recruiter_id:
                trans_q = trans_q.where(Vacancy.created_by == recruiter_id)
            if department_id:
                trans_q = trans_q.where(Vacancy.department_id == department_id)

            result = await db.execute(trans_q)
            avg_seconds = result.scalar()
            avg_stage_days = round(avg_seconds / 86400, 1) if avg_seconds else 0

            stage_timings.append(StageTimingItem(
                stage=stage,
                label=STAGE_LABELS.get(stage, stage),
                avg_days=avg_stage_days,
            ))

    return TimeToFillReport(
        summary=TimeToFillSummary(
            avg_days_to_close=avg_days,
            avg_delay_days=None,  # TODO: implement deadline comparison
            closed_positions=len(hired_rows),
            total_positions=total_positions,
        ),
        stage_timings=stage_timings,
        last_closings=last_closings[:10],
    )


@router.get("/funnel", response_model=FunnelReport)
async def get_funnel_report(
    period: str = Query("current"),
    recruiter_id: Optional[int] = None,
    department_id: Optional[int] = None,
    vacancy_status: str = Query("open"),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Funnel report — Huntflow-style 'Воронка'."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(404, "Organization not found")

    recruiter_id = await _scope_recruiter_id(recruiter_id, current_user, org.id, db)
    date_from_dt, date_to_dt = _get_date_filter(period, date_from, date_to)

    # Base filter
    base_filter = [Vacancy.org_id == org.id]
    if date_from_dt:
        base_filter.append(VacancyApplication.applied_at >= date_from_dt)
    if date_to_dt:
        base_filter.append(VacancyApplication.applied_at <= date_to_dt)
    if recruiter_id:
        base_filter.append(Vacancy.created_by == recruiter_id)
    if department_id:
        base_filter.append(Vacancy.department_id == department_id)
    if vacancy_status == "open":
        base_filter.append(Vacancy.status == VacancyStatus.open)
    elif vacancy_status == "closed":
        base_filter.append(Vacancy.status == VacancyStatus.closed)

    # Stage counts (including rejected/withdrawn per stage)
    stage_value = cast(VacancyApplication.stage, String)
    stage_q = (
        select(
            stage_value.label("stage"),
            func.count(VacancyApplication.id).label("cnt"),
        )
        .join(Vacancy, VacancyApplication.vacancy_id == Vacancy.id)
        .where(*base_filter)
        .group_by(stage_value)
    )
    stage_result = await db.execute(stage_q)
    stage_counts = {}
    for row in stage_result:
        key = _normalize_stage(row.stage)
        stage_counts[key] = row.cnt

    # Rejections by stage they were on before rejection (from StageTransition)
    rej_by_stage_q = (
        select(
            StageTransition.from_stage,
            func.count(StageTransition.id).label("cnt"),
        )
        .join(VacancyApplication, StageTransition.application_id == VacancyApplication.id)
        .join(Vacancy, VacancyApplication.vacancy_id == Vacancy.id)
        .where(
            Vacancy.org_id == org.id,
            StageTransition.to_stage == "rejected",
        )
        .group_by(StageTransition.from_stage)
    )
    if date_from_dt:
        rej_by_stage_q = rej_by_stage_q.where(StageTransition.created_at >= date_from_dt)
    rej_result = await db.execute(rej_by_stage_q)
    rej_by_stage: Dict[str, int] = {}
    for row in rej_result:
        stage_key = _normalize_stage(row.from_stage)
        if stage_key:
            rej_by_stage[stage_key] = rej_by_stage.get(stage_key, 0) + row.cnt

    # Build funnel
    stages = []
    total_candidates = 0
    total_rejections = stage_counts.get("rejected", 0)

    for stage in FUNNEL_STAGES:
        count = stage_counts.get(stage, 0)
        rej_count = rej_by_stage.get(stage, 0)
        total_candidates += count
        stages.append(FunnelStageData(
            stage=stage,
            label=STAGE_LABELS.get(stage, stage),
            candidate_count=count,
            rejection_count=rej_count,
        ))

    # Sources
    source_q = (
        select(
            VacancyApplication.source,
            func.count(VacancyApplication.id).label("cnt"),
        )
        .join(Vacancy, VacancyApplication.vacancy_id == Vacancy.id)
        .where(*base_filter)
        .where(VacancyApplication.source.isnot(None))
        .group_by(VacancyApplication.source)
        .order_by(func.count(VacancyApplication.id).desc())
    )
    source_result = await db.execute(source_q)
    sources = [
        SourceBreakdown(source=row.source or "Другой", count=row.cnt)
        for row in source_result
    ]

    # Rejection reasons
    reason_q = (
        select(
            VacancyApplication.rejection_reason,
            func.count(VacancyApplication.id).label("cnt"),
        )
        .join(Vacancy, VacancyApplication.vacancy_id == Vacancy.id)
        .where(
            *base_filter,
            VacancyApplication.stage == ApplicationStage.rejected,
            VacancyApplication.rejection_reason.isnot(None),
        )
        .group_by(VacancyApplication.rejection_reason)
        .order_by(func.count(VacancyApplication.id).desc())
    )
    reason_result = await db.execute(reason_q)
    rejection_reasons = [
        RejectionReasonItem(reason=row.rejection_reason or "Другая причина", count=row.cnt)
        for row in reason_result
    ]

    return FunnelReport(
        stages=stages,
        total_candidates=total_candidates,
        total_rejections=total_rejections,
        sources=sources,
        rejection_reasons=rejection_reasons,
    )


@router.get("/funnel-by-recruiter", response_model=FunnelByRecruiterReport)
async def get_funnel_by_recruiter(
    period: str = Query("current"),
    department_id: Optional[int] = None,
    vacancy_status: str = Query("open"),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Funnel with recruiter breakdown — Huntflow-style 'Воронка с детализацией по рекрутерам'."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(404, "Organization not found")

    is_admin = await _is_admin_analytics(current_user, org.id, db)

    # Get summary funnel first.
    # Для не-админа — суммарная воронка по его собственным вакансиям, не по всей оргe.
    summary = await get_funnel_report(
        period=period, recruiter_id=None if is_admin else current_user.id,
        department_id=department_id,
        vacancy_status=vacancy_status,
        date_from=date_from, date_to=date_to,
        db=db, current_user=current_user,
    )

    # Get recruiter list. Не-админ видит только себя.
    recruiter_q = (
        select(User.id, User.name)
        .join(Vacancy, Vacancy.created_by == User.id)
        .where(Vacancy.org_id == org.id)
        .group_by(User.id, User.name)
    )
    if not is_admin:
        recruiter_q = recruiter_q.where(User.id == current_user.id)
    if department_id:
        recruiter_q = recruiter_q.where(Vacancy.department_id == department_id)
    recruiter_result = await db.execute(recruiter_q)
    recruiters = recruiter_result.all()

    by_recruiter = []
    for rec in recruiters:
        rec_funnel = await get_funnel_report(
            period=period, recruiter_id=rec.id, vacancy_status=vacancy_status,
            department_id=department_id,
            date_from=date_from, date_to=date_to,
            db=db, current_user=current_user,
        )
        by_recruiter.append(RecruiterFunnelItem(
            recruiter_id=rec.id,
            recruiter_name=rec.name or f"User #{rec.id}",
            stages=rec_funnel.stages,
            total_candidates=rec_funnel.total_candidates,
            total_rejections=rec_funnel.total_rejections,
        ))

    return FunnelByRecruiterReport(
        summary=summary,
        by_recruiter=by_recruiter,
    )


# Как считаем судьбу кандидата. Стадии смотрим по ВСЕМ его заявкам сразу:
# человек мог быть в двух воронках, и «нанят хоть куда-то» важнее, чем «отказ
# в одной из них». Поэтому классифицируем один раз на кандидата, а не на заявку.
_HIRED_STAGES = {
    ApplicationStage.hired,
    ApplicationStage.probation,
    ApplicationStage.transferred,
}
_CLOSED_STAGES = {ApplicationStage.rejected, ApplicationStage.withdrawn}


@router.get("/sourcers", response_model=SourcersReport)
async def get_sourcers_report(
    period: str = Query("current"),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Кого привели сорсеры и что из этого вышло.

    Сорсер — внешний человек без доступа в систему; в базе он живёт меткой из
    общего справочника с kind='sourcer'. Считаем по связям кандидат↔метка,
    поэтому отдельного хранилища не нужно.

    Скрытые метки («убрали за ненадобностью») ОСТАЮТСЯ в отчёте: человек привёл
    кандидатов, и удаление метки из списка выбора не должно задним числом
    переписывать историю. В выдаче они помечены archived.
    """
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(404, "Organization not found")

    df, dt = _get_date_filter(period, date_from, date_to)
    is_admin = await _is_admin_analytics(current_user, org.id, db)

    # Одним запросом: метка → кандидат → стадии всех его заявок.
    # LEFT JOIN на заявки: кандидата могли завести с меткой и ещё никуда не
    # добавить — он всё равно «приведён» и должен попасть в счётчик.
    query = (
        select(
            EntityTag.id, EntityTag.name, EntityTag.color, EntityTag.archived_at,
            Entity.id, VacancyApplication.stage,
        )
        .select_from(EntityTag)
        .join(entity_tag_association, entity_tag_association.c.tag_id == EntityTag.id)
        .join(Entity, Entity.id == entity_tag_association.c.entity_id)
        .outerjoin(VacancyApplication, VacancyApplication.entity_id == Entity.id)
        .where(
            EntityTag.org_id == org.id,
            EntityTag.kind == "sourcer",
            Entity.org_id == org.id,
            Entity.is_archived.is_not(True),
        )
    )
    # Рекрутёр без прав на общую аналитику видит только тех, кого завёл сам —
    # то же правило, что у остальных отчётов (_is_admin_analytics).
    if not is_admin:
        query = query.where(Entity.created_by == current_user.id)
    if df:
        query = query.where(Entity.created_at >= df)
    if dt:
        query = query.where(Entity.created_at <= dt)

    rows = (await db.execute(query)).all()

    # tag_id → (имя, цвет, скрыта), tag_id → {entity_id: set(стадий)}
    meta: Dict[int, Any] = {}
    stages_by: Dict[int, Dict[int, set]] = {}
    for tag_id, name, color, archived_at, entity_id, stage in rows:
        meta.setdefault(tag_id, (name, color, archived_at is not None))
        per_entity = stages_by.setdefault(tag_id, {})
        bucket = per_entity.setdefault(entity_id, set())
        if stage is not None:
            bucket.add(stage)

    items: List[SourcerStat] = []
    for tag_id, (name, color, archived) in meta.items():
        brought = in_work = reached_offer = hired = rejected = 0
        for stages in stages_by.get(tag_id, {}).values():
            brought += 1
            if stages & _HIRED_STAGES:
                hired += 1
                reached_offer += 1
            elif ApplicationStage.offer in stages:
                reached_offer += 1
                in_work += 1
            elif stages and stages <= _CLOSED_STAGES:
                # Все заявки закрыты отказом — дальше человек не идёт.
                rejected += 1
            else:
                # Есть живые заявки либо заявок нет вовсе (просто в базе).
                in_work += 1
        items.append(SourcerStat(
            tag_id=tag_id, name=name, color=color, archived=archived,
            brought=brought, in_work=in_work, reached_offer=reached_offer,
            hired=hired, rejected=rejected,
            conversion=round(hired / brought * 100, 1) if brought else 0.0,
        ))

    items.sort(key=lambda i: (-i.brought, i.name))
    return SourcersReport(
        items=items,
        total_brought=sum(i.brought for i in items),
        total_hired=sum(i.hired for i in items),
    )


@router.get("/rejections", response_model=RejectionsReport)
async def get_rejections_report(
    period: str = Query("current"),
    recruiter_id: Optional[int] = None,
    department_id: Optional[int] = None,
    vacancy_status: str = Query("open"),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Rejections report — Huntflow-style 'Отказы'."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(404, "Organization not found")

    recruiter_id = await _scope_recruiter_id(recruiter_id, current_user, org.id, db)
    date_from_dt, date_to_dt = _get_date_filter(period, date_from, date_to)

    base_filter = [
        Vacancy.org_id == org.id,
        VacancyApplication.stage == ApplicationStage.rejected,
    ]
    if date_from_dt:
        base_filter.append(VacancyApplication.last_stage_change_at >= date_from_dt)
    if date_to_dt:
        base_filter.append(VacancyApplication.last_stage_change_at <= date_to_dt)
    if recruiter_id:
        base_filter.append(Vacancy.created_by == recruiter_id)
    if department_id:
        base_filter.append(Vacancy.department_id == department_id)
    if vacancy_status == "open":
        base_filter.append(Vacancy.status == VacancyStatus.open)
    elif vacancy_status == "closed":
        base_filter.append(Vacancy.status == VacancyStatus.closed)

    # Total rejections
    total_q = (
        select(func.count(VacancyApplication.id))
        .join(Vacancy, VacancyApplication.vacancy_id == Vacancy.id)
        .where(*base_filter)
    )
    total_result = await db.execute(total_q)
    total_rejections = total_result.scalar() or 0

    # Rejections by stage (from StageTransition — what stage were they on before rejection)
    by_stage_q = (
        select(
            StageTransition.from_stage,
            func.count(StageTransition.id).label("cnt"),
        )
        .join(VacancyApplication, StageTransition.application_id == VacancyApplication.id)
        .join(Vacancy, VacancyApplication.vacancy_id == Vacancy.id)
        .where(
            Vacancy.org_id == org.id,
            StageTransition.to_stage == "rejected",
        )
        .group_by(StageTransition.from_stage)
        .order_by(func.count(StageTransition.id).desc())
    )
    if date_from_dt:
        by_stage_q = by_stage_q.where(StageTransition.created_at >= date_from_dt)
    if date_to_dt:
        by_stage_q = by_stage_q.where(StageTransition.created_at <= date_to_dt)
    if recruiter_id:
        by_stage_q = by_stage_q.where(Vacancy.created_by == recruiter_id)
    if department_id:
        by_stage_q = by_stage_q.where(Vacancy.department_id == department_id)
    if vacancy_status == "open":
        by_stage_q = by_stage_q.where(Vacancy.status == VacancyStatus.open)
    elif vacancy_status == "closed":
        by_stage_q = by_stage_q.where(Vacancy.status == VacancyStatus.closed)
    by_stage_result = await db.execute(by_stage_q)

    by_stage = []
    for row in by_stage_result:
        # Если StageTransition.from_stage NULL (старые данные / прямой отказ
        # без явного перехода) — пропускаем, чтобы в графике не было 'unknown'.
        if not row.from_stage:
            continue
        stage_key = _normalize_stage(row.from_stage)
        if not stage_key:
            continue
        # Get rejection reasons for this stage
        reason_q = (
            select(
                VacancyApplication.rejection_reason,
                func.count(VacancyApplication.id).label("cnt"),
            )
            .join(Vacancy, VacancyApplication.vacancy_id == Vacancy.id)
            .join(
                StageTransition,
                and_(
                    StageTransition.application_id == VacancyApplication.id,
                    StageTransition.from_stage.in_(_stage_values(stage_key)),
                    StageTransition.to_stage == "rejected",
                )
            )
            .where(
                Vacancy.org_id == org.id,
                VacancyApplication.rejection_reason.isnot(None),
            )
            .group_by(VacancyApplication.rejection_reason)
            .order_by(func.count(VacancyApplication.id).desc())
        )
        reason_result = await db.execute(reason_q)
        reasons = [
            RejectionReasonItem(reason=r.rejection_reason or "Другая причина", count=r.cnt)
            for r in reason_result
        ]

        by_stage.append(RejectionsByStage(
            stage=stage_key,
            label=STAGE_LABELS.get(stage_key) or 'Без стадии',
            count=row.cnt,
            reasons=reasons,
        ))

    # Top reasons overall
    top_reason_q = (
        select(
            VacancyApplication.rejection_reason,
            func.count(VacancyApplication.id).label("cnt"),
        )
        .join(Vacancy, VacancyApplication.vacancy_id == Vacancy.id)
        .where(
            *base_filter,
            VacancyApplication.rejection_reason.isnot(None),
        )
        .group_by(VacancyApplication.rejection_reason)
        .order_by(func.count(VacancyApplication.id).desc())
        .limit(10)
    )
    top_reason_result = await db.execute(top_reason_q)
    top_reasons = [
        RejectionReasonItem(reason=r.rejection_reason or "Другая причина", count=r.cnt)
        for r in top_reason_result
    ]

    return RejectionsReport(
        total_rejections=total_rejections,
        by_stage=by_stage,
        top_reasons=top_reasons,
    )


@router.get("/sources", response_model=SourceReport)
async def get_sources_report(
    period: str = Query("current"),
    recruiter_id: Optional[int] = None,
    department_id: Optional[int] = None,
    vacancy_status: str = Query("open"),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Resume sources report — Huntflow-style 'Источники резюме'."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(404, "Organization not found")

    recruiter_id = await _scope_recruiter_id(recruiter_id, current_user, org.id, db)
    date_from_dt, date_to_dt = _get_date_filter(period, date_from, date_to)

    base_filter = [Vacancy.org_id == org.id]
    if date_from_dt:
        base_filter.append(VacancyApplication.applied_at >= date_from_dt)
    if date_to_dt:
        base_filter.append(VacancyApplication.applied_at <= date_to_dt)
    if recruiter_id:
        base_filter.append(Vacancy.created_by == recruiter_id)
    if department_id:
        base_filter.append(Vacancy.department_id == department_id)
    if vacancy_status == "open":
        base_filter.append(Vacancy.status == VacancyStatus.open)
    elif vacancy_status == "closed":
        base_filter.append(Vacancy.status == VacancyStatus.closed)

    # Total
    total_q = (
        select(func.count(VacancyApplication.id))
        .join(Vacancy, VacancyApplication.vacancy_id == Vacancy.id)
        .where(*base_filter)
    )
    total_result = await db.execute(total_q)
    total = total_result.scalar() or 0

    # Sources overall
    source_q = (
        select(
            func.coalesce(VacancyApplication.source, 'Другой').label("src"),
            func.count(VacancyApplication.id).label("cnt"),
        )
        .join(Vacancy, VacancyApplication.vacancy_id == Vacancy.id)
        .where(*base_filter)
        .group_by("src")
        .order_by(func.count(VacancyApplication.id).desc())
    )
    source_result = await db.execute(source_q)
    sources = [SourceBreakdown(source=r.src, count=r.cnt) for r in source_result]

    # Sources by stage
    by_stage = {}
    for stage in FUNNEL_STAGES:
        stage_source_q = (
            select(
                func.coalesce(VacancyApplication.source, 'Другой').label("src"),
                func.count(VacancyApplication.id).label("cnt"),
            )
            .join(Vacancy, VacancyApplication.vacancy_id == Vacancy.id)
            .where(*base_filter, cast(VacancyApplication.stage, String).in_(_stage_values(stage)))
            .group_by("src")
            .order_by(func.count(VacancyApplication.id).desc())
        )
        stage_result = await db.execute(stage_source_q)
        stage_sources = [SourceBreakdown(source=r.src, count=r.cnt) for r in stage_result]
        if stage_sources:
            by_stage[stage] = stage_sources

    return SourceReport(
        total_candidates=total,
        sources=sources,
        by_stage=by_stage,
    )


@router.get("/movement", response_model=MovementReport)
async def get_movement_report(
    period: str = Query("current"),
    recruiter_id: Optional[int] = None,
    department_id: Optional[int] = None,
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Candidate movement report — Huntflow-style 'Движение кандидатов'."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(404, "Organization not found")

    recruiter_id = await _scope_recruiter_id(recruiter_id, current_user, org.id, db)
    date_from_dt, date_to_dt = _get_date_filter(period, date_from, date_to)

    move_q = (
        select(
            StageTransition.from_stage,
            StageTransition.to_stage,
            func.count(StageTransition.id).label("cnt"),
        )
        .join(VacancyApplication, StageTransition.application_id == VacancyApplication.id)
        .join(Vacancy, VacancyApplication.vacancy_id == Vacancy.id)
        .where(Vacancy.org_id == org.id)
        .group_by(StageTransition.from_stage, StageTransition.to_stage)
        .order_by(func.count(StageTransition.id).desc())
    )
    if date_from_dt:
        move_q = move_q.where(StageTransition.created_at >= date_from_dt)
    if date_to_dt:
        move_q = move_q.where(StageTransition.created_at <= date_to_dt)
    if recruiter_id:
        move_q = move_q.where(Vacancy.created_by == recruiter_id)
    if department_id:
        move_q = move_q.where(Vacancy.department_id == department_id)

    result = await db.execute(move_q)

    movements = []
    total = 0
    for row in result:
        from_s = _normalize_stage(row.from_stage) or "applied"
        to_s = _normalize_stage(row.to_stage) or "unknown"
        movements.append(StageMovementItem(
            from_stage=from_s,
            from_label=STAGE_LABELS.get(from_s, from_s),
            to_stage=to_s,
            to_label=STAGE_LABELS.get(to_s, to_s),
            count=row.cnt,
        ))
        total += row.cnt

    return MovementReport(
        total_movements=total,
        movements=movements,
    )
