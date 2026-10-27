"""
Basic CRUD operations for vacancies.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, or_, text, cast, String
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from datetime import datetime, timezone

from .common import (
    logger, get_db, Vacancy, VacancyStatus, VacancyApplication,
    User, Department, DepartmentMember, DeptRole, OrgMember, OrgRole,
    VacancyCreate, VacancyUpdate, VacancyResponse,
    check_vacancy_access, has_full_database_access, can_access_vacancy,
    can_edit_vacancy, has_hr_segment_access,
    can_delete_vacancy, keep_server_extra,
)
from ...services.auth import get_current_user, get_user_org
from ...services.cache import scoring_cache
from ...services.hr_notifications import notify_new_request, notify_request_assigned


class AssignRequest(BaseModel):
    user_ids: List[int] = []
    all: bool = False

router = APIRouter()


@router.get("", response_model=List[VacancyResponse])
async def list_vacancies(
    status: Optional[VacancyStatus] = None,
    deleted: bool = False,
    department_id: Optional[int] = None,
    search: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_vacancy_access)
):
    """List vacancies filtered by user access rights.

    Access rules:
    - Superadmin/Owner: sees all vacancies in org
    - Lead/Sub_admin: sees vacancies in their department + own vacancies
    - Member: sees only own vacancies (created_by or hiring_manager)
    """
    org = await get_user_org(current_user, db)

    # Base query - filter by organization
    query = select(Vacancy).where(Vacancy.org_id == org.id if org else True)

    # Скоуп по воронкам (01.10.2026): наблюдателю-ментору видны только его
    # воронки — и в сайдбаре, и в «Заявках», и в выпадающих списках.
    from ...services.vacancy_scope import get_scope_vacancy_ids, vacancy_scope_filter
    _scope_ids = await get_scope_vacancy_ids(current_user, db)
    if _scope_ids:
        query = query.where(vacancy_scope_filter(_scope_ids))

    # Мягкое удаление: по умолчанию удалённые скрыты; фильтр «Удалённые» — только они.
    if deleted:
        query = query.where(Vacancy.deleted_at.isnot(None))
    else:
        query = query.where(Vacancy.deleted_at.is_(None))

    # Apply access control based on user role
    # Full access: superadmin, owner, or member with has_full_access flag
    has_full_access = await has_full_database_access(current_user, org, db)
    # 2026-09-07: просмотр воронок открыт ВСЕМУ HR-сегменту (см.
    # has_hr_segment_access) — рекрутёр видит воронки коллег, а не только свои.
    # Список ниже фильтруется на фронте: «Мои вакансии» по-прежнему показывает
    # только личные (isPersonallyActive), чужие открываются через переключатель
    # владельца в сайдбаре.
    sees_all_vacancies = has_full_access or await has_hr_segment_access(current_user, org, db)

    if not sees_all_vacancies:
        # Get departments where user is lead/sub_admin (not just member)
        lead_dept_result = await db.execute(
            select(DepartmentMember.department_id).where(
                DepartmentMember.user_id == current_user.id,
                DepartmentMember.role.in_([DeptRole.lead, DeptRole.sub_admin])
            )
        )
        lead_dept_ids = [row[0] for row in lead_dept_result.all()]

        # User can see:
        # 1. Vacancies they created
        # 2. Vacancies where they are hiring manager
        # 3. Vacancies in departments where they are lead/sub_admin
        # 4. Vacancies assigned to them (assigned_to JSON contains user_id)
        # 5. Vacancies open for all HR (assigned_to_all == True)
        access_conditions = []

        # Always add created_by and hiring_manager conditions
        access_conditions.append(Vacancy.created_by == current_user.id)
        access_conditions.append(Vacancy.hiring_manager_id == current_user.id)

        if lead_dept_ids:
            access_conditions.append(Vacancy.department_id.in_(lead_dept_ids))

        # ВАЖНО (2026-07-07): visible_to_all БОЛЬШЕ НЕ даёт member видимость.
        # Рекрутёр видит заявку ТОЛЬКО если она реально на него назначена
        # (assigned_to / assigned_to_all) или он создатель/наниматель/лид/шара.
        # Иначе «Общая» (visible_to_all) заявка утекала всем рекрутёрам, хотя
        # назначена на другого. Админ/owner/hr видят всё через has_full_access.

        # Vacancies assigned to this user (JSON containment via PostgreSQL)
        access_conditions.append(
            text(f"vacancies.assigned_to::jsonb @> '[{int(current_user.id)}]'::jsonb")
        )
        # Vacancies open for all HR recruiters
        access_conditions.append(Vacancy.assigned_to_all == True)

        # Apply OR filter - user must match at least one condition
        query = query.where(or_(*access_conditions))

    if status:
        query = query.where(Vacancy.status == status)
    if department_id:
        query = query.where(Vacancy.department_id == department_id)
    if search:
        search_term = f"%{search}%"
        query = query.where(
            or_(
                Vacancy.title.ilike(search_term),
                Vacancy.description.ilike(search_term),
                Vacancy.location.ilike(search_term)
            )
        )

    query = query.order_by(Vacancy.priority.desc(), Vacancy.created_at.desc())
    query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    vacancies = result.scalars().all()

    if not vacancies:
        return []

    # BULK LOAD: Get all related data in single queries to avoid N+1
    vacancy_ids = [v.id for v in vacancies]
    dept_ids = [v.department_id for v in vacancies if v.department_id]
    manager_ids = [v.hiring_manager_id for v in vacancies if v.hiring_manager_id]
    creator_ids = [v.created_by for v in vacancies if v.created_by]

    # Bulk load departments
    dept_names = {}
    if dept_ids:
        dept_result = await db.execute(
            select(Department.id, Department.name).where(Department.id.in_(dept_ids))
        )
        dept_names = {row[0]: row[1] for row in dept_result.all()}

    # Bulk load hiring managers and creators (combine user IDs for single query)
    all_user_ids = list(set(manager_ids + creator_ids))
    user_names = {}
    if all_user_ids:
        user_result = await db.execute(
            select(User.id, User.name).where(User.id.in_(all_user_ids))
        )
        user_names = {row[0]: row[1] for row in user_result.all()}

    # Split for convenience
    manager_names = {uid: user_names.get(uid) for uid in manager_ids}
    creator_names = {uid: user_names.get(uid) for uid in creator_ids}

    # Bulk load application counts by stage for all vacancies
    stage_value = cast(VacancyApplication.stage, String)
    stage_counts_result = await db.execute(
        select(
            VacancyApplication.vacancy_id,
            stage_value.label("stage"),
            func.count(VacancyApplication.id)
        )
        .where(VacancyApplication.vacancy_id.in_(vacancy_ids))
        .group_by(VacancyApplication.vacancy_id, stage_value)
    )
    # Build nested dict: {vacancy_id: {stage: count}}
    all_stage_counts = {}
    for row in stage_counts_result.all():
        vac_id, stage, count = row
        if vac_id not in all_stage_counts:
            all_stage_counts[vac_id] = {}
        all_stage_counts[vac_id][str(stage)] = count

    # Build response using pre-loaded data
    responses = []
    for vacancy in vacancies:
        dept_name = dept_names.get(vacancy.department_id)
        manager_name = manager_names.get(vacancy.hiring_manager_id)
        creator_name = creator_names.get(vacancy.created_by) if vacancy.created_by else None
        stage_counts = all_stage_counts.get(vacancy.id, {})
        total_apps = sum(stage_counts.values())

        responses.append(VacancyResponse(
            id=vacancy.id,
            title=vacancy.title,
            description=vacancy.description,
            requirements=vacancy.requirements,
            responsibilities=vacancy.responsibilities,
            salary_min=vacancy.salary_min,
            salary_max=vacancy.salary_max,
            salary_currency=vacancy.salary_currency or "RUB",
            location=vacancy.location,
            employment_type=vacancy.employment_type,
            experience_level=vacancy.experience_level,
            status=vacancy.status,
            priority=vacancy.priority or 0,
            tags=vacancy.tags or [],
            extra_data=vacancy.extra_data or {},
            visible_to_all=vacancy.visible_to_all or False,
            assigned_to=vacancy.assigned_to or [],
            assigned_to_all=bool(getattr(vacancy, 'assigned_to_all', False)),
            department_id=vacancy.department_id,
            department_name=dept_name,
            hiring_manager_id=vacancy.hiring_manager_id,
            hiring_manager_name=manager_name,
            created_by=vacancy.created_by,
            created_by_name=creator_name,
            published_at=vacancy.published_at,
            closes_at=vacancy.closes_at,
        reopened_at=vacancy.reopened_at,
            created_at=vacancy.created_at,
            updated_at=vacancy.updated_at,
            applications_count=total_apps,
            stage_counts=stage_counts,
            custom_stages=getattr(vacancy, 'custom_stages', None),
            kanban_card_fields=getattr(vacancy, 'kanban_card_fields', None)
        ))

    return responses


@router.post("", response_model=VacancyResponse, status_code=201)
async def create_vacancy(
    data: VacancyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_vacancy_access)
):
    """Create a new vacancy.

    Создавать заявки могут ВСЕ члены орга, включая рекрутёров (гейт «только
    HR-админ» из 16c5141 снят по решению пользователя 2026-07-02).
    """
    org = await get_user_org(current_user, db)

    # Build vacancy kwargs — custom_stages/kanban_card_fields are optional (migration may not be applied yet)
    vacancy_kwargs = dict(
        org_id=org.id if org else None,
        title=data.title,
        description=data.description,
        requirements=data.requirements,
        responsibilities=data.responsibilities,
        salary_min=data.salary_min,
        salary_max=data.salary_max,
        salary_currency=data.salary_currency,
        location=data.location,
        employment_type=data.employment_type,
        experience_level=data.experience_level,
        status=data.status,
        priority=data.priority,
        tags=data.tags,
        extra_data=data.extra_data,
        visible_to_all=data.visible_to_all,
        department_id=data.department_id,
        hiring_manager_id=data.hiring_manager_id,
        closes_at=data.closes_at,
        created_by=current_user.id,
        published_at=datetime.utcnow() if data.status == VacancyStatus.open else None,
    )
    # custom_stages/kanban_card_fields приходят Pydantic-моделями (CustomStagesSchema),
    # а колонки — JSON. Кладём dict, иначе json.dumps падает на commit -> 500
    # («Object of type CustomStagesSchema is not JSON serializable»).
    if hasattr(Vacancy, 'custom_stages'):
        cs = data.custom_stages
        vacancy_kwargs['custom_stages'] = cs.model_dump() if hasattr(cs, 'model_dump') else cs
    if hasattr(Vacancy, 'kanban_card_fields'):
        kcf = data.kanban_card_fields
        vacancy_kwargs['kanban_card_fields'] = kcf.model_dump() if hasattr(kcf, 'model_dump') else kcf
    vacancy = Vacancy(**vacancy_kwargs)

    db.add(vacancy)
    await db.commit()
    await db.refresh(vacancy)

    logger.info(f"Created vacancy {vacancy.id}: {vacancy.title}")

    # Новая заявка → уведомить HR-админов/owner'ов (кроме создателя). Они
    # распределяют заявки между рекрутёрами. Fire-and-forget (свой commit/rollback).
    await notify_new_request(db, vacancy, current_user)

    return VacancyResponse(
        id=vacancy.id,
        title=vacancy.title,
        description=vacancy.description,
        requirements=vacancy.requirements,
        responsibilities=vacancy.responsibilities,
        salary_min=vacancy.salary_min,
        salary_max=vacancy.salary_max,
        salary_currency=vacancy.salary_currency or "RUB",
        location=vacancy.location,
        employment_type=vacancy.employment_type,
        experience_level=vacancy.experience_level,
        status=vacancy.status,
        priority=vacancy.priority or 0,
        tags=vacancy.tags or [],
        extra_data=vacancy.extra_data or {},
        visible_to_all=vacancy.visible_to_all or False,
        assigned_to=vacancy.assigned_to or [],
        assigned_to_all=bool(getattr(vacancy, 'assigned_to_all', False)),
        department_id=vacancy.department_id,
        hiring_manager_id=vacancy.hiring_manager_id,
        created_by=vacancy.created_by,
        created_by_name=current_user.name,  # Creator is current user
        published_at=vacancy.published_at,
        closes_at=vacancy.closes_at,
        reopened_at=vacancy.reopened_at,
        created_at=vacancy.created_at,
        updated_at=vacancy.updated_at,
        applications_count=0,
        stage_counts={},
        custom_stages=vacancy.custom_stages,
        kanban_card_fields=vacancy.kanban_card_fields
    )


@router.get("/{vacancy_id}", response_model=VacancyResponse)
async def get_vacancy(
    vacancy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_vacancy_access)
):
    """Get a single vacancy by ID (with access control)."""
    # Скоуп по воронкам: чужая воронка не открывается и по прямой ссылке.
    from ...services.vacancy_scope import ensure_vacancy_visible
    await ensure_vacancy_visible(vacancy_id, current_user, db)

    org = await get_user_org(current_user, db)

    result = await db.execute(
        select(Vacancy).where(Vacancy.id == vacancy_id)
    )
    vacancy = result.scalar()

    if not vacancy:
        raise HTTPException(status_code=404, detail="Vacancy not found")

    # Check access rights
    if not await can_access_vacancy(vacancy, current_user, org, db):
        raise HTTPException(status_code=403, detail="Access denied to this vacancy")

    return await _serialize_vacancy(vacancy, db)


async def _serialize_vacancy(vacancy: Vacancy, db: AsyncSession) -> VacancyResponse:
    """Полный VacancyResponse без проверки доступа (проверяет вызывающий).

    Нужен отдельно от get_vacancy: после «закрыл у себя» (leave) юзер сам
    снимает с себя доступ, и повторная проверка в get_vacancy дала бы 403
    на сериализации собственного успешного действия.
    """
    # Get department name
    dept_name = None
    if vacancy.department_id:
        dept_result = await db.execute(
            select(Department.name).where(Department.id == vacancy.department_id)
        )
        dept_name = dept_result.scalar()

    # Get hiring manager name
    manager_name = None
    if vacancy.hiring_manager_id:
        manager_result = await db.execute(
            select(User.name).where(User.id == vacancy.hiring_manager_id)
        )
        manager_name = manager_result.scalar()

    # Get creator name
    creator_name = None
    if vacancy.created_by:
        creator_result = await db.execute(
            select(User.name).where(User.id == vacancy.created_by)
        )
        creator_name = creator_result.scalar()

    # Get application counts by stage
    stage_counts_result = await db.execute(
        select(
            VacancyApplication.stage,
            func.count(VacancyApplication.id)
        )
        .where(VacancyApplication.vacancy_id == vacancy.id)
        .group_by(VacancyApplication.stage)
    )
    stage_counts = {str(row[0].value): row[1] for row in stage_counts_result.all()}
    total_apps = sum(stage_counts.values())

    return VacancyResponse(
        id=vacancy.id,
        title=vacancy.title,
        description=vacancy.description,
        requirements=vacancy.requirements,
        responsibilities=vacancy.responsibilities,
        salary_min=vacancy.salary_min,
        salary_max=vacancy.salary_max,
        salary_currency=vacancy.salary_currency or "RUB",
        location=vacancy.location,
        employment_type=vacancy.employment_type,
        experience_level=vacancy.experience_level,
        status=vacancy.status,
        priority=vacancy.priority or 0,
        tags=vacancy.tags or [],
        extra_data=vacancy.extra_data or {},
        visible_to_all=vacancy.visible_to_all or False,
        assigned_to=vacancy.assigned_to or [],
        assigned_to_all=bool(getattr(vacancy, 'assigned_to_all', False)),
        department_id=vacancy.department_id,
        department_name=dept_name,
        hiring_manager_id=vacancy.hiring_manager_id,
        hiring_manager_name=manager_name,
        created_by=vacancy.created_by,
        created_by_name=creator_name,
        published_at=vacancy.published_at,
        closes_at=vacancy.closes_at,
        reopened_at=vacancy.reopened_at,
        created_at=vacancy.created_at,
        updated_at=vacancy.updated_at,
        applications_count=total_apps,
        stage_counts=stage_counts,
        custom_stages=vacancy.custom_stages,
        kanban_card_fields=vacancy.kanban_card_fields
    )


@router.put("/{vacancy_id}", response_model=VacancyResponse)
async def update_vacancy(
    vacancy_id: int,
    data: VacancyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_vacancy_access)
):
    """Update a vacancy (with access control)."""
    org = await get_user_org(current_user, db)

    result = await db.execute(
        select(Vacancy).where(Vacancy.id == vacancy_id)
    )
    vacancy = result.scalar()

    if not vacancy:
        raise HTTPException(status_code=404, detail="Vacancy not found")

    # Check edit rights
    if not await can_edit_vacancy(vacancy, current_user, org, db):
        raise HTTPException(status_code=403, detail="You don't have permission to edit this vacancy")

    # Get update data (only fields that were explicitly set)
    update_data = data.model_dump(exclude_unset=True)

    # Validate salary range with combined values (existing + updates)
    final_salary_min = update_data.get("salary_min", vacancy.salary_min)
    final_salary_max = update_data.get("salary_max", vacancy.salary_max)
    if final_salary_min is not None and final_salary_max is not None:
        if final_salary_min > final_salary_max:
            raise HTTPException(
                status_code=422,
                detail="salary_min cannot be greater than salary_max"
            )

    # Handle tags and extra_data: convert None to empty values
    if "tags" in update_data and update_data["tags"] is None:
        update_data["tags"] = []
    if "extra_data" in update_data and update_data["extra_data"] is None:
        update_data["extra_data"] = {}
    if "extra_data" in update_data:
        update_data["extra_data"] = keep_server_extra(vacancy.extra_data, update_data["extra_data"])

    # Посторонний рекрутёр (вакансия видна всем, но он в ней не работает)
    # закрывал её У ВСЕХ: ветка «выход» ниже срабатывает только для участника
    # (20.10.2026). Закрыть вакансию, в которой кто-то работает, может участник
    # или админ. Проверяем ДО изменения полей.
    if (
        data.status in (VacancyStatus.closed, VacancyStatus.cancelled)
        and not isinstance((vacancy.extra_data or {}).get("cloned_from_request_id"), int)
        and not await has_full_database_access(current_user, org, db)
    ):
        _dismissed = set((vacancy.extra_data or {}).get("dismissed_by") or [])
        _active = set(vacancy.assigned_to or []) | ({vacancy.created_by} if vacancy.created_by else set())
        _active -= _dismissed
        _participant = current_user.id in _active or (
            getattr(vacancy, "assigned_to_all", False) and current_user.id not in _dismissed
        )
        if _active and not _participant:
            raise HTTPException(
                status_code=403,
                detail="Закрыть вакансию может её участник или администратор",
            )

    # Запоминаем статус ДО применения апдейта — нужен для детекта строго
    # перехода closed→open (переоткрытие вакансии для новой «серии» подбора)
    # и для leave-семантики закрытия общей воронки (откат статуса).
    was_closed = vacancy.status == VacancyStatus.closed
    prev_status = vacancy.status
    left_shared_funnel = False

    # Update fields
    for field, value in update_data.items():
        setattr(vacancy, field, value)

    # Set published_at when status changes to open
    if data.status == VacancyStatus.open and not vacancy.published_at:
        vacancy.published_at = datetime.utcnow()

    # Переоткрытие: closed → open ставит точку отсчёта новой «серии». Отклики
    # старше этого момента фронт покажет под «В предыдущих сериях». Строки
    # VacancyApplication НЕ трогаем — этапы кандидатов сохраняются, меняется
    # только визуальная сегментация. NAIVE UTC — как все таймстемпы в проекте
    # (колонки TIMESTAMP WITHOUT TIME ZONE, last_stage_change_at тоже naive),
    # иначе сравнение в case() рассинхронится по смещению.
    if was_closed and data.status == VacancyStatus.open:
        vacancy.reopened_at = datetime.now(timezone.utc).replace(tzinfo=None)

    # Когда рекрутёр закрывает/отменяет свой клон заявки, заявка должна исчезнуть
    # у него из "Заявок": убираем его из assigned_to оригинала и помечаем dismissed_by.
    if data.status in (VacancyStatus.closed, VacancyStatus.cancelled):
        cloned_from = (vacancy.extra_data or {}).get("cloned_from_request_id")
        if isinstance(cloned_from, int):
            # ЛЕГАСИ-ветка: клоны, созданные до отказа от клонирования
            # (2026-07-02), продолжают закрываться по-старому.
            original = await db.get(Vacancy, cloned_from)
            if original is not None:
                assigned = list(original.assigned_to or [])
                if current_user.id in assigned:
                    original.assigned_to = [u for u in assigned if u != current_user.id]
                # Покрываем кейс assigned_to_all=True: помечаем что этот рекрутёр
                # уже закончил с заявкой, фронт фильтрует по dismissed_by.
                orig_extra = dict(original.extra_data or {})
                dismissed = list(orig_extra.get("dismissed_by") or [])
                if current_user.id not in dismissed:
                    dismissed.append(current_user.id)
                    orig_extra["dismissed_by"] = dismissed
                    original.extra_data = orig_extra
        elif not await has_full_database_access(current_user, org, db):
            # ОБЩАЯ воронка (сценарий А всегда): участник «закрывает у себя».
            # Если в вакансии остаются ДРУГИЕ активные участники — это ВЫХОД
            # из воронки, а не закрытие: статус откатываем, участника снимаем
            # (assigned_to + метка dismissed_by, чтобы «Мои вакансии» его
            # больше не показывали). Реальное закрытие происходит только когда
            # закрывает ПОСЛЕДНИЙ участник (фронт спрашивает подтверждение)
            # или HR-админ (ветку leave не проходит — полный доступ).
            extra = dict(vacancy.extra_data or {})
            dismissed_set = set(extra.get("dismissed_by") or [])
            participants = set(vacancy.assigned_to or [])
            if vacancy.created_by:
                participants.add(vacancy.created_by)
            active = participants - dismissed_set
            others = active - {current_user.id}
            is_participant = current_user.id in active or (
                getattr(vacancy, "assigned_to_all", False) and current_user.id not in dismissed_set
            )
            if is_participant and others:
                left_shared_funnel = True
                vacancy.status = prev_status  # откат закрытия
                vacancy.assigned_to = [
                    u for u in (vacancy.assigned_to or []) if u != current_user.id
                ]
                dismissed_list = list(extra.get("dismissed_by") or [])
                if current_user.id not in dismissed_list:
                    dismissed_list.append(current_user.id)
                extra["dismissed_by"] = dismissed_list
                # Как у «Выйти из вакансии» (decline): вышел — больше не «взял в работу».
                extra["accepted_by"] = [u for u in (extra.get("accepted_by") or []) if u != current_user.id]
                vacancy.extra_data = extra
                logger.info(
                    f"Vacancy {vacancy.id}: user {current_user.id} left shared funnel "
                    f"(others still active: {sorted(others)})"
                )

    await db.commit()
    await db.refresh(vacancy)

    # Заявка из ТГ-чата: при РЕАЛЬНОМ закрытии (не leave-выходе участника и не
    # повторном закрытии) бот отчитывается в исходный чат «Найм завершён».
    # Ошибка Telegram не должна ломать закрытие — только лог.
    if (
        vacancy.status == VacancyStatus.closed
        and prev_status != VacancyStatus.closed
        and not left_shared_funnel
    ):
        source_chat_id = (vacancy.extra_data or {}).get("source_chat_id")
        if source_chat_id:
            try:
                from ...bot import get_bot
                await get_bot().send_message(
                    int(source_chat_id),
                    f"🎉 Найм по заявке «{vacancy.title}» успешно завершён",
                )
                logger.info(f"Vacancy {vacancy.id}: closure notice sent to TG chat {source_chat_id}")
            except Exception as tg_err:
                logger.error(f"Vacancy {vacancy.id}: TG closure notice failed: {tg_err}")

    # Invalidate scoring cache if relevant fields changed
    # (requirements, salary, experience level, etc.)
    scoring_relevant_fields = {
        'requirements', 'salary_min', 'salary_max', 'salary_currency',
        'experience_level', 'tags', 'description', 'responsibilities'
    }
    if any(field in update_data for field in scoring_relevant_fields):
        await scoring_cache.invalidate_vacancy_scores(vacancy.id)
        logger.info(f"Invalidated scoring cache for vacancy {vacancy.id} due to scoring-relevant field change")

    logger.info(f"Updated vacancy {vacancy.id}")

    # Return full response. После leave юзер сам снял с себя доступ — обычный
    # get_vacancy() дал бы 403 на сериализации собственного успешного действия,
    # поэтому отдаём напрямую (право на действие уже проверено can_edit выше).
    if left_shared_funnel:
        return await _serialize_vacancy(vacancy, db)
    return await get_vacancy(vacancy_id, db, current_user)


@router.delete("/{vacancy_id}", status_code=204)
async def delete_vacancy(
    vacancy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_vacancy_access)
):
    """Delete a vacancy (with access control)."""
    org = await get_user_org(current_user, db)

    result = await db.execute(
        select(Vacancy).where(Vacancy.id == vacancy_id)
    )
    vacancy = result.scalar()

    # Вакансия должна быть в орге вызывающего — иначе cross-org IDOR: удаление
    # чужой вакансии по id. check_vacancy_access валидирует только ФИЧУ в своей
    # орге, но НЕ орг самой вакансии, а запрос выше без org-фильтра. Сверяем явно
    # (как assign_vacancy). Раньше дыру частично прикрывал admin-гейт, но и он
    # смотрел орг юзера, а не вакансии.
    if not vacancy or vacancy.org_id != org.id:
        raise HTTPException(status_code=404, detail="Vacancy not found")

    # Удаление доступно тем, кто вакансию реально ВЕДЁТ: админ/владелец орга,
    # создатель, наниматель, назначенный рекрутёр, лид отдела (см.
    # can_delete_vacancy). Рекрутёры-member сюда по-прежнему входят как
    # участники (запрос юзера 2026-08-04), но посторонний рекрутёр — нет.
    # Раньше явной проверки не было: гейтом служил сам доступ к вакансии, а он
    # с 2026-09-07 открыт всему HR-сегменту — без этой проверки любой рекрутёр
    # сносил бы чужую воронку у ВСЕХ её участников. Кому нужен только выход у
    # себя — есть decline_vacancy («Отказаться»), это отдельная кнопка.
    if not await can_delete_vacancy(vacancy, current_user, org, db):
        raise HTTPException(
            status_code=403,
            detail="Удалить воронку может только тот, кто её ведёт: владелец, назначенный рекрутёр или админ",
        )

    # Если удаляем КЛОН заявки — «закрываем» оригинал у этого рекрутёра (как при
    # закрытии клона), иначе после удаления рабочей вакансии исходная заявка снова
    # всплывает в «Заявки» (она перестаёт считаться «уже взятой»).
    cloned_from = (vacancy.extra_data or {}).get("cloned_from_request_id")
    if isinstance(cloned_from, int):
        original = await db.get(Vacancy, cloned_from)
        if original is not None:
            assigned = list(original.assigned_to or [])
            if current_user.id in assigned:
                original.assigned_to = [u for u in assigned if u != current_user.id]
            orig_extra = dict(original.extra_data or {})
            dismissed = list(orig_extra.get("dismissed_by") or [])
            if current_user.id not in dismissed:
                dismissed.append(current_user.id)
                orig_extra["dismissed_by"] = dismissed
                original.extra_data = orig_extra

    # Мягкое удаление: вакансия исчезает из всех активных списков (deleted_at IS
    # NULL фильтруется), но видна в фильтре «Удалённые». Восстановимо через update.
    vacancy.deleted_at = datetime.utcnow()
    await db.commit()

    logger.info(f"Soft-deleted vacancy {vacancy_id}")


@router.get("/assignable-users")
async def get_assignable_users(
    include_owners: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Вернуть только реальный HR-персонал для дропдауна 'Назначить рекрутерам'.

    Логика:
    1. Ищем HR-отделы — по названию, содержащему 'hr' или 'рекрут' (case-insensitive).
    2. Если HR-отделы есть → возвращаем их членов с org_role IN ('admin','hr').
    3. Если HR-отделов нет в орге → fallback: все org_role IN ('admin','hr').
    """
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=403, detail="Organization not found")

    # 1. Находим HR-отделы по названию
    hr_depts_result = await db.execute(
        select(Department.id).where(
            Department.org_id == org.id,
            Department.is_active == True,
            or_(
                Department.name.ilike('%hr%'),
                Department.name.ilike('%рекрут%'),
            ),
        )
    )
    hr_dept_ids = [row[0] for row in hr_depts_result.all()]

    # 2. Базовый фильтр — всегда только HR org_role
    # Наблюдатели (is_readonly) только смотрят — назначать и передавать им
    # кандидатов нельзя. include_owners — для «Забрать»: владельцу организации
    # (Настя) тоже можно отдать кандидата (26.10.2026).
    roles = [OrgRole.owner, OrgRole.admin, OrgRole.hr] if include_owners else [OrgRole.admin, OrgRole.hr]
    base_conds = [
        OrgMember.org_id == org.id,
        User.is_active == True,
        OrgMember.role.in_(roles),
        OrgMember.is_readonly.isnot(True),
    ]

    if hr_dept_ids:
        # Только те HR, кто является членом HR-отдела
        result = await db.execute(
            select(User.id, User.name, OrgMember.role)
            .join(OrgMember, OrgMember.user_id == User.id)
            .join(DepartmentMember, DepartmentMember.user_id == User.id)
            .where(
                *base_conds,
                DepartmentMember.department_id.in_(hr_dept_ids),
            )
            .distinct()
            .order_by(User.name)
        )
        logger.info(f"Filtering recruiters by HR departments: {hr_dept_ids}")
    else:
        # HR-отделов нет — fallback на OrgRole
        result = await db.execute(
            select(User.id, User.name, OrgMember.role)
            .join(OrgMember, OrgMember.user_id == User.id)
            .where(*base_conds)
            .order_by(User.name)
        )
        logger.info("No HR departments found — falling back to OrgRole filter")

    users = list(result.all())
    if include_owners:
        # Владелец может не состоять в HR-отделе — добавляем отдельно.
        seen = {u[0] for u in users}
        owners = (await db.execute(
            select(User.id, User.name, OrgMember.role)
            .join(OrgMember, OrgMember.user_id == User.id)
            .where(
                OrgMember.org_id == org.id, User.is_active == True,
                OrgMember.role == OrgRole.owner, OrgMember.is_readonly.isnot(True),
            )
        )).all()
        users += [o for o in owners if o[0] not in seen]
        users.sort(key=lambda r: (r[1] or "").lower())
    logger.info(f"Assignable HR block ({len(users)}): {[(r[1], r[2]) for r in users]}")
    return [{"id": row[0], "name": row[1], "role": row[2]} for row in users]


async def take_vacancy(
    vacancy_id: int,
    force: bool = Query(False, description="Создать клон даже если он уже есть (подтверждение дубля)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_vacancy_access),
):
    """Рекрутёр берёт заявку в работу.

    НОВАЯ МОДЕЛЬ (2026-07-02): заявка = ОДНА общая воронка, клонов больше нет.
    «Взять в работу» присоединяет рекрутёра к ТОЙ ЖЕ вакансии: добавляет его в
    assigned_to, снимает из dismissed_by (если возвращается) и переводит заявку
    pending_review/draft → open при первом взятии. Все участники видят всех
    кандидатов воронки; кто с кем работает — по чипам «HR: Имя» на карточках.
    Параметр force сохранён для совместимости API (больше не используется —
    дублей-клонов не существует). Старые клоны в проде не трогаются и живут
    по легаси-логике закрытия (ветка cloned_from_request_id в update_vacancy).

    ЛИЧНОЕ ПРИНЯТИЕ (2026-07-08): «воронка общая, но заявку каждый берёт сам» —
    статус вакансии переключается pending_review/draft → open один раз, при
    ПЕРВОМ чьём-либо взятии (иначе воронка никогда не станет рабочей), но это
    НЕ означает, что все назначенные автоматически «приняли» её. Кто именно
    лично нажал «Взять в работу», трекается отдельно в extra_data.accepted_by —
    остальные назначенные, ещё не принявшие, продолжают видеть её как заявку
    (сайдбар «Заявки», utils/vacancy.ts: isRequestVisibleTo/isPersonallyActive),
    пока не примут сами.

    Доступно тем, кто в assigned_to или при assigned_to_all=True, создателю
    (либо у пользователя полный доступ к БД).
    """
    _ = force  # legacy param, no-op
    org = await get_user_org(current_user, db)
    # FOR UPDATE: сериализует одновременные «Взять в работу» (join мутирует
    # assigned_to/status одной строки).
    source_result = await db.execute(
        select(Vacancy).where(Vacancy.id == vacancy_id).with_for_update()
    )
    source = source_result.scalar_one_or_none()
    if not source or (org and source.org_id != org.id):
        raise HTTPException(status_code=404, detail="Vacancy not found")

    has_full_access = await has_full_database_access(current_user, org, db)
    if not has_full_access:
        assigned_to_list = source.assigned_to or []
        is_assigned = current_user.id in assigned_to_list
        is_assigned_all = bool(getattr(source, 'assigned_to_all', False))
        # Создатель заявки тоже может взять её в работу.
        is_creator = source.created_by == current_user.id
        if not is_assigned and not is_assigned_all and not is_creator:
            raise HTTPException(status_code=403, detail="You are not assigned to this vacancy")

    # Join: участник = в assigned_to. Идемпотентно (повторное взятие — no-op).
    assigned = list(source.assigned_to or [])
    if current_user.id not in assigned:
        assigned.append(current_user.id)
        source.assigned_to = assigned

    # Возвращение после «завершил работу»: снимаем метку dismissed_by.
    extra = dict(source.extra_data or {})
    dismissed = list(extra.get("dismissed_by") or [])
    changed_extra = False
    if current_user.id in dismissed:
        extra["dismissed_by"] = [u for u in dismissed if u != current_user.id]
        changed_extra = True

    # Личное принятие: ЭТОТ пользователь лично взял заявку в работу —
    # независимо от того, брал ли её уже кто-то другой.
    accepted_by = list(extra.get("accepted_by") or [])
    if current_user.id not in accepted_by:
        accepted_by.append(current_user.id)
        extra["accepted_by"] = accepted_by
        changed_extra = True
    if changed_extra:
        source.extra_data = extra

    # Первое взятие делает заявку рабочей воронкой.
    if source.status in (VacancyStatus.pending_review, VacancyStatus.draft):
        source.status = VacancyStatus.open
        if not source.published_at:
            source.published_at = datetime.utcnow()

    await db.commit()
    await db.refresh(source)

    logger.info(f"Request {source.id} taken (joined) by user {current_user.id}")

    return await get_vacancy(source.id, db=db, current_user=current_user)


async def decline_vacancy(
    vacancy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_vacancy_access),
):
    """Рекрутёр «Отказывается» от заявки: снимает ТОЛЬКО СЕБЯ.

    Убирает current_user из assigned_to + ставит метку dismissed_by. Заявку НЕ
    удаляет — если после этого не осталось назначенных, она снова становится
    нераспределённой и возвращается в сайдбар «Заявки» к админу. Это замена
    кнопки «Удалить» для рекрутёра (member); удалять заявки может только
    админ-уровень (can_edit_vacancy → owner/admin/hr/superadmin/создатель).
    """
    org = await get_user_org(current_user, db)
    result = await db.execute(
        select(Vacancy).where(Vacancy.id == vacancy_id).with_for_update()
    )
    vacancy = result.scalar_one_or_none()
    if not vacancy or (org and vacancy.org_id != org.id):
        raise HTTPException(status_code=404, detail="Vacancy not found")

    # Снять себя из назначенных.
    assigned = list(vacancy.assigned_to or [])
    if current_user.id in assigned:
        vacancy.assigned_to = [u for u in assigned if u != current_user.id]

    # Пометить dismissed_by — исключает себя и из assigned_to_all/общей воронки.
    extra = dict(vacancy.extra_data or {})
    dismissed = list(extra.get("dismissed_by") or [])
    changed_extra = False
    if current_user.id not in dismissed:
        dismissed.append(current_user.id)
        extra["dismissed_by"] = dismissed
        changed_extra = True

    # Снять личное принятие — «отказался» значит больше не «взял в работу».
    accepted_by = list(extra.get("accepted_by") or [])
    if current_user.id in accepted_by:
        extra["accepted_by"] = [u for u in accepted_by if u != current_user.id]
        changed_extra = True
    if changed_extra:
        vacancy.extra_data = extra

    await db.commit()
    logger.info(f"Vacancy {vacancy.id}: user {current_user.id} declined (removed self)")
    # НЕ возвращаем get_vacancy: юзер уже снял себя и мог потерять доступ (403).
    return {"declined": True, "vacancy_id": vacancy.id}


async def assign_vacancy(
    vacancy_id: int,
    data: AssignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Назначить рекрутеров на вакансию.

    data.all = True  → assigned_to_all=True, assigned_to=[]
    data.all = False → assigned_to=user_ids, assigned_to_all=False

    Требует прав редактирования вакансии (can_edit_vacancy).
    """
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=403, detail="Organization not found")

    # FOR UPDATE: сериализует конкурентные assign vs take_vacancy/decline (все
    # мутируют assigned_to/accepted_by/dismissed_by одной строки). Без лока
    # read-modify-write assign не видел append из take → перезаписывал assigned_to
    # и «терял» рекрутёра (рассинхрон assigned_to/accepted_by). Аудит 2026-08-07.
    vacancy = (await db.execute(
        select(Vacancy).where(Vacancy.id == vacancy_id).with_for_update()
    )).scalar_one_or_none()
    if not vacancy or vacancy.org_id != org.id:
        raise HTTPException(status_code=404, detail="Vacancy not found")

    if not await can_edit_vacancy(vacancy, current_user, org, db):
        raise HTTPException(status_code=403, detail="No permission to edit this vacancy")

    # Запоминаем, кто был назначен ДО — чтобы уведомить только вновь назначенных.
    old_assigned = {int(u) for u in (vacancy.assigned_to or [])}
    old_all = bool(getattr(vacancy, "assigned_to_all", False))

    if data.all:
        vacancy.assigned_to_all = True
        vacancy.assigned_to = []
        # «Всем рекрутёрам» → снимаем dismissed_by: иначе ранее «отказавшиеся»
        # рекрутёры не увидят вакансию (isVacancyParticipant проверяет dismissed_by
        # первым), хотя уведомление «вам назначена» им придёт. Аудит 2026-08-07.
        _extra = dict(vacancy.extra_data or {})
        if _extra.get("dismissed_by"):
            _extra["dismissed_by"] = []
            vacancy.extra_data = _extra
    else:
        # Проверяем что все user_ids — валидные участники орга.
        valid_ids: set[int] = set()
        if data.user_ids:
            check = await db.execute(
                select(User.id)
                .join(OrgMember, OrgMember.user_id == User.id)
                .where(OrgMember.org_id == org.id, User.id.in_(data.user_ids))
            )
            valid_ids = {row[0] for row in check.all()}
            invalid = set(data.user_ids) - valid_ids
            # Ронять сейв ТОЛЬКО если НОВО добавляют невалидного юзера. Старые
            # «фантомные» назначенцы (были в assigned_to, но потеряли членство в
            # орге — вышли/удалены) молча вычищаются: иначе один устаревший id
            # блокировал ЛЮБОЕ редактирование списка рекрутёров («Users not in
            # org»), т.к. фронт шлёт весь assigned_to, а фантом в UI невидим
            # (имя не резолвится в assignable-users → строка пропускается).
            newly_invalid = invalid - old_assigned
            if newly_invalid:
                raise HTTPException(status_code=400, detail=f"Users not in org: {sorted(newly_invalid)}")
        vacancy.assigned_to_all = False
        # Итоговый список — только валидные участники орга (стряхиваем фантомов),
        # с сохранением порядка и уникальности.
        vacancy.assigned_to = [u for u in dict.fromkeys(data.user_ids) if u in valid_ids]

    # ЗАЯВКА vs ВОРОНКА (2026-07-13, по уточнению юзера — это РАЗНОЕ):
    #   • ЗАЯВКА (pending_review/draft) — ещё не в работе. Назначение = РАЗДАЧА:
    #     рекрутёр видит её в «Заявки», статус НЕ меняем, ведущим НЕ делаем —
    #     он сам жмёт «Взять в работу» (take_vacancy → open + accepted_by).
    #   • ВОРОНКА (open) — уже рабочий пайплайн. Тут «назначил = сразу ведёт»:
    #     назначенный сразу попадает в accepted_by (карточка «Рекрутер: …» +
    #     раздел «Мои вакансии»), без отдельного «Взять в работу».
    if not vacancy.assigned_to_all:
        extra = dict(vacancy.extra_data or {})
        assigned_list = list(vacancy.assigned_to or [])
        assigned_set = set(assigned_list)
        accepted = list(extra.get("accepted_by") or [])
        changed = False

        if vacancy.status == VacancyStatus.open:
            # Активная воронка: accepted_by == assigned_to (добавляем новых
            # назначенных в «ведущие», убираем снятых переназначением).
            desired = assigned_list
        else:
            # Заявка: ведущим не делаем. Лишь поддерживаем инвариант
            # accepted_by ⊆ assigned_to (если кого-то сняли — убираем).
            desired = [u for u in accepted if u in assigned_set]
        if desired != accepted:
            extra["accepted_by"] = desired
            changed = True

        # dismissed_by: снимаем метку «вышел/снят» с назначенных — иначе
        # isVacancyParticipant отсёк бы их (первым делом смотрит dismissed_by),
        # и повторно добавленный рекрутёр остался бы невидимым (и в «Заявки»,
        # и в воронке). Применяем в обоих случаях.
        dismissed = list(extra.get("dismissed_by") or [])
        if dismissed:
            un_dismissed = [u for u in dismissed if u not in assigned_set]
            if un_dismissed != dismissed:
                extra["dismissed_by"] = un_dismissed
                changed = True

        if changed:
            vacancy.extra_data = extra
    # Статус НЕ трогаем: заявка остаётся заявкой (pending_review) до «Взять в
    # работу». Воронкой (open) её делает только take_vacancy.

    await db.commit()
    await db.refresh(vacancy)
    logger.info(f"Vacancy {vacancy_id} assigned: all={vacancy.assigned_to_all}, ids={vacancy.assigned_to}")

    # Уведомляем ТОЛЬКО вновь назначенных рекрутёров (не дёргаем уже назначенных).
    try:
        if data.all:
            # «Всем рекрутёрам»: уведомляем всю команду орга, если раньше не было
            # assigned_to_all (иначе никто реально не «прибавился»).
            if not old_all:
                res = await db.execute(
                    select(OrgMember.user_id).where(OrgMember.org_id == org.id)
                )
                newly = {int(r[0]) for r in res.all()}
            else:
                newly = set()
        else:
            newly = {int(u) for u in (vacancy.assigned_to or [])} - old_assigned
        if newly:
            await notify_request_assigned(db, vacancy, newly, current_user)
    except Exception:
        logger.exception("assign notify failed for vacancy %s", vacancy_id)

    # Возвращаем сериализованную вакансию через тот же механизм, что get_vacancy
    return await get_vacancy(vacancy_id, db=db, current_user=current_user)
