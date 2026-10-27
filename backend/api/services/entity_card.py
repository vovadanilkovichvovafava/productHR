"""Карточка кандидата/контакта в ответах API — одно место (20.10.2026).

Раньше одни и те же поля собирались словарём в четырёх ручках
(`GET /entities`, `POST`, `GET /{id}`, `PUT /{id}`), и копии разъехались: фильтр
скоупа по воронкам (`filter_extra_for_scope`) стоял только в `GET /{id}`, а ответ
на правку и создание отдавал `extra_data` целиком — с заметками и метками
чужих воронок. Здесь же — какие чаты и звонки кандидата человеку видны
(было скопировано в список и в карточку).
"""
from datetime import datetime
from typing import Any, Dict, Iterable, Optional, Tuple

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import (
    CallRecording, Chat, DepartmentMember, DeptRole, Entity, ResourceType,
    SharedAccess, User,
)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def entity_base_dict(
    entity: Entity,
    *,
    department_name: Optional[str],
    scope_ids: Optional[Iterable[int]] = None,
) -> Dict[str, Any]:
    """Поля карточки, общие для всех ответов. extra_data — уже со скоупом."""
    from .vacancy_scope import filter_extra_for_scope

    return {
        "id": entity.id,
        "type": entity.type,
        "name": entity.name,
        "status": entity.status,
        "phone": entity.phone,
        "email": entity.email,
        "telegram_user_id": entity.telegram_user_id,
        "telegram_usernames": entity.telegram_usernames or [],
        "emails": entity.emails or [],
        "phones": entity.phones or [],
        "company": entity.company,
        "position": entity.position,
        "tags": entity.tags or [],
        "extra_data": filter_extra_for_scope(entity.extra_data or {}, scope_ids) or {},
        "created_by": entity.created_by,
        "department_id": entity.department_id,
        "department_name": department_name,
        "created_at": _iso(entity.created_at),
        "updated_at": _iso(entity.updated_at),
        "expected_salary_min": entity.expected_salary_min,
        "expected_salary_max": entity.expected_salary_max,
        "expected_salary_currency": entity.expected_salary_currency or "RUB",
        # Optimistic locking version
        "version": entity.version or 1,
    }


def entity_broadcast_payload(entity: Entity) -> Dict[str, Any]:
    """Что уходит по WebSocket в entity.created / entity.updated.

    Рассылка идёт ВСЕМ подключённым в организации — и сотрудникам без
    HR-раздела, и наблюдателю со скоупом по воронкам. Раньше туда уходила
    карточка целиком: контакты и extra_data со всеми комментариями. Экраны HR
    эти события не читают (свои списки обновляют сами), поэтому отдаём только
    то, по чему можно понять «карточка изменилась»: без контактов и заметок.

    Читаем только УЖЕ загруженные поля: рассылка идёт после коммита, а
    updated_at обновляет сама база (onupdate), и обращение к нему тут лезло бы
    в базу из синхронного кода — MissingGreenlet, то есть 500 на ответе.
    """
    from sqlalchemy import inspect

    loaded = inspect(entity).dict
    return {
        "id": loaded.get("id"),
        "type": loaded.get("type"),
        "name": loaded.get("name"),
        "status": loaded.get("status"),
        "updated_at": _iso(loaded.get("updated_at")),
        "version": loaded.get("version") or 1,
    }


async def accessible_chat_call_conditions(
    db: AsyncSession, user: User, *, full_access: bool,
) -> Tuple[Optional[list], Optional[list]]:
    """Условия «какие чаты и звонки кандидата видны» — (чаты, звонки).

    (None, None) — полный доступ, видно всё. Иначе: свои, расшаренные мне и,
    если я lead/sub_admin отдела, — сотрудников моих отделов.
    """
    if full_access:
        return None, None
    now = datetime.utcnow()

    async def _shared(resource_type) -> set:
        return set((await db.execute(
            select(SharedAccess.resource_id).where(
                SharedAccess.resource_type == resource_type,
                SharedAccess.shared_with_id == user.id,
                or_(SharedAccess.expires_at.is_(None), SharedAccess.expires_at > now),
            )
        )).scalars().all())

    shared_chat_ids = await _shared(ResourceType.chat)
    shared_call_ids = await _shared(ResourceType.call)

    admin_dept_ids = list((await db.execute(
        select(DepartmentMember.department_id).where(
            DepartmentMember.user_id == user.id,
            DepartmentMember.role.in_([DeptRole.lead, DeptRole.sub_admin]),
        )
    )).scalars().all())
    dept_member_ids: set = set()
    if admin_dept_ids:
        dept_member_ids = set((await db.execute(
            select(DepartmentMember.user_id).where(
                DepartmentMember.department_id.in_(admin_dept_ids)
            )
        )).scalars().all())

    chat_conditions = [Chat.owner_id == user.id]
    if shared_chat_ids:
        chat_conditions.append(Chat.id.in_(shared_chat_ids))
    if dept_member_ids:
        chat_conditions.append(Chat.owner_id.in_(dept_member_ids))

    call_conditions = [CallRecording.owner_id == user.id]
    if shared_call_ids:
        call_conditions.append(CallRecording.id.in_(shared_call_ids))
    if dept_member_ids:
        call_conditions.append(CallRecording.owner_id.in_(dept_member_ids))

    return chat_conditions, call_conditions
