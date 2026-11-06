"""Страница «Анкеты → Ответы»: все отправленные анкеты и потерянные ответы.

Смысл и устройство — `services/form_inbox.py`. Видят все рекрутёры (owner,
admin, hr и наблюдатель — только чтение), каждый — анкеты кандидатов, которых
видит и так (скоуп по воронкам). «Привязать к кандидату» — только админы HR,
как и перенос анкеты (`/forms/dispatch/{id}/reassign`). Решение владельца
06.11.2026.

Свой префикс `/api/form-answers`, а не `/api/forms/...`: там `/{form_id}`
перехватил бы любое слово в пути.
"""
import logging
import secrets
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.database import (
    Entity, FormClientError, FormDispatch, FormSubmission, FormTemplate, OrgRole, User, UserRole,
)
from ..services.auth import get_current_user, get_user_org, get_user_org_role
from ..services.form_dispatch_view import build_dispatch_list
from ..services.form_inbox import file_urls, load_items, summarize
from ..services.vacancy_scope import ensure_entity_visible, get_scope_vacancy_ids

logger = logging.getLogger("hr-analyzer.form_answers")
router = APIRouter()

HR_ROLES = (OrgRole.owner, OrgRole.admin, OrgRole.hr)


async def _hr_org(db: AsyncSession, user: User):
    """(организация, админ ли HR). Не рекрутёр — 403."""
    org = await get_user_org(user, db)
    if user.role == UserRole.superadmin:
        return org, True
    role = await get_user_org_role(user, org.id, db) if org else None
    if role not in HR_ROLES:
        raise HTTPException(403, "Ответы на анкеты доступны только рекрутёрам")
    return org, role in (OrgRole.owner, OrgRole.admin)


@router.get("")
async def list_form_answers(
    status: Optional[str] = None,
    form_id: Optional[int] = None,
    sent_by: Optional[int] = None,
    days: Optional[int] = None,
    q: str = "",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user = await db.merge(current_user)
    org, is_admin = await _hr_org(db, current_user)
    scope_ids = await get_scope_vacancy_ids(current_user, db)
    items = await load_items(db, org.id if org else None, scope_ids)

    # Списки для фильтров — из всех строк, а не из отфильтрованных, иначе
    # выбранная анкета пропала бы из своего же выпадающего списка.
    forms = sorted({(i["form_id"], i["form_title"] or "Анкета") for i in items}, key=lambda x: x[1].lower())
    senders = sorted(
        {(i["sent_by_id"], i["sent_by_name"]) for i in items if i["sent_by_id"]},
        key=lambda x: (x[1] or "").lower(),
    )
    result = summarize(items, status=status, q=q, form_id=form_id, sent_by=sent_by,
                       days=days if days and days > 0 else None)
    return {
        **result,
        "forms": [{"id": fid, "title": t} for fid, t in forms],
        "senders": [{"id": uid, "name": n or f"#{uid}"} for uid, n in senders],
        "can_attach": is_admin,
    }


async def _answer_view(db: AsyncSession, row: dict, entity_id: Optional[int], merged_from) -> dict:
    items = await build_dispatch_list(
        db, [row], entity_id=entity_id or 0, merged_from=merged_from,
        file_urls=lambda needed: file_urls(db, needed),
    )
    return items[0]


@router.get("/dispatch/{dispatch_id}")
async def get_dispatch_answer(
    dispatch_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user = await db.merge(current_user)
    org, _ = await _hr_org(db, current_user)
    d = await db.get(FormDispatch, dispatch_id)
    form = await db.get(FormTemplate, d.form_id) if d else None
    entity = await db.get(Entity, d.entity_id) if d else None
    # Чужая организация и чужой скоуп — 404, как везде: номера перебираются.
    if not d or not form or not entity or (org and (form.org_id != org.id or entity.org_id != org.id)):
        raise HTTPException(404, "Анкета не найдена")
    await ensure_entity_visible(entity.id, current_user, db)
    extra = entity.extra_data if isinstance(entity.extra_data, dict) else {}
    view = await _answer_view(db, d, entity.id, extra.get("merged_from") or [])
    errors = (await db.execute(
        select(FormClientError).where(FormClientError.dispatch_id == d.id)
        .order_by(FormClientError.created_at.desc()).limit(20)
    )).scalars().all()
    view["source_name"] = None
    view["entity_id"] = entity.id
    view["entity_name"] = entity.name
    view["errors"] = [
        {"at": e.created_at.isoformat() if e.created_at else None, "kind": e.kind,
         "status": e.status, "message": e.message, "online": e.online}
        for e in errors
    ]
    return view


async def _orphan(db: AsyncSession, submission_id: int, org) -> tuple:
    sub = await db.get(FormSubmission, submission_id)
    form = await db.get(FormTemplate, sub.form_id) if sub else None
    if not sub or not form or (org and form.org_id != org.id):
        raise HTTPException(404, "Ответ не найден")
    return sub, form


@router.get("/submission/{submission_id}")
async def get_orphan_answer(
    submission_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user = await db.merge(current_user)
    org, _ = await _hr_org(db, current_user)
    sub, form = await _orphan(db, submission_id, org)
    if await get_scope_vacancy_ids(current_user, db) is not None:
        raise HTTPException(404, "Ответ не найден")  # в списке скоупу их тоже нет
    entity = await db.get(Entity, sub.entity_id) if sub.entity_id else None
    row = {
        "id": None, "form_id": sub.form_id, "token": None, "status": "submitted",
        "seen_by_recruiter": True, "submission_id": sub.id, "entity_id": entity.id if entity else None,
        "created_at": sub.submitted_at, "submitted_at": sub.submitted_at,
    }
    view = await _answer_view(db, row, entity.id if entity else None, [])
    view["source_name"] = None
    view["entity_id"] = entity.id if entity else None
    view["entity_name"] = entity.name if entity else None
    view["errors"] = []
    return view


class AttachBody(BaseModel):
    entity_id: int


@router.post("/submission/{submission_id}/attach")
async def attach_orphan_answer(
    submission_id: int,
    body: AttachBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Привязать ответ без кандидата к карточке: он появится во вкладке «Анкета»
    как заполненная анкета. Ссылка создаётся заново (старая стёрлась вместе с
    прежней карточкой), отправлять её никому не нужно."""
    current_user = await db.merge(current_user)
    org, is_admin = await _hr_org(db, current_user)
    if not is_admin:
        raise HTTPException(403, "Привязать ответ к кандидату может только админ HR")
    sub, form = await _orphan(db, submission_id, org)
    linked = (await db.execute(
        select(FormDispatch.id).where(FormDispatch.submission_id == sub.id)
    )).scalars().first()
    if linked:
        raise HTTPException(409, "Этот ответ уже есть в карточке кандидата")
    target = await db.get(Entity, body.entity_id)
    if not target or (org and target.org_id != org.id):
        raise HTTPException(404, "Кандидат не найден")
    request.state.audit_extra = {"entity_id": target.id}

    # Даты — от самого ответа: в карточке он встанет на своё место по времени.
    when = sub.submitted_at or datetime.utcnow()
    dispatch = FormDispatch(
        form_id=sub.form_id, entity_id=target.id, token=secrets.token_urlsafe(16),
        status="submitted", submission_id=sub.id, seen_by_recruiter=False,
        created_by=current_user.id, created_at=when, opened_at=when, submitted_at=when,
    )
    db.add(dispatch)
    await db.flush()
    previous = sub.entity_id
    sub.entity_id = target.id
    sub.dispatch_id = dispatch.id
    await db.commit()
    logger.info(
        "FORM_ATTACH submission=%s form=%s entity=%s (was %s) dispatch=%s by=%s",
        sub.id, sub.form_id, target.id, previous, dispatch.id, current_user.id,
    )
    return {"dispatch_id": dispatch.id, "entity_id": target.id}
