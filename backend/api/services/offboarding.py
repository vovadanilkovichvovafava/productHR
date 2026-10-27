"""Оркестратор оффбординга: чек-лист отзыва доступов при увольнении.

По ТЗ: «при увольнении оркестратор строит чек-лист отзыва по активным грантам,
рассылает ответственным, фиксирует закрытие».

Что делает автоматически (по решению бизнеса: «увольняем — отключаем от всего»):
ПОЛНОСТЬЮ ОТРЕЗАЕТ ВХОД. Раньше увольнение гасило только запись сотрудника, а сам
аккаунт оставался живым — уволенный заходил на сайт своим паролем и видел то, к
чему был допущен, а бот продолжал его узнавать. Теперь гасим аккаунт, обнуляем
сессии и отвязываем Telegram.

Чего по-прежнему НЕ делает: не отзывает сами ресурсы и не удаляет членства.
Отзыв — действие ответственного (кнопка «Отозвать»), а членства нужны при
обратном найме: hire.py реактивирует ту же запись и возвращает вход.

Единая точка входа нужна потому, что увольнение в системе имеет ДВЕ двери:
  * DELETE /employees/{id} — ставит Employee.is_active = False;
  * доска «Статусы» — ставит Entity.status = dismissed/quit.
Раньше они ничего не знали друг о друге, и любая из них была тихим обходом.
"""
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import (
    AccessRequest, AccessRequestStatus, ResourceCatalog,
    ApiToken, DepartmentMember, Employee, OrgMember, OrgRole,
    RefreshToken, SharedAccess, User,
)

logger = logging.getLogger("hr-analyzer.offboarding")


async def build_checklist(db: AsyncSession, org_id: int, user_id: int) -> Dict[str, Any]:
    """Что нужно забрать у человека. Только чтение, ничего не меняет."""
    # 1. Выданные ресурсы из хаба доступов — по ним есть ответственный
    grants = (await db.execute(
        select(AccessRequest, ResourceCatalog)
        .join(ResourceCatalog, ResourceCatalog.id == AccessRequest.resource_id)
        .where(
            AccessRequest.org_id == org_id,
            AccessRequest.status == AccessRequestStatus.granted,
            func.coalesce(AccessRequest.target_user_id, AccessRequest.requester_user_id) == user_id,
        )
        .order_by(AccessRequest.granted_at)
    )).all()

    resource_items = [
        {
            "request_id": req.id,
            "resource_id": res.id,
            "resource_name": res.name,
            "category": res.category.value if hasattr(res.category, "value") else str(res.category),
            "params": req.params if isinstance(req.params, dict) else {},
            "granted_at": req.granted_at.isoformat() if req.granted_at else None,
            "responsible_user_id": req.assignee_user_id,
        }
        for req, res in grants
    ]

    # 2. Прочие доступы в самой системе — их отзывает админ вручную
    shared_cnt = (await db.execute(
        select(func.count(SharedAccess.id)).where(SharedAccess.shared_with_id == user_id)
    )).scalar() or 0
    shared_by_cnt = (await db.execute(
        select(func.count(SharedAccess.id)).where(SharedAccess.shared_by_id == user_id)
    )).scalar() or 0
    dept_cnt = (await db.execute(
        select(func.count(DepartmentMember.id)).where(DepartmentMember.user_id == user_id)
    )).scalar() or 0
    org_cnt = (await db.execute(
        select(func.count(OrgMember.id)).where(
            OrgMember.user_id == user_id, OrgMember.org_id == org_id
        )
    )).scalar() or 0
    api_tokens = (await db.execute(
        select(func.count(ApiToken.id)).where(ApiToken.user_id == user_id)
    )).scalar() or 0
    sessions = (await db.execute(
        select(func.count(RefreshToken.id)).where(
            RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
        )
    )).scalar() or 0

    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()

    # Человек мог быть ОТВЕТСТВЕННЫМ за выдачу — это отдельная проблема:
    # его уход осиротит целые типы ресурсов и подвесит чужие заявки.
    owned_types = (await db.execute(
        select(ResourceCatalog.id, ResourceCatalog.name)
        .where(
            ResourceCatalog.org_id == org_id,
            ResourceCatalog.responsible_user_id == user_id,
            ResourceCatalog.is_active.is_(True),
        )
    )).all()
    stuck_requests = (await db.execute(
        select(func.count(AccessRequest.id)).where(
            AccessRequest.org_id == org_id,
            AccessRequest.assignee_user_id == user_id,
            AccessRequest.status.in_([AccessRequestStatus.new,
                                      AccessRequestStatus.in_progress]),
        )
    )).scalar() or 0

    system_items: List[Dict[str, Any]] = []

    def add(key: str, label: str, count: int, hint: str) -> None:
        if count:
            system_items.append({"key": key, "label": label, "count": count, "hint": hint})

    add("shared_access", "Доступы к чатам/кандидатам, выданные человеку", shared_cnt,
        "Снять в разделе «Доступы» на ресурсах")
    add("shared_by", "Доступы, которые человек выдал другим", shared_by_cnt,
        "Проверить и переназначить владельца")
    add("departments", "Членство в отделах", dept_cnt, "Убрать из отделов")
    add("org", "Членство в организации", org_cnt, "Убрать из организации")
    add("api_tokens", "Активные API-токены", api_tokens, "Отозвать токены")
    add("sessions", "Активные сессии (refresh-токены)", sessions,
        "Разлогинить — сбросить сессии")
    if user and user.telegram_id:
        system_items.append({
            "key": "telegram", "label": "Привязанный Telegram", "count": 1,
            "hint": f"@{user.telegram_username}" if user.telegram_username else "отвязать",
        })

    return {
        "user_id": user_id,
        "user_name": user.name if user else None,
        "resources": resource_items,
        "system": system_items,
        # Что он выдавал сам — требует передачи другому человеку
        "responsible_for": [{"resource_id": r[0], "name": r[1]} for r in owned_types],
        "stuck_requests": int(stuck_requests),
        "total": len(resource_items) + sum(i["count"] for i in system_items),
    }


async def cut_off_access(db: AsyncSession, user_id: int) -> Dict[str, Any]:
    """Отрезает уволенному вход во ВСЕ точки. Коммитит вызывающий.

    Порядок важен: гасим аккаунт и поднимаем token_version, чтобы уже выданные
    токены протухли немедленно, а не досидели свои 15 минут. Отзыв refresh-токенов
    отдельно — иначе он обменяет их на новый доступ.
    """
    result = {"login_disabled": False, "sessions_revoked": 0,
              "api_tokens_revoked": 0, "telegram_unbound": False}

    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        return result

    user.is_active = False
    # Инвалидирует все ранее выданные JWT: их token_version перестаёт совпадать
    user.token_version = (user.token_version or 0) + 1
    result["login_disabled"] = True

    if user.telegram_id:
        user.telegram_id = None
        user.telegram_username = None
        user.telegram_bind_token = None
        user.telegram_bind_expires = None
        result["telegram_unbound"] = True

    try:
        from .auth import revoke_all_user_tokens
        result["sessions_revoked"] = await revoke_all_user_tokens(db, user_id)
    except Exception:
        logger.exception("offboarding: не удалось отозвать refresh-токены")

    # API-токены: удаляем, отдельного флага «отозван» у модели нет
    try:
        tokens = (await db.execute(
            select(ApiToken).where(ApiToken.user_id == user_id)
        )).scalars().all()
        for t in tokens:
            await db.delete(t)
        result["api_tokens_revoked"] = len(tokens)
    except Exception:
        logger.exception("offboarding: не удалось отозвать API-токены")

    logger.info("offboarding: доступ отрезан user=%s %s", user_id, result)
    return result


async def run_offboarding(
    db: AsyncSession,
    org_id: int,
    user_id: int,
    actor_id: Optional[int],
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    """Собирает чек-лист и рассылает ответственным. Коммитит вызывающий.

    Ошибки уведомлений не должны валить само увольнение, поэтому каждый канал
    обёрнут отдельно — как и в остальных нотификаторах проекта.
    """
    checklist = await build_checklist(db, org_id, user_id)
    who = checklist.get("user_name") or f"Сотрудник #{user_id}"

    # Сначала отрезаем вход, потом уведомления: если рассылка упадёт, доступ
    # всё равно уже закрыт — это важнее, чем письма.
    checklist["cut_off"] = await cut_off_access(db, user_id)

    # Каждому ответственному — только его позиции, чтобы не раскрывать чужие
    by_responsible: Dict[int, List[Dict[str, Any]]] = {}
    for item in checklist["resources"]:
        rid = item.get("responsible_user_id")
        if rid:
            by_responsible.setdefault(rid, []).append(item)

    notified = 0
    for responsible_id, items in by_responsible.items():
        lines = "\n".join(f"• {i['resource_name']}" for i in items[:20])
        try:
            from .hr_notifications import _create_notification
            await _create_notification(
                db, responsible_id, "offboarding_revoke",
                f"Отзыв доступов: {who}",
                f"Сотрудник уволен. Нужно отозвать:\n{lines}",
                "/access-hub?tab=assigned",
            )
            notified += 1
        except Exception:
            logger.exception("offboarding: не удалось создать уведомление ответственному")
        try:
            from ..bot import send_telegram_notification
            await send_telegram_notification(
                responsible_id,
                f"<b>Отзыв доступов: {who}</b>\nСотрудник уволен. Нужно отозвать:\n{lines}",
            )
        except Exception:
            logger.exception("offboarding: не удалось отправить в Telegram")

    # Если уходил ответственный — это срочнее чем отзыв его доступов: без
    # передачи типы ресурсов остаются без владельца, а чужие заявки виснут.
    owned = checklist.get("responsible_for") or []
    stuck = checklist.get("stuck_requests") or 0
    if owned or stuck:
        names = ", ".join(o["name"] for o in owned[:10]) or "—"
        for admin_id in (await db.execute(
            select(OrgMember.user_id).where(
                OrgMember.org_id == org_id,
                OrgMember.role.in_([OrgRole.owner, OrgRole.admin]),
            )
        )).scalars().all():
            try:
                from .hr_notifications import _create_notification
                await _create_notification(
                    db, admin_id, "offboarding_responsible_left",
                    f"Ушёл ответственный за выдачу: {who}",
                    (f"Типы ресурсов без ответственного: {names}. "
                     f"Зависших заявок: {stuck}. Назначьте замену."),
                    "/access-hub?tab=assigned",
                )
            except Exception:
                logger.exception("offboarding: не удалось предупредить админа")

    logger.info(
        "offboarding: user=%s org=%s ресурсов=%s системных=%s уведомлено=%s причина=%r",
        user_id, org_id, len(checklist["resources"]), len(checklist["system"]), notified, reason,
    )
    checklist["notified_responsibles"] = notified
    return checklist


async def resolve_user_id_for_employee(db: AsyncSession, employee: Employee) -> int:
    return employee.user_id


async def user_id_for_entity(db: AsyncSession, entity_id: int) -> Optional[int]:
    """Кандидат → пользователь. Нужно второй «двери» (доска «Статусы»),
    которая оперирует карточкой, а не записью сотрудника."""
    return (await db.execute(
        select(Employee.user_id)
        .where(Employee.entity_id == entity_id)
        .order_by(Employee.id.desc())
        .limit(1)
    )).scalar_one_or_none()
