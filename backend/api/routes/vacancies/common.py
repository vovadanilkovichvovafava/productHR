"""
Shared schemas, imports, and helper functions for vacancy management.
"""
import re
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, func, or_, and_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing import Optional, List, Literal, Iterable
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, field_validator, model_validator
import logging


_HTML_TAG_RE = re.compile(r"<[^>]*>")


def _strip_html(value: str) -> str:
    """Удаляет HTML-теги из строки (защита от мусора в title/tag/label)."""
    if not value:
        return value
    return _HTML_TAG_RE.sub("", value)

logger = logging.getLogger("hr-analyzer.vacancies")

from ...database import get_db
from ...models.database import (
    Vacancy, VacancyStatus, VacancyApplication, ApplicationStage,
    Entity, EntityType, EntityStatus, User, Organization, Department, STAGE_SYNC_MAP, STATUS_SYNC_MAP,
    UserRole, OrgMember, OrgRole, DepartmentMember, DeptRole
)
from ...services.auth import get_current_user, get_user_org, has_full_database_access as auth_has_full_database_access
from ...services.features import can_access_feature
from ...services.cache import scoring_cache


# === Vacancy Access Control Helpers ===

async def is_org_owner(user: User, org: Organization, db: AsyncSession) -> bool:
    """Check if user is owner of organization (not admin - they follow same rules as members)."""
    if user.role == UserRole.superadmin:
        return True

    result = await db.execute(
        select(OrgMember).where(
            OrgMember.org_id == org.id,
            OrgMember.user_id == user.id,
            OrgMember.role == OrgRole.owner  # Only owner, not admin
        )
    )
    return result.scalar_one_or_none() is not None


async def is_org_admin_or_owner(user: User, org: Organization, db: AsyncSession) -> bool:
    """Админ/владелец организации (или суперадмин).

    OrgRole.admin = «HR Admin — всё кроме /users»: такие пользователи ведут
    подбор и должны двигать кандидатов в ЛЮБОЙ воронке орга, даже если не
    назначены на конкретную вакансию. Применяется к правам ПЕРЕМЕЩЕНИЯ откликов
    (одиночное + массовое). В отличие от is_org_owner включает и OrgRole.admin.
    """
    if user.role == UserRole.superadmin:
        return True
    result = await db.execute(
        select(OrgMember).where(
            OrgMember.org_id == org.id,
            OrgMember.user_id == user.id,
            OrgMember.role.in_([OrgRole.owner, OrgRole.admin])
        )
    )
    return result.scalar_one_or_none() is not None


async def has_full_database_access(user: User, org: Organization, db: AsyncSession) -> bool:
    """
    Check if user has full database access (can see all vacancies and candidates).
    Wrapper around auth service function that accepts Organization object instead of org_id.
    """
    return await auth_has_full_database_access(user, org.id, db)


async def has_hr_segment_access(user: User, org: Organization, db: AsyncSession) -> bool:
    """Есть ли у пользователя HR-раздел — и, с 2026-09-07, ПРОСМОТР ВСЕХ воронок орга.

    Раньше рекрутёр видел только «свои» воронки (создатель / назначенный /
    принявший / лид отдела / шара). Из-за этого ссылка на кандидата в чужой
    воронке молча вела в обзор СВОИХ вакансий, а в базе кандидатов метка
    «HR: <коллега> · <вакансия>» была кликабельной, но никуда не открывалась
    (обратная связь Эльвиры, 2026-09-07). По решению юзера воронки открыты всем,
    у кого вообще есть HR-сегмент.

    Это НЕ то же самое, что has_full_database_access: тот даёт ещё ПЭН, экспорт,
    аналитику и обзор всех кандидатов внутри воронки (sees_all_candidates) —
    его намеренно не трогаем. Здесь только видимость самих воронок.

    Кто входит: superadmin, owner, admin (HR Админ), hr (HR Рекрутер) и
    «Наблюдатель» (is_readonly, любой org_role). Обычный member HR-раздела не
    имеет (сайдбар и RoleRoute его туда не пускают) — сюда он тоже не попадает.
    """
    if getattr(user, 'role', None) == UserRole.superadmin:
        return True
    if org is None:
        return False
    result = await db.execute(
        select(OrgMember.role, OrgMember.is_readonly).where(
            OrgMember.org_id == org.id,
            OrgMember.user_id == user.id,
        )
    )
    row = result.first()
    if row is None:
        return False
    member_role, member_readonly = row
    return member_role in (OrgRole.owner, OrgRole.admin, OrgRole.hr) or bool(member_readonly)


async def sees_all_candidates(user: User, org: Organization, db: AsyncSession) -> bool:
    """Видит ли пользователь ВСЕ отклики в воронке (не только свои).

    Модель приватности «общая воронка, но каждый видит своих»: обычный рекрутёр
    (member без полного доступа) видит в kanban ТОЛЬКО кандидатов, которых сам
    добавил (VacancyApplication.created_by == self). Полный обзор воронки — у
    админа/владельца орга, суперадмина и member с полным доступом к базе.
    Ограничение действует ТОЛЬКО в воронке вакансии; глобальная база кандидатов
    и поиск остаются общими.
    """
    return (
        await is_org_admin_or_owner(user, org, db)
        or await has_full_database_access(user, org, db)
    )


def recruiter_owns_application(vacancy: Vacancy, recruiter_id: int):
    """Условие «заявка принадлежит рекрутёру R» для скоупа воронки по рекрутёру.

    R — автор заявки (created_by), а если автор не записан (NULL: старые данные,
    удалённый пользователь — FK ondelete=SET NULL) — владелец вакансии. Ровно то
    же правило, что у авто-метки «HR: …» (services/hr_tags.py, coalesce): иначе
    метка говорила «кандидат Марии», а воронка Марии его не показывала.
    """
    cond = VacancyApplication.created_by == recruiter_id
    if vacancy.created_by == recruiter_id:
        cond = or_(cond, VacancyApplication.created_by.is_(None))
    return cond


def co_recruiter_of(user_id: int):
    """Условие «R — со-рекрутёр заявки» (общая воронка, старые пары до 21.09)."""
    from ...models.database import ApplicationCoRecruiter
    return VacancyApplication.id.in_(
        select(ApplicationCoRecruiter.application_id).where(ApplicationCoRecruiter.user_id == user_id)
    )


def applications_of_recruiter(vacancy: Vacancy, recruiter_id: int):
    """Скоуп воронки «кандидаты рекрутёра R»: его заявки (см.
    recruiter_owns_application) ИЛИ где он со-рекрутёр. Одно условие на список
    заявок и канбан — до 20.10.2026 канбан со-рекрутёров не учитывал."""
    return or_(recruiter_owns_application(vacancy, recruiter_id), co_recruiter_of(recruiter_id))


def private_funnel_view(user_id: int):
    """Что видит рекрутёр в СКРЫТОЙ воронке без явного скоупа: свои, старые без
    автора (NULL) и те, где он со-рекрутёр."""
    return or_(
        VacancyApplication.created_by == user_id,
        VacancyApplication.created_by.is_(None),
        co_recruiter_of(user_id),
    )


# Запрета «двигать только своих кандидатов» в воронке больше нет (владелец,
# 21.10.2026: «если Мария поставила фильтр на Владу, она может смотреть и
# редактировать её кандидатов, и это касается всех в любой воронке»). Кто видит
# вакансию (check_vacancy_access / can_access_vacancy), тот и двигает. Раньше
# здесь была ensure_may_touch_applications: в скрытой воронке не-админ получал
# 403 на чужого кандидата.


async def get_user_department_ids(user_id: int, org_id: int, db: AsyncSession) -> List[int]:
    """Get all department IDs user belongs to in the organization."""
    result = await db.execute(
        select(DepartmentMember.department_id)
        .join(Department, Department.id == DepartmentMember.department_id)
        .where(
            Department.org_id == org_id,
            DepartmentMember.user_id == user_id,
            Department.is_active == True
        )
    )
    return [row[0] for row in result.all()]


async def is_dept_lead_or_admin(user_id: int, department_id: int, db: AsyncSession) -> bool:
    """Check if user is lead or sub_admin of a specific department."""
    result = await db.execute(
        select(DepartmentMember).where(
            DepartmentMember.department_id == department_id,
            DepartmentMember.user_id == user_id,
            DepartmentMember.role.in_([DeptRole.lead, DeptRole.sub_admin])
        )
    )
    return result.scalar_one_or_none() is not None


async def can_access_vacancy(vacancy: Vacancy, user: User, org: Organization, db: AsyncSession) -> bool:
    """
    Check if user can access (view) a specific vacancy.

    Access rules:
    - Superadmin/Owner: can access all vacancies in org
    - Member with has_full_access flag: can access all vacancies in org
    - visible_to_all flag: any org member can access
    - Lead/Sub_admin of department: can access all vacancies in their department
    - Member: can only access vacancies they created or where they are hiring manager
    """
    # Суперадмин — глобальный доступ (видит все орги). Для ВСЕХ остальных org-
    # граница идёт ДО проверки роли: иначе admin/owner своей орги проходит
    # has_full_database_access и получает доступ к ЧУЖОЙ вакансии (cross-org IDOR
    # на роутах, грузящих вакансию без org-фильтра: list_applications, kanban,
    # get_vacancy, update/delete_application). Аудит 2026-08-07.
    if getattr(user, 'role', None) == UserRole.superadmin:
        return True
    if org is None or getattr(vacancy, 'org_id', None) != org.id:
        return False

    # Full database access (owner, или member с has_full_access — теперь в СВОЕЙ орг).
    if await has_full_database_access(user, org, db):
        return True

    # ПРОСМОТР ВОРОНОК ОТКРЫТ ВСЕМУ HR-СЕГМЕНТУ (2026-09-07, решение юзера):
    # рекрутёр видит воронки коллег, а не только свои. Org-граница уже проверена
    # выше, так что это видимость строго внутри своей организации.
    if await has_hr_segment_access(user, org, db):
        return True

    # visible_to_all БОЛЬШЕ НЕ даёт member доступ (2026-07-07): рекрутёр видит
    # заявку только если реально назначен/создатель/наниматель/лид/шара, иначе
    # «Общая» заявка утекала всем. Админ/owner/hr уже прошли по has_full_access.

    # Vacancy open for all HR recruiters (назначение «всем рекрутёрам» — это ok)
    if getattr(vacancy, 'assigned_to_all', False):
        return True

    # User is in assigned_to list
    assigned_to_list = vacancy.assigned_to or []
    if user.id in assigned_to_list:
        return True

    # User is the creator or hiring manager
    if vacancy.created_by == user.id or vacancy.hiring_manager_id == user.id:
        return True

    # If vacancy has a department, check if user is lead/sub_admin of that dept
    if vacancy.department_id:
        if await is_dept_lead_or_admin(user.id, vacancy.department_id, db):
            return True

    return False


# Ключи extra_data вакансии, которые ведёт сервер, а не форма. Форма шлёт
# extra_data целиком из снимка на момент открытия, и сохранение стирало то, что
# случилось за это время: «Взять в работу» коллеги (accepted_by), «Выйти»
# (dismissed_by). А через ту же форму можно было вписать чат бота или id
# «исходной заявки», которую потом правил сервер (20.10.2026).
SERVER_MANAGED_EXTRA = ("accepted_by", "dismissed_by", "source_chat_id", "cloned_from_request_id")


def keep_server_extra(current: Optional[dict], incoming: Optional[dict]) -> dict:
    """extra_data из формы, но серверные ключи — как в базе."""
    out = dict(incoming or {})
    cur = current or {}
    for key in SERVER_MANAGED_EXTRA:
        if key in cur:
            out[key] = cur[key]
        else:
            out.pop(key, None)
    return out


async def can_edit_vacancy(vacancy: Vacancy, user: User, org: Organization, db: AsyncSession) -> bool:
    """
    Check if user can edit a specific vacancy.

    Edit rules:
    - Superadmin/Owner: can edit all vacancies in org
    - visible_to_all flag: any org member can edit
    - Lead/Sub_admin of department: can edit vacancies in their department
    - Creator: can edit their own vacancies
    - Hiring manager: can edit vacancies where they are hiring manager
    """
    # Суперадмин — глобально. Остальные — org-граница ДО проверки роли (иначе owner
    # своей орги правил бы чужую вакансию, cross-org IDOR). Аудит 2026-08-07.
    if getattr(user, 'role', None) == UserRole.superadmin:
        return True
    if org is None or getattr(vacancy, 'org_id', None) != org.id:
        return False

    # Владелец и админ орга правят любую вакансию (в СВОЕЙ орг). До 20.10.2026
    # здесь был только owner: Мария (admin) получала 403 на скрытой вакансии
    # рекрутёра, хотя двигать в ней кандидатов и удалять её могла.
    if await is_org_admin_or_owner(user, org, db):
        return True

    # Vacancy marked as visible to all org members
    if getattr(vacancy, 'visible_to_all', False):
        return True

    # User is the creator or hiring manager
    if vacancy.created_by == user.id or vacancy.hiring_manager_id == user.id:
        return True

    # Участник общей воронки (назначенный рекрутёр) может её редактировать —
    # в т.ч. «закрыть у себя» (leave-семантика в update_vacancy). Без этого
    # назначенный рекрутёр не мог завершить свою работу над воронкой, если
    # она не visible_to_all (общая модель 2026-07-02).
    if user.id in (vacancy.assigned_to or []) or getattr(vacancy, 'assigned_to_all', False):
        return True

    # If vacancy has a department, check if user is lead/sub_admin of that dept
    if vacancy.department_id:
        if await is_dept_lead_or_admin(user.id, vacancy.department_id, db):
            return True

    return False


async def can_manage_applications(vacancy: Vacancy, user: User, org: Organization, db: AsyncSession) -> bool:
    """Кто может ДВИГАТЬ/УДАЛЯТЬ отклики в воронке вакансии.

    Те, кто реально ведёт вакансию: владелец/админ орга (full access),
    создатель/наниматель, назначенные рекрутёры (assigned_to / assigned_to_all),
    лид отдела, edit-шара. В отличие от can_access_vacancy НЕ даёт право мутации
    случайному члену орга только по visible_to_all (это видимость, а не работа).
    """
    # Суперадмин — глобально. Остальные — org-граница ДО проверки роли (иначе
    # admin/owner своей орги двигал/удалял бы отклики чужой воронки). Аудит 2026-08-07.
    if getattr(user, 'role', None) == UserRole.superadmin:
        return True
    if org is None or getattr(vacancy, 'org_id', None) != org.id:
        return False
    if await has_full_database_access(user, org, db):
        return True
    if vacancy.created_by == user.id or vacancy.hiring_manager_id == user.id:
        return True
    if getattr(vacancy, 'assigned_to_all', False):
        return True
    if user.id in (vacancy.assigned_to or []):
        return True
    if vacancy.department_id and await is_dept_lead_or_admin(user.id, vacancy.department_id, db):
        return True
    return False


async def can_delete_vacancy(vacancy: Vacancy, user: User, org: Organization, db: AsyncSession) -> bool:
    """Кто может УДАЛИТЬ воронку.

    Отдельной проверки тут не было: delete_vacancy полагался на то, что сам
    доступ к вакансии уже означает участие в ней (создатель / назначенный /
    лид отдела / админ орга). Когда просмотр воронок открыли всему HR-сегменту
    (см. has_hr_segment_access, 2026-09-07), это молча превратилось в «любой
    рекрутёр может снести чужую воронку» — а удаление в общей воронке убирает
    её у ВСЕХ участников. Возвращаем прежний смысл явным правилом: удаляет тот,
    кто вакансию реально ведёт.

    Намеренно НЕ используем can_edit_vacancy: та отдаёт True любому члену орга
    на вакансии с visible_to_all («Видна коллегам»), а этот флаг стоит по
    умолчанию — как гейт на удаление она бесполезна.

    Кому нужен только выход из общей воронки, а не снос у всех, — есть
    decline_vacancy («Отказаться»), отдельная кнопка.
    """
    if getattr(user, 'role', None) == UserRole.superadmin:
        return True
    if org is None or getattr(vacancy, 'org_id', None) != org.id:
        return False
    # Админ/владелец орга ведут подбор во всех воронках.
    if await is_org_admin_or_owner(user, org, db):
        return True
    if vacancy.created_by == user.id or vacancy.hiring_manager_id == user.id:
        return True
    # Участник общей воронки: назначенный лично или «всем рекрутёрам».
    if user.id in (vacancy.assigned_to or []) or getattr(vacancy, 'assigned_to_all', False):
        return True
    if vacancy.department_id and await is_dept_lead_or_admin(user.id, vacancy.department_id, db):
        return True
    return False


# === Feature Access Control ===

async def check_vacancy_access(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> User:
    """Check if user has access to the vacancies feature.

    This dependency verifies that:
    1. User is authenticated
    2. User's organization/department has the vacancies feature enabled
    3. Superadmin and Owner always have access (bypassed in can_access_feature)

    Raises:
        HTTPException 403 if user cannot access vacancies feature

    Returns:
        The authenticated user if they have access
    """
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(
            status_code=403,
            detail="Vacancies feature unavailable - organization not found"
        )

    has_access = await can_access_feature(db, current_user.id, org.id, "candidate_database")
    if not has_access:
        raise HTTPException(
            status_code=403,
            detail="Candidate Database feature is not enabled for your department"
        )

    # Чужая организация — «не найдено», как у кандидатов (24.10.2026). Раньше
    # вакансия другой организации отвечала 403 «нет доступа», а несуществующая —
    # 404, и по разнице перебором номеров было видно, какие вакансии есть.
    # Наблюдатель и рекрутёры своей организации этим не затронуты.
    await _ensure_path_in_org(request, current_user, org.id, db)

    # Скоуп по воронкам — здесь, одним горлышком на все ручки вакансий: раньше
    # он стоял только на чтении, и человек со скоупом (например, наблюдатель,
    # которого потом сделали рекрутёром — скоуп при этом остаётся) мог по id
    # двигать, править и удалять заявки чужих воронок (20.10.2026).
    await _ensure_path_in_scope(request, current_user, db)
    return current_user


async def _path_vacancy_id(params: dict, db: AsyncSession) -> Optional[int]:
    """Номер вакансии из адреса: прямо (`vacancy_id`) или через заявку."""
    raw = params.get("vacancy_id")
    if raw is not None:
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None
    try:
        app_id = int(params["application_id"])
    except (KeyError, TypeError, ValueError):
        return None
    return (await db.execute(
        select(VacancyApplication.vacancy_id).where(VacancyApplication.id == app_id)
    )).scalar()


async def _ensure_path_in_org(request: Request, user: User, org_id: int, db: AsyncSession) -> None:
    if user.role == UserRole.superadmin:
        return
    params = request.path_params or {}
    if "vacancy_id" not in params and "application_id" not in params:
        return
    vacancy_id = await _path_vacancy_id(params, db)
    if vacancy_id is None:
        return  # нет такой — ответит сама ручка (404)
    vacancy_org = (await db.execute(select(Vacancy.org_id).where(Vacancy.id == vacancy_id))).scalar()
    if vacancy_org is not None and vacancy_org != org_id:
        raise HTTPException(status_code=404, detail="Vacancy not found")


async def _ensure_path_in_scope(request: Request, user: User, db: AsyncSession) -> None:
    from ...services.vacancy_scope import ensure_vacancy_visible, get_scope_vacancy_ids
    params = request.path_params or {}
    if "vacancy_id" not in params and "application_id" not in params:
        return
    if await get_scope_vacancy_ids(user, db) is None:
        return
    vacancy_id = params.get("vacancy_id")
    if vacancy_id is None:
        try:
            app_id = int(params["application_id"])
        except (TypeError, ValueError):
            return
        vacancy_id = (await db.execute(
            select(VacancyApplication.vacancy_id).where(VacancyApplication.id == app_id)
        )).scalar()
        if vacancy_id is None:
            return  # заявки нет — ответит сама ручка (404)
    try:
        await ensure_vacancy_visible(int(vacancy_id), user, db)
    except (TypeError, ValueError):
        return


# === Pydantic Schemas ===

class StageColumnSchema(BaseModel):
    key: str
    label: str
    visible: bool
    maps_to: Optional[str] = None


class CustomStagesSchema(BaseModel):
    columns: List[StageColumnSchema]


class VacancyCreate(BaseModel):
    title: str
    description: Optional[str] = None
    requirements: Optional[str] = None
    responsibilities: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: str = "RUB"
    location: Optional[str] = None
    employment_type: Optional[str] = None
    experience_level: Optional[str] = None
    status: VacancyStatus = VacancyStatus.pending_review
    priority: int = 0
    tags: List[str] = []
    extra_data: dict = {}
    visible_to_all: bool = False
    department_id: Optional[int] = None
    hiring_manager_id: Optional[int] = None
    closes_at: Optional[datetime] = None
    custom_stages: Optional[CustomStagesSchema] = None
    kanban_card_fields: Optional[List[str]] = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        """Validate title: non-empty, min 3 chars, max 200, без HTML-тегов."""
        if not v or not v.strip():
            raise ValueError("title cannot be empty")
        cleaned = _strip_html(v).strip()
        if len(cleaned) < 3:
            raise ValueError("title must be at least 3 characters long")
        if len(cleaned) > 200:
            raise ValueError("title must be 200 characters or fewer")
        return cleaned

    @field_validator("salary_min", "salary_max")
    @classmethod
    def validate_salary_positive(cls, v: Optional[int]) -> Optional[int]:
        """Validate salary: non-negative and within INT column range (B4-fix).

        Без верхней границы значение вроде 14_124_124_124_124 проходило
        Pydantic, но падало на INSERT/UPDATE в Postgres (integer out of range)
        -> 500 при создании/редактировании заявки.
        """
        if v is not None:
            if v < 0:
                raise ValueError("salary cannot be negative")
            if v > 2_147_483_647:
                raise ValueError("Зарплата слишком большая (максимум 2 147 483 647)")
        return v

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: int) -> int:
        """Validate priority is in range 0-2."""
        if v < 0 or v > 2:
            raise ValueError("priority must be between 0 and 2")
        return v

    @field_validator("closes_at")
    @classmethod
    def validate_closes_at(cls, v: Optional[datetime]) -> Optional[datetime]:
        """Validate closes_at is not in the past."""
        if v is not None:
            now = datetime.now(timezone.utc) if v.tzinfo else datetime.utcnow()
            if v < now:
                raise ValueError("closes_at cannot be in the past")
        return v

    @field_validator("tags", mode="before")
    @classmethod
    def validate_tags(cls, v) -> List[str]:
        """Ensure tags is a valid list and strip HTML/whitespace."""
        if v is None:
            return []
        if not isinstance(v, list):
            raise ValueError("tags must be a list")
        cleaned = []
        for item in v:
            if not isinstance(item, str):
                continue
            stripped = _strip_html(item).strip()
            if stripped:
                cleaned.append(stripped[:80])
        return cleaned

    @field_validator("extra_data", mode="before")
    @classmethod
    def validate_extra_data(cls, v) -> dict:
        """Ensure extra_data is a valid dict."""
        if v is None:
            return {}
        if not isinstance(v, dict):
            raise ValueError("extra_data must be a dictionary")
        return v

    @model_validator(mode="after")
    def validate_salary_range(self):
        """Validate salary_min is not greater than salary_max."""
        if self.salary_min is not None and self.salary_max is not None:
            if self.salary_min > self.salary_max:
                raise ValueError("salary_min cannot be greater than salary_max")
        return self


class VacancyUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    responsibilities: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: Optional[str] = None
    location: Optional[str] = None
    employment_type: Optional[str] = None
    experience_level: Optional[str] = None
    status: Optional[VacancyStatus] = None
    priority: Optional[int] = None
    tags: Optional[List[str]] = None
    extra_data: Optional[dict] = None
    visible_to_all: Optional[bool] = None
    department_id: Optional[int] = None
    hiring_manager_id: Optional[int] = None
    closes_at: Optional[datetime] = None
    custom_stages: Optional[CustomStagesSchema] = None
    kanban_card_fields: Optional[List[str]] = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: Optional[str]) -> Optional[str]:
        """Validate title: non-empty, min 3, max 200, без HTML-тегов."""
        if v is not None:
            cleaned = _strip_html(v).strip()
            if not cleaned:
                raise ValueError("title cannot be empty")
            if len(cleaned) < 3:
                raise ValueError("title must be at least 3 characters long")
            if len(cleaned) > 200:
                raise ValueError("title must be 200 characters or fewer")
            return cleaned
        return v

    @field_validator("salary_min", "salary_max")
    @classmethod
    def validate_salary_positive(cls, v: Optional[int]) -> Optional[int]:
        """Validate salary: non-negative and within INT column range (B4-fix).

        Без верхней границы значение вроде 14_124_124_124_124 проходило
        Pydantic, но падало на INSERT/UPDATE в Postgres (integer out of range)
        -> 500 при создании/редактировании заявки.
        """
        if v is not None:
            if v < 0:
                raise ValueError("salary cannot be negative")
            if v > 2_147_483_647:
                raise ValueError("Зарплата слишком большая (максимум 2 147 483 647)")
        return v

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: Optional[int]) -> Optional[int]:
        """Validate priority is in range 0-2 if provided."""
        if v is not None and (v < 0 or v > 2):
            raise ValueError("priority must be between 0 and 2")
        return v

    @field_validator("closes_at")
    @classmethod
    def validate_closes_at(cls, v: Optional[datetime]) -> Optional[datetime]:
        """Validate closes_at is not in the past."""
        if v is not None:
            now = datetime.now(timezone.utc) if v.tzinfo else datetime.utcnow()
            if v < now:
                raise ValueError("closes_at cannot be in the past")
        return v

    @field_validator("tags", mode="before")
    @classmethod
    def validate_tags(cls, v) -> Optional[List[str]]:
        """Ensure tags is a valid list if provided, strip HTML/whitespace."""
        if v is None:
            return None
        if not isinstance(v, list):
            raise ValueError("tags must be a list")
        cleaned = []
        for item in v:
            if not isinstance(item, str):
                continue
            stripped = _strip_html(item).strip()
            if stripped:
                cleaned.append(stripped[:80])
        return cleaned

    @field_validator("extra_data", mode="before")
    @classmethod
    def validate_extra_data(cls, v) -> Optional[dict]:
        """Ensure extra_data is a valid dict if provided."""
        if v is None:
            return None
        if not isinstance(v, dict):
            raise ValueError("extra_data must be a dictionary")
        return v

    @model_validator(mode="after")
    def validate_salary_range(self):
        """Validate salary_min is not greater than salary_max."""
        if self.salary_min is not None and self.salary_max is not None:
            if self.salary_min > self.salary_max:
                raise ValueError("salary_min cannot be greater than salary_max")
        return self


class VacancyResponse(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    requirements: Optional[str] = None
    responsibilities: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: str = "RUB"
    location: Optional[str] = None
    employment_type: Optional[str] = None
    experience_level: Optional[str] = None
    status: VacancyStatus
    priority: int = 0
    tags: List[str] = []
    extra_data: dict = {}
    visible_to_all: bool = False
    assigned_to: List[int] = []
    assigned_to_all: bool = False
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    hiring_manager_id: Optional[int] = None
    hiring_manager_name: Optional[str] = None
    created_by: Optional[int] = None
    created_by_name: Optional[str] = None
    published_at: Optional[datetime] = None
    closes_at: Optional[datetime] = None
    reopened_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
    applications_count: int = 0
    # Stage counts for quick overview
    stage_counts: dict = {}
    # Funnel customization
    custom_stages: Optional[dict] = None
    kanban_card_fields: Optional[List[str]] = None

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }


class ApplicationCreate(BaseModel):
    vacancy_id: int
    entity_id: int
    stage: ApplicationStage = ApplicationStage.applied  # Default to 'applied' (exists in DB enum, shown as "Novyj" in UI)
    rating: Optional[int] = None
    notes: Optional[str] = None
    source: Optional[str] = None


class ApplicationUpdate(BaseModel):
    stage: Optional[ApplicationStage] = None
    stage_order: Optional[int] = None
    rating: Optional[int] = None
    notes: Optional[str] = None
    rejection_reason: Optional[str] = None
    interview_summary: Optional[str] = None
    next_interview_at: Optional[datetime] = None
    comment: Optional[str] = None  # коммент к переходу этапа (пишется в историю, не поле заявки)
    # Кандидат, которому фронт СОБИРАЛСЯ менять этап. Страховка от промаха по
    # заявке (2026-09-15: этап уходил заявке предыдущего открытого кандидата).
    # Не совпало с заявкой — 409 и запись в лог, вместо тихой правки не того.
    expected_entity_id: Optional[int] = None


class ApplicationResponse(BaseModel):
    id: int
    vacancy_id: int
    vacancy_title: Optional[str] = None
    entity_id: int
    entity_name: Optional[str] = None
    entity_type: Optional[EntityType] = None
    entity_email: Optional[str] = None
    entity_phone: Optional[str] = None
    entity_telegram: Optional[str] = None
    entity_telegrams: Optional[List[str]] = None   # ВСЕ ники (для поиска по не-первому тг)
    entity_notes_text: Optional[str] = None         # текст комментариев карточки (для поиска ника/почты из комментов)
    entity_position: Optional[str] = None
    entity_photo: Optional[str] = None  # photo URL для аватара в списке
    # Яркие теги-ярлыки у имени (extra_data.headline_tags=[{text,color}]) — чтобы
    # показывать их в воронке так же, как в «Все кандидаты».
    entity_headline_tags: Optional[List[dict]] = None
    # «Был отказ»: отказ этого человека в ДРУГОЙ воронке, в другой его карточке
    # или в архиве ClickUp — services/prior_rejection.py (22.10.2026).
    prior_rejection: Optional[dict] = None
    # Только ответ «Забрать»: added | transferred | unchanged и у кого забрали.
    take_outcome: Optional[str] = None
    taken_from: Optional[int] = None
    stage: ApplicationStage
    stage_order: int = 0
    rating: Optional[int] = None
    notes: Optional[str] = None
    rejection_reason: Optional[str] = None
    interview_summary: Optional[str] = None
    source: Optional[str] = None
    next_interview_at: Optional[datetime] = None
    applied_at: datetime
    last_stage_change_at: datetime
    updated_at: datetime
    # «В предыдущих сериях»: отклик старше последнего переоткрытия вакансии
    # (last_stage_change_at < vacancy.reopened_at). Дефолт False — страховка на
    # старых данных и для create/update-эндпоинтов, где не вычисляется.
    is_previous_series: bool = False
    # Рекрутёр-владелец заявки (кто добавил) — нужен фронту для авто-метки HR.
    created_by: Optional[int] = None
    # Общий статус кандидата ПОСЛЕ этой правки (recompute_entity_status).
    # Заполняет только update_application: «Все кандидаты» ставят карточку в
    # колонку по нему, а не по выбранному этапу заявки. Иначе отказ в ОДНОЙ
    # воронке уводил карточку в колонку «Отказ», хотя сервер держит статус по
    # живой второй воронке — до F5 список расходился с сервером.
    entity_status: Optional[str] = None

    class Config:
        from_attributes = True


class KanbanColumn(BaseModel):
    stage: ApplicationStage
    title: str
    applications: List[ApplicationResponse]
    count: int  # Number of applications loaded (may be limited)
    total_count: int = 0  # Total applications in this stage (for "X more" indicator)
    has_more: bool = False  # True if there are more applications not loaded


class KanbanBoard(BaseModel):
    vacancy_id: int
    vacancy_title: str
    columns: List[KanbanColumn]
    total_count: int


class BulkStageUpdate(BaseModel):
    application_ids: List[int]
    stage: ApplicationStage


# === Синхронизация этапа заявки с глобальным статусом кандидата ===

# Этапы, на которых работа по воронке ОСТАНОВЛЕНА. Такой этап не должен
# перебивать живую работу в другой воронке: отказали в одной — человек всё ещё
# «Выполняет ТЗ» во второй (решение юзера 2026-09-17, обратная связь Эльвиры).
INACTIVE_STAGES = {
    ApplicationStage.rejected,
    ApplicationStage.withdrawn,
    ApplicationStage.reserve,
}


def pick_primary_application(apps: List[VacancyApplication]):
    """«Актуальная» заявка кандидата: самая свежая среди ЖИВЫХ, а если живых нет —
    самая свежая из остановленных. По ней считается общий статус кандидата и
    подпись воронки в списке «Все кандидаты»."""
    if not apps:
        return None

    def _when(a):
        return a.last_stage_change_at or a.applied_at or a.updated_at

    live = [a for a in apps if a.stage not in INACTIVE_STAGES]
    pool = live or list(apps)
    # Без даты — в конец: неизвестное время не должно выигрывать у реальной смены.
    return max(pool, key=lambda a: (_when(a) is not None, _when(a), a.id))


# Куда можно уйти из «Перешёл в отдел», оставаясь сотрудником: практика,
# оффер и принятый оффер (новая роль внутри компании). Любой другой этап —
# «Отказ», «Отозван», «Резерв», возврат в начало воронки — означает, что
# человек ушёл: на доске «Статусы» он должен оказаться в «Уволен».
# Статуса «уволен» в воронке нет, поэтому HR нажимает «Отказ», а доска сама
# переводит человека в уволенные (встреча с владельцем 24.09.2026).
STAYS_EMPLOYED_AFTER_TRANSFER = {
    EntityStatus.probation,
    EntityStatus.offer,
    EntityStatus.hired,
    EntityStatus.transferred,
}


# Ушёл из штата — финальный статус доски «Штат».
DEPARTED_FROM_STAFF = {EntityStatus.dismissed, EntityStatus.quit}

async def recompute_entity_status(
    db: AsyncSession, entity_id: int, moved_app_ids: Iterable[int] = (),
    *, undo: bool = False,
) -> None:
    """Пересчитать Entity.status по «актуальной» заявке кандидата (см.
    pick_primary_application). Раньше общий статус просто НЕ обновлялся, если
    воронок больше одной, и на «Все кандидаты» кандидат подвисал в старой
    колонке — было не видно, где он сейчас.

    Не коммитит. Закрытые вакансии не учитываем: работа идёт в открытых.

    moved_app_ids — заявки, которые сдвинулись В ЭТОМ действии. Только такое
    движение меняет «Уволен»/«Уволился» (см. ниже).

    undo — это ОТМЕНА перевода (удалили последнюю запись истории), а не новое
    решение по кандидату: подмену «отказ у оформленного в отдел = увольнение»
    тогда не делаем, иначе откат уводит человека в статус, которого у него
    никогда не было. Так разъехались карточка и доска у Саленик (21.10.2026):
    удаление записи вернуло заявку в «Отказ», статус карточки стал «Уволен», а
    доска осталась в «Перевёлся».
    """
    apps = (await db.execute(
        select(VacancyApplication)
        .join(Vacancy, VacancyApplication.vacancy_id == Vacancy.id)
        .where(
            VacancyApplication.entity_id == entity_id,
            Vacancy.status != VacancyStatus.closed,
            # Удалённая воронка (мягкое удаление) — не работа: до 20.10.2026
            # её заявка считалась открытой, и смена статуса на карточке не
            # доходила до живой воронки («две открытые — не трогаем»).
            Vacancy.deleted_at.is_(None),
        )
    )).scalars().all()
    primary = pick_primary_application(apps)
    if primary is None or primary.stage not in STAGE_SYNC_MAP:
        return
    new_status = STAGE_SYNC_MAP[primary.stage]
    entity = (await db.execute(
        select(Entity).where(Entity.id == entity_id)
    )).scalar()
    # Уволен / уволился — итог, который HR поставил сам (доска «Штат» или
    # «Отказ» после выхода в отдел). Пересчёт по СТАРОЙ заявке его не отменяет:
    # раньше любое действие рядом (удаление соседней заявки, сохранение заявки
    # без смены этапа) превращало уволенного обратно в «Перешёл в отдел»,
    # «Отказ» или даже «Практику», если заявка там застряла (20.10.2026).
    # Меняет его только реальное движение по воронке — повторный найм:
    # актуальная заявка сдвинулась в этом же действии.
    if (
        entity is not None
        and entity.status in DEPARTED_FROM_STAFF
        and primary.id not in set(moved_app_ids)
    ):
        logger.info(
            "KEEP_DEPARTED: entity=%s остаётся %s (заявка %s на этапе %s не двигалась)",
            entity_id, entity.status.value, primary.id, primary.stage.value,
        )
        return
    # Уже оформленного в отдел «Отказ» в воронке не возвращает в кандидаты —
    # он увольняется (см. STAYS_EMPLOYED_AFTER_TRANSFER).
    if (
        entity is not None
        and entity.status == EntityStatus.transferred
        and new_status not in STAYS_EMPLOYED_AFTER_TRANSFER
        and not undo
    ):
        logger.info(
            "DISMISS_AFTER_TRANSFER: entity=%s этап %s -> статус dismissed (заявка %s)",
            entity_id, primary.stage.value, primary.id,
        )
        new_status = EntityStatus.dismissed
    if entity is not None and entity.status != new_status:
        entity.status = new_status
        entity.updated_at = datetime.utcnow()
        logger.info(
            "ENTITY_STATUS recompute: entity=%s -> %s (по заявке %s, воронка %s)",
            entity_id, new_status.value, primary.id, primary.vacancy_id,
        )

    # Практика ведёт в песочницу. Проверяем не только в момент смены статуса:
    # кандидат мог стать practice другой дверью, а отдел ему так и не
    # проставился. Функция сама ничего не делает, если отдел уже есть.
    if new_status == EntityStatus.probation and entity is not None:
        try:
            from ...services.board_placements import ensure_sandbox_placement
            vacancy = (await db.execute(
                select(Vacancy).where(Vacancy.id == primary.vacancy_id)
            )).scalar_one_or_none()
            await ensure_sandbox_placement(db, entity_id, vacancy, org_id=entity.org_id)
        except Exception:
            logger.exception("Не удалось поставить entity=%s в песочницу", entity_id)



async def has_single_active_application(db: AsyncSession, entity_id: int) -> bool:
    """Можно ли отражать этап заявки в глобальном Entity.status.

    Entity.status — ОДНО поле на кандидата, а заявок у него может быть сколько
    угодно. Обратное направление синка (Entity.status -> VacancyApplication.stage)
    давно отказывается работать при нескольких откликах: «непонятно, в какой
    вакансии менять этап, и можно затереть чужую воронку» (см. update_entity и
    update_entity_status в routes/entities/crud.py). Прямое направление такой
    проверки не имело вовсе — и любой перенос в ОДНОЙ воронке переписывал общий
    статус: на «Статусах» и «Всех кандидатах» человек уезжал в этап, верный лишь
    для одной из его воронок, а вторая воронка об этом даже не знала. Добавление
    во ВТОРУЮ воронку и вовсе сбрасывало статус стоящего на оффере в «Новый».

    Закрытые вакансии не считаем: работа идёт только в открытых.
    """
    count = (await db.execute(
        select(func.count(VacancyApplication.id))
        .join(Vacancy, VacancyApplication.vacancy_id == Vacancy.id)
        .where(
            VacancyApplication.entity_id == entity_id,
            Vacancy.status != VacancyStatus.closed,
            Vacancy.deleted_at.is_(None),
        )
    )).scalar() or 0
    return count <= 1


async def entities_with_single_active_application(
    db: AsyncSession, entity_ids: List[int]
) -> set:
    """Bulk-вариант has_single_active_application — одним запросом, без N+1."""
    if not entity_ids:
        return set()
    rows = (await db.execute(
        select(VacancyApplication.entity_id, func.count(VacancyApplication.id))
        .join(Vacancy, VacancyApplication.vacancy_id == Vacancy.id)
        .where(
            VacancyApplication.entity_id.in_(entity_ids),
            Vacancy.status != VacancyStatus.closed,
            Vacancy.deleted_at.is_(None),
        )
        .group_by(VacancyApplication.entity_id)
    )).all()
    return {eid for eid, cnt in rows if cnt <= 1}
