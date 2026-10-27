"""
Kanban board endpoints for vacancy management.

`/{id}/kanban` интерфейс больше не зовёт (воронка берёт /{id}/applications), но
его оставили: на нём держатся тесты приватности воронки (test_kanban_privacy).
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import datetime, date

from .common import (
    logger, get_db, Vacancy, VacancyStatus, VacancyApplication, ApplicationStage,
    Entity, User, STAGE_SYNC_MAP,
    ApplicationResponse, KanbanColumn, KanbanBoard, BulkStageUpdate,
    check_vacancy_access, can_access_vacancy, is_org_admin_or_owner,
    sees_all_candidates, recompute_entity_status,
    applications_of_recruiter, private_funnel_view,
)
from ...services.auth import get_user_org

from ...services.hr_stages import STAGE_LABELS_BY_ENUM, stage_label

router = APIRouter()


@router.get("/{vacancy_id}/kanban", response_model=KanbanBoard)
async def get_kanban_board(
    vacancy_id: int,
    limit_per_column: int = Query(50, ge=1, le=200, description="Max candidates per column"),
    created_by: Optional[int] = Query(None, description="Filter by recruiter (user who created the application)"),
    applied_after: Optional[date] = Query(None, description="Filter applications created on or after this date"),
    applied_before: Optional[date] = Query(None, description="Filter applications created on or before this date"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_vacancy_access)
):
    """Get Kanban board data for a vacancy with pagination per column (with access control).

    Supports filtering by recruiter (created_by) and date range (applied_after/applied_before).
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

    # Org-level кастомизация лейблов с /all-candidates → ⚙️ Настройка этапов.
    # Org config хранит EntityStatus-ключи (new/screening/practice/...).
    # ApplicationStage и EntityStatus связаны через STAGE_SYNC_MAP, поэтому
    # для каждой колонки воронки находим соответствующий EntityStatus и
    # подтягиваем его лейбл из org-config (если задан).
    from ...models.database import STAGE_SYNC_MAP, Organization
    org_stage_overrides: dict[str, str] = {}
    if org:
        org_row = await db.get(Organization, org.id)
        cfg = (org_row.settings or {}).get("stage_config") if org_row else None
        if isinstance(cfg, list):
            for s in cfg:
                if isinstance(s, dict) and s.get("key") and s.get("label"):
                    org_stage_overrides[s["key"]] = s["label"]

    def _label_for(app_stage: ApplicationStage, fallback: str) -> str:
        # ApplicationStage → EntityStatus → org-level label
        entity_status = STAGE_SYNC_MAP.get(app_stage)
        if entity_status is not None:
            key = entity_status.value if hasattr(entity_status, "value") else str(entity_status)
            return org_stage_overrides.get(key, fallback)
        return fallback

    # Default labels for ApplicationStage (если у орги нет кастомизации
    # — берутся отсюда). Должны совпадать с дефолтами /all-candidates.
    # Справочник этапов — services/hr_stages.py (свой словарь здесь разъехался
    # с /all-candidates: «Практика» вместо «Интервью с HR», «Отклонён» вместо «Отказ»).
    _DEFAULTS = STAGE_LABELS_BY_ENUM
    default_stage_config = [
        (s, _label_for(s, _DEFAULTS[s]), [s]) for s in [
            ApplicationStage.applied, ApplicationStage.screening,
            ApplicationStage.phone_screen, ApplicationStage.interview,
            ApplicationStage.assessment, ApplicationStage.offer,
            ApplicationStage.hired, ApplicationStage.rejected,
        ]
    ]

    custom_columns = (vacancy.custom_stages or {}).get("columns") if vacancy.custom_stages else None
    if custom_columns and isinstance(custom_columns, list) and len(custom_columns) > 0:
        stage_config = []
        seen = set()
        for col in custom_columns:
            if not col.get("visible", True):
                continue
            enum_key = col.get("maps_to") or col.get("key")
            if not enum_key or enum_key in seen:
                continue
            # Validate that enum_key is a real ApplicationStage value
            try:
                stage_enum = ApplicationStage(enum_key)
            except ValueError:
                logger.warning(f"Unknown custom stage key '{enum_key}' in vacancy {vacancy_id}, skipping")
                continue
            seen.add(enum_key)
            stage_config.append((stage_enum, col.get("label", enum_key), [stage_enum]))
    else:
        stage_config = default_stage_config

    # Приватность воронки: обычный рекрутёр видит ТОЛЬКО своих кандидатов
    # (created_by == self). Админ/овнер/суперадмин/полный доступ видят всех и
    # могут вручную фильтровать по рекрутёру. Клиентский created_by от не-админа
    # игнорируем — сервер жёстко ограничивает своими откликами.
    # «Видна коллегам» (visible_to_all): все, у кого есть доступ к вакансии,
    # видят ВСЕХ кандидатов воронки (по запросу юзера 2026-08-04). «Скрыта» →
    # прежняя приватность.
    is_admin_viewer = await sees_all_candidates(current_user, org, db)

    # Build base filter conditions
    base_filters = [VacancyApplication.vacancy_id == vacancy_id]
    if created_by is not None and (is_admin_viewer or created_by == current_user.id):
        # Явный скоуп: админ — на любого рекрутёра, ЛЮБОЙ — на СЕБЯ («Только мои»),
        # даже на «Видна коллегам».
        base_filters.append(applications_of_recruiter(vacancy, created_by))
    elif not is_admin_viewer and not bool(vacancy.visible_to_all):
        # Обычный рекрутёр на «скрытой» вакансии без скоупа: свои + legacy (NULL).
        base_filters.append(private_funnel_view(current_user.id))
    # else: админ без скоупа / «Видна коллегам» → видит всех
    if applied_after is not None:
        base_filters.append(VacancyApplication.applied_at >= datetime.combine(applied_after, datetime.min.time()))
    if applied_before is not None:
        base_filters.append(VacancyApplication.applied_at <= datetime.combine(applied_before, datetime.max.time()))

    # Get total counts per stage (for UI to show "X more" indicators)
    counts_result = await db.execute(
        select(VacancyApplication.stage, func.count(VacancyApplication.id))
        .where(*base_filters)
        .group_by(VacancyApplication.stage)
    )
    stage_total_counts = {row[0]: row[1] for row in counts_result.all()}

    # Fetch all applications across all visible stages in one query,
    # then apply per-column limit in Python to avoid N queries (one per stage).
    all_visible_stages = []
    for _, _, query_stages in stage_config:
        all_visible_stages.extend(query_stages)

    all_apps_result = await db.execute(
        select(VacancyApplication)
        .where(
            *base_filters,
            VacancyApplication.stage.in_(all_visible_stages)
        )
        .order_by(VacancyApplication.stage_order, func.coalesce(VacancyApplication.last_stage_change_at, VacancyApplication.applied_at).desc())
    )
    all_apps_unsorted = all_apps_result.scalars().all()

    # Group by stage and apply per-column limit
    from collections import defaultdict
    apps_by_stage = defaultdict(list)
    for app in all_apps_unsorted:
        apps_by_stage[app.stage].append(app)

    all_apps = []
    for _, _, query_stages in stage_config:
        for qs in query_stages:
            all_apps.extend(apps_by_stage[qs][:limit_per_column])

    # Get entity info for all loaded applications (bulk load)
    entity_ids = [app.entity_id for app in all_apps]
    entities_map = {}
    if entity_ids:
        entities_result = await db.execute(
            select(Entity).where(Entity.id.in_(entity_ids))
        )
        for entity in entities_result.scalars().all():
            entities_map[entity.id] = entity

    # Build columns with pagination info
    columns = []
    total_count = sum(stage_total_counts.values())

    for display_stage, title, query_stages in stage_config:
        # Filter apps that belong to this column (including legacy stages)
        stage_apps = [app for app in all_apps if app.stage in query_stages]
        # Sum counts for all stages in this column
        stage_total = sum(stage_total_counts.get(s, 0) for s in query_stages)

        app_responses = []
        now = datetime.utcnow()
        for app in stage_apps:
            entity = entities_map.get(app.entity_id)
            app_responses.append(ApplicationResponse(
                id=app.id,
                vacancy_id=app.vacancy_id,
                vacancy_title=vacancy.title,
                entity_id=app.entity_id,
                entity_name=entity.name if entity else None,
                entity_type=entity.type if entity else None,
                entity_email=entity.email if entity else None,
                entity_phone=entity.phone if entity else None,
                entity_telegram=(entity.telegram_usernames[0] if entity.telegram_usernames else None) if entity else None,
                entity_position=entity.position if entity else None,
                stage=app.stage,
                stage_order=app.stage_order or 0,
                rating=app.rating,
                notes=app.notes,
                rejection_reason=app.rejection_reason,
                interview_summary=app.interview_summary,
                source=app.source,
                next_interview_at=app.next_interview_at,
                applied_at=app.applied_at or now,
                last_stage_change_at=app.last_stage_change_at or app.applied_at or now,
                updated_at=app.updated_at or now
            ))

        columns.append(KanbanColumn(
            stage=display_stage,
            title=title,
            applications=app_responses,
            count=len(app_responses),
            total_count=stage_total,
            has_more=len(app_responses) < stage_total
        ))

    return KanbanBoard(
        vacancy_id=vacancy.id,
        vacancy_title=vacancy.title,
        columns=columns,
        total_count=total_count
    )


@router.get("/{vacancy_id}/kanban/column/{stage}", response_model=KanbanColumn)
async def get_kanban_column(
    vacancy_id: int,
    stage: ApplicationStage,
    skip: int = Query(0, ge=0, description="Number of items to skip"),
    limit: int = Query(50, ge=1, le=200, description="Max candidates to return"),
    created_by: Optional[int] = Query(None, description="Filter by recruiter (user who created the application)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_vacancy_access)
):
    """Get paginated candidates for a specific Kanban column (with access control).

    This endpoint is used for loading more candidates in a column (infinite scroll).
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

    # Приватность воронки (как в get_kanban_board): обычный рекрутёр видит в
    # колонке только своих кандидатов; иначе бесконечный скролл стал бы дырой.
    # «Видна коллегам» (visible_to_all) → видят всех (по запросу юзера 2026-08-04).
    is_admin_viewer = await sees_all_candidates(current_user, org, db)
    col_filters = [
        VacancyApplication.vacancy_id == vacancy_id,
        VacancyApplication.stage == stage,
    ]
    if created_by is not None and (is_admin_viewer or created_by == current_user.id):
        # Явный скоуп: админ — на любого, ЛЮБОЙ — на СЕБЯ («Только мои»).
        col_filters.append(applications_of_recruiter(vacancy, created_by))
    elif not is_admin_viewer and not bool(vacancy.visible_to_all):
        col_filters.append(private_funnel_view(current_user.id))

    # Get total count for this stage
    total_count_result = await db.execute(
        select(func.count(VacancyApplication.id))
        .where(*col_filters)
    )
    total_count = total_count_result.scalar() or 0

    # Get applications with pagination
    apps_result = await db.execute(
        select(VacancyApplication)
        .where(*col_filters)
        .order_by(VacancyApplication.stage_order, func.coalesce(VacancyApplication.last_stage_change_at, VacancyApplication.applied_at).desc())
        .offset(skip)
        .limit(limit)
    )
    applications = apps_result.scalars().all()

    # Bulk load entities
    entity_ids = [app.entity_id for app in applications]
    entities_map = {}
    if entity_ids:
        entities_result = await db.execute(
            select(Entity).where(Entity.id.in_(entity_ids))
        )
        for entity in entities_result.scalars().all():
            entities_map[entity.id] = entity

    # Build response
    app_responses = []
    for app in applications:
        entity = entities_map.get(app.entity_id)
        app_responses.append(ApplicationResponse(
            id=app.id,
            vacancy_id=app.vacancy_id,
            vacancy_title=vacancy.title,
            entity_id=app.entity_id,
            entity_name=entity.name if entity else None,
            entity_type=entity.type if entity else None,
            entity_email=entity.email if entity else None,
            entity_phone=entity.phone if entity else None,
            entity_telegram=(entity.telegram_usernames[0] if entity.telegram_usernames else None) if entity else None,
            entity_position=entity.position if entity else None,
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
            updated_at=app.updated_at
        ))

    return KanbanColumn(
        stage=stage,
        # Подпись — из справочника этапов (раньше тут был свой словарь
        # транслитом: «Novyj», «Otkaz»).
        title=stage_label(stage),
        applications=app_responses,
        count=len(app_responses),
        total_count=total_count,
        has_more=(skip + len(app_responses)) < total_count
    )


async def rebalance_stage_orders(
    db: AsyncSession,
    vacancy_id: int,
    stage: ApplicationStage
) -> None:
    """Rebalance all stage_order values in a column to prevent negative numbers.

    This function reassigns sequential positive order values (starting from 1000)
    to all applications in a given stage, preserving their relative order.
    Uses a starting value of 1000 with gaps to leave room for future insertions.
    """
    # DEADLOCK-SAFE: сначала берём row-locks на все строки колонки В ПОРЯДКЕ id —
    # тем же порядком, что и прочие FOR UPDATE по vacancy_applications (статус-синк
    # по entity_id и др.). Без этого гонка «реордер колонки» ↔ «синк статуса» ловила
    # deadlock (прод 2026-08-27): стороны брали локи на пересекающиеся строки в разном
    # порядке. Последующие UPDATE (flush) новых локов не берут — они уже held.
    await db.execute(
        select(VacancyApplication.id)
        .where(
            VacancyApplication.vacancy_id == vacancy_id,
            VacancyApplication.stage == stage
        )
        .order_by(VacancyApplication.id)
        .with_for_update()
    )
    # Get all applications in this stage ordered by current stage_order
    result = await db.execute(
        select(VacancyApplication)
        .where(
            VacancyApplication.vacancy_id == vacancy_id,
            VacancyApplication.stage == stage
        )
        .order_by(VacancyApplication.stage_order, func.coalesce(VacancyApplication.last_stage_change_at, VacancyApplication.applied_at).desc())
    )
    applications = result.scalars().all()

    # Reassign sequential orders starting from 1000 with gaps of 1000
    for i, app in enumerate(applications):
        app.stage_order = (i + 1) * 1000

    logger.info(f"Rebalanced {len(applications)} applications in stage {stage} for vacancy {vacancy_id}")


@router.post("/applications/bulk-move", response_model=List[ApplicationResponse])
async def bulk_move_applications(
    data: BulkStageUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_vacancy_access)
):
    """Move multiple applications to a new stage (with access control)."""
    if not data.application_ids:
        return []

    # Get user's organization
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=403, detail="No organization access")

    # FOR UPDATE: сериализует конкурентные bulk-move над теми же заявками —
    # та же гонка, что чинили в update_application (2026-07-14): без лока два
    # почти одновременных запроса оба читают старый stage и оба пишут дубль
    # в StageTransition.
    result = await db.execute(
        select(VacancyApplication).where(
            VacancyApplication.id.in_(data.application_ids)
        ).with_for_update()
    )
    applications = result.scalars().all()

    if not applications:
        raise HTTPException(status_code=404, detail="No applications found")

    # Get the vacancy_id from first application
    vacancy_id = applications[0].vacancy_id

    # Verify vacancy exists and belongs to user's organization
    vacancy_result = await db.execute(
        select(Vacancy).where(Vacancy.id == vacancy_id, Vacancy.org_id == org.id)
    )
    vacancy = vacancy_result.scalar()
    if not vacancy:
        raise HTTPException(status_code=404, detail="Vacancy not found in your organization")

    # Право перемещения: админ/владелец орга двигает кандидатов в ЛЮБОЙ воронке,
    # остальные — только если видят конкретную вакансию (can_access_vacancy).
    if not (
        await is_org_admin_or_owner(current_user, org, db)
        or await can_access_vacancy(vacancy, current_user, org, db)
    ):
        raise HTTPException(status_code=403, detail="Access denied to this vacancy")

    # Чужих кандидатов двигать можно — то же правило, что у перевода одной
    # заявки (21.10.2026).

    # Verify all applications belong to the same vacancy
    for app in applications:
        if app.vacancy_id != vacancy_id:
            raise HTTPException(
                status_code=400,
                detail="All applications must belong to the same vacancy"
            )

    # Verify all entities belong to the same organization
    entity_ids = [app.entity_id for app in applications]
    entities_result = await db.execute(
        select(Entity).where(Entity.id.in_(entity_ids))
    )
    entities_map = {e.id: e for e in entities_result.scalars().all()}

    for app in applications:
        entity = entities_map.get(app.entity_id)
        if not entity:
            raise HTTPException(
                status_code=404,
                detail=f"Entity {app.entity_id} not found"
            )
        if entity.org_id != org.id:
            logger.warning(
                f"Cross-org bulk-move attempt: user {current_user.id} tried to move "
                f"entity {entity.id} (org {entity.org_id}) in vacancy {vacancy_id} (org {org.id})"
            )
            raise HTTPException(
                status_code=403,
                detail=f"Entity {entity.id} does not belong to your organization"
            )

    # Требования «итог собеседования перед практикой» здесь больше нет: оно
    # висело на phone_screen («Интервью с HR», а не практика) и расходилось с
    # одиночным переводом, где его нет (20.10.2026).

    # Get max stage_order for the new stage
    #
    # БЕЗ FOR UPDATE. Postgres запрещает его с агрегатами («FOR UPDATE is not
    # allowed with aggregate functions»), поэтому этот запрос ронял ВЕСЬ
    # bulk-move в 500 на проде — массовое перемещение не работало вообще.
    # Тесты этого не ловили: сьют идёт на SQLite, где FOR UPDATE игнорируется.
    # В update_application ту же строку уже сняли с тем же обоснованием:
    # stage_order — только порядок показа, гонка тут допустима. Сами заявки
    # заблокированы выше (SELECT ... FOR UPDATE по application_ids), так что
    # дубли переходов в StageTransition по-прежнему исключены.
    max_order_result = await db.execute(
        select(func.max(VacancyApplication.stage_order))
        .where(
            VacancyApplication.vacancy_id == vacancy_id,
            VacancyApplication.stage == data.stage
        )
    )
    max_order = max_order_result.scalar() or 0

    from ...services.stage_change import log_moves, move_application, settle_entities

    now = datetime.utcnow()
    moves = []
    for i, app in enumerate(applications):
        moves.append(await move_application(
            db, app, data.stage,
            changed_by=current_user,
            order=max_order + (i + 1) * 1000,
        ))
        # B2-fix: ставим updated_at явно (Python-значением), иначе после commit
        # server-side onupdate делает атрибут expired -> ленивая подгрузка в
        # ответе вне async-контекста -> MissingGreenlet (500).
        app.updated_at = now

    # Общий статус кандидата — по АКТУАЛЬНОЙ заявке (самой свежей среди живых
    # воронок; отказ/резерв учитываются, только если живых нет).
    await settle_entities(db, [app.entity_id for app in applications], moves)

    await db.commit()
    log_moves(moves, current_user, via="bulk_move")

    # --- Notifications (fire-and-forget) ---
    # Только по реальным переводам и с НАСТОЯЩИМ прежним этапом: раньше
    # уведомление всегда говорило «из Новый», откуда бы кандидат ни шёл.
    try:
        from ...services.hr_notifications import notify_stage_change, notify_practice_started

        apps_by_id = {app.id: app for app in applications}
        for move in moves:
            if move is None:
                continue
            app = apps_by_id[move.application_id]
            entity = entities_map.get(app.entity_id)
            if not entity:
                continue
            await notify_stage_change(
                db, app, entity, move.from_stage, data.stage, current_user
            )
            if data.stage == ApplicationStage.probation:
                await notify_practice_started(db, app, entity, current_user)
    except Exception:
        logger.exception("Bulk-move notifications failed (non-critical)")

    # Build response using already loaded entities
    responses = []
    for app in applications:
        entity = entities_map.get(app.entity_id)
        responses.append(ApplicationResponse(
            id=app.id,
            vacancy_id=app.vacancy_id,
            entity_id=app.entity_id,
            entity_name=entity.name if entity else None,
            entity_type=entity.type if entity else None,
            entity_email=entity.email if entity else None,
            entity_phone=entity.phone if entity else None,
            entity_telegram=(entity.telegram_usernames[0] if entity.telegram_usernames else None) if entity else None,
            entity_position=entity.position if entity else None,
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
            updated_at=app.updated_at
        ))

    logger.info(f"Bulk moved {len(applications)} applications to stage {data.stage}")

    return responses
