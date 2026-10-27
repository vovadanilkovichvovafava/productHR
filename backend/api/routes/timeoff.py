"""Time-off / vacation request endpoints."""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from ..models.database import TimeOffRequest, User, OrgMember, OrgRole, Employee, LeaveRequest, DepartmentMember, DeptRole, UserRole
from ..database import get_db
from ..services.auth import get_current_user, get_user_org


async def _scoped_user_ids(user: User, org_id: int, db: AsyncSession) -> list[int] | None:
    """Какие user_id видны в этом org для текущего юзера.

    None  — без фильтра (платформ-админ / owner / org-admin).
    list  — конкретные id (лид → коллеги отделов; остальные → только self).
    """
    if user.role == UserRole.superadmin:
        return None
    om = await db.execute(
        select(OrgMember.role).where(
            OrgMember.user_id == user.id, OrgMember.org_id == org_id
        )
    )
    org_role = om.scalar_one_or_none()
    if org_role in (OrgRole.owner, OrgRole.admin):
        return None

    dept_ids_res = await db.execute(
        select(DepartmentMember.department_id).where(
            DepartmentMember.user_id == user.id,
            DepartmentMember.role.in_([DeptRole.lead, DeptRole.sub_admin]),
        )
    )
    admin_dept_ids = [r for r in dept_ids_res.scalars().all()]
    if not admin_dept_ids:
        return [user.id]

    members_res = await db.execute(
        select(DepartmentMember.user_id).where(
            DepartmentMember.department_id.in_(admin_dept_ids)
        )
    )
    ids = {uid for uid in members_res.scalars().all()}
    ids.add(user.id)
    return list(ids)

router = APIRouter()


async def _is_admin_or_owner(user: User, org_id: int, db: AsyncSession) -> bool:
    """superadmin / owner / admin org-а (зеркало helper-а из employees.py)."""
    if user.role and user.role.value == "superadmin":
        return True
    result = await db.execute(
        select(OrgMember).where(
            OrgMember.user_id == user.id,
            OrgMember.org_id == org_id,
            OrgMember.role.in_([OrgRole.owner, OrgRole.admin]),
        )
    )
    return result.scalar_one_or_none() is not None


# Нормализация типов из обеих систем в единый набор + рус. подпись
_TYPE_NORMALIZE = {
    "vacation": "vacation",
    "day_off": "day_off",
    "sick_leave": "sick",
    "sick": "sick",
    "family_leave": "family_leave",
    "bereavement": "bereavement",
    "other": "other",
}
_TYPE_LABELS = {
    "vacation": "Отпуск",
    "day_off": "Отгул",
    "sick": "Больничный",
    "family_leave": "Семейные дни",
    "bereavement": "По утрате",
    "other": "Другое",
}


class TimeOffAllItem(BaseModel):
    source: str            # 'timeoff' (A) | 'leave' (B)
    source_id: int
    user_id: int | None = None
    person_name: str | None = None
    type: str              # canonical: vacation|day_off|sick|family_leave|bereavement|other
    type_label: str
    start: datetime
    end: datetime
    days: int
    status: str            # pending|approved|rejected
    reason: str | None = None


class TimeOffOut(BaseModel):
    id: int
    user_id: int
    user_name: str | None = None
    type: str
    status: str
    date_from: datetime
    date_to: datetime
    reason: str | None = None
    reviewed_by: int | None = None
    reviewer_name: str | None = None
    reviewed_at: datetime | None = None
    reject_reason: str | None = None
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class TimeOffCreate(BaseModel):
    type: str = "vacation"
    date_from: datetime
    date_to: datetime
    reason: str | None = None


@router.get("")
async def list_timeoff(
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List time-off requests for the org."""
    org_result = await db.execute(
        select(OrgMember.org_id).where(OrgMember.user_id == current_user.id).limit(1)
    )
    org_id = org_result.scalar_one_or_none()
    if not org_id:
        raise HTTPException(404, "No organization")

    query = select(TimeOffRequest).where(TimeOffRequest.org_id == org_id).order_by(TimeOffRequest.created_at.desc())
    if status:
        query = query.where(TimeOffRequest.status == status)
    allowed = await _scoped_user_ids(current_user, org_id, db)
    if allowed is not None:
        query = query.where(TimeOffRequest.user_id.in_(allowed))

    result = await db.execute(query)
    requests = result.scalars().all()

    # Enrich with user names
    user_ids = set()
    for r in requests:
        user_ids.add(r.user_id)
        if r.reviewed_by:
            user_ids.add(r.reviewed_by)

    users_result = await db.execute(select(User).where(User.id.in_(user_ids)))
    users_map = {u.id: u.name for u in users_result.scalars().all()}

    return [
        TimeOffOut(
            id=r.id,
            user_id=r.user_id,
            user_name=users_map.get(r.user_id),
            type=r.type if isinstance(r.type, str) else r.type.value,
            status=r.status if isinstance(r.status, str) else r.status.value,
            date_from=r.date_from,
            date_to=r.date_to,
            reason=r.reason,
            reviewed_by=r.reviewed_by,
            reviewer_name=users_map.get(r.reviewed_by) if r.reviewed_by else None,
            reviewed_at=r.reviewed_at,
            reject_reason=r.reject_reason,
            created_at=r.created_at,
        )
        for r in requests
    ]


@router.get("/calendar")
async def timeoff_calendar(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return approved/pending timeoffs for calendar view."""
    org_result = await db.execute(
        select(OrgMember.org_id).where(OrgMember.user_id == current_user.id).limit(1)
    )
    org_id = org_result.scalar_one_or_none()
    if not org_id:
        raise HTTPException(404, "No organization")

    query = (
        select(TimeOffRequest)
        .where(TimeOffRequest.org_id == org_id)
        .where(TimeOffRequest.status.in_(["pending", "approved"]))
        .order_by(TimeOffRequest.date_from)
    )
    result = await db.execute(query)
    requests = result.scalars().all()

    user_ids = {r.user_id for r in requests}
    users_result = await db.execute(select(User).where(User.id.in_(user_ids)))
    users_map = {u.id: u.name for u in users_result.scalars().all()}

    return [
        {
            "id": r.id,
            "user_name": users_map.get(r.user_id, "?"),
            "date_from": r.date_from.isoformat(),
            "date_to": r.date_to.isoformat(),
            "type": r.type if isinstance(r.type, str) else r.type.value,
            "status": r.status if isinstance(r.status, str) else r.status.value,
        }
        for r in requests
    ]


@router.get("/all", response_model=list[TimeOffAllItem])
async def list_all_timeoff(
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Объединённый орг-обзор ВСЕХ отпусков из обеих систем. Только admin/owner, read-only."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization")
    if not await _is_admin_or_owner(current_user, org.id, db):
        raise HTTPException(403, "Admin access required")

    items: list[TimeOffAllItem] = []

    # ── Система A: time_off_requests (заявки из Telegram-бота) ──
    a_query = select(TimeOffRequest).where(TimeOffRequest.org_id == org.id)
    if status:
        a_query = a_query.where(TimeOffRequest.status == status)
    a_rows = (await db.execute(a_query)).scalars().all()

    a_user_ids = {r.user_id for r in a_rows}
    a_names: dict[int, str] = {}
    if a_user_ids:
        res = await db.execute(select(User).where(User.id.in_(a_user_ids)))
        a_names = {u.id: u.name for u in res.scalars().all()}

    for r in a_rows:
        raw = r.type if isinstance(r.type, str) else r.type.value
        st = r.status if isinstance(r.status, str) else r.status.value
        canon = _TYPE_NORMALIZE.get(raw, "other")
        items.append(TimeOffAllItem(
            source="timeoff",
            source_id=r.id,
            user_id=r.user_id,
            person_name=a_names.get(r.user_id),
            type=canon,
            type_label=_TYPE_LABELS.get(canon, raw),
            start=r.date_from,
            end=r.date_to,
            days=max(1, (r.date_to.date() - r.date_from.date()).days + 1),
            status=st,
            reason=r.reason,
        ))

    # ── Система B: leave_requests (заявки из Factorial-формы) ──
    b_query = (
        select(LeaveRequest)
        .join(Employee, LeaveRequest.employee_id == Employee.id)
        .options(selectinload(LeaveRequest.employee).selectinload(Employee.user))
        .where(Employee.org_id == org.id)
    )
    if status:
        b_query = b_query.where(LeaveRequest.status == status)
    b_rows = (await db.execute(b_query)).scalars().all()

    for lr in b_rows:
        raw = lr.type
        canon = _TYPE_NORMALIZE.get(raw, "other")
        emp = lr.employee
        items.append(TimeOffAllItem(
            source="leave",
            source_id=lr.id,
            user_id=emp.user_id if emp else None,
            person_name=(emp.user.name if emp and emp.user else None),
            type=canon,
            type_label=_TYPE_LABELS.get(canon, raw),
            start=lr.start_date,
            end=lr.end_date,
            days=lr.days,
            status=lr.status,
            reason=lr.reason,
        ))

    items.sort(key=lambda x: x.start, reverse=True)
    return items


@router.post("/{request_id}/approve")
async def approve_timeoff(
    request_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Approve a time-off request."""
    req = await db.get(TimeOffRequest, request_id)
    if not req:
        raise HTTPException(404, "Request not found")

    req.status = "approved"
    req.reviewed_by = current_user.id
    req.reviewed_at = datetime.utcnow()
    await db.commit()

    # Send Telegram notification
    try:
        from ..bot import send_telegram_notification
        await send_telegram_notification(
            req.user_id,
            f"\u2705 <b>\u0417\u0430\u044f\u0432\u043a\u0430 \u043e\u0434\u043e\u0431\u0440\u0435\u043d\u0430!</b>\n\n"
            f"\U0001f4c5 {req.date_from.strftime('%d.%m')} \u2014 {req.date_to.strftime('%d.%m')}\n"
            f"\u041e\u0434\u043e\u0431\u0440\u0438\u043b: {current_user.name}",
        )
    except Exception:
        pass  # Don't fail the API call if notification fails

    return {"status": "approved"}


@router.post("/{request_id}/reject")
async def reject_timeoff(
    request_id: int,
    reason: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reject a time-off request."""
    req = await db.get(TimeOffRequest, request_id)
    if not req:
        raise HTTPException(404, "Request not found")

    req.status = "rejected"
    req.reviewed_by = current_user.id
    req.reviewed_at = datetime.utcnow()
    req.reject_reason = reason
    await db.commit()

    # Send Telegram notification
    try:
        from ..bot import send_telegram_notification
        reason_text = f"\n\u041f\u0440\u0438\u0447\u0438\u043d\u0430: {reason}" if reason else ""
        await send_telegram_notification(
            req.user_id,
            f"\u274c <b>\u0417\u0430\u044f\u0432\u043a\u0430 \u043e\u0442\u043a\u043b\u043e\u043d\u0435\u043d\u0430</b>\n\n"
            f"\U0001f4c5 {req.date_from.strftime('%d.%m')} \u2014 {req.date_to.strftime('%d.%m')}\n"
            f"\u041e\u0442\u043a\u043b\u043e\u043d\u0438\u043b: {current_user.name}{reason_text}",
        )
    except Exception:
        pass

    return {"status": "rejected"}
