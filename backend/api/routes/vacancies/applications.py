"""
Application management endpoints for vacancies.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, func, or_, text, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from datetime import datetime

from .common import (
    logger, get_db, Vacancy, VacancyStatus, VacancyApplication, ApplicationStage,
    Entity, EntityType, User, STAGE_SYNC_MAP, STATUS_SYNC_MAP,
    ApplicationCreate, ApplicationUpdate, ApplicationResponse,
    check_vacancy_access, can_access_vacancy, can_manage_applications,
    is_org_admin_or_owner, sees_all_candidates, recompute_entity_status,
    applications_of_recruiter, private_funnel_view,
    BaseModel, OrgMember, OrgRole, UserRole,
)
from ...services.auth import get_user_org
from ...models.database import ApplicationCoRecruiter, EntityStatus, StageTransition

router = APIRouter()


def _notes_blob(entity) -> Optional[str]:
    """Плоский текст всех комментариев карточки (для клиентского поиска в воронке):
    extra_data.notes[].text + extra_data.participations[].notes[] (строки или dict с text)."""
    ed = getattr(entity, "extra_data", None)
    if not isinstance(ed, dict):
        return None
    parts = []
    for n in (ed.get("notes") or []):
        if isinstance(n, dict) and isinstance(n.get("text"), str):
            parts.append(n["text"])
        elif isinstance(n, str):
            parts.append(n)
    for p in (ed.get("participations") or []):
        if not isinstance(p, dict):
            continue
        for n in (p.get("notes") or []):
            if isinstance(n, dict) and isinstance(n.get("text"), str):
                parts.append(n["text"])
            elif isinstance(n, str):
                parts.append(n)
    blob = " ".join(parts).strip()
    return blob or None


async def _load_photo_file_map(db: AsyncSession, entity_ids: list[int]) -> dict:
    """Bulk-load EntityFile (image/*) для списка entity_ids.
    Возвращает {entity_id → /api/entities/.../files/.../download}.
    Локальный файл предпочтительнее extra_data.photo_url, т.к. hh.ru CDN
    может отдавать 403 / истечь срок ссылки. Совпадает с логикой
    /api/candidates/search (candidate_search.py)."""
    photo_file_map: dict = {}
    if not entity_ids:
        return photo_file_map
    try:
        from ...models.database import EntityFile
        f_result = await db.execute(
            select(EntityFile.entity_id, EntityFile.id, EntityFile.file_name)
            .where(
                EntityFile.entity_id.in_(entity_ids),
                EntityFile.mime_type.startswith("image/"),
                # Файлы, загруженные кандидатом ЧЕРЕЗ АНКЕТУ, не должны становиться
                # аватаром профиля (это просто вложение, а не фото).
                or_(
                    EntityFile.description.is_(None),
                    ~EntityFile.description.like("Загружено через форму%"),
                ),
            )
            .order_by(EntityFile.id.desc())
        )
        for row in f_result.all():
            if row.entity_id in photo_file_map:
                continue
            fname = (row.file_name or "").lower()
            # Аватар — ТОЛЬКО авто-фото: и резюме-портрет (Фото_из_резюме), и
            # парсер-фото (Фото_<имя>) сохраняются с именем на «Фото_». Произвольные
            # картинки, загруженные вручную через «Файл», в аватар НЕ идут.
            if not fname.startswith("фото"):
                continue
            photo_file_map[row.entity_id] = (
                f"/api/entities/{row.entity_id}/files/{row.id}/download"
            )
    except Exception as exc:
        logger.warning(f"Photo file fallback query failed (non-critical): {exc}")
    return photo_file_map


def _entity_photo(entity, photo_file_map: Optional[dict] = None):
    """Локальный файл (EntityFile image/*) → fallback на extra_data.photo_url."""
    if entity is None:
        return None
    if photo_file_map and entity.id in photo_file_map:
        return photo_file_map[entity.id]
    ed = entity.extra_data if isinstance(entity.extra_data, dict) else {}
    photo = ed.get("photo_url") if ed else None
    return photo if isinstance(photo, str) else None


async def _load_headline_tag_map(db: AsyncSession, entity_ids: list[int]) -> dict:
    """entity_id → яркие ярлыки у ФИО, одним запросом (без N+1).

    С 21.09.2026 теги у ФИО — свой справочник (entity_name_tags_catalog),
    отдельный от меток; раньше это были метки с флагом show_at_name, а ещё
    раньше — свободный текст в extra_data.headline_tags.
    """
    out: dict = {}
    if not entity_ids:
        return out
    try:
        # С 21.09.2026 теги у ФИО — свой справочник, отдельный от меток.
        from ...models.database import NameTag, entity_name_tag_association
        rows = await db.execute(
            select(entity_name_tag_association.c.entity_id, NameTag.name, NameTag.color)
            .join(NameTag, NameTag.id == entity_name_tag_association.c.tag_id)
            .where(entity_name_tag_association.c.entity_id.in_(entity_ids))
            .order_by(NameTag.name)
        )
        for ent_id, name, color in rows.all():
            out.setdefault(ent_id, []).append({"name": name, "color": color})
    except Exception as exc:
        logger.warning(f"Headline tags query failed (non-critical): {exc}")
    return out


def _headline_tags(entity, headline_map: Optional[dict] = None):
    """Ярлыки кандидата: из справочника, с откатом на старое хранение.

    extra_data.headline_tags бэкафилл намеренно не удаляет, так что пока прод не
    устаканился, у карточки может не быть связей — тогда показываем старое, а не
    пустоту.
    """
    if entity is None:
        return None
    if headline_map is not None:
        from_catalog = headline_map.get(entity.id)
        if from_catalog:
            return from_catalog
    ed = entity.extra_data if isinstance(entity.extra_data, dict) else {}
    raw = ed.get("headline_tags")
    if not isinstance(raw, list):
        return None
    out = [t for t in raw if isinstance(t, dict) and isinstance(t.get("text"), str)]
    return out or None


@router.get("/{vacancy_id}/applications", response_model=List[ApplicationResponse])

async def list_applications(
    vacancy_id: int,
    stage: Optional[ApplicationStage] = None,
    created_by: Optional[List[int]] = Query(None, description="Кандидаты этих рекрутёров (можно несколько: ?created_by=1&created_by=2)"),
    all_recruiters: bool = Query(False, description="Кандидаты ВСЕХ рекрутёров воронки (фильтр «Все рекрутёры»)"),
    search: Optional[str] = Query(None, description="Умный поиск кандидата по имени (транслит+порядок+опечатки)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_vacancy_access)
):
    """List all applications for a vacancy (with access control).

    Приватность воронки (как в /kanban): обычный рекрутёр видит ТОЛЬКО своих
    кандидатов (created_by == self) + legacy без автора (created_by IS NULL).
    Админ/овнер/суперадмин/полный доступ видят всех и могут скоупить по
    конкретному рекрутёру через created_by (селектор «Вакансии: <рекрутёр>» в
    левом сайдбаре /my-funnels).
    """
    # Скоуп по воронкам: чужая воронка не открывается и по прямой ссылке.
    from ...services.vacancy_scope import ensure_vacancy_visible
    await ensure_vacancy_visible(vacancy_id, current_user, db)

    org = await get_user_org(current_user, db)

    # Verify vacancy exists
    vacancy_result = await db.execute(
        select(Vacancy).where(Vacancy.id == vacancy_id)
    )
    vacancy = vacancy_result.scalar()
    if not vacancy:
        raise HTTPException(status_code=404, detail="Vacancy not found")

    # Check access rights
    if not await can_access_vacancy(vacancy, current_user, org, db):
        raise HTTPException(status_code=403, detail="Access denied to this vacancy")

    query = (
        select(VacancyApplication)
        .where(VacancyApplication.vacancy_id == vacancy_id)
        # Сортировка по ПОСЛЕДНЕМУ переносу статуса (недавно двинутые — вверху),
        # фолбэк на дату отклика для тех, кого ещё не двигали. Это эндпоинт, который
        # реально использует воронка (getApplications), — прошлый фикс ошибочно
        # правил vacancies/kanban.py, который воронка не вызывает.
        .order_by(
            VacancyApplication.stage_order,
            func.coalesce(VacancyApplication.last_stage_change_at, VacancyApplication.applied_at).desc(),
        )
    )

    # «Видна коллегам» (visible_to_all): все, у кого есть доступ к вакансии,
    # видят ВСЕХ кандидатов воронки, а не только своих (по запросу юзера
    # 2026-08-04). Member попадает сюда только назначенным/создателем/лидом/шарой
    # (см. can_access_vacancy — visible_to_all сам по себе доступ member НЕ даёт),
    # так что «видят всех» получают именно те, кому воронку реально пошарили.
    # «Скрыта от коллег» → прежняя приватность: каждый видит только своих.
    # Скоуп «кандидаты рекрутёра R» = заявки, где R владелец (created_by) ИЛИ
    # со-рекрутёр (общая воронка: один кандидат у нескольких HR сразу).
    # Фильтр «Рекрутёр: …» над воронкой (владелец, 21.10.2026): любой, кто
    # видит вакансию, отмечает ЛЮБЫХ рекрутёров (одного или нескольких) или
    # «Все рекрутёры» — и
    # смотрит (и правит) их кандидатов. По умолчанию фронт просит своих
    # (created_by = себя): чужие сами «не прилетают». Раньше на коллегу мог
    # фильтровать только админ.
    is_admin_viewer = await sees_all_candidates(current_user, org, db)
    if all_recruiters:
        pass
    elif created_by:
        # Несколько рекрутёров сразу — их кандидаты вместе (владелец, 21.10.2026).
        query = query.where(or_(*(applications_of_recruiter(vacancy, r) for r in created_by)))
    elif not is_admin_viewer and not vacancy.visible_to_all:
        # Обычный рекрутёр на «скрытой» вакансии без явного скоупа: только свои +
        # legacy без автора. На «Видна коллегам» без скоупа — видит всех (выше).
        query = query.where(private_funnel_view(current_user.id))

    if stage:
        query = query.where(VacancyApplication.stage == stage)

    # Умный поиск кандидата в воронке по имени (транслит + любой порядок слов +
    # опечатки через pg_trgm; при отсутствии pg_trgm — транслит-ILIKE).
    if search and search.strip():
        from ...services.search_index import name_search_conditions, ensure_pg_trgm_checked, contact_search_conditions
        await ensure_pg_trgm_checked(db)
        _term = f"%{search.strip()}%"
        query = query.join(Entity, Entity.id == VacancyApplication.entity_id).where(
            or_(
                *name_search_conditions(search),
                *contact_search_conditions(search),  # почта/телефон(норм.)/telegram + доп-списки
            )
        )

    result = await db.execute(query)
    applications = result.scalars().all()

    # Bulk load all entities in one query to avoid N+1
    entity_ids = list({app.entity_id for app in applications})
    entities_map = {}
    if entity_ids:
        entities_result = await db.execute(
            select(Entity).where(Entity.id.in_(entity_ids))
        )
        for entity in entities_result.scalars().all():
            entities_map[entity.id] = entity

    photo_file_map = await _load_photo_file_map(db, entity_ids)
    headline_map = await _load_headline_tag_map(db, entity_ids)

    # «Был отказ» — у тех, кто в этой воронке НЕ на «Отказе»: отказы в других
    # воронках, в других карточках того же человека и в архиве.
    prior_map: dict = {}
    try:
        from ...services.prior_rejection import prior_rejections, summary
        from ...services.vacancy_scope import get_scope_vacancy_ids
        live_ids = {a.entity_id for a in applications if a.stage != ApplicationStage.rejected}
        live = [entities_map[i] for i in live_ids if i in entities_map]
        found = await prior_rejections(
            db, live, own_except_vacancy={i: vacancy_id for i in live_ids},
            scope_ids=await get_scope_vacancy_ids(current_user, db),
        )
        prior_map = {eid: summary(items) for eid, items in found.items()}
    except Exception:
        logger.warning("Prior rejection query failed (non-critical)", exc_info=True)

    # Точка отсчёта «серии» — момент последнего переоткрытия вакансии. Константа
    # для всех откликов (vacancy уже загружен выше), поэтому флаг считаем в этом
    # же цикле, а не отдельным SQL — сравнение x < const, O(1) на строку.
    reopened_at = vacancy.reopened_at

    responses = []
    for app in applications:
        entity = entities_map.get(app.entity_id)
        # Фоллбэк на applied_at, если last_stage_change_at вдруг NULL (старые данные).
        is_previous_series = bool(
            reopened_at is not None
            and (app.last_stage_change_at or app.applied_at) < reopened_at
        )

        responses.append(ApplicationResponse(
            id=app.id,
            vacancy_id=app.vacancy_id,
            entity_id=app.entity_id,
            entity_name=entity.name if entity else None,
            entity_type=entity.type if entity else None,
            entity_email=entity.email if entity else None,
            entity_phone=entity.phone if entity else None,
            entity_telegram=(entity.telegram_usernames[0] if entity and entity.telegram_usernames else None),
            entity_telegrams=(list(entity.telegram_usernames) if entity and entity.telegram_usernames else None),
            entity_notes_text=_notes_blob(entity),
            entity_position=entity.position if entity else None,
            entity_photo=_entity_photo(entity, photo_file_map),
            entity_headline_tags=_headline_tags(entity, headline_map),
            stage=app.stage,
            stage_order=app.stage_order or 0,
            rating=app.rating,
            notes=app.notes,
            rejection_reason=app.rejection_reason,
            interview_summary=app.interview_summary,
            source=app.source,
            next_interview_at=app.next_interview_at,
            applied_at=app.applied_at,
            last_stage_change_at=app.last_stage_change_at,
            updated_at=app.updated_at,
            is_previous_series=is_previous_series,
            created_by=app.created_by,
            prior_rejection=prior_map.get(app.entity_id),
        ))

    return responses


class FunnelRecruiterOption(BaseModel):
    user_id: int
    name: str
    count: int


class FunnelRecruiters(BaseModel):
    total: int
    recruiters: List[FunnelRecruiterOption]


@router.get("/{vacancy_id}/applications/recruiters", response_model=FunnelRecruiters)
async def list_application_recruiters(
    vacancy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_vacancy_access),
):
    """Кто ведёт кандидатов в этой воронке и сколько у каждого — для фильтра
    «Кандидаты: <рекрутёр>» над воронкой (21.10.2026). Только имена и числа:
    самих кандидатов фронт берёт под выбранного человека.

    Участник — тот, кто взял воронку в работу (accepted_by), автор заявки, а
    у заявки без автора — владелец вакансии (то же правило, что у метки «HR: …»
    и applications_of_recruiter), плюс со-рекрутёры старых пар."""
    from ...services.vacancy_scope import ensure_vacancy_visible
    await ensure_vacancy_visible(vacancy_id, current_user, db)
    org = await get_user_org(current_user, db)
    vacancy = await db.get(Vacancy, vacancy_id)
    if not vacancy:
        raise HTTPException(status_code=404, detail="Vacancy not found")
    if not await can_access_vacancy(vacancy, current_user, org, db):
        raise HTTPException(status_code=403, detail="Access denied to this vacancy")

    counts: dict[int, int] = {}
    rows = (await db.execute(
        select(VacancyApplication.id, VacancyApplication.created_by)
        .where(VacancyApplication.vacancy_id == vacancy_id)
    )).all()
    app_ids = [r.id for r in rows]
    co_by_app: dict[int, set[int]] = {}
    if app_ids:
        for app_id, user_id in (await db.execute(
            select(ApplicationCoRecruiter.application_id, ApplicationCoRecruiter.user_id)
            .where(ApplicationCoRecruiter.application_id.in_(app_ids))
        )).all():
            co_by_app.setdefault(app_id, set()).add(user_id)
    for r in rows:
        owners = {r.created_by if r.created_by is not None else vacancy.created_by}
        owners |= co_by_app.get(r.id, set())
        for uid in owners:
            if uid is not None:
                counts[uid] = counts.get(uid, 0) + 1

    accepted = (vacancy.extra_data or {}).get("accepted_by") if isinstance(vacancy.extra_data, dict) else None
    for uid in accepted if isinstance(accepted, list) else []:
        if isinstance(uid, int):
            counts.setdefault(uid, 0)
    counts.setdefault(current_user.id, counts.get(current_user.id, 0))

    names = {
        u.id: (u.name or u.email or f"#{u.id}")
        for u in (await db.execute(select(User).where(User.id.in_(list(counts))))).scalars().all()
    } if counts else {}
    options = [
        FunnelRecruiterOption(user_id=uid, name=names.get(uid, f"#{uid}"), count=n)
        for uid, n in counts.items() if uid in names
    ]
    # Сначала сам смотрящий, дальше — у кого больше кандидатов.
    options.sort(key=lambda o: (o.user_id != current_user.id, -o.count, o.name))
    return FunnelRecruiters(total=len(rows), recruiters=options)


@router.post("/{vacancy_id}/applications", response_model=ApplicationResponse, status_code=201)
async def create_application(
    vacancy_id: int,
    data: ApplicationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_vacancy_access)
):
    """Add a candidate to a vacancy pipeline (with access control)."""
    # Get user's organization
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=403, detail="No organization access")

    # Verify vacancy exists and belongs to user's organization
    vacancy_result = await db.execute(
        select(Vacancy).where(
            Vacancy.id == vacancy_id, Vacancy.org_id == org.id,
            Vacancy.deleted_at.is_(None),  # в удалённую воронку не добавляем
        )
    )
    vacancy = vacancy_result.scalar()
    if not vacancy:
        raise HTTPException(status_code=404, detail="Vacancy not found")

    # Check access rights to this vacancy
    if not await can_access_vacancy(vacancy, current_user, org, db):
        raise HTTPException(status_code=403, detail="Access denied to this vacancy")

    # Verify entity exists and belongs to same organization
    entity_result = await db.execute(
        select(Entity).where(Entity.id == data.entity_id, Entity.org_id == org.id)
    )
    entity = entity_result.scalar()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found in your organization")
    # Скоуп по воронкам: чужого кандидата (вне своих воронок) по номеру не
    # добавить — иначе после добавления он становился виден целиком (26.10.2026).
    from ...services.vacancy_scope import ensure_entity_visible
    await ensure_entity_visible(entity.id, current_user, db)

    # Security: Explicit cross-organization check
    if vacancy.org_id != entity.org_id:
        logger.warning(
            f"Cross-org application attempt: user {current_user.id} tried to add "
            f"entity {entity.id} (org {entity.org_id}) to vacancy {vacancy.id} (org {vacancy.org_id})"
        )
        raise HTTPException(
            status_code=403,
            detail="Cannot add candidate from different organization"
        )

    # Check if candidate already has an application for THIS vacancy (prevent duplicates)
    existing_same_vacancy = await db.execute(
        select(VacancyApplication).where(
            VacancyApplication.entity_id == data.entity_id,
            VacancyApplication.vacancy_id == vacancy_id
        )
    )
    if existing_same_vacancy.scalar():
        raise HTTPException(
            status_code=400,
            detail="Кандидат уже добавлен в эту вакансию"
        )

    # Use candidate's current Entity.status as initial stage (converted via
    # STATUS_SYNC_MAP) — но ТОЛЬКО если это ПЕРВАЯ заявка кандидата вообще.
    # Entity.status — ОДНО глобальное поле на кандидата, а не на воронку. Если
    # у него уже есть другие заявки (мультивакансийность), entity.status может
    # отражать СОВСЕМ ДРУГУЮ, не связанную воронку (напр. «Отказ» там, где его
    # отклонили) — наследовать его в НОВУЮ воронку неверно: кандидат должен
    # начинать с «Новый», как и любой другой. Инцидент: добавленный в свежую
    # воронку кандидат, отклонённый ранее в другой, стартовал сразу «Отказ».
    initial_stage, has_other_applications = await initial_application_stage(db, entity, data.stage)

    # New candidates appear at TOP of the column (Maria's request).
    # Sort is ORDER BY stage_order ASC, applied_at DESC, so we need the
    # smallest stage_order. Use min(stage_order) - 1000 to leave gap room.
    # Race condition acceptable — stage_order is display-only.
    min_order_result = await db.execute(
        select(func.min(VacancyApplication.stage_order))
        .where(
            VacancyApplication.vacancy_id == vacancy_id,
            VacancyApplication.stage == initial_stage
        )
    )
    min_order = min_order_result.scalar()
    new_order = (min_order - 1000) if min_order is not None else 0

    application = VacancyApplication(
        vacancy_id=vacancy_id,
        entity_id=data.entity_id,
        stage=initial_stage,
        stage_order=new_order,
        rating=data.rating,
        notes=data.notes,
        source=data.source,
        created_by=current_user.id
    )

    db.add(application)

    # Sync Entity.status if the application stage differs from current entity status
    # This ensures Entity.status matches VacancyApplication.stage.
    #
    # ТОЛЬКО для ПЕРВОЙ воронки кандидата (has_other_applications посчитан выше).
    # Иначе добавление во вторую воронку сбрасывало общий статус в «Новый»: у
    # новой заявки этап applied, и человек, стоящий на оффере в первой воронке,
    # визуально откатывался на старт на «Статусах» и «Всех кандидатах» — просто
    # потому, что его позвали ещё в одну вакансию.
    sync_status_for_first_application(entity, initial_stage, has_other_applications)

    try:
        await db.commit()
    except IntegrityError:
        # Двойной клик «Добавить»: второй запрос прошёл проверку выше раньше,
        # чем первый записал заявку, и упирался в уникальность (500).
        await db.rollback()
        raise HTTPException(status_code=400, detail="Кандидат уже добавлен в эту вакансию")
    await db.refresh(application)

    # Record initial stage transition
    from ...services.stage_transitions import record_transition
    await record_transition(
        db=db,
        application_id=application.id,
        entity_id=data.entity_id,
        from_stage=None,
        to_stage=initial_stage.value,
        changed_by_id=current_user.id,
        comment="Первичная заявка",
    )
    await db.commit()

    # Авто-метка HR: кандидат попал в воронку → пересчитываем закреплённых
    # рекрутеров (по created_by активных заявок). Некритично: ошибка синка не
    # должна валить добавление кандидата.
    try:
        from ...services.hr_tags import sync_for_entity
        await sync_for_entity(db, data.entity_id)
    except Exception:
        logger.exception("HR-tags sync failed after add (non-critical)")

    # --- Notification: new candidate added ---
    try:
        from ...services.hr_notifications import notify_new_candidate
        await notify_new_candidate(db, entity, vacancy, current_user)
    except Exception:
        logger.exception("notify_new_candidate failed (non-critical)")

    logger.info(f"Created application {application.id} for vacancy {vacancy_id}")

    photo_file_map = await _load_photo_file_map(db, [entity.id])
    headline_map = await _load_headline_tag_map(db, [entity.id])

    return ApplicationResponse(
        id=application.id,
        vacancy_id=application.vacancy_id,
        entity_id=application.entity_id,
        entity_name=entity.name,
        entity_type=entity.type,
        entity_email=entity.email,
        entity_phone=entity.phone,
        entity_telegram=(entity.telegram_usernames[0] if entity.telegram_usernames else None),
        entity_position=entity.position,
        entity_photo=_entity_photo(entity, photo_file_map),
        entity_headline_tags=_headline_tags(entity, headline_map),
        stage=application.stage,
        stage_order=application.stage_order or 0,
        rating=application.rating,
        notes=application.notes,
        rejection_reason=application.rejection_reason,
        interview_summary=application.interview_summary,
        source=application.source,
        next_interview_at=application.next_interview_at,
        applied_at=application.applied_at,
        last_stage_change_at=application.last_stage_change_at,
        updated_at=application.updated_at
    )


class ApplicationTake(BaseModel):
    entity_id: int
    recruiter_id: int


@router.post("/{vacancy_id}/applications/take", response_model=ApplicationResponse)
async def take_application(
    vacancy_id: int,
    data: ApplicationTake,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_vacancy_access),
):
    """«Забрать» кандидата в воронку на выбранного рекрутёра.

    Идемпотентно: если кандидата в этой воронке ещё НЕТ — создаём заявку с
    created_by = recruiter_id; если он УЖЕ там — ПЕРЕНОСИМ: владелец заявки
    (created_by) меняется на нового, прежний кандидата теряет. Кнопка для
    кандидатов уходящих рекрутёров (решение владельца 21.09.2026). «Кому отдать» —
    любой любому (в пределах пула рекрутёров орга).
    """
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=403, detail="No organization access")

    vacancy = (await db.execute(
        select(Vacancy).where(
            Vacancy.id == vacancy_id, Vacancy.org_id == org.id, Vacancy.deleted_at.is_(None),
        )
    )).scalar()
    if not vacancy:
        raise HTTPException(status_code=404, detail="Vacancy not found")
    if not await can_access_vacancy(vacancy, current_user, org, db):
        raise HTTPException(status_code=403, detail="Access denied to this vacancy")

    entity = (await db.execute(
        select(Entity).where(Entity.id == data.entity_id, Entity.org_id == org.id)
    )).scalar()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found in your organization")
    from ...services.vacancy_scope import ensure_entity_visible, get_scope_vacancy_ids
    await ensure_entity_visible(entity.id, current_user, db)

    # Новый владелец — рекрутёр или админ орга, не наблюдатель (ревью 26.10.2026).
    from ...services.hr_notifications import valid_handover_recipients
    if data.recruiter_id not in await valid_handover_recipients(db, org.id, [data.recruiter_id]):
        raise HTTPException(status_code=400, detail="Отдать кандидата можно только рекрутёру или админу")
    # И он должен видеть эту воронку (то же правило доступа, что у него самого)
    # и не иметь ограничения, в которое она не входит. Иначе кандидат
    # становился «его» в воронке, которую он не может открыть.
    recipient = await db.get(User, data.recruiter_id)
    if not await can_access_vacancy(vacancy, recipient, org, db):
        raise HTTPException(status_code=400, detail="Этому рекрутёру закрыта выбранная воронка")
    recipient_scope = await get_scope_vacancy_ids(recipient, db)
    if recipient_scope is not None and vacancy_id not in recipient_scope:
        raise HTTPException(status_code=400, detail="Этому рекрутёру закрыта выбранная воронка")
    actor_id, actor_name = current_user.id, current_user.name or "Коллега"

    # Лочим кандидата — сериализуем конкурентные «Забрать» одного человека.
    await db.execute(select(Entity.id).where(Entity.id == data.entity_id).with_for_update())

    application = (await db.execute(
        select(VacancyApplication).where(
            VacancyApplication.entity_id == data.entity_id,
            VacancyApplication.vacancy_id == vacancy_id,
        ).with_for_update()
    )).scalar()

    created = False
    outcome = "unchanged"
    prev_owner = None
    if application:
        # Уже в воронке — ПЕРЕНОС к новому рекрутёру. Раньше (28.08) было
        # аддитивно: новый добавлялся со-рекрутёром, прежний оставался, и
        # «Забрать» у уходящего рекрутёра ничего у него не забирало.
        prev_owner = application.created_by
        if prev_owner != data.recruiter_id:
            outcome = "transferred"
            application.created_by = data.recruiter_id
            # Новый мог быть со-рекрутёром — теперь он владелец, запись лишняя.
            # Остальных со-рекрутёров не трогаем.
            await db.execute(
                delete(ApplicationCoRecruiter).where(
                    ApplicationCoRecruiter.application_id == application.id,
                    ApplicationCoRecruiter.user_id == data.recruiter_id,
                )
            )
            # Карточка («кто добавил») — за новым, если ею владел прежний: как в
            # передаче уходящего рекрутёра (services/recruiter_transfer.py). Иначе
            # у нового кандидат не попадал в «Только по моим» на «Все кандидаты».
            if prev_owner is not None and entity.created_by == prev_owner:
                entity.created_by = data.recruiter_id
                entity.updated_at = datetime.utcnow()
            logger.info(
                "TAKE_TRANSFER app=%s entity=%s vacancy=%s from=%s to=%s by=%s",
                application.id, data.entity_id, vacancy_id, prev_owner,
                data.recruiter_id, current_user.id,
            )
        application.updated_at = datetime.utcnow()
    else:
        created = True
        outcome = "added"
        # В воронку, куда кандидата забрали, он всегда приходит на «Новый»: это
        # новый подбор (решение владельца 20.10.2026). До этого этап копировался
        # из общего статуса — из «Отказа» в другой воронке кандидат приходил
        # сюда сразу в «Отказ». В прежней воронке он остаётся у прежнего
        # рекрутёра как был.
        initial_stage = ApplicationStage.applied
        _, has_other_applications = await initial_application_stage(db, entity, initial_stage)
        min_order = (await db.execute(
            select(func.min(VacancyApplication.stage_order)).where(
                VacancyApplication.vacancy_id == vacancy_id,
                VacancyApplication.stage == initial_stage,
            )
        )).scalar()
        new_order = (min_order - 1000) if min_order is not None else 0
        application = VacancyApplication(
            vacancy_id=vacancy_id,
            entity_id=data.entity_id,
            stage=initial_stage,
            stage_order=new_order,
            source='taken',
            created_by=data.recruiter_id,
        )
        db.add(application)
        sync_status_for_first_application(entity, initial_stage, has_other_applications)

    await db.commit()
    await db.refresh(application)

    if created:
        from ...services.stage_transitions import record_transition
        await record_transition(
            db=db,
            application_id=application.id,
            entity_id=data.entity_id,
            from_stage=None,
            to_stage=application.stage.value,
            changed_by_id=current_user.id,
            comment="Забрал в воронку",
        )
        await db.commit()
    elif outcome == "transferred":
        # След в ленте карточки: кто кому передал (раньше перенос был виден только
        # в логе сервера, а он живёт до перезапуска). Этап тот же — отмена этой
        # записи ничего не двигает.
        names = dict((await db.execute(
            select(User.id, User.name).where(User.id.in_([u for u in (prev_owner, data.recruiter_id) if u]))
        )).all())
        new_name = names.get(data.recruiter_id) or "новый рекрутёр"
        prev_part = f", раньше {names[prev_owner]}" if names.get(prev_owner) else ""
        db.add(StageTransition(
            application_id=application.id, entity_id=application.entity_id,
            from_stage=application.stage.value, to_stage=application.stage.value,
            changed_by=actor_id,
            # Имена не склоняем — только именительный падеж.
            comment=f"Сменился рекрутёр: теперь {new_name}{prev_part}",
        ))
        from ...services.hr_notifications import notify_candidate_taken
        await notify_candidate_taken(
            db, entity_id=application.entity_id, entity_name=entity.name or "Кандидат",
            vacancy_title=vacancy.title, prev_owner_id=prev_owner,
            new_owner_id=data.recruiter_id, new_owner_name=new_name,
            actor_id=actor_id, actor_name=actor_name,
        )
        await db.commit()

    request.state.audit_action = {
        "added": "Забрал кандидата в воронку",
        "transferred": "Передал кандидата другому рекрутёру",
        "unchanged": "Забрать: кандидат уже у этого рекрутёра",
    }[outcome]
    request.state.audit_extra = {"application_id": application.id, "entity_id": application.entity_id}

    # HR-метки: владелец сменился → пересчитать закреплённых рекрутёров.
    try:
        from ...services.hr_tags import sync_for_entity
        await sync_for_entity(db, data.entity_id)
    except Exception:
        logger.exception("HR-tags sync failed after take (non-critical)")

    return ApplicationResponse(
        id=application.id,
        vacancy_id=application.vacancy_id,
        entity_id=application.entity_id,
        stage=application.stage,
        stage_order=application.stage_order or 0,
        rating=application.rating,
        notes=application.notes,
        source=application.source,
        next_interview_at=application.next_interview_at,
        applied_at=application.applied_at,
        last_stage_change_at=application.last_stage_change_at,
        updated_at=application.updated_at,
        created_by=application.created_by,
        take_outcome=outcome,
        taken_from=prev_owner if outcome == "transferred" else None,
    )


@router.put("/applications/{application_id}", response_model=ApplicationResponse)
async def update_application(
    application_id: int,
    data: ApplicationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_vacancy_access)
):
    """Update an application (move stage, add notes, etc.) - with access control."""
    from .kanban import rebalance_stage_orders
    from ...services.stage_change import log_moves, move_application, settle_entities

    org = await get_user_org(current_user, db)

    # FOR UPDATE: сериализует конкурентные PUT на ОДНУ заявку — иначе два
    # почти одновременных запроса (двойной клик/задвоенный запрос) оба читают
    # ещё не закоммиченный старый stage и оба пишут дубль-переход в
    # StageTransition (баг 2026-07-14, найден на проде в воронке «Трафик»:
    # разрыв между дублями от 0 до ~400мс — гонка, не повторное действие юзера).
    result = await db.execute(
        select(VacancyApplication).where(VacancyApplication.id == application_id).with_for_update()
    )
    application = result.scalar()

    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    # Get the vacancy to check access
    vacancy_result = await db.execute(
        select(Vacancy).where(Vacancy.id == application.vacancy_id)
    )
    vacancy = vacancy_result.scalar()

    # Org-граница ДО ролевых проверок. is_org_admin_or_owner смотрит роль в
    # СВОЕЙ орге вызывающего и, вернув True, замыкает `or` ниже — граница,
    # которая живёт ВНУТРИ can_access_vacancy, тогда не выполняется вовсе, и
    # admin орга A правил заявку орга B, зная только её id. Тот же класс бага,
    # что чинили в can_access_vacancy (аудит 2026-08-07), где update_application
    # прямо назван среди затронутых роутов: там границу поставили внутрь
    # функции, а короткое замыкание перед ней осталось. Массовое перемещение
    # (kanban.bulk_move) грузит вакансию сразу с фильтром org_id — здесь
    # фильтра не было. 404, а не 403: наличие чужой заявки подтверждать нечего.
    if vacancy and current_user.role != UserRole.superadmin:
        if org is None or vacancy.org_id != org.id:
            raise HTTPException(status_code=404, detail="Application not found")

    # Перемещение по этапам: админ/владелец орга двигает в ЛЮБОЙ воронке,
    # остальные — если видят вакансию (can_access_vacancy). Единая логика с
    # массовым перемещением (bulk-move). Удаление из воронки (delete) остаётся
    # строгим (can_manage_applications), т.к. деструктивно.
    if vacancy and not (
        await is_org_admin_or_owner(current_user, org, db)
        or await can_access_vacancy(vacancy, current_user, org, db)
    ):
        raise HTTPException(status_code=403, detail="Недостаточно прав для изменения этой вакансии")

    # Чужого кандидата в воронке двигать можно (21.10.2026): в фильтре воронки
    # выбирают любого рекрутёра — его кандидатов и смотрят, и правят.

    # Страховка от промаха по заявке: фронт присылает, КОМУ он собирался менять
    # этап. Не совпало — значит, карточка держала чужую заявку (баг 2026-09-15,
    # «поставила отказ, а он висит в Выполняет ТЗ»): отказываем и пишем в лог.
    if data.expected_entity_id is not None and data.expected_entity_id != application.entity_id:
        logger.error(
            "STAGE_GUARD mismatch: user=%s app=%s принадлежит entity=%s, "
            "а фронт ожидал entity=%s (vacancy=%s, stage %s -> %s)",
            current_user.id, application.id, application.entity_id,
            data.expected_entity_id, application.vacancy_id,
            application.stage.value if application.stage else None,
            data.stage.value if data.stage else None,
        )
        raise HTTPException(
            status_code=409,
            detail="Карточка кандидата устарела — обновите страницу и повторите",
        )

    # Save old values for notifications
    old_stage = application.stage
    old_interview_at = application.next_interview_at

    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    # comment — не поле VacancyApplication, а коммент к переходу (пишется в историю).
    transition_comment = update_data.pop("comment", None)
    # expected_entity_id — тоже не поле заявки, а служебная сверка (см. выше).
    # Без pop его вслепую вешает setattr ниже: сегодня это безобидный атрибут
    # мимо маппинга, но стоит появиться колонке с таким именем — служебное поле
    # начнёт молча писаться в строку.
    update_data.pop("expected_entity_id", None)
    # Этап меняет ТОЛЬКО move_application — общий для всех путей смены этапа.
    new_stage = update_data.pop("stage", None)
    update_data.pop("stage_order", None)
    for field, value in update_data.items():
        setattr(application, field, value)

    move = None
    if new_stage is not None:
        move = await move_application(
            db, application, new_stage,
            changed_by=current_user,
            comment=transition_comment,
            order=data.stage_order,
        )
        # Общий статус кандидата (колонка на «Все кандидаты»/«Статусы») — по
        # АКТУАЛЬНОЙ заявке: самой свежей среди живых воронок; отказ/резерв
        # берутся в расчёт, только если живых не осталось (решение 2026-09-17).
        await settle_entities(db, [application.entity_id], [move])
    if move is None and data.stage_order is not None:
        # Перестановка внутри колонки без смены этапа (drag-n-drop).
        application.stage_order = data.stage_order

    # Check if stage_order went negative and rebalance if needed
    if application.stage_order is not None and application.stage_order < 0:
        await rebalance_stage_orders(db, application.vacancy_id, application.stage)

    await db.commit()
    await db.refresh(application)

    log_moves([move], current_user, via="application", expected_entity=data.expected_entity_id)

    # Get entity info
    entity_result = await db.execute(
        select(Entity).where(Entity.id == application.entity_id)
    )
    entity = entity_result.scalar()

    # Get vacancy title
    vacancy_result = await db.execute(
        select(Vacancy.title).where(Vacancy.id == application.vacancy_id)
    )
    vacancy_title = vacancy_result.scalar()

    # --- Notifications (fire-and-forget) ---
    try:
        from ...services.hr_notifications import (
            notify_stage_change, notify_interview_scheduled, notify_practice_started,
        )

        # Stage change notification
        if data.stage and data.stage != old_stage and entity:
            await notify_stage_change(
                db, application, entity, old_stage, data.stage, current_user
            )
            # Практика началась. phone_screen — это «Интервью с HR» (hr_stages):
            # до 20.10.2026 уведомление «переведён на этап «Практика»» приходило
            # на интервью, а на настоящей практике — нет.
            if data.stage == ApplicationStage.probation:
                await notify_practice_started(db, application, entity, current_user)

        # Interview scheduled notification
        if (
            data.next_interview_at
            and data.next_interview_at != old_interview_at
            and entity
        ):
            await notify_interview_scheduled(
                db, application, entity, data.next_interview_at, current_user
            )
    except Exception:
        logger.exception("Update-application notifications failed (non-critical)")

    logger.info(f"Updated application {application.id}, stage: {application.stage}")

    photo_file_map = await _load_photo_file_map(db, [entity.id]) if entity else {}

    return ApplicationResponse(
        id=application.id,
        vacancy_id=application.vacancy_id,
        vacancy_title=vacancy_title,
        entity_id=application.entity_id,
        entity_name=entity.name if entity else None,
        entity_type=entity.type if entity else None,
        entity_email=entity.email if entity else None,
        entity_phone=entity.phone if entity else None,
        entity_telegram=(entity.telegram_usernames[0] if entity and entity.telegram_usernames else None),
        entity_position=entity.position if entity else None,
        entity_photo=_entity_photo(entity, photo_file_map),
        stage=application.stage,
        stage_order=application.stage_order or 0,
        rating=application.rating,
        notes=application.notes,
        rejection_reason=application.rejection_reason,
        interview_summary=application.interview_summary,
        source=application.source,
        next_interview_at=application.next_interview_at,
        applied_at=application.applied_at,
        last_stage_change_at=application.last_stage_change_at,
        updated_at=application.updated_at,
        # Пересчитанный общий статус — фронту, чтобы переставить карточку в
        # «Все кандидаты» БЕЗ перезагрузки и ровно туда, где её увидит сервер.
        entity_status=entity.status.value if entity and entity.status else None,
    )


# Статусы, которые не сбрасываются при снятии с последней воронки.
# Статусы человека, а не этап воронки: новая воронка их не перезаписывает
# («Новый» в ней — начало подбора, а не увольнение из отдела).
STATUSES_KEPT_ON_NEW_APPLICATION = {
    EntityStatus.transferred, EntityStatus.dismissed, EntityStatus.quit,
}


async def initial_application_stage(db, entity, requested: ApplicationStage):
    """С какого этапа кандидат входит в воронку → (этап, есть ли другие заявки).

    Общий статус кандидата наследуется ТОЛЬКО в первую воронку: если заявки уже
    есть, статус может описывать совсем другую воронку (инцидент: отклонённый в
    одной воронке стартовал в новой сразу с «Отказа»). Одно правило для
    «Добавить в воронку» и «Забрать».
    """
    has_other = (await db.execute(
        select(func.count(VacancyApplication.id)).where(VacancyApplication.entity_id == entity.id)
    )).scalar() or 0
    stage = requested
    if not has_other and entity.status in STATUS_SYNC_MAP:
        stage = STATUS_SYNC_MAP[entity.status]
        logger.info(f"Using entity status {entity.status} -> stage {stage} for new application")
    return stage, bool(has_other)


def sync_status_for_first_application(entity, stage: ApplicationStage, has_other: bool) -> None:
    """Первая воронка задаёт общий статус кандидата; вторая и дальше — нет.

    Иначе добавление во вторую воронку сбрасывало человека с оффера в «Новый».
    Уволенного / перешедшего в отдел не трогаем вовсе: без этого он пропадал с
    доски «Штат», как только его звали в новую вакансию.
    """
    if has_other or entity.status in STATUSES_KEPT_ON_NEW_APPLICATION:
        return
    expected = STAGE_SYNC_MAP.get(stage)
    if expected and entity.status != expected:
        entity.status = expected
        entity.updated_at = datetime.utcnow()
        logger.info(f"New application: synchronized entity {entity.id} status to {expected} (from stage {stage})")


STAFF_STATUSES_KEPT_ON_REMOVE = {
    EntityStatus.transferred, EntityStatus.dismissed, EntityStatus.quit,
}


@router.delete("/applications/{application_id}", status_code=204)
async def delete_application(
    application_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_vacancy_access)
):
    """Remove a candidate from a vacancy pipeline (with access control)."""
    from ...models.database import EntityStatus

    org = await get_user_org(current_user, db)

    result = await db.execute(
        select(VacancyApplication).where(VacancyApplication.id == application_id)
    )
    application = result.scalar()

    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    # Get the vacancy to check access
    vacancy_result = await db.execute(
        select(Vacancy).where(Vacancy.id == application.vacancy_id)
    )
    vacancy = vacancy_result.scalar()
    if vacancy and not await can_manage_applications(vacancy, current_user, org, db):
        raise HTTPException(status_code=403, detail="Недостаточно прав для изменения этой вакансии")

    # Get the entity to reset its status
    entity_id = application.entity_id
    entity_result = await db.execute(
        select(Entity).where(Entity.id == entity_id)
    )
    entity = entity_result.scalar()

    # Сбрасываем статус кандидата в 'new' ТОЛЬКО если он больше не участвует
    # ни в одной вакансии. Иначе в других воронках кандидата слетал бы этап.
    other_apps = await db.execute(
        select(func.count(VacancyApplication.id)).where(
            VacancyApplication.entity_id == entity_id,
            VacancyApplication.id != application_id,
        )
    )
    has_other_apps = (other_apps.scalar() or 0) > 0

    # В корзину на 7 дней (21.10.2026): этап, чей был, история переводов с
    # комментариями, закреп. Раньше «Удалить с воронки» стирало это навсегда —
    # а с фильтром «Рекрутёры» коллега видит чужих кандидатов и может
    # промахнуться кнопкой.
    from ...services.entity_trash import move_application_to_trash
    trash_record = await move_application_to_trash(db, application, vacancy, entity, current_user)
    await db.flush()
    # Журнал действий: заявки после ответа уже нет — подсказываем, чья она.
    request.state.audit_extra = {"entity_id": entity_id, "vacancy_id": application.vacancy_id}
    # Всё для строки лога — ДО коммита: после него поля объектов в async
    # недоступны (MissingGreenlet).
    log_args = (
        application_id, entity_id, entity.name if entity else "?",
        vacancy.id if vacancy else "?", vacancy.title if vacancy else "?",
        application.stage.value if hasattr(application.stage, "value") else application.stage,
        application.created_by, current_user.id, current_user.name, trash_record.id,
    )

    await db.delete(application)

    # В отделе / уволен / уволился — статус человека, а не этап воронки:
    # снятие с последней воронки не превращает сотрудника в «Новый» (раньше
    # он так молча пропадал с доски «Штат», 20.10.2026).
    if entity and not has_other_apps and entity.status not in STAFF_STATUSES_KEPT_ON_REMOVE:
        entity.status = EntityStatus.new
        entity.updated_at = datetime.utcnow()
        logger.info(f"DELETE /applications/{application_id}: Reset entity {entity_id} status to 'new'")
    elif entity and has_other_apps:
        # Остались другие воронки — общий статус по «актуальной» из них. Раньше
        # он оставался от удалённой заявки: убрали из воронки, где был «Оффер»,
        # а в «Все кандидаты» он так и висел «Оффером» (20.10.2026).
        from ...services.stage_change import settle_entities
        await settle_entities(db, [entity_id])

    await db.commit()

    # Авто-метка HR: кандидата сняли с воронки → пересчитываем закреплённых
    # рекрутеров. Если это была последняя активная заявка данного HR — его
    # метка уходит. Некритично для удаления.
    try:
        from ...services.hr_tags import sync_for_entity
        await sync_for_entity(db, entity_id)
    except Exception:
        logger.exception("HR-tags sync failed after delete (non-critical)")

    logger.info(
        "APPLICATION_DELETE: app=%s entity=%s «%s» vacancy=%s «%s» stage=%s owner=%s by user=%s (%s) -> корзина #%s",
        *log_args,
    )
