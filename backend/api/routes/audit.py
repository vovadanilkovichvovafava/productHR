"""Журнал действий — чтение (21.10.2026, services/audit.py пишет).

Только админам HR (как корзина): владелец, админы, суперадмин; наблюдатель
смотрит тоже — у него полный ЧИТАЮЩИЙ доступ. Своя организация: строки людей
из других организаций не видны.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.database import AuditEvent, Entity, OrgMember, User, UserRole, Vacancy
from ..services.auth import get_current_user, get_user_org, has_full_database_access

router = APIRouter()


async def _scope(db: AsyncSession, user: User):
    """Чьи строки видны: None — все (суперадмин), иначе список id людей орга."""
    org = await get_user_org(user, db)
    if user.role == UserRole.superadmin:
        return None
    if not org or not await has_full_database_access(user, org.id, db):
        raise HTTPException(403, "Журнал действий доступен только админам HR")
    return (await db.execute(select(OrgMember.user_id).where(OrgMember.org_id == org.id))).scalars().all()


@router.get("")
async def list_audit(
    entity_id: Optional[int] = Query(None, description="Всё по кандидату"),
    user_id: Optional[int] = Query(None, description="Всё, что сделал человек"),
    vacancy_id: Optional[int] = Query(None, description="Всё по воронке"),
    only_errors: bool = Query(False, description="Только неудачные (ответ 4xx/5xx)"),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    before_id: Optional[int] = Query(None, description="Дальше по списку: строки старше этой"),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user = await db.merge(current_user)
    people = await _scope(db, current_user)
    q = select(AuditEvent)
    if people is not None:
        q = q.where(AuditEvent.user_id.in_(people))
    if entity_id is not None:
        q = q.where(AuditEvent.entity_id == entity_id)
    if user_id is not None:
        q = q.where(AuditEvent.user_id == user_id)
    if vacancy_id is not None:
        q = q.where(AuditEvent.vacancy_id == vacancy_id)
    if only_errors:
        q = q.where(AuditEvent.status >= 400)
    if date_from is not None:
        q = q.where(AuditEvent.at >= date_from)
    if date_to is not None:
        q = q.where(AuditEvent.at <= date_to)
    if before_id is not None:
        q = q.where(AuditEvent.id < before_id)
    rows = (await db.execute(q.order_by(AuditEvent.id.desc()).limit(limit))).scalars().all()

    # Подписи кандидатов и воронок — по нынешним именам (удалённых — из тела запроса).
    entity_ids = {r.entity_id for r in rows if r.entity_id}
    vacancy_ids = {r.vacancy_id for r in rows if r.vacancy_id}
    names = dict((await db.execute(
        select(Entity.id, Entity.name).where(Entity.id.in_(entity_ids))
    )).all()) if entity_ids else {}
    titles = dict((await db.execute(
        select(Vacancy.id, Vacancy.title).where(Vacancy.id.in_(vacancy_ids))
    )).all()) if vacancy_ids else {}

    return {
        "items": [
            {
                "id": r.id,
                "at": r.at.isoformat() if r.at else None,
                "user_id": r.user_id,
                "user_name": r.user_name,
                "action": r.action,
                "method": r.method,
                "path": r.path,
                "status": r.status,
                "duration_ms": r.duration_ms,
                "entity_id": r.entity_id,
                "entity_name": names.get(r.entity_id),
                "vacancy_id": r.vacancy_id,
                "vacancy_title": titles.get(r.vacancy_id),
                "application_id": r.application_id,
                "body": r.body,
            }
            for r in rows
        ],
        "next_before_id": rows[-1].id if len(rows) == limit else None,
    }


@router.get("/users")
async def audit_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Кто есть в журнале и сколько действий — для фильтра «Кто»."""
    current_user = await db.merge(current_user)
    people = await _scope(db, current_user)
    q = (
        select(AuditEvent.user_id, func.max(AuditEvent.user_name), func.count(AuditEvent.id))
        .where(AuditEvent.user_id.is_not(None))
        .group_by(AuditEvent.user_id)
    )
    if people is not None:
        q = q.where(AuditEvent.user_id.in_(people))
    rows = (await db.execute(q)).all()
    return {
        "items": sorted(
            ({"user_id": uid, "name": name or f"#{uid}", "count": n} for uid, name, n in rows),
            key=lambda x: -x["count"],
        )
    }
