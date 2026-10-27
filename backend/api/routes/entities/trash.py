"""
Корзина кандидатов: список удалённых и возврат (20.10.2026, services/entity_trash.py).

Смотреть, открывать и возвращать — ВСЕМ рекрутёрам (владелец, 23.10.2026;
до этого — только админам HR): удалить кандидата может любой, кто с ним
работает, значит и вернуть должен мочь каждый. Человек со скоупом по
воронкам видит только записи своих воронок. Удалённую карточку можно открыть
как обычную (`/trash/{id}/card`, только чтение) и скачать её файлы.
Подключается РАНЬШЕ crud: иначе GET /entities/{entity_id} перехватил бы
/entities/trash.
"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .common import (
    logger, get_db, User, UserRole, get_current_user, get_user_org, get_user_org_role,
)
from ...models.database import OrgRole
from ...models.database import DeletedEntity

router = APIRouter()

# Сколько показывать в журнале: вернуть можно 7 дней, но кто и когда удалял —
# полезно видеть и дольше.
JOURNAL_DAYS = 90


async def _admin_org(db: AsyncSession, user: User):
    """Организация человека, если он в HR (рекрутёр, админ, владелец)."""
    org = await get_user_org(user, db)
    if user.role == UserRole.superadmin:
        return org
    role = await get_user_org_role(user, org.id, db) if org else None
    if role not in (OrgRole.owner, OrgRole.admin, OrgRole.hr):
        raise HTTPException(403, "Корзина доступна только рекрутёрам")
    return org


def _snapshot_vacancy_ids(r: DeletedEntity) -> set:
    rows = ((r.snapshot or {}).get("tables") or {}).get("vacancy_applications") or []
    return {row.get("vacancy_id") for row in rows if row.get("vacancy_id") is not None}


def _in_scope(r: DeletedEntity, scope_ids) -> bool:
    """Скоуп по воронкам: запись видна, только если касается разрешённой воронки."""
    if scope_ids is None:
        return True
    if (r.kind or "entity") == "application":
        return r.vacancy_id in scope_ids
    return bool(_snapshot_vacancy_ids(r) & set(scope_ids))


async def _record_for(db: AsyncSession, trash_id: int, user: User, org, *, lock: bool = False) -> DeletedEntity:
    from ...services.vacancy_scope import get_scope_vacancy_ids
    q = select(DeletedEntity).where(DeletedEntity.id == trash_id)
    if lock:
        q = q.with_for_update()
    record = (await db.execute(q)).scalar_one_or_none()
    if record is None or (
        user.role != UserRole.superadmin and org is not None and record.org_id != org.id
    ) or not _in_scope(record, await get_scope_vacancy_ids(user, db)):
        raise HTTPException(404, "Запись корзины не найдена")
    return record


def _row(r: DeletedEntity, now: datetime) -> dict:
    from ...services.entity_trash import snapshot_summary
    return {
        "id": r.id,
        "entity_id": r.entity_id,
        "name": r.entity_name,
        "deleted_by_name": r.deleted_by_name,
        "deleted_at": r.deleted_at.isoformat() if r.deleted_at else None,
        "restorable_until": r.purge_after.isoformat() if r.purge_after else None,
        "restorable": bool(r.snapshot) and r.restored_at is None and r.purge_after > now,
        "restored_at": r.restored_at.isoformat() if r.restored_at else None,
        "restored_by_name": r.restored_by_name,
        "purged_at": r.purged_at.isoformat() if r.purged_at else None,
        "summary": snapshot_summary(r.snapshot),
        # «application» — кандидат убран из одной воронки (карточка осталась).
        "kind": r.kind or "entity",
        "vacancy_id": r.vacancy_id,
        "vacancy_title": r.vacancy_title,
        "owner_name": r.owner_name,
        "stage": r.stage,
    }


@router.get("/trash")
async def list_trash(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Удалённые кандидаты: кого можно вернуть и журнал «кто, кого, когда»."""
    from ...services.entity_trash import purge_expired

    current_user = await db.merge(current_user)
    org = await _admin_org(db, current_user)
    if await purge_expired(db):
        await db.commit()
    now = datetime.utcnow()
    q = select(DeletedEntity).where(DeletedEntity.deleted_at > now - timedelta(days=JOURNAL_DAYS))
    if org is not None and current_user.role != UserRole.superadmin:
        q = q.where(DeletedEntity.org_id == org.id)
    elif org is not None:
        q = q.where(or_(DeletedEntity.org_id == org.id, DeletedEntity.org_id.is_(None)))
    rows = (await db.execute(q.order_by(DeletedEntity.deleted_at.desc()))).scalars().all()
    from ...services.vacancy_scope import get_scope_vacancy_ids
    scope_ids = await get_scope_vacancy_ids(current_user, db)
    return {"items": [_row(r, now) for r in rows if _in_scope(r, scope_ids)]}


@router.get("/trash/{trash_id}/card")
async def trash_card(
    trash_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Удалённый кандидат как обычная карточка, только для чтения: поля
    карточки, воронки с историей переводов, комментарии, файлы (без байтов).
    Для «Удалить с воронки» — живая карточка + удалённая заявка из слепка."""
    from ...services.entity_trash import trash_card_view

    current_user = await db.merge(current_user)
    org = await _admin_org(db, current_user)
    record = await _record_for(db, trash_id, current_user, org)
    if not record.snapshot:
        raise HTTPException(410, "Слепок уже стёрт — прошло больше 7 дней")
    view = await trash_card_view(db, record)
    view["trash"] = _row(record, datetime.utcnow())
    return view


@router.get("/trash/{trash_id}/files/{file_id}")
async def trash_file(
    trash_id: int,
    file_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Файл удалённого кандидата — байты из слепка корзины."""
    from fastapi.responses import Response
    from urllib.parse import quote
    from ...services.entity_trash import trash_file_bytes

    current_user = await db.merge(current_user)
    org = await _admin_org(db, current_user)
    record = await _record_for(db, trash_id, current_user, org)
    found = trash_file_bytes(record, file_id)
    if found is None:
        raise HTTPException(404, "Файла нет в корзине")
    data, name, mime = found
    return Response(
        content=data,
        media_type=mime or "application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name or 'file')}"},
    )


@router.post("/trash/{trash_id}/restore")
async def restore_trash(
    trash_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Вернуть кандидата как был: воронки, история, файлы, метки, анкеты."""
    from ...services.entity_trash import RestoreError, restore_from_trash

    current_user = await db.merge(current_user)
    org = await _admin_org(db, current_user)
    record = await _record_for(db, trash_id, current_user, org, lock=True)
    if record.purge_after <= datetime.utcnow() and not record.restored_at:
        raise HTTPException(410, "Срок хранения в корзине истёк — вернуть уже нельзя")
    kind = record.kind or "entity"
    entity_id, entity_name = record.entity_id, record.entity_name
    vacancy_id, vacancy_title = record.vacancy_id, record.vacancy_title
    # Журнал действий: кого вернули (в адресе только номер записи корзины).
    request.state.audit_extra = {"entity_id": entity_id, "vacancy_id": vacancy_id}
    user_id, user_name = current_user.id, current_user.name
    try:
        skipped = await restore_from_trash(db, record, current_user)
        if kind == "application":
            # Заявка вернулась — общий статус кандидата снова по «актуальной»
            # заявке (снятие с последней воронки сбрасывало его в «Новый»).
            from ...services.stage_change import settle_entities
            await settle_entities(db, [entity_id])
    except RestoreError as e:
        await db.rollback()
        raise HTTPException(409, str(e))
    await db.commit()
    if kind == "application":
        try:
            from ...services.hr_tags import sync_for_entity
            await sync_for_entity(db, entity_id)
        except Exception:
            logger.exception("HR-tags sync failed after application restore (non-critical)")
        logger.info(
            "APPLICATION_RESTORE: entity=%s «%s» vacancy=%s «%s» by user=%s (%s), не вернулось: %s",
            entity_id, entity_name, vacancy_id, vacancy_title, user_id, user_name, skipped or "—",
        )
    else:
        logger.info(
            "ENTITY_RESTORE: entity=%s «%s» by user=%s (%s), не вернулось: %s",
            entity_id, entity_name, user_id, user_name, skipped or "—",
        )
    return {"success": True, "entity_id": entity_id, "vacancy_id": vacancy_id, "kind": kind, "skipped": skipped}
