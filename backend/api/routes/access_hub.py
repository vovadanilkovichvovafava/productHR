"""Хаб доступов — каталог ресурсов, заявки, выдача, леджер и оффбординг.

Сценарий: сотрудник по своей роли запрашивает ресурс (прокси, аккаунт,
пополнение) → заявка уходит ответственному за этот ТИП ресурса → тот выдаёт
или отклоняет → выданное копится в карточке сотрудника → при увольнении по
этому же списку строится чек-лист отзыва.

Два принципа из ТЗ, которые здесь зашиты:

1. АНОНИМНОСТЬ СНАБЖЕНИЯ. Заявитель никогда не видит имя ответственного —
   в ответе ему приходит «Снабжение». Настоящее имя видят только сам
   ответственный и админы (см. _serialize_request).

2. НИКАКИХ СЕКРЕТОВ. Модуль трекает только факт выдачи и статус. Пароли,
   ключи и данные карт здесь не хранятся и не передаются — поэтому в моделях
   нет ни одного поля под креды.
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

from ..database import get_db
from ..models.database import (
    AccessRequest, AccessRequestAudit, AccessRequestMessage, AccessRequestStatus,
    ResourceCatalog, ResourceCategory, RoleResourceGrant,
    CustomRole, UserCustomRole, Employee, Entity, OrgUnit,
    User, OrgMember, OrgRole, UserRole,
)
from ..services.auth import get_current_user, get_user_org

logger = logging.getLogger("hr-analyzer.access-hub")

router = APIRouter()

ANON_ASSIGNEE = "Снабжение"

# Заявки, которые считаются «живыми» — по ним нельзя решать повторно.
OPEN_STATUSES = (AccessRequestStatus.new, AccessRequestStatus.in_progress)


# --------------------------------------------------------------------------- #
# Схемы                                                                         #
# --------------------------------------------------------------------------- #

class ResourceParam(BaseModel):
    key: str
    label: str
    type: str = "text"              # text | select | number
    required: bool = False
    options: List[str] = []


class ResourceCreate(BaseModel):
    key: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    category: str = ResourceCategory.other.value
    description: Optional[str] = None
    responsible_user_id: Optional[int] = None
    params_schema: List[ResourceParam] = []
    unlock_condition: str = "always"
    limit_per_month: Optional[int] = None
    limit_amount_month: Optional[int] = None
    currency: Optional[str] = "RUB"
    available_to_all: bool = False


class ResourceUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    responsible_user_id: Optional[int] = None
    params_schema: Optional[List[ResourceParam]] = None
    unlock_condition: Optional[str] = None
    limit_per_month: Optional[int] = None
    limit_amount_month: Optional[int] = None
    currency: Optional[str] = None
    available_to_all: Optional[bool] = None
    is_active: Optional[bool] = None


class ResourceOut(BaseModel):
    id: int
    key: str
    name: str
    category: str
    description: Optional[str] = None
    responsible_user_id: Optional[int] = None
    responsible_name: Optional[str] = None
    params_schema: List[Dict[str, Any]] = []
    unlock_condition: str
    limit_per_month: Optional[int] = None
    limit_amount_month: Optional[int] = None
    currency: Optional[str] = None
    available_to_all: bool = False
    is_active: bool
    # для экрана «Создать заявку»
    locked: bool = False
    lock_reason: Optional[str] = None
    used_this_month: int = 0
    # Состояние доступа для «кнопки» в кабинете:
    #   granted — выдан (зелёная), pending — заявка в работе (жёлтая),
    #   rejected — отказ (красная), none — ещё не запрашивал (нейтральная)
    state: str = "none"
    last_request_id: Optional[int] = None
    # Параметры последней ВЫДАННОЙ заявки — чтобы кнопка показывала, что именно
    # на руках («Выдан · US»), а не просто «Выдан».
    granted_params: Dict[str, Any] = {}


class RequestCreate(BaseModel):
    resource_id: int
    params: Dict[str, Any] = {}
    comment: Optional[str] = None
    amount: Optional[int] = None
    target_user_id: Optional[int] = None   # админ может завести за сотрудника


class RequestDecision(BaseModel):
    comment: Optional[str] = None
    amount: Optional[int] = None


class RequestOut(BaseModel):
    id: int
    resource_id: int
    resource_name: str
    resource_category: str
    requester_user_id: int
    requester_name: Optional[str] = None
    target_user_id: Optional[int] = None
    target_name: Optional[str] = None
    assignee_display: str                  # «Снабжение» для заявителя
    assignee_user_id: Optional[int] = None  # только для админа/исполнителя
    params: Dict[str, Any] = {}
    comment: Optional[str] = None
    status: str
    amount: Optional[int] = None
    currency: Optional[str] = None
    decision_comment: Optional[str] = None
    decided_at: Optional[datetime] = None
    granted_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    can_decide: bool = False               # текущий юзер может выдать/отклонить


class AuditOut(BaseModel):
    id: int
    from_status: Optional[str] = None
    to_status: str
    action: str
    changed_by: Optional[int] = None
    changed_by_name: Optional[str] = None
    comment: Optional[str] = None
    created_at: Optional[datetime] = None


class GrantOut(BaseModel):
    """Строка леджера — что у человека сейчас на руках."""
    request_id: int
    resource_id: int
    resource_name: str
    resource_category: str
    params: Dict[str, Any] = {}
    granted_at: Optional[datetime] = None
    responsible_user_id: Optional[int] = None
    status: str


# --------------------------------------------------------------------------- #
# Доступ и хелперы                                                              #
# --------------------------------------------------------------------------- #

async def _is_org_admin(user: User, org, db: AsyncSession) -> bool:
    """Суперадмин / владелец / админ организации."""
    if user.role == UserRole.superadmin:
        return True
    row = (await db.execute(
        select(OrgMember.role).where(
            OrgMember.org_id == org.id, OrgMember.user_id == user.id
        )
    )).scalar_one_or_none()
    return row in (OrgRole.owner, OrgRole.admin)


async def _is_active_in_org(user_id: Optional[int], org_id: int, db: AsyncSession) -> bool:
    """Работает ли человек в организации прямо сейчас.

    Увольнение в системе ставит Employee.is_active=False, но НЕ трогает
    User.is_active — поэтому проверять надо запись сотрудника, иначе уволенный
    ответственный продолжит выдавать доступы.
    """
    if not user_id:
        return False
    emp = (await db.execute(
        select(Employee.is_active)
        .where(Employee.user_id == user_id, Employee.org_id == org_id)
        .order_by(Employee.id.desc())
        .limit(1)
    )).scalar_one_or_none()
    # Нет записи сотрудника — это админ/владелец без оформления в штат,он имеет право
    return True if emp is None else bool(emp)


async def _org_admin_ids(org_id: int, db: AsyncSession) -> List[int]:
    """Владельцы и админы организации — запасной адресат осиротевших заявок."""
    rows = (await db.execute(
        select(OrgMember.user_id).where(
            OrgMember.org_id == org_id,
            OrgMember.role.in_([OrgRole.owner, OrgRole.admin]),
        )
    )).scalars().all()
    return list(rows)


async def _require_active_member(user: User, org, db: AsyncSession) -> bool:
    """Уволенный не может пользоваться хабом. Возвращает is_admin.

    Проверяем ЗАПИСЬ СОТРУДНИКА, а не User.is_active: увольнение ставит
    Employee.is_active=False и не трогает флаг аккаунта. Без этой проверки
    уволенный человек с ролью продолжал видеть каталог и создавать заявки —
    доступ к кабинету ему закрыли, а к хабу нет.

    Отсутствие записи сотрудника нарушением НЕ считаем: у владельца/админа
    её может не быть, они в штат не оформлены.
    """
    is_admin = await _is_org_admin(user, org, db)
    if is_admin:
        return True
    if not await _is_active_in_org(user.id, org.id, db):
        raise HTTPException(403, "Сотрудник уволен — хаб доступов закрыт")
    return False


async def _active_role_id(user_id: int, db: AsyncSession) -> Optional[int]:
    """Текущая кастомная роль пользователя (побеждает последняя назначенная —
    та же логика, что в admin/custom_roles)."""
    return (await db.execute(
        select(UserCustomRole.role_id)
        .join(CustomRole, CustomRole.id == UserCustomRole.role_id)
        .where(UserCustomRole.user_id == user_id, CustomRole.is_active.is_(True))
        .order_by(UserCustomRole.assigned_at.desc())
        .limit(1)
    )).scalar_one_or_none()


async def _unlock_state(user_id: int, org_id: int, db: AsyncSession) -> Dict[str, bool]:
    """Условия разблокировки ресурсов для конкретного человека."""
    emp = (await db.execute(
        select(Employee).where(Employee.user_id == user_id, Employee.org_id == org_id)
    )).scalars().first()

    in_staff = bool(emp and emp.is_active)

    prometheus_ok = False
    if emp and emp.entity_id:
        extra = (await db.execute(
            select(Entity.extra_data).where(Entity.id == emp.entity_id)
        )).scalar_one_or_none()
        if isinstance(extra, dict):
            # Prometheus присылает код ACCEPTED, у нас он лежит уже в русской
            # канонической форме (см. services/prometheus_status.STATUS_CODE_MAP)
            prometheus_ok = (
                extra.get("prometheus_status") == "Принят"
                or extra.get("prometheus_status_code") == "ACCEPTED"
            )

    return {"always": True, "in_staff": in_staff, "prometheus_accepted": prometheus_ok}


async def _used_this_month(user_id: int, resource_id: int, db: AsyncSession) -> tuple[int, int]:
    """Сколько штук и на какую сумму человек уже получил по этому ресурсу
    в текущем календарном месяце (учитываем только реально выданное)."""
    now = datetime.utcnow()
    start = datetime(now.year, now.month, 1)
    row = (await db.execute(
        select(func.count(AccessRequest.id), func.coalesce(func.sum(AccessRequest.amount), 0))
        .where(
            AccessRequest.resource_id == resource_id,
            AccessRequest.status == AccessRequestStatus.granted,
            AccessRequest.granted_at >= start,
            func.coalesce(AccessRequest.target_user_id, AccessRequest.requester_user_id) == user_id,
        )
    )).one()
    return int(row[0] or 0), int(row[1] or 0)


async def _company_unit_id(user_id: int, db: AsyncSession) -> Optional[int]:
    """Компания холдинга = КОРНЕВОЙ org_unit в ветке сотрудника.

    Компания — отдельный уровень над отделом, поэтому поднимаемся по parent_id
    до корня. Ограничиваем глубину, чтобы кривые данные с циклом не повесили
    запрос.
    """
    emp = (await db.execute(
        select(Employee.org_unit_id).where(Employee.user_id == user_id)
    )).scalar_one_or_none()
    if not emp:
        return None
    unit_id, seen = emp, set()
    for _ in range(10):
        if unit_id in seen:
            break
        seen.add(unit_id)
        parent = (await db.execute(
            select(OrgUnit.parent_id).where(OrgUnit.id == unit_id)
        )).scalar_one_or_none()
        if not parent:
            return unit_id
        unit_id = parent
    return unit_id


def _audit(db: AsyncSession, req: AccessRequest, action: str,
           from_status: Optional[str], to_status: str,
           user_id: Optional[int], comment: Optional[str] = None) -> None:
    """Строка журнала. Коммитит вызывающий — как в services/stage_transitions."""
    db.add(AccessRequestAudit(
        request_id=req.id, org_id=req.org_id,
        from_status=from_status, to_status=to_status,
        action=action, changed_by=user_id, comment=comment,
    ))


async def _push(user_ids: List[Optional[int]], event: str, payload: Dict[str, Any]) -> None:
    """Адресный WebSocket-пуш (ТЗ п. 5: live-обновление «доступ выдан»).

    Шлём точечно участникам заявки, а не всей организации: заявки видны
    только своим, и рассылка на org раскрыла бы факт чужих запросов.

    Падение сокета не должно ронять саму операцию — статус уже сохранён.
    """
    targets = {u for u in user_ids if u}
    if not targets:
        return
    try:
        from .realtime import manager
        await manager.broadcast_to_users(list(targets), event, payload)
    except Exception:
        logger.exception("access-hub: не удалось отправить событие в WebSocket")


def _request_event(req: "AccessRequest") -> Dict[str, Any]:
    """Полезная нагрузка события. Имя ответственного НЕ кладём: событие
    прилетает и заявителю, для которого он анонимен."""
    return {
        "request_id": req.id,
        "resource_id": req.resource_id,
        "resource_name": req.resource.name if req.resource else None,
        "status": req.status.value if hasattr(req.status, "value") else str(req.status),
    }


async def _notify(db: AsyncSession, user_id: Optional[int], ntype: str,
                  title: str, message: str, link: str) -> None:
    """Уведомление в интерфейс + Telegram. Никогда не роняет основную операцию."""
    if not user_id:
        return
    try:
        from ..services.hr_notifications import _create_notification
        await _create_notification(db, user_id, ntype, title, message, link)
    except Exception:
        logger.exception("access-hub: не удалось создать уведомление")
    try:
        from ..bot import send_telegram_notification
        # with_app_button: под сообщением появится «Открыть приложение» —
        # человек попадает в Mini App одним касанием, а не ищет ссылку.
        await send_telegram_notification(
            user_id, f"<b>{title}</b>\n{message}", with_app_button=True
        )
    except Exception:
        logger.exception("access-hub: не удалось отправить в Telegram")
    try:
        from .realtime import manager
        await manager.broadcast_to_user(user_id, "access_request.updated", {"link": link})
    except Exception:
        logger.debug("access-hub: WS-пуш не доставлен", exc_info=True)


def _serialize_request(req: AccessRequest, *, viewer_id: int, is_admin: bool,
                       names: Dict[int, str]) -> RequestOut:
    """Анонимность: имя ответственного видят только он сам и админы."""
    reveal = is_admin or req.assignee_user_id == viewer_id
    return RequestOut(
        id=req.id,
        resource_id=req.resource_id,
        resource_name=req.resource.name if req.resource else "—",
        resource_category=(req.resource.category.value
                           if req.resource and hasattr(req.resource.category, "value")
                           else str(req.resource.category) if req.resource else "other"),
        requester_user_id=req.requester_user_id,
        requester_name=names.get(req.requester_user_id),
        target_user_id=req.target_user_id,
        target_name=names.get(req.target_user_id) if req.target_user_id else None,
        assignee_display=(names.get(req.assignee_user_id) or ANON_ASSIGNEE) if reveal else ANON_ASSIGNEE,
        assignee_user_id=req.assignee_user_id if reveal else None,
        params=req.params if isinstance(req.params, dict) else {},
        comment=req.comment,
        status=req.status.value if hasattr(req.status, "value") else str(req.status),
        amount=req.amount,
        currency=req.currency,
        decision_comment=req.decision_comment,
        decided_at=req.decided_at,
        granted_at=req.granted_at,
        revoked_at=req.revoked_at,
        created_at=req.created_at,
        can_decide=(is_admin or req.assignee_user_id == viewer_id)
                   and req.status in OPEN_STATUSES,
    )


async def _names_for(db: AsyncSession, ids: List[Optional[int]]) -> Dict[int, str]:
    clean = [i for i in ids if i]
    if not clean:
        return {}
    rows = (await db.execute(
        select(User.id, User.name).where(User.id.in_(set(clean)))
    )).all()
    return {r[0]: r[1] for r in rows}


# --------------------------------------------------------------------------- #
# Каталог ресурсов                                                              #
# --------------------------------------------------------------------------- #

@router.get("/catalog", response_model=List[ResourceOut])
async def list_catalog(
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Полный каталог (для админа). Пользователю нужен /available."""
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")
    if not await _is_org_admin(current_user, org, db):
        raise HTTPException(403, "Каталог доступен только администраторам")

    await _ensure_default_catalog(db, org)

    q = select(ResourceCatalog).where(ResourceCatalog.org_id == org.id)
    if not include_inactive:
        q = q.where(ResourceCatalog.is_active.is_(True))
    rows = (await db.execute(q.order_by(ResourceCatalog.name))).scalars().all()

    names = await _names_for(db, [r.responsible_user_id for r in rows])
    return [
        ResourceOut(
            id=r.id, key=r.key, name=r.name,
            category=r.category.value if hasattr(r.category, "value") else str(r.category),
            description=r.description,
            responsible_user_id=r.responsible_user_id,
            responsible_name=names.get(r.responsible_user_id),
            params_schema=r.params_schema or [],
            unlock_condition=r.unlock_condition,
            limit_per_month=r.limit_per_month,
            limit_amount_month=r.limit_amount_month,
            currency=r.currency, available_to_all=bool(r.available_to_all), is_active=r.is_active,
        ) for r in rows
    ]


@router.post("/catalog", response_model=ResourceOut, status_code=201)
async def create_resource(
    data: ResourceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")
    if not await _is_org_admin(current_user, org, db):
        raise HTTPException(403, "Добавлять типы ресурсов может только администратор")

    key = data.key.strip()
    dup = (await db.execute(
        select(ResourceCatalog.id).where(
            ResourceCatalog.org_id == org.id, ResourceCatalog.key == key
        )
    )).scalar_one_or_none()
    if dup:
        raise HTTPException(409, f"Ресурс с ключом «{key}» уже есть")

    try:
        category = ResourceCategory(data.category)
    except ValueError:
        raise HTTPException(400, f"Неизвестная категория: {data.category}")

    res = ResourceCatalog(
        org_id=org.id, key=key, name=data.name.strip(), category=category,
        description=data.description, responsible_user_id=data.responsible_user_id,
        params_schema=[p.model_dump() for p in data.params_schema],
        unlock_condition=data.unlock_condition,
        limit_per_month=data.limit_per_month,
        limit_amount_month=data.limit_amount_month,
        currency=data.currency, available_to_all=bool(data.available_to_all),
        created_by=current_user.id,
    )
    db.add(res)
    await db.commit()
    await db.refresh(res)

    names = await _names_for(db, [res.responsible_user_id])
    return ResourceOut(
        id=res.id, key=res.key, name=res.name, category=res.category.value,
        description=res.description, responsible_user_id=res.responsible_user_id,
        responsible_name=names.get(res.responsible_user_id),
        params_schema=res.params_schema or [], unlock_condition=res.unlock_condition,
        limit_per_month=res.limit_per_month, limit_amount_month=res.limit_amount_month,
        currency=res.currency, available_to_all=bool(res.available_to_all), is_active=res.is_active,
    )


@router.patch("/catalog/{resource_id}", response_model=ResourceOut)
async def update_resource(
    resource_id: int,
    data: ResourceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")
    if not await _is_org_admin(current_user, org, db):
        raise HTTPException(403, "Изменять каталог может только администратор")

    res = (await db.execute(
        select(ResourceCatalog).where(
            ResourceCatalog.id == resource_id, ResourceCatalog.org_id == org.id
        )
    )).scalar_one_or_none()
    if not res:
        raise HTTPException(404, "Ресурс не найден")

    payload = data.model_dump(exclude_unset=True)
    if "category" in payload and payload["category"] is not None:
        try:
            res.category = ResourceCategory(payload.pop("category"))
        except ValueError:
            raise HTTPException(400, "Неизвестная категория")
    if "params_schema" in payload and payload["params_schema"] is not None:
        res.params_schema = [p if isinstance(p, dict) else p.model_dump()
                             for p in payload.pop("params_schema")]
    for field, value in payload.items():
        if value is not None or field in ("description", "responsible_user_id"):
            setattr(res, field, value)

    await db.commit()
    await db.refresh(res)
    names = await _names_for(db, [res.responsible_user_id])
    return ResourceOut(
        id=res.id, key=res.key, name=res.name,
        category=res.category.value if hasattr(res.category, "value") else str(res.category),
        description=res.description, responsible_user_id=res.responsible_user_id,
        responsible_name=names.get(res.responsible_user_id),
        params_schema=res.params_schema or [], unlock_condition=res.unlock_condition,
        limit_per_month=res.limit_per_month, limit_amount_month=res.limit_amount_month,
        currency=res.currency, available_to_all=bool(res.available_to_all), is_active=res.is_active,
    )


# --------------------------------------------------------------------------- #
# Конструктор ролей: галочки «что этой роли можно запрашивать»                   #
# --------------------------------------------------------------------------- #

@router.get("/roles/{role_id}/resources", response_model=List[int])
async def get_role_resources(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """ID ресурсов, разрешённых роли."""
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org or not await _is_org_admin(current_user, org, db):
        raise HTTPException(403, "Доступно только администратору")
    rows = (await db.execute(
        select(RoleResourceGrant.resource_id).where(
            RoleResourceGrant.role_id == role_id,
            RoleResourceGrant.can_request.is_(True),
        )
    )).scalars().all()
    return list(rows)


@router.put("/roles/{role_id}/resources", response_model=List[int])
async def set_role_resources(
    role_id: int,
    resource_ids: List[int],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Полная перезапись набора галочек для роли."""
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org or not await _is_org_admin(current_user, org, db):
        raise HTTPException(403, "Доступно только администратору")

    role = (await db.execute(
        select(CustomRole).where(CustomRole.id == role_id)
    )).scalar_one_or_none()
    if not role:
        raise HTTPException(404, "Роль не найдена")
    if role.org_id and role.org_id != org.id:
        raise HTTPException(404, "Роль не найдена")

    valid = set((await db.execute(
        select(ResourceCatalog.id).where(
            ResourceCatalog.org_id == org.id,
            ResourceCatalog.id.in_(resource_ids or [0]),
        )
    )).scalars().all())

    existing = (await db.execute(
        select(RoleResourceGrant).where(RoleResourceGrant.role_id == role_id)
    )).scalars().all()
    by_res = {g.resource_id: g for g in existing}

    for res_id in valid:
        if res_id in by_res:
            by_res[res_id].can_request = True
        else:
            db.add(RoleResourceGrant(role_id=role_id, resource_id=res_id, can_request=True))
    for res_id, grant in by_res.items():
        if res_id not in valid:
            await db.delete(grant)

    await db.commit()
    return sorted(valid)


# --------------------------------------------------------------------------- #
# Что я могу запросить                                                          #
# --------------------------------------------------------------------------- #


# Базовый справочник типов из ТЗ, п. 3.3: «прокси, пополнение платёжки,
# оплата, аккаунт, расходник, TG-аккаунт и другие».
_DEFAULT_CATALOG = [
    dict(key="proxy", name="Прокси", category=ResourceCategory.proxy,
         description="Резидентный прокси под задачу",
         unlock_condition="always", limit_per_month=5, available_to_all=True),
    dict(key="tg_account", name="Telegram-аккаунт", category=ResourceCategory.tg_account,
         description="Рабочий аккаунт для связи",
         unlock_condition="always", limit_per_month=3, available_to_all=True),
    dict(key="service_account", name="Аккаунт сервиса", category=ResourceCategory.account,
         description="Доступ к рабочему сервису",
         unlock_condition="always", available_to_all=True),
    dict(key="consumable", name="Расходник", category=ResourceCategory.consumable,
         description="Расходные материалы",
         unlock_condition="always", limit_per_month=10, available_to_all=True),
    dict(key="card_topup", name="Пополнение платёжки", category=ResourceCategory.payment_topup,
         description="Пополнение рабочей карты",
         unlock_condition="prometheus_accepted", limit_amount_month=50000, currency="RUB"),
    dict(key="subscription", name="Оплата подписки", category=ResourceCategory.payment,
         description="Оплата сервиса по счёту",
         unlock_condition="prometheus_accepted", limit_amount_month=30000, currency="RUB"),
]

_SEEDED_FLAG = "access_hub_seeded"
# Версия набора. Поднимается, когда прошлый проход отработал неверно и его
# нужно повторить: организации с меньшим значением засеиваются ещё раз.
_SEED_VERSION = 2


async def _ensure_default_catalog(db: AsyncSession, org) -> None:
    """Разово завести базовые типы ресурсов организации.

    Без этого хаб открывается пустым экраном: заявок не создать, потому что
    запрашивать нечего, — а заводить шесть типов руками должен был бы каждый
    новый клиент.

    Помечаем организацию флагом и больше не возвращаемся: иначе типы, которые
    админ намеренно удалил, воскресали бы при каждом открытии.
    """
    settings = dict(org.settings) if isinstance(org.settings, dict) else {}
    try:
        seeded = int(settings.get(_SEEDED_FLAG) or 0)
    except (TypeError, ValueError):
        seeded = 1 if settings.get(_SEEDED_FLAG) else 0
    if seeded >= _SEED_VERSION:
        return

    # Заводим недостающие ПО КЛЮЧУ, а не «только если каталог пуст».
    # Прошлая версия молча ничего не делала, если админ успел создать хотя бы
    # один свой ресурс: базовых типов не появлялось, а флаг проставлялся — и
    # второго шанса уже не было.
    existing_keys = set((await db.execute(
        select(ResourceCatalog.key).where(ResourceCatalog.org_id == org.id)
    )).scalars().all())

    for item in _DEFAULT_CATALOG:
        if item["key"] in existing_keys:
            continue
        db.add(ResourceCatalog(org_id=org.id, params_schema=[], **item))

    settings[_SEEDED_FLAG] = _SEED_VERSION
    org.settings = settings
    flag_modified(org, "settings")
    await db.commit()
    logger.info("Access hub: базовый каталог заведён для org=%s", org.id)


@router.get("/available", response_model=List[ResourceOut])
async def available_resources(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Экран «Создать заявку»: только то, что доступно по роли, с учётом
    условия разблокировки и уже израсходованного лимита."""
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    await _ensure_default_catalog(db, org)

    is_admin = await _require_active_member(current_user, org, db)
    role_id = await _active_role_id(current_user.id, db)

    q = select(ResourceCatalog).where(
        ResourceCatalog.org_id == org.id, ResourceCatalog.is_active.is_(True)
    )
    # Админ видит весь каталог; остальные — то, что открыто их ролью, ЛИБО
    # помечено как доступное всем.
    #
    # Раньше здесь стоял ранний выход при отсутствии роли, и сотрудник без
    # кастомной роли — а это большинство — не видел вообще ничего, сколько бы
    # ресурсов ни завели.
    if not is_admin:
        allowed_by_role = select(RoleResourceGrant.resource_id).where(
            RoleResourceGrant.role_id == role_id,
            RoleResourceGrant.can_request.is_(True),
        ) if role_id else None

        if allowed_by_role is not None:
            q = q.where(or_(
                ResourceCatalog.available_to_all.is_(True),
                ResourceCatalog.id.in_(allowed_by_role),
            ))
        else:
            q = q.where(ResourceCatalog.available_to_all.is_(True))
    rows = (await db.execute(q.order_by(ResourceCatalog.name))).scalars().all()

    unlock = await _unlock_state(current_user.id, org.id, db)

    # Последняя заявка пользователя по каждому ресурсу — из неё берём состояние
    # кнопки. Один запрос на всё, чтобы не долбить БД в цикле.
    my_requests = (await db.execute(
        select(AccessRequest)
        .where(
            AccessRequest.org_id == org.id,
            func.coalesce(AccessRequest.target_user_id,
                          AccessRequest.requester_user_id) == current_user.id,
        )
        .order_by(AccessRequest.created_at.desc())
    )).scalars().all()
    latest: Dict[int, AccessRequest] = {}
    for req in my_requests:
        latest.setdefault(req.resource_id, req)

    def state_of(resource_id: int) -> tuple[str, Optional[int], Dict[str, Any]]:
        req = latest.get(resource_id)
        if not req:
            return "none", None, {}
        params = req.params if isinstance(req.params, dict) else {}
        st = req.status
        if st == AccessRequestStatus.granted:
            return "granted", req.id, params
        if st in OPEN_STATUSES:
            return "pending", req.id, {}
        if st == AccessRequestStatus.rejected:
            return "rejected", req.id, {}
        return "none", req.id, {}   # revoked → снова можно запрашивать

    out: List[ResourceOut] = []
    for r in rows:
        cond = r.unlock_condition or "always"
        unlocked = unlock.get(cond, True)
        used_cnt, used_amount = await _used_this_month(current_user.id, r.id, db)

        locked, reason = False, None
        if not unlocked:
            locked = True
            reason = ("Доступно после успешного прохождения практики"
                      if cond == "prometheus_accepted" else "Доступно после оформления в штат")
        elif r.limit_per_month is not None and used_cnt >= r.limit_per_month:
            locked = True
            reason = f"Исчерпан лимит: {used_cnt}/{r.limit_per_month} в этом месяце"
        elif r.limit_amount_month is not None and used_amount >= r.limit_amount_month:
            locked = True
            reason = "Исчерпан бюджет по этому ресурсу в этом месяце"

        out.append(ResourceOut(
            id=r.id, key=r.key, name=r.name,
            category=r.category.value if hasattr(r.category, "value") else str(r.category),
            description=r.description,
            params_schema=r.params_schema or [],
            unlock_condition=cond,
            limit_per_month=r.limit_per_month,
            limit_amount_month=r.limit_amount_month,
            currency=r.currency, available_to_all=bool(r.available_to_all), is_active=r.is_active,
            locked=locked, lock_reason=reason, used_this_month=used_cnt,
            **dict(zip(("state", "last_request_id", "granted_params"), state_of(r.id))),
        ))
    return out


# --------------------------------------------------------------------------- #
# Заявки                                                                        #
# --------------------------------------------------------------------------- #

@router.post("/requests", response_model=RequestOut, status_code=201)
async def create_request(
    data: RequestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    res = (await db.execute(
        select(ResourceCatalog).where(
            ResourceCatalog.id == data.resource_id,
            ResourceCatalog.org_id == org.id,
            ResourceCatalog.is_active.is_(True),
        )
    )).scalar_one_or_none()
    if not res:
        raise HTTPException(404, "Ресурс не найден или отключён")

    is_admin = await _require_active_member(current_user, org, db)
    target_id = data.target_user_id or current_user.id
    if data.target_user_id and data.target_user_id != current_user.id and not is_admin:
        raise HTTPException(403, "Заводить заявку за другого может только администратор")

    # Право по роли. Проверка обязана совпадать с тем, что показывает
    # /available: там ресурс виден и по признаку «доступен всем», а здесь
    # учитывалась только роль — человек видел кнопку, жал и получал отказ.
    if not is_admin and not res.available_to_all:
        role_id = await _active_role_id(current_user.id, db)
        allowed = role_id and (await db.execute(
            select(RoleResourceGrant.id).where(
                RoleResourceGrant.role_id == role_id,
                RoleResourceGrant.resource_id == res.id,
                RoleResourceGrant.can_request.is_(True),
            )
        )).scalar_one_or_none()
        if not allowed:
            raise HTTPException(403, "Этот ресурс недоступен для вашей роли")

    # Условие разблокировки
    unlock = await _unlock_state(target_id, org.id, db)
    if not unlock.get(res.unlock_condition or "always", True):
        raise HTTPException(
            403,
            "Ресурс ещё не разблокирован: "
            + ("нужно успешно пройти практику"
               if res.unlock_condition == "prometheus_accepted" else "нужно быть оформленным в штат"),
        )

    # Лимиты
    used_cnt, used_amount = await _used_this_month(target_id, res.id, db)
    if res.limit_per_month is not None and used_cnt >= res.limit_per_month:
        raise HTTPException(429, f"Исчерпан лимит по ресурсу: {used_cnt}/{res.limit_per_month} в месяц")
    if res.limit_amount_month is not None:
        planned = used_amount + (data.amount or 0)
        if planned > res.limit_amount_month:
            raise HTTPException(429, "Превышен месячный бюджет по этому ресурсу")

    # Обязательные параметры формы
    for p in (res.params_schema or []):
        if p.get("required") and not str(data.params.get(p.get("key"), "")).strip():
            raise HTTPException(400, f"Не заполнено обязательное поле: {p.get('label') or p.get('key')}")

    req = AccessRequest(
        org_id=org.id,
        requester_user_id=current_user.id,
        target_user_id=target_id if target_id != current_user.id else None,
        resource_id=res.id,
        company_unit_id=await _company_unit_id(target_id, db),
        params=data.params or {},
        comment=data.comment,
        status=AccessRequestStatus.new,
        # Роутинг по ТИПУ ресурса. Если ответственный уволился или не назначен —
        # НЕ оставляем заявку висеть в никуда: assignee пустой, и она попадает
        # админам (они видят все заявки и могут решать).
        assignee_user_id=(res.responsible_user_id
                          if await _is_active_in_org(res.responsible_user_id, org.id, db)
                          else None),
        amount=data.amount,
        currency=res.currency,
    )
    db.add(req)
    await db.flush()
    _audit(db, req, "create", None, AccessRequestStatus.new.value, current_user.id, data.comment)
    await db.commit()

    if req.assignee_user_id:
        await _notify(
            db, req.assignee_user_id, "access_request_new",
            "Новая заявка на ресурс",
            f"{res.name} — от {current_user.name}",
            f"/access-hub/requests/{req.id}",
        )
    else:
        # Осиротевший тип ресурса — зовём админов и прямо говорим почему
        for admin_id in await _org_admin_ids(org.id, db):
            await _notify(
                db, admin_id, "access_request_orphan",
                "Заявка без ответственного",
                f"{res.name} — от {current_user.name}. "
                "За этот тип ресурса некому отвечать: назначьте ответственного.",
                f"/access-hub/requests/{req.id}",
            )
    await db.commit()

    req = (await db.execute(
        select(AccessRequest).where(AccessRequest.id == req.id)
        .options(selectinload(AccessRequest.resource))
    )).scalar_one()
    names = await _names_for(db, [req.requester_user_id, req.target_user_id, req.assignee_user_id])
    return _serialize_request(req, viewer_id=current_user.id, is_admin=is_admin, names=names)


@router.get("/requests", response_model=List[RequestOut])
async def list_requests(
    scope: str = Query("my", pattern="^(my|assigned|all)$"),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Видимость из ТЗ: пользователь — только свои, исполнитель — назначенные,
    суперадмин — все."""
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")
    is_admin = await _require_active_member(current_user, org, db)

    q = (select(AccessRequest)
         .where(AccessRequest.org_id == org.id)
         .options(selectinload(AccessRequest.resource)))

    if scope == "all":
        if not is_admin:
            raise HTTPException(403, "Все заявки видит только администратор")
    elif scope == "assigned":
        q = q.where(AccessRequest.assignee_user_id == current_user.id)
    else:
        q = q.where(
            (AccessRequest.requester_user_id == current_user.id)
            | (AccessRequest.target_user_id == current_user.id)
        )

    if status:
        try:
            q = q.where(AccessRequest.status == AccessRequestStatus(status))
        except ValueError:
            raise HTTPException(400, f"Неизвестный статус: {status}")

    rows = (await db.execute(q.order_by(AccessRequest.created_at.desc()).limit(500))).scalars().all()
    names = await _names_for(
        db, [i for r in rows for i in (r.requester_user_id, r.target_user_id, r.assignee_user_id)]
    )
    return [_serialize_request(r, viewer_id=current_user.id, is_admin=is_admin, names=names)
            for r in rows]


async def _load_for_decision(request_id: int, current_user: User, db: AsyncSession):
    """Общая часть выдачи/отклонения: загрузка, права, защита от повторного решения."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")
    req = (await db.execute(
        select(AccessRequest)
        .where(AccessRequest.id == request_id, AccessRequest.org_id == org.id)
        .options(selectinload(AccessRequest.resource))
    )).scalar_one_or_none()
    if not req:
        raise HTTPException(404, "Заявка не найдена")

    is_admin = await _is_org_admin(current_user, org, db)
    if not is_admin and req.assignee_user_id != current_user.id:
        raise HTTPException(403, "Решать по этой заявке может только ответственный")
    # Уволенный ответственный права выдачи теряет, даже если остался назначенным
    if not is_admin and not await _is_active_in_org(current_user.id, org.id, db):
        raise HTTPException(403, "Сотрудник уволен — выдача доступов недоступна")
    if req.status not in OPEN_STATUSES:
        raise HTTPException(400, "По заявке уже принято решение")
    return req, org, is_admin


@router.post("/requests/{request_id}/grant", response_model=RequestOut)
async def grant_request(
    request_id: int,
    data: RequestDecision,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user = await db.merge(current_user)
    req, org, is_admin = await _load_for_decision(request_id, current_user, db)

    prev = req.status.value
    now = datetime.utcnow()
    req.status = AccessRequestStatus.granted
    req.decided_by = current_user.id
    req.decided_at = now
    req.granted_at = now
    req.decision_comment = data.comment
    if data.amount is not None:
        req.amount = data.amount
    _audit(db, req, "grant", prev, req.status.value, current_user.id, data.comment)
    await db.commit()

    await _notify(
        db, req.requester_user_id, "access_request_granted",
        "Ресурс выдан",
        f"{req.resource.name if req.resource else 'Ресурс'} — заявка закрыта",
        f"/access-hub/requests/{req.id}",
    )
    await db.commit()

    await _push(
        [req.requester_user_id, req.target_user_id, req.assignee_user_id],
        "access_request.updated", _request_event(req),
    )

    names = await _names_for(db, [req.requester_user_id, req.target_user_id, req.assignee_user_id])
    return _serialize_request(req, viewer_id=current_user.id, is_admin=is_admin, names=names)


@router.post("/requests/{request_id}/reject", response_model=RequestOut)
async def reject_request(
    request_id: int,
    data: RequestDecision,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user = await db.merge(current_user)
    req, org, is_admin = await _load_for_decision(request_id, current_user, db)

    prev = req.status.value
    req.status = AccessRequestStatus.rejected
    req.decided_by = current_user.id
    req.decided_at = datetime.utcnow()
    req.decision_comment = data.comment
    _audit(db, req, "reject", prev, req.status.value, current_user.id, data.comment)
    await db.commit()

    await _notify(
        db, req.requester_user_id, "access_request_rejected",
        "Заявка отклонена",
        (data.comment or "Без комментария"),
        f"/access-hub/requests/{req.id}",
    )
    await db.commit()

    await _push(
        [req.requester_user_id, req.target_user_id, req.assignee_user_id],
        "access_request.updated", _request_event(req),
    )

    names = await _names_for(db, [req.requester_user_id, req.target_user_id, req.assignee_user_id])
    return _serialize_request(req, viewer_id=current_user.id, is_admin=is_admin, names=names)


@router.post("/requests/{request_id}/progress", response_model=RequestOut)
async def take_in_progress(
    request_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Ответственный берёт заявку в работу."""
    current_user = await db.merge(current_user)
    req, org, is_admin = await _load_for_decision(request_id, current_user, db)
    if req.status == AccessRequestStatus.in_progress:
        raise HTTPException(400, "Заявка уже в работе")

    prev = req.status.value
    req.status = AccessRequestStatus.in_progress
    if not req.assignee_user_id:
        req.assignee_user_id = current_user.id
    _audit(db, req, "progress", prev, req.status.value, current_user.id, None)
    await db.commit()

    await _notify(
        db, req.requester_user_id, "access_request_progress",
        "Заявка взята в работу",
        req.resource.name if req.resource else "Ресурс",
        f"/access-hub/requests/{req.id}",
    )
    await db.commit()

    await _push(
        [req.requester_user_id, req.target_user_id, req.assignee_user_id],
        "access_request.updated", _request_event(req),
    )

    names = await _names_for(db, [req.requester_user_id, req.target_user_id, req.assignee_user_id])
    return _serialize_request(req, viewer_id=current_user.id, is_admin=is_admin, names=names)


class MessageOut(BaseModel):
    id: int
    text: str
    source: str
    created_at: Optional[datetime] = None
    # кто написал; для заявителя ответственный анонимен
    author: str
    mine: bool


class MessageCreate(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


async def _load_for_chat(request_id: int, user: User, db: AsyncSession):
    """Заявка + права на чат. Писать могут только участники и админ."""
    org = await get_user_org(user, db)
    if not org:
        raise HTTPException(403, "No organization access")
    is_admin = await _require_active_member(user, org, db)

    req = (await db.execute(
        select(AccessRequest)
        .options(selectinload(AccessRequest.resource))
        .where(AccessRequest.id == request_id, AccessRequest.org_id == org.id)
    )).scalar_one_or_none()
    if not req:
        raise HTTPException(404, "Заявка не найдена")

    participant = user.id in {req.requester_user_id, req.target_user_id, req.assignee_user_id}
    if not (participant or is_admin):
        raise HTTPException(403, "Чат доступен только участникам заявки")
    return req, org, is_admin


def _chat_author(msg: AccessRequestMessage, req: AccessRequest,
                 viewer_id: int, is_admin: bool, names: Dict[int, str]) -> str:
    """Подпись автора с учётом анонимности снабжения (ТЗ п. 3.5).

    Заявитель видит «Снабжение» вместо имени ответственного — так же, как в
    самой заявке. Раскрыть его здесь означало бы обойти анонимность через чат.
    """
    if msg.sender_user_id == viewer_id:
        return "Вы"
    reveal = is_admin or viewer_id == req.assignee_user_id
    if msg.sender_user_id == req.assignee_user_id and not reveal:
        return ANON_ASSIGNEE
    return names.get(msg.sender_user_id) or "Участник"


@router.get("/requests/{request_id}/messages", response_model=List[MessageOut])
async def list_messages(
    request_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Переписка по заявке."""
    current_user = await db.merge(current_user)
    req, org, is_admin = await _load_for_chat(request_id, current_user, db)

    rows = (await db.execute(
        select(AccessRequestMessage)
        .where(AccessRequestMessage.request_id == req.id)
        .order_by(AccessRequestMessage.created_at, AccessRequestMessage.id)
    )).scalars().all()

    names = await _names_for(db, [m.sender_user_id for m in rows])
    return [
        MessageOut(
            id=m.id, text=m.text, source=m.source, created_at=m.created_at,
            author=_chat_author(m, req, current_user.id, is_admin, names),
            mine=m.sender_user_id == current_user.id,
        )
        for m in rows
    ]


@router.post("/requests/{request_id}/messages", response_model=MessageOut, status_code=201)
async def post_message(
    request_id: int,
    data: MessageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Написать в чат по заявке. Собеседнику уходит пуш и сообщение в бота."""
    current_user = await db.merge(current_user)
    req, org, is_admin = await _load_for_chat(request_id, current_user, db)

    msg = AccessRequestMessage(
        request_id=req.id, org_id=org.id, sender_user_id=current_user.id,
        text=data.text.strip(), source="web",
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)

    await _deliver_chat_message(db, req, msg, current_user.id)

    names = await _names_for(db, [msg.sender_user_id])
    return MessageOut(
        id=msg.id, text=msg.text, source=msg.source, created_at=msg.created_at,
        author="Вы", mine=True,
    )


async def _deliver_chat_message(db: AsyncSession, req: AccessRequest,
                                msg: AccessRequestMessage, sender_id: int) -> None:
    """Доставка сообщения второй стороне: WebSocket + бот.

    Собеседник вычисляется от отправителя: заявителю отвечает ответственный и
    наоборот. Если ответственный не назначен, разговор ведут админы — иначе
    сообщение ушло бы в никуда.
    """
    if sender_id == req.assignee_user_id:
        recipients = [req.requester_user_id]
        author = ANON_ASSIGNEE
    else:
        recipients = [req.assignee_user_id] if req.assignee_user_id else \
            await _org_admin_ids(req.org_id, db)
        names = await _names_for(db, [sender_id])
        author = names.get(sender_id) or "Сотрудник"

    resource = req.resource.name if req.resource else "заявке"
    for uid in recipients:
        if not uid or uid == sender_id:
            continue
        await _push([uid], "access_request.message", {
            "request_id": req.id, "text": msg.text, "author": author,
        })
        try:
            from ..bot import send_access_chat_message
            await send_access_chat_message(uid, req.id, resource, author, msg.text)
        except Exception:
            logger.exception("access-hub: не удалось отправить сообщение чата в бота")


@router.get("/requests/{request_id}/audit", response_model=List[AuditOut])
async def request_audit(
    request_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")
    req = (await db.execute(
        select(AccessRequest).where(
            AccessRequest.id == request_id, AccessRequest.org_id == org.id
        )
    )).scalar_one_or_none()
    if not req:
        raise HTTPException(404, "Заявка не найдена")

    is_admin = await _is_org_admin(current_user, org, db)
    if not is_admin and current_user.id not in (
        req.requester_user_id, req.target_user_id, req.assignee_user_id
    ):
        raise HTTPException(403, "Нет доступа к этой заявке")

    rows = (await db.execute(
        select(AccessRequestAudit)
        .where(AccessRequestAudit.request_id == request_id)
        .order_by(AccessRequestAudit.created_at)
    )).scalars().all()
    names = await _names_for(db, [r.changed_by for r in rows])
    return [
        AuditOut(
            id=a.id, from_status=a.from_status, to_status=a.to_status,
            action=a.action, changed_by=a.changed_by,
            # действия снабжения обезличены для всех, кроме админов
            changed_by_name=(names.get(a.changed_by) if is_admin else None),
            comment=a.comment, created_at=a.created_at,
        ) for a in rows
    ]


# --------------------------------------------------------------------------- #
# Леджер и оффбординг                                                           #
# --------------------------------------------------------------------------- #

@router.get("/ledger/{user_id}", response_model=List[GrantOut])
async def user_ledger(
    user_id: int,
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Что у человека на руках — для карточки сотрудника и оффбординга."""
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")
    if user_id != current_user.id and not await _is_org_admin(current_user, org, db):
        raise HTTPException(403, "Чужой леджер доступен только администратору")

    statuses = [AccessRequestStatus.granted] if active_only else [
        AccessRequestStatus.granted, AccessRequestStatus.revoked
    ]
    rows = (await db.execute(
        select(AccessRequest)
        .where(
            AccessRequest.org_id == org.id,
            AccessRequest.status.in_(statuses),
            func.coalesce(AccessRequest.target_user_id, AccessRequest.requester_user_id) == user_id,
        )
        .options(selectinload(AccessRequest.resource))
        .order_by(AccessRequest.granted_at.desc())
    )).scalars().all()

    return [
        GrantOut(
            request_id=r.id, resource_id=r.resource_id,
            resource_name=r.resource.name if r.resource else "—",
            resource_category=(r.resource.category.value
                               if r.resource and hasattr(r.resource.category, "value")
                               else "other"),
            params=r.params if isinstance(r.params, dict) else {},
            granted_at=r.granted_at,
            responsible_user_id=r.assignee_user_id,
            status=r.status.value if hasattr(r.status, "value") else str(r.status),
        ) for r in rows
    ]


@router.post("/requests/{request_id}/revoke", response_model=RequestOut)
async def revoke_grant(
    request_id: int,
    data: RequestDecision,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Отзыв уже выданного ресурса — шаг чек-листа оффбординга."""
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    req = (await db.execute(
        select(AccessRequest)
        .where(AccessRequest.id == request_id, AccessRequest.org_id == org.id)
        .options(selectinload(AccessRequest.resource))
    )).scalar_one_or_none()
    if not req:
        raise HTTPException(404, "Заявка не найдена")

    is_admin = await _is_org_admin(current_user, org, db)
    if not is_admin and req.assignee_user_id != current_user.id:
        raise HTTPException(403, "Отзывать может ответственный или администратор")
    if req.status != AccessRequestStatus.granted:
        raise HTTPException(400, "Отозвать можно только выданный ресурс")

    prev = req.status.value
    req.status = AccessRequestStatus.revoked
    req.revoked_at = datetime.utcnow()
    req.revoke_reason = data.comment
    _audit(db, req, "revoke", prev, req.status.value, current_user.id, data.comment)
    await db.commit()

    # Отзыв тоже гасит зелёную кнопку у человека — сообщаем сразу, а не
    # ждём, пока он обновит страницу.
    await _notify(
        db, req.requester_user_id, "access_request_revoked",
        "Доступ отозван",
        f"{req.resource.name if req.resource else 'Ресурс'}"
        + (f" — {data.comment}" if data.comment else ""),
        f"/access-hub/requests/{req.id}",
    )
    await db.commit()

    await _push(
        [req.requester_user_id, req.target_user_id, req.assignee_user_id],
        "access_request.updated", _request_event(req),
    )

    names = await _names_for(db, [req.requester_user_id, req.target_user_id, req.assignee_user_id])
    return _serialize_request(req, viewer_id=current_user.id, is_admin=is_admin, names=names)


@router.get("/offboarding/{user_id}/checklist", response_model=List[GrantOut])
async def offboarding_checklist(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Чек-лист отзыва при увольнении: всё активное, что надо забрать.

    Отдельный эндпоинт, а не алиас леджера: у него своя семантика (только
    активные гранты, сгруппированные по ответственным) и он админский.
    """
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")
    if not await _is_org_admin(current_user, org, db):
        raise HTTPException(403, "Чек-лист доступен только администратору")

    rows = (await db.execute(
        select(AccessRequest)
        .where(
            AccessRequest.org_id == org.id,
            AccessRequest.status == AccessRequestStatus.granted,
            func.coalesce(AccessRequest.target_user_id, AccessRequest.requester_user_id) == user_id,
        )
        .options(selectinload(AccessRequest.resource))
        .order_by(AccessRequest.granted_at)
    )).scalars().all()

    return [
        GrantOut(
            request_id=r.id, resource_id=r.resource_id,
            resource_name=r.resource.name if r.resource else "—",
            resource_category=(r.resource.category.value
                               if r.resource and hasattr(r.resource.category, "value")
                               else "other"),
            params=r.params if isinstance(r.params, dict) else {},
            granted_at=r.granted_at,
            responsible_user_id=r.assignee_user_id,
            status=r.status.value if hasattr(r.status, "value") else str(r.status),
        ) for r in rows
    ]
