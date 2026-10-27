"""
CRUD operations for entities (create, read, update, delete).
"""
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, Request
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from datetime import datetime
import asyncio
import logging

from .common import (
    logger, get_db, Entity, EntityType, EntityStatus, EntityTransfer,
    Chat, CallRecording, AnalysisHistory, User, SharedAccess, ResourceType,
    UserRole, AccessLevel, Department, DepartmentMember, DeptRole,
    Vacancy, VacancyApplication,
    get_current_user, get_user_org, has_full_database_access,
    broadcast_entity_created, broadcast_entity_updated, broadcast_entity_deleted,
    scoring_cache, OwnershipFilter,
    EntityCreate, EntityUpdate, StatusUpdate,
    normalize_and_validate_identifiers, check_entity_access,
    regenerate_entity_profile_background
)
from ...services.shadow_filter import get_isolated_creator_ids
from ...services.entity_card import (
    accessible_chat_call_conditions, entity_base_dict, entity_broadcast_payload,
)

router = APIRouter()

# Ключи extra_data, которыми владеет ТОЛЬКО сервер (свои эндпоинты/сервисы). Клиент
# их через PUT /entities слать не должен: формы и модалки нередко спредят весь
# card.extra_data, включая устаревший notes, и его merge затёр бы свежие заметки/
# теги/реакции (потеря данных). При апдейте эти ключи из присланного отбрасываем —
# менять их можно лишь профильными ручками (/notes, /timeline-reaction, hr_tags и т.п.).
_SERVER_OWNED_EXTRA_KEYS = frozenset({
    "notes", "system_hr_tags", "timeline_reactions", "merged_from",
    "participations", "hidden_duplicate_meta", "hidden_duplicate_id",
    "dismissed_duplicate_ids",
})


@router.get("/")
async def list_entities(
    type: Optional[EntityType] = None,
    status: Optional[EntityStatus] = None,
    search: Optional[str] = None,
    identifier: Optional[str] = None,  # Search by any identifier (email, phone, telegram username)
    tags: Optional[str] = None,  # comma-separated
    ownership: Optional[OwnershipFilter] = None,  # mine, shared, all
    department_id: Optional[int] = None,  # filter by department
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List contacts with filters (filtered by user's organization and departments)"""
    from .common import normalize_telegram_username

    current_user = await db.merge(current_user)

    # Initialize org for all code paths
    org = None

    # SUPERADMIN sees everything across all organizations (with shadow content isolation)
    if current_user.role == UserRole.superadmin:
        query = select(Entity)
        # Apply shadow user content isolation
        isolated_ids = await get_isolated_creator_ids(current_user, db)
        if isolated_ids:
            query = query.where(~Entity.created_by.in_(isolated_ids))
        # Apply filters
        if ownership == "mine":
            query = query.where(Entity.created_by == current_user.id)
        # For superadmin, skip org/department filtering
    else:
        org = await get_user_org(current_user, db)
        if not org:
            return []

        # Get user's department memberships for access control
        dept_memberships_result = await db.execute(
            select(DepartmentMember).where(DepartmentMember.user_id == current_user.id)
        )
        dept_memberships = list(dept_memberships_result.scalars().all())
        user_dept_ids = [dm.department_id for dm in dept_memberships]
        # Only lead and sub_admin can see all department entities
        admin_dept_ids = [dm.department_id for dm in dept_memberships if dm.role in (DeptRole.lead, DeptRole.sub_admin)]

        # Shared entities query
        shared_ids_query = select(SharedAccess.resource_id).where(
            SharedAccess.resource_type == ResourceType.entity,
            SharedAccess.shared_with_id == current_user.id,
            or_(SharedAccess.expires_at.is_(None), SharedAccess.expires_at > datetime.utcnow())
        )

        # Determine base query based on ownership filter
        if ownership == "mine":
            # Only entities created by current user
            query = select(Entity).where(
                Entity.org_id == org.id,
                Entity.created_by == current_user.id
            )
        elif ownership == "shared":
            # Only entities shared with current user (not owned by them)
            query = select(Entity).where(
                Entity.org_id == org.id,
                Entity.id.in_(shared_ids_query),
                Entity.created_by != current_user.id
            )
        else:
            # All entities user can see: own + shared + department entities
            # Full access (superadmin, owner, or member with has_full_access flag) sees all
            has_full_access = await has_full_database_access(current_user, org.id, db)
            if has_full_access:
                query = select(Entity).where(Entity.org_id == org.id)
            else:
                # Own entities + shared with me + department entities (for admins only)
                conditions = [
                    Entity.created_by == current_user.id,
                    Entity.id.in_(shared_ids_query)
                ]
                # Only lead/sub_admin can view all entities in their departments
                # Regular members see only their own entities + shared
                if admin_dept_ids:
                    # Get all user IDs from admin's departments
                    dept_member_ids_result = await db.execute(
                        select(DepartmentMember.user_id).where(
                            DepartmentMember.department_id.in_(admin_dept_ids)
                        )
                    )
                    dept_member_ids = [r for r in dept_member_ids_result.scalars().all()]

                    # DEBUG: Log department access info
                    logger.info(f"list_entities: user={current_user.id}, admin_dept_ids={admin_dept_ids}, dept_member_ids={dept_member_ids}")

                    # Show entities created by department members (even without department_id)
                    if dept_member_ids:
                        conditions.append(Entity.created_by.in_(dept_member_ids))
                    # Also show entities explicitly assigned to admin's departments
                    conditions.append(Entity.department_id.in_(admin_dept_ids))

                query = select(Entity).where(
                    Entity.org_id == org.id,
                    or_(*conditions)
                )

    # Теневая база: архивные кандидаты скрыты из активного списка
    query = query.where(Entity.is_archived.is_not(True))

    # Скоуп по воронкам (01.10.2026): человеку, допущенному только до отдельных
    # воронок, список кандидатов режется так же, как доска и поиск.
    from ...services.vacancy_scope import entity_scope_filter, get_scope_vacancy_ids
    _scope_ids = await get_scope_vacancy_ids(current_user, db)
    if _scope_ids:
        query = query.where(entity_scope_filter(_scope_ids))

    if type:
        query = query.where(Entity.type == type)
    if status:
        query = query.where(Entity.status == status)
    if search:
        search_term = f"%{search}%"
        from ...services.search_index import name_search_conditions, ensure_pg_trgm_checked, contact_search_conditions
        await ensure_pg_trgm_checked(db)
        query = query.where(
            or_(
                *name_search_conditions(search),  # умный поиск по имени (транслит+порядок+опечатки)
                *contact_search_conditions(search),  # почта/телефон(норм.)/telegram + доп-списки
                Entity.company.ilike(search_term)
            )
        )
    if identifier:
        # Search by any identifier: email, emails[], phone, phones[], telegram_usernames[]
        identifier_term = identifier.strip()
        # Normalize telegram username for search
        normalized_username = normalize_telegram_username(identifier_term)
        query = query.where(
            or_(
                Entity.email.ilike(f"%{identifier_term}%"),
                Entity.phone.ilike(f"%{identifier_term}%"),
                # For JSON arrays, use PostgreSQL's JSONB operators
                # Поиск по JSON-массивам через @> (Python-оператор and на ClauseElement
                # тут ронял запрос TypeError; @> сам корректно обрабатывает NULL/пустые).
                Entity.emails.op('@>')(func.jsonb_build_array(identifier_term)),
                Entity.phones.op('@>')(func.jsonb_build_array(identifier_term)),
                Entity.telegram_usernames.op('@>')(func.jsonb_build_array(normalized_username))
            )
        )
    if tags:
        tag_list = [t.strip() for t in tags.split(",")]
        for tag in tag_list:
            query = query.where(Entity.tags.contains([tag]))
    if department_id:
        query = query.where(Entity.department_id == department_id)

    query = query.order_by(Entity.updated_at.desc())
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    entities = result.scalars().all()

    # DEBUG: Log query results
    logger.info(f"list_entities RESULT: user={current_user.id}, found {len(entities)} entities, ids={[e.id for e in entities][:20]}")

    if not entities:
        return []

    # Get all entity IDs for batch queries
    entity_ids = [entity.id for entity in entities]

    # Pre-fetch shared entity IDs for current user
    shared_with_me_result = await db.execute(
        select(SharedAccess.resource_id).where(
            SharedAccess.resource_type == ResourceType.entity,
            SharedAccess.shared_with_id == current_user.id,
            or_(SharedAccess.expires_at.is_(None), SharedAccess.expires_at > datetime.utcnow())
        )
    )
    shared_with_me_ids = set(shared_with_me_result.scalars().all())

    # Pre-fetch owner names
    creator_ids = list(set(e.created_by for e in entities if e.created_by))
    owner_names = {}
    if creator_ids:
        owners_result = await db.execute(select(User).where(User.id.in_(creator_ids)))
        for owner in owners_result.scalars().all():
            owner_names[owner.id] = owner.name

    # Pre-fetch transferred_to names
    transferred_to_ids = list(set(e.transferred_to_id for e in entities if e.transferred_to_id))
    transferred_to_names = {}
    if transferred_to_ids:
        transferred_result = await db.execute(select(User).where(User.id.in_(transferred_to_ids)))
        for user in transferred_result.scalars().all():
            transferred_to_names[user.id] = user.name

    # Pre-fetch department names
    dept_ids = list(set(e.department_id for e in entities if e.department_id))
    dept_names = {}
    if dept_ids:
        depts_result = await db.execute(select(Department).where(Department.id.in_(dept_ids)))
        for dept in depts_result.scalars().all():
            dept_names[dept.id] = dept.name

    # Batch query: Get chat/call counts WITH ACCESS CONTROL
    # Full access users (superadmin, owner, or member with has_full_access) see all counts
    user_has_full_access = await has_full_database_access(current_user, org.id, db) if org else False
    chat_conditions, call_conditions = await accessible_chat_call_conditions(
        db, current_user, full_access=user_has_full_access,
    )
    chats_counts_result = await db.execute(
        select(Chat.entity_id, func.count(Chat.id))
        .where(Chat.entity_id.in_(entity_ids), *([or_(*chat_conditions)] if chat_conditions else []))
        .group_by(Chat.entity_id)
    )
    chats_counts = {row[0]: row[1] for row in chats_counts_result.fetchall()}
    calls_counts_result = await db.execute(
        select(CallRecording.entity_id, func.count(CallRecording.id))
        .where(CallRecording.entity_id.in_(entity_ids), *([or_(*call_conditions)] if call_conditions else []))
        .group_by(CallRecording.entity_id)
    )
    calls_counts = {row[0]: row[1] for row in calls_counts_result.fetchall()}

    # Batch query: Get vacancy application counts and vacancy names
    vacancies_counts = {}
    vacancy_names_map = {}
    try:
        # Get vacancy applications grouped by entity
        apps_result = await db.execute(
            select(VacancyApplication.entity_id, VacancyApplication.vacancy_id)
            .where(VacancyApplication.entity_id.in_(entity_ids))
        )
        apps_data = apps_result.fetchall()

        # Collect vacancy IDs and count per entity
        vacancy_ids = set()
        entity_vacancy_ids = {}  # {entity_id: [vacancy_ids]}
        for entity_id, vacancy_id in apps_data:
            vacancy_ids.add(vacancy_id)
            if entity_id not in entity_vacancy_ids:
                entity_vacancy_ids[entity_id] = []
            entity_vacancy_ids[entity_id].append(vacancy_id)

        # Get vacancy names
        if vacancy_ids:
            vacancies_result = await db.execute(
                select(Vacancy.id, Vacancy.title).where(Vacancy.id.in_(vacancy_ids))
            )
            vacancy_titles = {v.id: v.title for v in vacancies_result.fetchall()}

            # Build counts and names for each entity
            for entity_id, vac_ids in entity_vacancy_ids.items():
                vacancies_counts[entity_id] = len(vac_ids)
                # Get first 3 vacancy names
                names = [vacancy_titles.get(vid, "Unknown") for vid in vac_ids[:3]]
                vacancy_names_map[entity_id] = names
    except Exception as e:
        logger.warning(f"Failed to fetch vacancy data: {e}")
        # Continue without vacancy data

    # Build response using pre-fetched data
    response = []
    for entity in entities:
        is_mine = entity.created_by == current_user.id
        is_shared = entity.id in shared_with_me_ids and not is_mine

        row = entity_base_dict(
            entity,
            department_name=dept_names.get(entity.department_id) if entity.department_id else None,
            scope_ids=_scope_ids,
        )
        row.update({
            "owner_name": owner_names.get(entity.created_by, "Unknown"),
            "is_mine": is_mine,
            "is_shared": is_shared,
            "chats_count": chats_counts.get(entity.id, 0),
            "calls_count": calls_counts.get(entity.id, 0),
            # Transfer tracking
            "is_transferred": entity.is_transferred or False,
            "transferred_to_id": entity.transferred_to_id,
            "transferred_to_name": transferred_to_names.get(entity.transferred_to_id) if entity.transferred_to_id else None,
            "transferred_at": entity.transferred_at.isoformat() if entity.transferred_at else None,
            # Vacancy tracking
            "vacancies_count": vacancies_counts.get(entity.id, 0),
            "vacancy_names": vacancy_names_map.get(entity.id, []),
        })
        response.append(row)

    return response


@router.post("/", status_code=201)
async def create_entity(
    data: EntityCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a contact (in user's organization)"""
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    # Validate department_id if provided
    department_name = None
    if data.department_id:
        dept_result = await db.execute(
            select(Department).where(Department.id == data.department_id, Department.org_id == org.id)
        )
        dept = dept_result.scalar_one_or_none()
        if not dept:
            raise HTTPException(400, "Invalid department")
        department_name = dept.name

    # Normalize and validate multiple identifiers
    normalized_usernames, validated_emails, filtered_phones = normalize_and_validate_identifiers(
        telegram_usernames=data.telegram_usernames,
        emails=data.emails,
        phones=data.phones
    )

    entity = Entity(
        org_id=org.id,
        type=data.type,
        name=data.name,
        status=data.status,
        phone=data.phone,
        email=data.email,
        telegram_user_id=data.telegram_user_id,
        telegram_usernames=normalized_usernames,
        emails=validated_emails,
        phones=filtered_phones,
        company=data.company,
        position=data.position,
        tags=data.tags or [],
        extra_data=data.extra_data or {},
        created_by=current_user.id,
        department_id=data.department_id,
        expected_salary_min=data.expected_salary_min,
        expected_salary_max=data.expected_salary_max,
        expected_salary_currency=data.expected_salary_currency or 'RUB'
    )
    db.add(entity)
    await db.commit()
    await db.refresh(entity)
    # Журнал действий: номер новой карточки (в адресе запроса его нет).
    request.state.audit_extra = {"entity_id": entity.id}

    # Теневая дедупликация: сверяем нового активного кандидата с архивом.
    # При совпадении помечаем профиль флагом — фронт покажет баннер «Проверить».
    hidden_duplicate_id = None
    if entity.type == EntityType.candidate:
        try:
            from ...services.similarity import detect_archived_duplicate
            hidden_duplicate_id = await detect_archived_duplicate(db, entity)
            if hidden_duplicate_id:
                extra = dict(entity.extra_data or {})
                extra["hidden_duplicate_id"] = hidden_duplicate_id
                entity.extra_data = extra
                await db.commit()
                await db.refresh(entity)
        except Exception as e:
            logger.warning(f"shadow-dedup detect failed for new entity {entity.id}: {e}")

        # Детектор «копипаст текста резюме» (Feature B) — независим от детектора
        # личности. Best-effort: ошибка не должна ломать создание кандидата.
        try:
            from ...services.resume_text_twin import detect_resume_text_twin
            twin_id, _sim = await detect_resume_text_twin(db, entity)
            if twin_id:
                await db.commit()
                await db.refresh(entity)
        except Exception as e:
            logger.warning(f"resume-text-twin detect failed for new entity {entity.id}: {e}")

    from ...services.vacancy_scope import get_scope_vacancy_ids
    response_data = entity_base_dict(
        entity,
        department_name=department_name,
        scope_ids=await get_scope_vacancy_ids(current_user, db),
    )
    response_data.update({
        "chats_count": 0,
        "calls_count": 0,
        "has_hidden_duplicate": bool(hidden_duplicate_id),
        "hidden_duplicate_id": hidden_duplicate_id,
    })

    # Broadcast entity.created event (без контактов и заметок — см. entity_card)
    await broadcast_entity_created(org.id, entity_broadcast_payload(entity))

    return response_data


@router.get("/{entity_id}")
async def get_entity(
    entity_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get contact with all relations"""
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    result = await db.execute(
        select(Entity).where(Entity.id == entity_id, Entity.org_id == org.id)
    )
    entity = result.scalar_one_or_none()

    if not entity:
        raise HTTPException(404, "Entity not found")

    # Check if user has access to view this entity
    has_access = await check_entity_access(entity, current_user, org.id, db, required_level=None)
    if not has_access:
        raise HTTPException(404, "Entity not found")

    # Ленивый self-heal авто-меток HR: при открытии карточки пересчитываем
    # закреплённых рекрутеров. Ловит заявки, созданные путями без явного вызова
    # синка (формы, CSV-импорт, рекоммендер, magic-button). Diff-guard внутри:
    # пишет (и коммитит) ТОЛЬКО при реальном изменении — обычный GET остаётся
    # read-only. После коммита entity перечитается с уже свежим extra_data.
    try:
        from ...services.hr_tags import sync_for_entity
        await sync_for_entity(db, entity_id)
    except Exception:
        logging.getLogger("hr-analyzer.entities").warning(
            "HR-tags self-heal failed for entity %s", entity_id, exc_info=True
        )

    # Load related data WITH ACCESS CONTROL
    # Full access users (superadmin, owner, or member with has_full_access) see all
    user_has_full_access = await has_full_database_access(current_user, org.id, db)
    chat_conditions, call_conditions = await accessible_chat_call_conditions(
        db, current_user, full_access=user_has_full_access,
    )
    chats = (await db.execute(
        select(Chat).where(
            Chat.entity_id == entity_id,
            *([or_(*chat_conditions)] if chat_conditions else []),
        )
    )).scalars().all()
    calls = (await db.execute(
        select(CallRecording).where(
            CallRecording.entity_id == entity_id,
            *([or_(*call_conditions)] if call_conditions else []),
        ).order_by(CallRecording.created_at.desc())
    )).scalars().all()

    # Get transfers - wrap in try/except in case new columns don't exist yet
    try:
        transfers_result = await db.execute(
            select(EntityTransfer).where(EntityTransfer.entity_id == entity_id).order_by(EntityTransfer.created_at.desc())
        )
        transfers = transfers_result.scalars().all()
    except Exception as e:
        logger.warning(f"Could not fetch transfers (migration may be pending): {e}")
        transfers = []

    analyses_result = await db.execute(
        select(AnalysisHistory).where(AnalysisHistory.entity_id == entity_id).order_by(AnalysisHistory.created_at.desc())
    )
    analyses = analyses_result.scalars().all()

    # Get department info for entity
    department_name = None
    if entity.department_id:
        dept_result = await db.execute(select(Department).where(Department.id == entity.department_id))
        dept = dept_result.scalar_one_or_none()
        if dept:
            department_name = dept.name

    # Pre-fetch user names and department names for transfers (batch queries to avoid N+1)
    user_ids = set()
    dept_ids = set()
    for t in transfers:
        if t.from_user_id:
            user_ids.add(t.from_user_id)
        if t.to_user_id:
            user_ids.add(t.to_user_id)
        if hasattr(t, 'from_department_id') and t.from_department_id:
            dept_ids.add(t.from_department_id)
        if hasattr(t, 'to_department_id') and t.to_department_id:
            dept_ids.add(t.to_department_id)

    # Batch fetch user names
    user_names = {}
    if user_ids:
        users_result = await db.execute(select(User).where(User.id.in_(user_ids)))
        for user in users_result.scalars().all():
            user_names[user.id] = user.name

    # Batch fetch department names
    dept_names = {}
    if dept_ids:
        depts_result = await db.execute(select(Department).where(Department.id.in_(dept_ids)))
        for dept in depts_result.scalars().all():
            dept_names[dept.id] = dept.name

    # Build transfer data using pre-fetched names
    transfer_data = []
    for t in transfers:
        from_user_name = user_names.get(t.from_user_id) if t.from_user_id else None
        to_user_name = user_names.get(t.to_user_id) if t.to_user_id else None
        from_dept_name = None
        to_dept_name = None

        # Get department names (use new fields if available, fallback to old strings)
        if hasattr(t, 'from_department_id') and t.from_department_id:
            from_dept_name = dept_names.get(t.from_department_id)
        elif hasattr(t, 'from_department') and t.from_department:
            from_dept_name = t.from_department

        if hasattr(t, 'to_department_id') and t.to_department_id:
            to_dept_name = dept_names.get(t.to_department_id)
        elif hasattr(t, 'to_department') and t.to_department:
            to_dept_name = t.to_department

        transfer_data.append({
            "id": t.id,
            "entity_id": t.entity_id,
            "from_user_id": t.from_user_id,
            "to_user_id": t.to_user_id,
            "from_department_id": getattr(t, 'from_department_id', None),
            "to_department_id": getattr(t, 'to_department_id', None),
            "from_department_name": from_dept_name,
            "to_department_name": to_dept_name,
            "comment": t.comment,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "from_user_name": from_user_name,
            "to_user_name": to_user_name
        })

    # Get transferred_to name if entity is transferred
    transferred_to_name = None
    if entity.transferred_to_id:
        transferred_to_result = await db.execute(
            select(User.name).where(User.id == entity.transferred_to_id)
        )
        transferred_to_name = transferred_to_result.scalar()

    # Кто добавил — окно сравнения дублей пишет «добавлена 22 окт · Мария».
    owner_name = None
    if entity.created_by:
        owner_name = (await db.execute(select(User.name).where(User.id == entity.created_by))).scalar()

    # Скоуп по воронкам: из карточки убираем следы чужих воронок (метки
    # «HR: Имя · Воронка» и заметки, привязанные к ним).
    from ...services.vacancy_scope import get_scope_vacancy_ids
    _scope_ids = await get_scope_vacancy_ids(current_user, db)

    card = entity_base_dict(entity, department_name=department_name, scope_ids=_scope_ids)
    return {
        **card,
        # Transfer tracking
        "is_transferred": entity.is_transferred or False,
        "transferred_to_id": entity.transferred_to_id,
        "transferred_to_name": transferred_to_name,
        "transferred_at": entity.transferred_at.isoformat() if entity.transferred_at else None,
        # Ownership info for frontend permissions
        "owner_id": entity.created_by,
        "owner_name": owner_name,
        "is_mine": entity.created_by == current_user.id,
        "chats": [
            {
                "id": c.id,
                "title": c.custom_name or c.title,
                "chat_type": c.chat_type,
                "created_at": c.created_at.isoformat() if c.created_at else None
            }
            for c in chats
        ],
        "calls": [
            {
                "id": c.id,
                "source_type": c.source_type,
                "status": c.status,
                "duration_seconds": c.duration_seconds,
                "summary": c.summary,
                "created_at": c.created_at.isoformat() if c.created_at else None
            }
            for c in calls
        ],
        "transfers": transfer_data,
        "analyses": [
            {
                "id": a.id,
                "report_type": a.report_type,
                "result": a.result[:500] if a.result else None,
                "created_at": a.created_at.isoformat() if a.created_at else None
            }
            for a in analyses
        ]
    }


@router.put("/{entity_id}")
async def update_entity(
    entity_id: int,
    data: EntityUpdate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a contact"""
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    # Use SELECT FOR UPDATE to prevent race conditions
    result = await db.execute(
        select(Entity)
        .where(Entity.id == entity_id, Entity.org_id == org.id)
        .with_for_update()
    )
    entity = result.scalar_one_or_none()

    if not entity:
        raise HTTPException(404, "Entity not found")

    # Don't allow editing of transferred entities (frozen copies)
    if entity.is_transferred:
        raise HTTPException(400, "Cannot edit a transferred entity. This is a read-only copy.")

    # Check edit permissions (Salesforce-style)
    can_edit = False
    if current_user.role == UserRole.superadmin:
        can_edit = True
    else:
        # Full access (owner or member with has_full_access) can edit all
        user_has_full_access = await has_full_database_access(current_user, org.id, db)
        if user_has_full_access:
            can_edit = True
        elif entity.created_by == current_user.id:
            can_edit = True  # Owner of record
        else:
            # Check if shared with edit/full access
            shared_result = await db.execute(
                select(SharedAccess).where(
                    SharedAccess.resource_type == ResourceType.entity,
                    SharedAccess.resource_id == entity_id,
                    SharedAccess.shared_with_id == current_user.id,
                    SharedAccess.access_level.in_([AccessLevel.edit, AccessLevel.full]),
                    or_(SharedAccess.expires_at.is_(None), SharedAccess.expires_at > datetime.utcnow())
                )
            )
            if shared_result.scalar_one_or_none():
                can_edit = True

    if not can_edit and entity.type == EntityType.candidate:
        # Кандидаты общие (модель A): править ЛЮБОГО кандидата может любой, кто
        # работает в HR орга (hr/admin/owner) — неважно, кто его добавил: админ,
        # суперадмин или другой рекрутёр (решение юзера 2026-09-15; раньше рекрутёр
        # на чужом кандидате получал «Ошибка сохранения» и не мог вписать Telegram).
        # Удаление и передача — по-прежнему только автор/админ. Наблюдателю запись
        # закрыта раньше, в get_current_user.
        if await check_entity_access(entity, current_user, org.id, db, AccessLevel.edit):
            can_edit = True

    if not can_edit:
        raise HTTPException(403, "No edit permission for this entity")

    # Validate department_id if provided
    if data.department_id is not None:
        if data.department_id:
            dept_result = await db.execute(
                select(Department).where(Department.id == data.department_id, Department.org_id == org.id)
            )
            if not dept_result.scalar_one_or_none():
                raise HTTPException(400, "Invalid department")

    # Normalize and validate multiple identifiers if provided
    if data.telegram_usernames is not None or data.emails is not None or data.phones is not None:
        normalized_usernames, validated_emails, filtered_phones = normalize_and_validate_identifiers(
            telegram_usernames=data.telegram_usernames,
            emails=data.emails,
            phones=data.phones
        )
        # Override the data with normalized values
        if data.telegram_usernames is not None:
            data.telegram_usernames = normalized_usernames
        if data.emails is not None:
            data.emails = validated_emails
        if data.phones is not None:
            data.phones = filtered_phones

    # Optimistic locking: check version if provided
    if data.version is not None and entity.version != data.version:
        raise HTTPException(
            409,
            f"Conflict: Entity was modified by another request. "
            f"Expected version {data.version}, but current version is {entity.version}. "
            f"Please refresh and try again."
        )

    update_data = data.model_dump(exclude_unset=True)
    # Remove version from update_data to prevent it from being set directly
    update_data.pop('version', None)

    # Снимок ключей личности ДО правки: изменились ФИО/контакты/дата рождения —
    # совпадения пересчитываются сразу (иначе новая плашка ждала повторного
    # открытия, а после исправленной опечатки старая висела бесконечно).
    from ...services.similarity import identity_fingerprint, recheck_duplicates_after_edit
    _is_candidate = entity.type == EntityType.candidate
    _identity_before = identity_fingerprint(entity) if _is_candidate else None
    _status_before = entity.status

    # extra_data: MERGE, не заменять — иначе частичный апдейт (напр. форма правки
    # шлёт только salary/city/...) затрёт notes, merged_from, timeline_reactions,
    # resume_demos и пр. Присланные ключи перекрывают существующие, остальное
    # сохраняется.
    if 'extra_data' in update_data:
        _merged_extra = dict(entity.extra_data or {})
        _sent_extra = dict(update_data.pop('extra_data') or {})
        # Серверные ключи не даём переопределить клиентским снимком — иначе
        # устаревший notes из спреда card.extra_data затрёт свежие комментарии.
        for _srv_key in _SERVER_OWNED_EXTRA_KEYS:
            _sent_extra.pop(_srv_key, None)
        _merged_extra.update(_sent_extra)
        entity.extra_data = _merged_extra

    for key, value in update_data.items():
        setattr(entity, key, value)

    entity.updated_at = datetime.utcnow()
    # Increment version for optimistic locking
    entity.version = (entity.version or 1) + 1

    from ...services.stage_change import apply_entity_status, log_moves

    status_move = None
    if 'status' in update_data and data.status is not None:
        # Те же правила, что у PATCH /status (apply_entity_status). Из архива
        # выводит только НАСТОЯЩАЯ смена статуса: форма правки шлёт статус при
        # каждом сохранении, и сохранить карточку архивного не значит вернуть его.
        status_move = await apply_entity_status(
            db, entity, data.status, changed_by=current_user,
            unarchive=data.status != _status_before,
        )

    if _is_candidate and identity_fingerprint(entity) != _identity_before:
        # Сбой пересчёта не должен ронять сохранение карточки: откатываем только
        # его (savepoint), правка рекрутёра сохраняется.
        try:
            async with db.begin_nested():
                await recheck_duplicates_after_edit(db, entity)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"DUP_RECHECK failed for entity {entity_id}: {e}")

    await db.commit()
    log_moves([status_move], current_user, via="entity_edit")
    await db.refresh(entity)

    # Get department name
    department_name = None
    if entity.department_id:
        dept_result = await db.execute(select(Department.name).where(Department.id == entity.department_id))
        department_name = dept_result.scalar()

    from ...services.vacancy_scope import get_scope_vacancy_ids
    response_data = entity_base_dict(
        entity,
        department_name=department_name,
        scope_ids=await get_scope_vacancy_ids(current_user, db),
    )

    # Invalidate scoring cache if relevant fields changed
    scoring_relevant_fields = {
        'tags', 'extra_data', 'expected_salary_min', 'expected_salary_max',
        'expected_salary_currency', 'position', 'ai_summary'
    }
    if any(field in update_data for field in scoring_relevant_fields):
        await scoring_cache.invalidate_entity_scores(entity.id)
        logger.info(f"Invalidated scoring cache for entity {entity.id} due to scoring-relevant field change")

    # Regenerate AI profile in background if profile-relevant fields changed
    profile_relevant_fields = {
        'name', 'position', 'company', 'tags', 'extra_data',
        'expected_salary_min', 'expected_salary_max', 'expected_salary_currency'
    }
    if any(field in update_data for field in profile_relevant_fields):
        # Only regenerate if entity already has an AI profile
        if entity.extra_data and entity.extra_data.get('ai_profile'):
            background_tasks.add_task(
                asyncio.create_task,
                regenerate_entity_profile_background(entity.id, org.id)
            )
            logger.info(f"Scheduled AI profile regeneration for entity {entity.id}")

    # Broadcast entity.updated event (без контактов и заметок — см. entity_card)
    await broadcast_entity_updated(org.id, entity_broadcast_payload(entity))

    return response_data


@router.patch("/{entity_id}/status")
async def update_entity_status(
    entity_id: int,
    data: StatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Quick status update for drag & drop in Kanban board.

    This is a simplified endpoint for updating only the status field,
    optimized for Kanban drag & drop operations.
    """
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    result = await db.execute(
        select(Entity)
        .where(Entity.id == entity_id, Entity.org_id == org.id)
        .with_for_update()
    )
    entity = result.scalar_one_or_none()

    if not entity:
        raise HTTPException(404, "Entity not found")

    if entity.is_transferred:
        raise HTTPException(400, "Cannot edit a transferred entity")
    # Скоуп по воронкам: чужой кандидат — 404, как у карточки (раньше статус
    # можно было сменить по номеру мимо скоупа).
    from ...services.vacancy_scope import ensure_entity_visible
    await ensure_entity_visible(entity_id, current_user, db)

    # Смена этапа/статуса — additive workflow-действие в общем kanban, как
    # комментарий и загрузка файла (см. add_entity_note и upload_entity_file в
    # files.py): доступно ЛЮБОМУ пользователю той же организации. Рекрутёр видит
    # и ведёт ВСЕХ кандидатов оргa, поэтому отдельная edit-проверка тут только
    # мешала — «чужой» кандидат давал «No edit permission for this entity» при
    # «Сменить этап подбора». Entity уже отфильтрован по org_id выше (cross-org →
    # 404). Жёсткие действия (удаление, перенос, полный edit профиля) остаются
    # под edit-доступом — см. delete_entity / update_entity.
    logger.info(
        f"Status change allowed (org-scope): user {current_user.id} → entity {entity_id}"
    )

    old_status = entity.status
    from ...services.stage_change import apply_entity_status, log_moves

    # Статус, единственная открытая заявка, выход из архива, песочница на
    # практике — одним правилом с правкой карточки (apply_entity_status).
    status_move = await apply_entity_status(db, entity, data.status, changed_by=current_user)

    await db.commit()
    log_moves([status_move], current_user, via="entity_status")
    await db.refresh(entity)

    logger.info(f"Entity {entity_id} status changed: {old_status} -> {data.status}")

    # Broadcast update
    await broadcast_entity_updated(org.id, entity_broadcast_payload(entity))

    return {
        "id": entity.id,
        "status": entity.status,
        "previous_status": old_status
    }


@router.delete("/{entity_id}")
async def delete_entity(
    entity_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a contact"""
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    # Use SELECT FOR UPDATE to prevent race conditions
    result = await db.execute(
        select(Entity)
        .where(Entity.id == entity_id, Entity.org_id == org.id)
        .with_for_update()
    )
    entity = result.scalar_one_or_none()

    if not entity:
        raise HTTPException(404, "Entity not found")

    # Don't allow deleting of transferred entities (frozen copies)
    if entity.is_transferred:
        raise HTTPException(400, "Cannot delete a transferred entity. This is a read-only copy.")

    # Check delete permissions
    can_delete = False
    if current_user.role == UserRole.superadmin:
        can_delete = True
    else:
        # Full access (owner or member with has_full_access) can delete all
        user_has_full_access = await has_full_database_access(current_user, org.id, db)
        if user_has_full_access:
            can_delete = True
        elif entity.created_by == current_user.id:
            can_delete = True  # Owner of record
        else:
            # Check if shared with full access
            shared_result = await db.execute(
                select(SharedAccess).where(
                    SharedAccess.resource_type == ResourceType.entity,
                    SharedAccess.resource_id == entity_id,
                    SharedAccess.shared_with_id == current_user.id,
                    SharedAccess.access_level == AccessLevel.full,
                    or_(SharedAccess.expires_at.is_(None), SharedAccess.expires_at > datetime.utcnow())
                )
            )
            if shared_result.scalar_one_or_none():
                can_delete = True

    if not can_delete:
        raise HTTPException(403, "No delete permission for this entity")

    # If deleting a prometheus-exported entity, add email to exclusion list
    # so that auto-sync won't re-create this contact and status shows "Обучается"
    extra = dict(entity.extra_data or {})
    if extra.get("prometheus_exported") or extra.get("prometheus_intern_id"):
        entity_email = (entity.email or "").strip().lower()
        if entity_email and org:
            org_settings = dict(org.settings or {})
            exclusions = org_settings.get("prometheus_export_exclusions", [])
            if entity_email not in exclusions:
                exclusions.append(entity_email)
                org_settings["prometheus_export_exclusions"] = exclusions
                org.settings = org_settings

    # Store entity_id and org_id before deletion
    deleted_entity_id = entity.id
    deleted_org_id = entity.org_id

    # Корзина (20.10.2026): полный слепок перед удалением — 7 дней его можно
    # вернуть, а «кто, кого, когда» остаётся в журнале навсегда. Раньше
    # кандидат стирался бесследно (случай 19.10.2026).
    from ...services.entity_trash import move_to_trash, purge_expired
    trash = await move_to_trash(db, entity, current_user)
    await purge_expired(db)
    deleted_name = entity.name

    await db.delete(entity)
    await db.commit()
    logger.info(
        "ENTITY_DELETE: entity=%s «%s» by user=%s (%s) -> корзина #%s до %s",
        deleted_entity_id, deleted_name, current_user.id, current_user.name,
        trash.id, trash.purge_after.isoformat(timespec="minutes"),
    )

    # Broadcast entity.deleted event
    await broadcast_entity_deleted(deleted_org_id, deleted_entity_id)

    return {"success": True, "trash_id": trash.id, "restorable_until": trash.purge_after.isoformat()}


# Stats endpoints

@router.get("/stats/by-type")
async def get_entities_stats_by_type(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get entity counts by type (filtered by org)"""
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        return {}

    result = await db.execute(
        select(Entity.type, func.count(Entity.id))
        .where(Entity.org_id == org.id, Entity.is_archived.is_not(True))
        .group_by(Entity.type)
    )
    stats = {row[0].value: row[1] for row in result.all()}
    return stats


@router.get("/stats/by-status")
async def get_entities_stats_by_status(
    type: Optional[EntityType] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get entity counts by status (filtered by org)"""
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        return {}

    query = select(Entity.status, func.count(Entity.id)).where(
        Entity.org_id == org.id, Entity.is_archived.is_not(True)
    )
    if type:
        query = query.where(Entity.type == type)
    query = query.group_by(Entity.status)

    result = await db.execute(query)
    stats = {row[0].value: row[1] for row in result.all()}
    return stats
