"""
Candidate Search CRM — global search and bulk actions for candidates.

Endpoints:
  GET  /api/candidates/search       — full-text search with filters, pagination, stats
  POST /api/candidates/bulk-action  — bulk status change, tag add, vacancy attach, CSV export
  GET  /api/candidates/recruiters   — list of recruiters (for filter dropdown)
  GET  /api/candidates/tags         — list of all existing tags (for autocomplete)
"""

import csv
import io
import logging
import re
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import Select, case, cast, func, literal, or_, select, String, text
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.services.similarity import first_real_telegram
from api.models.database import (
    DepartmentMember,
    DeptRole,
    Entity,
    EntityStatus,
    EntityType,
    SharedAccess,
    ResourceType,
    User,
    UserRole,
    Vacancy,
    VacancyStatus,
    VacancyApplication,
    ApplicationStage,
    StageTransition,
    AccessLevel,
    STATUS_SYNC_MAP,
)
from api.services.auth import get_current_user, get_user_org, has_full_database_access
from api.services.shadow_filter import get_isolated_creator_ids
from api.services.hr_stages import (
    BOARD_STATUSES, OTHER_STATUS, STATUS_LABELS, board_column, statuses_in_column,
)
from api.services.vacancy_scope import (
    entity_scope_filter, filter_extra_for_scope, get_scope_vacancy_ids,
)

logger = logging.getLogger("hr-analyzer.candidate-search")

router = APIRouter()

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class CandidateItem(BaseModel):
    id: int
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    telegram_username: Optional[str] = None
    status: str
    source: Optional[str] = None
    recruiter_id: Optional[int] = None
    recruiter_name: Optional[str] = None
    created_at: datetime
    tags: list = []
    position: Optional[str] = None
    company: Optional[str] = None
    vacancy_count: int = 0
    is_duplicate: bool = False
    # Из теневой базы (попадает в выдачу только при поиске) — фронт метит «Архив».
    is_archived: bool = False

    class Config:
        from_attributes = True


class StatsBlock(BaseModel):
    total: int = 0
    new: int = 0
    screening: int = 0
    practice: int = 0
    hired: int = 0
    rejected: int = 0


class CandidateSearchResponse(BaseModel):
    items: List[CandidateItem]
    total: int
    page: int
    per_page: int
    stats: StatsBlock


class BulkActionRequest(BaseModel):
    entity_ids: List[int]
    action: str  # add_to_vacancy | change_status | add_tag | export_csv
    vacancy_id: Optional[int] = None
    status: Optional[str] = None
    tag: Optional[str] = None


class RecruiterItem(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Паттерны поиска по имени раньше строились локальным _name_search_terms — точной
# копией search_index._translit_ilike_patterns. Копия предсказуемо отстала: фикс
# «Ё≡Е» лёг в канонический хелпер, а сюда не доехал, и главные окна поиска не
# находили «Дёмина» по запросу «Демин». Теперь все окна зовут
# search_index.name_search_conditions(q) — один источник правды.


def _base_candidate_query(
    org_id: Optional[int],
    current_user: User,
    isolated_ids: list,
    include_archived: bool = False,
    scope_ids: Optional[set] = None,
) -> Select:
    """Return a base SELECT for Entity filtered to candidates + org scoping.

    Скрываем frozen-копии после трансфера (is_transferred=true) — это
    read-only артефакты с суффиксом '[Transferred -> ...]' в имени,
    они не должны загромождать активную доску HR.

    include_archived — подмешать теневую базу. По умолчанию архив скрыт (пустая
    доска/списки не должны тонуть в тысячах импортных карточек), но при ПОИСКЕ
    его включаем: рекрутёр должен находить, что человек уже проходил у нас
    (карточки помечаются флагом is_archived). Права не меняются: org-скоуп и
    shadow-фильтр остаются, а сам раздел «Архив» — по-прежнему superadmin-only.
    """
    conds = [
        Entity.type == EntityType.candidate,
        Entity.is_transferred.is_not(True),
    ]
    if not include_archived:
        conds.append(Entity.is_archived.is_not(True))
    q = select(Entity).where(*conds)
    if current_user.role == UserRole.superadmin:
        if isolated_ids:
            q = q.where(~Entity.created_by.in_(isolated_ids))
    elif org_id:
        q = q.where(Entity.org_id == org_id)
    # Скоуп по воронкам (наблюдатель «только Трафик», 01.10.2026): и список, и
    # счётчики, и «Выбрать всех» считаются из ОДНОГО запроса — поэтому фильтр
    # стоит здесь, а не в каждом эндпоинте отдельно.
    if scope_ids:
        q = q.where(entity_scope_filter(scope_ids))
    return q


def _as_str(v):
    """Привести JSON-значение к str для str-полей схемы (KanbanCard.*).

    Парсер/PDF-автозаполнение кладёт age/salary/experience в extra_data ЧИСЛОМ
    (например age=29), а KanbanCard.* типизированы Optional[str]. Pydantic v2 не
    коэрсит int→str → валидация падает → кандидат МОЛЧА выпадал с канбана
    (см. except «Skipping entity … in kanban»). Приводим заранее.
    """
    if v is None:
        return None
    return v if isinstance(v, str) else str(v)


def _age_from_birthdate(v, today: Optional[date] = None) -> Optional[str]:
    """'YYYY-MM-DD' → возраст (строка) для карточки.

    Импорт/парсер кладут в extra_data `birth_date`, но карточка показывает
    `age`. Считаем возраст на лету (не храним — иначе устаревает после дня
    рождения). Мусор/непарсимое → None.
    """
    if not v or not isinstance(v, str):
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", v.strip())
    if not m:
        return None
    try:
        bd = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None
    today = today or date.today()
    age = today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
    if age < 14 or age > 100:
        return None
    return str(age)


async def _get_org_id(current_user: User, db: AsyncSession) -> Optional[int]:
    if current_user.role == UserRole.superadmin:
        return None
    org = await get_user_org(current_user, db)
    if not org:
        return None
    return org.id


# ---------------------------------------------------------------------------
# GET /search
# ---------------------------------------------------------------------------

@router.get("/search", response_model=CandidateSearchResponse)
async def search_candidates(
    q: Optional[str] = None,
    status: Optional[str] = None,
    source: Optional[str] = None,
    recruiter_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    tags: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    sort_by: str = Query("created_at", regex="^(name|created_at|status)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user = await db.merge(current_user)
    org_id = await _get_org_id(current_user, db)
    if org_id is None and current_user.role != UserRole.superadmin:
        return CandidateSearchResponse(items=[], total=0, page=page, per_page=per_page, stats=StatsBlock())

    isolated_ids = await get_isolated_creator_ids(current_user, db) if current_user.role == UserRole.superadmin else []

    # Как и на доске: архив подмешиваем только когда реально ищут.
    scope_ids = await get_scope_vacancy_ids(current_user, db)
    base = _base_candidate_query(
        org_id, current_user, isolated_ids,
        include_archived=bool(q and q.strip()), scope_ids=scope_ids,
    )

    # --- filters ---
    if status:
        try:
            status_enum = EntityStatus(status)
            base = base.where(Entity.status == status_enum)
        except ValueError:
            pass

    if recruiter_id:
        base = base.where(Entity.created_by == recruiter_id)

    if date_from:
        base = base.where(Entity.created_at >= datetime.combine(date_from, datetime.min.time()))

    if date_to:
        base = base.where(Entity.created_at <= datetime.combine(date_to, datetime.max.time()))

    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        for tag in tag_list:
            base = base.where(Entity.tags.op("@>")(f'["{tag}"]'))

    if source:
        # source stored in extra_data -> source
        base = base.where(
            cast(Entity.extra_data["source"].astext, String).ilike(f"%{source}%")
        )

    # --- full-text search ---
    if q and q.strip():
        # Один помощник на все три окна поиска: условия + откат со строгого «@ник»,
        # если по нику ничего нет (см. apply_text_search). extra_data целиком (весь
        # JSON-блоб) в поиск НАМЕРЕННО не входит — самый шумный источник ложных
        # совпадений (матчит запрос где угодно внутри чужого extra_data).
        from ..services.search_index import apply_text_search
        base, _nick_fallback = await apply_text_search(db, base, q, include_tags=True)

    # --- stats (on the filtered base, before pagination) ---
    stats_base = base.with_only_columns(
        func.count().label("total"),
        func.count().filter(Entity.status == EntityStatus.new).label("cnt_new"),
        func.count().filter(Entity.status == EntityStatus.screening).label("cnt_screening"),
        func.count().filter(Entity.status == EntityStatus.practice).label("cnt_practice"),
        func.count().filter(Entity.status == EntityStatus.hired).label("cnt_hired"),
        func.count().filter(Entity.status == EntityStatus.rejected).label("cnt_rejected"),
    )
    stats_row = (await db.execute(stats_base)).one()
    total = stats_row.total

    stats = StatsBlock(
        total=total,
        new=stats_row.cnt_new,
        screening=stats_row.cnt_screening,
        practice=stats_row.cnt_practice,
        hired=stats_row.cnt_hired,
        rejected=stats_row.cnt_rejected,
    )

    # --- sorting ---
    sort_col = {
        "name": Entity.name,
        "created_at": Entity.created_at,
        "status": Entity.status,
    }[sort_by]

    # При поиске (q) — сначала по релевантности (лучшее совпадение первым),
    # затем по выбранной сортировке. Без q — как выбрано.
    from ..services.search_index import smart_name_score
    _score = smart_name_score(q) if (q and q.strip()) else None
    _primary = sort_col.desc() if sort_order == "desc" else sort_col.asc()
    if _score is not None:
        base = base.order_by(_score.desc(), _primary)
    else:
        base = base.order_by(_primary)

    # --- pagination ---
    offset = (page - 1) * per_page
    base = base.offset(offset).limit(per_page)

    result = await db.execute(base)
    entities = list(result.scalars().all())

    if not entities:
        return CandidateSearchResponse(items=[], total=total, page=page, per_page=per_page, stats=stats)

    entity_ids = [e.id for e in entities]
    creator_ids = list({e.created_by for e in entities if e.created_by})

    # --- fetch recruiter names ---
    recruiter_map: dict[int, str] = {}
    if creator_ids:
        users_result = await db.execute(
            select(User.id, User.name).where(User.id.in_(creator_ids))
        )
        recruiter_map = {row.id: row.name for row in users_result.all()}

    # --- vacancy counts ---
    vacancy_counts_result = await db.execute(
        select(
            VacancyApplication.entity_id,
            func.count(VacancyApplication.id).label("cnt"),
        )
        .where(VacancyApplication.entity_id.in_(entity_ids))
        .group_by(VacancyApplication.entity_id)
    )
    vacancy_count_map = {row.entity_id: row.cnt for row in vacancy_counts_result.all()}

    # --- duplicate detection (shared email or phone) ---
    duplicate_ids: set[int] = set()
    emails_list = [e.email for e in entities if e.email]
    phones_list = [e.phone for e in entities if e.phone]

    if emails_list:
        dup_email_result = await db.execute(
            select(Entity.email)
            .where(
                Entity.type == EntityType.candidate,
                Entity.email.in_(emails_list),
            )
            .group_by(Entity.email)
            .having(func.count(Entity.id) > 1)
        )
        dup_emails = {row.email for row in dup_email_result.all()}
        for e in entities:
            if e.email and e.email in dup_emails:
                duplicate_ids.add(e.id)

    if phones_list:
        dup_phone_result = await db.execute(
            select(Entity.phone)
            .where(
                Entity.type == EntityType.candidate,
                Entity.phone.in_(phones_list),
            )
            .group_by(Entity.phone)
            .having(func.count(Entity.id) > 1)
        )
        dup_phones = {row.phone for row in dup_phone_result.all()}
        for e in entities:
            if e.phone and e.phone in dup_phones:
                duplicate_ids.add(e.id)

    # --- build response items ---
    items: List[CandidateItem] = []
    for e in entities:
        tg_username = first_real_telegram(e.telegram_usernames)

        source_val = None
        if e.extra_data and isinstance(e.extra_data, dict):
            source_val = e.extra_data.get("source")

        items.append(CandidateItem(
            id=e.id,
            name=e.name,
            email=e.email or (e.emails[0] if e.emails else None),
            phone=e.phone or (e.phones[0] if e.phones else None),
            telegram_username=tg_username,
            status=e.status.value if hasattr(e.status, "value") else str(e.status),
            source=source_val,
            recruiter_id=e.created_by,
            recruiter_name=recruiter_map.get(e.created_by) if e.created_by else None,
            created_at=e.created_at,
            tags=e.tags or [],
            position=e.position,
            company=e.company,
            vacancy_count=vacancy_count_map.get(e.id, 0),
            is_duplicate=e.id in duplicate_ids,
            is_archived=bool(getattr(e, "is_archived", False)),
        ))

    return CandidateSearchResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        stats=stats,
    )


# ---------------------------------------------------------------------------
# POST /bulk-action
# ---------------------------------------------------------------------------

@router.post("/bulk-action")
async def bulk_action(
    body: BulkActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user = await db.merge(current_user)
    org_id = await _get_org_id(current_user, db)
    # org_id=None у не-суперадмина = юзер без OrgMember (напр. выбыл из орга, но с
    # валидным токеном). Ниже org-фильтр стоит `if org_id:` → без гарда bulk-action
    # (delete/export/status/tag) прошёлся бы по кандидатам ВСЕХ орг. Аудит 2026-08-07.
    if org_id is None and current_user.role != UserRole.superadmin:
        raise HTTPException(403, "No organization access")

    if not body.entity_ids:
        raise HTTPException(400, "entity_ids is required")

    # Fetch entities
    q = select(Entity).where(
        Entity.id.in_(body.entity_ids),
        Entity.type == EntityType.candidate,
    )
    if org_id:
        q = q.where(Entity.org_id == org_id)

    result = await db.execute(q)
    entities = list(result.scalars().all())

    if not entities:
        raise HTTPException(404, "No matching candidates found")

    # --- add_to_vacancy ---
    if body.action == "add_to_vacancy":
        if not body.vacancy_id:
            raise HTTPException(400, "vacancy_id is required for add_to_vacancy")

        # Вакансия строго в орг вызывающего (org_id=None только у суперадмина) —
        # иначе bulk-add закидывал кандидатов в чужую воронку по vacancy_id.
        vq = select(Vacancy).where(Vacancy.id == body.vacancy_id)
        if org_id:
            vq = vq.where(Vacancy.org_id == org_id)
        vacancy_result = await db.execute(vq)
        vacancy = vacancy_result.scalar_one_or_none()
        if not vacancy:
            raise HTTPException(404, "Vacancy not found")

        # Get already-linked entity ids
        existing_result = await db.execute(
            select(VacancyApplication.entity_id).where(
                VacancyApplication.vacancy_id == body.vacancy_id,
                VacancyApplication.entity_id.in_([e.id for e in entities]),
            )
        )
        existing_ids = {row[0] for row in existing_result.all()}

        from api.services.stage_transitions import record_transition
        added = 0
        created_apps = []
        for entity in entities:
            if entity.id not in existing_ids:
                app = VacancyApplication(
                    vacancy_id=body.vacancy_id,
                    entity_id=entity.id,
                    stage=ApplicationStage.applied,
                    source="bulk_crm",
                    created_by=current_user.id,  # кто массово добавил → авто-метка HR
                )
                db.add(app)
                created_apps.append((app, entity.id))
                added += 1

        await db.commit()
        # Начальный транзишн в историю для каждого добавленного отклика.
        for app, ent_id in created_apps:
            await db.refresh(app)
            await record_transition(
                db=db,
                application_id=app.id,
                entity_id=ent_id,
                from_stage=None,
                to_stage=app.stage.value if hasattr(app.stage, "value") else str(app.stage),
                changed_by_id=current_user.id,
                comment="Первичная заявка",
            )
        if created_apps:
            await db.commit()
        return {"success": True, "action": "add_to_vacancy", "affected": added, "skipped": len(existing_ids)}

    # --- change_status ---
    elif body.action == "change_status":
        if not body.status:
            raise HTTPException(400, "status is required for change_status")
        try:
            new_status = EntityStatus(body.status)
        except ValueError:
            raise HTTPException(400, f"Invalid status: {body.status}")

        for entity in entities:
            entity.status = new_status
        await db.commit()
        return {"success": True, "action": "change_status", "affected": len(entities)}

    # --- add_tag ---
    elif body.action == "add_tag":
        if not body.tag:
            raise HTTPException(400, "tag is required for add_tag")

        tag = body.tag.strip()
        updated = 0
        for entity in entities:
            current_tags = list(entity.tags or [])
            if tag not in current_tags:
                current_tags.append(tag)
                entity.tags = current_tags
                updated += 1
        await db.commit()
        return {"success": True, "action": "add_tag", "affected": updated}

    # --- delete ---
    elif body.action == "delete":
        count = len(entities)
        for entity in entities:
            await db.delete(entity)
        await db.commit()
        return {"success": True, "action": "delete", "affected": count}

    # --- export_csv ---
    elif body.action == "export_csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["ID", "Name", "Email", "Phone", "Status", "Position", "Company", "Tags", "Created At"])
        for entity in entities:
            writer.writerow([
                entity.id,
                entity.name,
                entity.email or "",
                entity.phone or "",
                entity.status.value if hasattr(entity.status, "value") else str(entity.status),
                entity.position or "",
                entity.company or "",
                ", ".join(entity.tags or []),
                entity.created_at.isoformat() if entity.created_at else "",
            ])
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=candidates_export.csv"},
        )

    else:
        raise HTTPException(400, f"Unknown action: {body.action}")


# ---------------------------------------------------------------------------
# PATCH /{entity_id}/status  — смена этапа из карточки «Все кандидаты»
# ---------------------------------------------------------------------------

class ChangeStatusRequest(BaseModel):
    status: str
    # Комментарий к переводу и подпись этапа (как её видит рекрутёр — колонки
    # доски бывают переименованы): у кандидата вне воронок перевод живёт
    # записью в ленте, и пишется она здесь же, в одной транзакции с переводом.
    comment: Optional[str] = None
    stage_label: Optional[str] = None


@router.patch("/{entity_id}/status")
async def change_candidate_status(
    entity_id: int,
    body: ChangeStatusRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Перевести кандидата на этап из карточки «Все кандидаты».

    Кандидат в воронке переводится в ней (move_application) — и только если
    открытая воронка ОДНА. Раньше эндпоинт выравнивал под новый этап ВСЕ заявки
    кандидата: смена в одной воронке меняла его во всех (17.09.2026). Карточка
    сама шлёт перевод в нужную воронку через PUT заявки, сюда приходит
    кандидат вне воронок — для него перевод записывается в ленту.
    """
    from api.services.stage_change import (
        change_status_without_application,
        log_moves,
        log_out_of_funnel,
        move_application,
        settle_entities,
    )

    current_user = await db.merge(current_user)

    try:
        new_status = EntityStatus(body.status)
    except ValueError:
        raise HTTPException(400, f"Invalid status: {body.status}")

    # Org-изоляция: смена статуса только для своего org — иначе любой HR мог
    # менять этап чужого кандидата по id.
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")
    # FOR UPDATE: сериализует конкурентную смену одного кандидата (двойной клик
    # писал дубль-переход, 2026-07-14) и защищает ленту в extra_data от lost
    # update с соседним писателем заметок.
    entity = (await db.execute(
        select(Entity).where(
            Entity.id == entity_id,
            Entity.type == EntityType.candidate,
            Entity.org_id == org.id,
        ).with_for_update()
    )).scalar_one_or_none()
    if not entity:
        raise HTTPException(404, "Candidate not found")
    old_status = entity.status

    # order_by(id): единый порядок взятия row-locks со всеми прочими FOR UPDATE
    # по vacancy_applications — иначе deadlock с реордером колонки (2026-08-27).
    open_apps = (await db.execute(
        select(VacancyApplication)
        .join(Vacancy, VacancyApplication.vacancy_id == Vacancy.id)
        .where(
            VacancyApplication.entity_id == entity_id,
            Vacancy.status != VacancyStatus.closed,
            Vacancy.deleted_at.is_(None),
        )
        .order_by(VacancyApplication.id)
        .with_for_update(of=VacancyApplication)
    )).scalars().all()

    move = None
    note = None
    if open_apps:
        target_stage = STATUS_SYNC_MAP.get(new_status)
        if target_stage is None:
            raise HTTPException(409, "Этот этап нельзя поставить заявке — кандидат остался на прежнем")
        if len(open_apps) > 1:
            raise HTTPException(
                409,
                "Кандидат в нескольких воронках — смените этап в карточке нужной воронки",
            )
        move = await move_application(
            db, open_apps[0], target_stage,
            changed_by=current_user, comment=(body.comment or "").strip() or None,
        )
        await settle_entities(db, [entity_id], [move])
    else:
        try:
            note = await change_status_without_application(
                db, entity, new_status,
                changed_by=current_user,
                comment=body.comment,
                stage_label=body.stage_label,
            )
        except ValueError:
            raise HTTPException(400, "Comment too long")

    await db.commit()
    await db.refresh(entity)
    log_moves([move], current_user, via="candidate_status")
    log_out_of_funnel(current_user, entity_id, note)

    return {
        "success": True,
        "entity_id": entity_id,
        "old_status": old_status.value if hasattr(old_status, "value") else str(old_status),
        # Итоговый статус считает сервер (у кандидата в воронке — по актуальной
        # заявке), фронт ставит карточку в колонку по нему.
        "new_status": entity.status.value if entity.status else new_status.value,
        "entity_status": entity.status.value if entity.status else None,
        "application_id": move.application_id if move else None,
        "note": note,
    }


@router.get("/{entity_id}/stage-history")
async def get_candidate_stage_history(
    entity_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Сквозная история смены этапов кандидата по ВСЕМ его откликам.

    Используется глобальной карточкой в «Все кандидаты», чтобы показывать
    тот же лог переходов, что и карточка в воронке (единая история).
    """
    current_user = await db.merge(current_user)
    org_id = await _get_org_id(current_user, db)

    entity_result = await db.execute(
        select(Entity).where(Entity.id == entity_id, Entity.type == EntityType.candidate)
    )
    entity = entity_result.scalar_one_or_none()
    if not entity:
        raise HTTPException(404, "Candidate not found")
    # Не-суперадмин: только своя орг. При org_id=None (юзер без OrgMember) прежнее
    # `if org_id and ...` схлопывалось в false и отдавало историю ЧУЖОГО кандидата.
    if current_user.role != UserRole.superadmin and (org_id is None or entity.org_id != org_id):
        raise HTTPException(404, "Candidate not found")
    # Скоуп по воронкам: сквозная история — это этапы, даты, рекрутёры и
    # комментарии. Кандидата вне своих воронок человек не читает и здесь.
    _scope_ids = await get_scope_vacancy_ids(current_user, db)
    if _scope_ids is not None:
        from ..services.vacancy_scope import entity_in_scope
        if not await entity_in_scope(entity_id, _scope_ids, db):
            raise HTTPException(404, "Candidate not found")

    rows = (await db.execute(
        select(StageTransition, Vacancy.title)
        .join(VacancyApplication, StageTransition.application_id == VacancyApplication.id)
        .join(Vacancy, Vacancy.id == VacancyApplication.vacancy_id)
        .where(StageTransition.entity_id == entity_id)
        .order_by(StageTransition.created_at.desc())
    )).all()

    user_ids = [t.changed_by for t, _ in rows if t.changed_by]
    names = {}
    if user_ids:
        names = {
            r[0]: r[1]
            for r in (await db.execute(
                select(User.id, User.name).where(User.id.in_(user_ids))
            )).all()
        }

    return [
        {
            "id": t.id,
            "application_id": t.application_id,
            "vacancy_title": vac_title,
            "from_stage": t.from_stage,
            "to_stage": t.to_stage,
            "changed_by": t.changed_by,
            "changed_by_name": names.get(t.changed_by),
            "comment": t.comment,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t, vac_title in rows
    ]


# ---------------------------------------------------------------------------
# GET /recruiters  — list of users who created candidates (for filter dropdown)
# ---------------------------------------------------------------------------

@router.get("/recruiters", response_model=List[RecruiterItem])
async def list_recruiters(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user = await db.merge(current_user)
    org_id = await _get_org_id(current_user, db)
    if org_id is None and current_user.role != UserRole.superadmin:
        return []  # юзер без орга — не отдаём агрегаты по всем оргам (аудит 2026-08-07)

    q = (
        select(User.id, User.name)
        .join(Entity, Entity.created_by == User.id)
        .where(Entity.type == EntityType.candidate)
        .distinct()
    )
    if org_id:
        q = q.where(Entity.org_id == org_id)

    result = await db.execute(q)
    return [RecruiterItem(id=row.id, name=row.name) for row in result.all()]


# ---------------------------------------------------------------------------
# GET /tags  — list of all existing tags across candidates
# ---------------------------------------------------------------------------

@router.get("/tags")
async def list_tags(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user = await db.merge(current_user)
    org_id = await _get_org_id(current_user, db)
    if org_id is None and current_user.role != UserRole.superadmin:
        return []  # юзер без орга — не отдаём теги по всем оргам (аудит 2026-08-07)

    q = select(Entity.tags).where(
        Entity.type == EntityType.candidate,
        Entity.tags.isnot(None),
    )
    if org_id:
        q = q.where(Entity.org_id == org_id)

    result = await db.execute(q)
    all_tags: set[str] = set()
    for row in result.all():
        if row.tags and isinstance(row.tags, list):
            all_tags.update(row.tags)

    return sorted(all_tags)


# ---------------------------------------------------------------------------
# GET /kanban  — candidates grouped by status for kanban board
# ---------------------------------------------------------------------------

# Колонки доски, их порядок и подписи — общий справочник (services/hr_stages.py).
KANBAN_STATUSES = BOARD_STATUSES

# Колонка-приёмник для статусов вне воронки (dismissed/quit/interview/active и
# прочее легаси). Раньше такие кандидаты просто ВЫПАДАЛИ с доски: карточка в базе
# есть, по id открывается, а в «Все кандидаты» её нет и поиск её не находит
# (Эльвира, 18.09.2026). «Все кандидаты» обязаны показывать всех.
BOARD_COLUMNS = KANBAN_STATUSES + [OTHER_STATUS]

KANBAN_STATUS_LABELS = STATUS_LABELS


class CandidateFunnelInfo(BaseModel):
    """Одна воронка кандидата для списка: название вакансии + его этап в ней."""
    vacancy_title: str
    stage: str


class KanbanCard(BaseModel):
    id: int
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    telegram_username: Optional[str] = None
    position: Optional[str] = None
    source: Optional[str] = None
    source_url: Optional[str] = None
    # Кто добавил (Entity.created_by). Фильтр «Только мои» на фронте сравнивает
    # ЭТО поле, а не имя: у двух рекрутёров может совпасть имя.
    recruiter_id: Optional[int] = None
    recruiter_name: Optional[str] = None
    created_at: datetime
    # Когда кандидата перевели на ТЕКУЩИЙ статус. Строка списка показывает
    # именно её рядом с этапом, и по ней же список отсортирован (просьба Марии
    # 20.10.2026). None — перевода в истории нет (статус выставлен правкой
    # карточки), тогда строка показывает дату добавления, как раньше.
    status_changed_at: Optional[datetime] = None
    # Место в общем порядке доски (0 — первый): дата этапа, при поиске — совпадение.
    rank: Optional[int] = None
    tags: list = []
    photo_url: Optional[str] = None
    company: Optional[str] = None
    city: Optional[str] = None
    age: Optional[str] = None
    salary: Optional[str] = None
    total_experience: Optional[str] = None
    vacancy_name: Optional[str] = None
    # Воронка, по которой сейчас показан статус кандидата (самая свежая среди
    # живых), и сколько у него воронок всего — список рисует подпись «этап ·
    # воронка (+N)», чтобы было видно, где человек сейчас.
    status_vacancy_name: Optional[str] = None
    funnel_count: int = 0
    # Этапы по ВСЕМ живым воронкам кандидата — список рисует «Выполняет ТЗ ·
    # Трафик, Отказ · UAM», чтобы не открывать карточку. Живые впереди.
    funnels: List[CandidateFunnelInfo] = []
    rejection_reason: Optional[str] = None
    # Карточка из теневой базы: попадает в выдачу ТОЛЬКО при поиске, помечается
    # на фронте плашкой «Архив», чтобы не путать с активными.
    is_archived: bool = False
    extra_data: Optional[dict] = None
    # Версия карточки для оптимистичной блокировки при правке (PUT /entities
    # сверяет её и отдаёт 409). Без неё форма правки не могла ничего прислать,
    # и параллельные правки двух рекрутёров тихо затирали друг друга.
    version: int = 1
    # Теги у ФИО (свой справочник entity_name_tags_catalog, отдельно от меток).
    # Отдаём прямо в карточке — список слева рисует их на каждой строке, и
    # дозагружать по одному было бы N+1.
    headline_tags: list[dict] = []
    # «Был отказ»: последний отказ ЭТОГО ЧЕЛОВЕКА в другой его карточке или в
    # архиве ClickUp (+ count) — services/prior_rejection.py. Строка списка
    # рисует метку «Был отказ · 28 авг · Трафик» (владелец, 22.10.2026).
    prior_rejection: Optional[dict] = None

    class Config:
        from_attributes = True


class KanbanColumn(BaseModel):
    status: str
    label: str
    color: Optional[str] = None  # из org stage_config (если задан)
    cards: List[KanbanCard]
    count: int


class KanbanBoardResponse(BaseModel):
    columns: List[KanbanColumn]
    total: int
    # true — искали «@ник», по нему НИЧЕГО не нашлось, и список показывает
    # совпадения обычного поиска (имя/контакты). Окно подписывает это строкой,
    # иначе рекрутёр думает, что нашёлся «не тот» человек.
    nick_fallback: bool = False


@router.get("/kanban", response_model=KanbanBoardResponse)
async def get_candidates_kanban(
    q: Optional[str] = None,
    recruiter_id: Optional[int] = None,
    # 2000: «Все кандидаты» без поиска должны показывать ВСЕХ на каждом этапе
    # (при 500 «Новый» с 468 вот-вот начал бы молча терять хвост). Выборка из БД
    # и счётчики от лимита не зависят — он режет только сборку карточек.
    per_column: int = Query(50, ge=1, le=2000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get candidates grouped by EntityStatus for kanban board view."""
    current_user = await db.merge(current_user)
    org_id = await _get_org_id(current_user, db)
    isolated_ids = await get_isolated_creator_ids(current_user, db) if org_id else []

    # При ПОИСКЕ подмешиваем теневую базу: человека, который уже проходил у нас,
    # надо находить прямо здесь, а не в отдельном разделе. Без запроса архив
    # скрыт — иначе доска утонет в тысячах импортных карточек.
    scope_ids = await get_scope_vacancy_ids(current_user, db)
    base_q = _base_candidate_query(
        org_id, current_user, isolated_ids,
        include_archived=bool(q and q.strip()), scope_ids=scope_ids,
    )

    # Recruiter filter — ДО поиска: откат со строгого «@ник» смотрит, есть ли
    # совпадения в ЭТОЙ выборке, и чужие карточки учитывать нельзя.
    if recruiter_id:
        base_q = base_q.where(Entity.created_by == recruiter_id)

    # Optional text search
    nick_fallback = False
    if q and q.strip():
        from ..services.search_index import apply_text_search
        base_q, nick_fallback = await apply_text_search(db, base_q, q)

    # Фильтра по статусу НЕТ: кандидат с нестандартным статусом попадает в колонку
    # «Вне воронки», а не исчезает из «Все кандидаты» вместе с поиском.

    # Порядок: при поиске — по релевантности (лучшее совпадение первым, ранг —
    # сумма пословных word_similarity), иначе новизна.
    from ..services.search_index import smart_name_score
    _score = smart_name_score(q) if (q and q.strip()) else None
    if _score is not None:
        base_q = base_q.order_by(_score.desc(), Entity.created_at.desc())
    else:
        base_q = base_q.order_by(Entity.created_at.desc())

    result = await db.execute(base_q)
    entities = list(result.scalars().all())

    # Дата перевода на текущий статус — только ПОДПИСЬ в строке. Порядок списка
    # — по дате ДОБАВЛЕНИЯ, свежие сверху (владелец, 21.10.2026: «не по дате
    # изменения, а по дате добавления, сначала новые»; с 20.10 по 21.10 список
    # стоял по дате перевода). При поиске — по релевантности (см. order_by выше).
    from ..services.status_dates import status_changed_at_map
    status_at = await status_changed_at_map(db, entities)

    # Место в общем порядке — фронт по нему собирает вкладку «Все» и выдачу
    # поиска из разных колонок (порядок колонок сам по себе не общий).
    rank_of = {e.id: i for i, e in enumerate(entities)}

    # Группируем по статусу и берём только per_column на колонку ДО дорогой работы
    # (построение карточек + два IN-подзапроса фото/вакансий). Раньше всё это
    # гонялось по ВСЕМ кандидатам, а хвост выкидывался — не держало «тысячи».
    # counts считаем по полному набору, поэтому числа в колонках точные.
    by_status: dict[str, list] = {s: [] for s in BOARD_COLUMNS}
    counts: dict[str, int] = {s: 0 for s in BOARD_COLUMNS}
    for e in entities:
        # Вкладка по статусу: уволен/уволился — в «Отказе», прочее без колонки —
        # «Вне воронки», но кандидат ВИДЕН (hr_stages.board_column).
        status_val = board_column(e.status.value if hasattr(e.status, "value") else str(e.status))
        counts[status_val] += 1
        if len(by_status[status_val]) < per_column:
            by_status[status_val].append(e)
    # Плоский список ТОЛЬКО отображаемых кандидатов (≤ per_column × колонок)
    display_entities = [e for s in BOARD_COLUMNS for e in by_status[s]]

    # Get recruiter names
    creator_ids = {e.created_by for e in display_entities if e.created_by}
    recruiter_map = {}
    if creator_ids:
        r = await db.execute(
            select(User.id, User.name).where(User.id.in_(creator_ids))
        )
        recruiter_map = {row.id: row.name for row in r.all()}

    # Get vacancy names and rejection reasons for entities (только отображаемые)
    entity_ids = [e.id for e in display_entities]
    vacancy_map: dict = {}
    status_vacancy_map: dict = {}
    funnel_count_map: dict = {}
    funnels_map: dict = {}
    rejection_map: dict = {}

    # Bulk fetch photo files (EntityFile rows with image mime types) as a
    # fallback when extra_data.photo_url is missing. Keyed by entity_id →
    # download URL string the frontend can render directly in <img>.
    photo_file_map: dict = {}
    if entity_ids:
        try:
            from ..models.database import EntityFile, EntityFileType
            f_result = await db.execute(
                select(EntityFile.entity_id, EntityFile.id, EntityFile.file_name)
                .where(
                    EntityFile.entity_id.in_(entity_ids),
                    EntityFile.mime_type.startswith("image/"),
                    # Резюме-страницы (PDF→JPEG) хранятся как file_type=resume —
                    # это НЕ аватар, иначе скан резюме становится «фото» кандидата.
                    # Берём только настоящие фото (HH-фото = file_type other и пр.).
                    EntityFile.file_type != EntityFileType.resume,
                    # Файлы, загруженные кандидатом через АНКЕТУ, — не аватар.
                    or_(
                        EntityFile.description.is_(None),
                        ~EntityFile.description.like("Загружено через форму%"),
                    ),
                )
                .order_by(EntityFile.id.desc())
            )
            for row in f_result.all():
                # first (most recent) photo wins per entity
                if row.entity_id not in photo_file_map:
                    # Skip resume-page JPEGs (AI-generated profile pages) —
                    # those are multi-page PDF renders, not a real avatar.
                    fname = (row.file_name or "").lower()
                    # Аватар — ТОЛЬКО авто-фото: и резюме-портрет (Фото_из_резюме),
                    # и парсер-фото (Фото_<имя>) сохраняются с именем на «Фото_».
                    # Произвольные картинки, загруженные вручную через «Файл», в
                    # аватар НЕ идут (у них оригинальное имя файла).
                    if not fname.startswith("фото"):
                        continue
                    photo_file_map[row.entity_id] = (
                        f"/api/entities/{row.entity_id}/files/{row.id}/download"
                    )
        except Exception as exc:
            logger.warning(f"Photo file fallback query failed (non-critical): {exc}")

    if entity_ids:
        try:
            va_result = await db.execute(
                select(
                    VacancyApplication.entity_id,
                    VacancyApplication.id,
                    VacancyApplication.stage,
                    VacancyApplication.last_stage_change_at,
                    VacancyApplication.applied_at,
                    Vacancy.title,
                    Vacancy.status,
                    VacancyApplication.rejection_reason,
                ).select_from(VacancyApplication)
                .join(Vacancy, Vacancy.id == VacancyApplication.vacancy_id)
                .where(
                    VacancyApplication.entity_id.in_(entity_ids),
                    # Скоуп по воронкам: чипы этапов и подпись воронки в строке
                    # списка считаются ТОЛЬКО по разрешённым воронкам — иначе у
                    # кандидата из двух воронок светилось название чужой.
                    *([VacancyApplication.vacancy_id.in_(list(scope_ids))] if scope_ids else []),
                )
            )
            from .vacancies.common import INACTIVE_STAGES as _INACTIVE
            _by_entity: dict = {}
            for row in va_result.all():
                if row.entity_id not in vacancy_map:
                    vacancy_map[row.entity_id] = row.title
                if row.rejection_reason and row.entity_id not in rejection_map:
                    rejection_map[row.entity_id] = row.rejection_reason
                if row.status != VacancyStatus.closed:
                    _by_entity.setdefault(row.entity_id, []).append(row)
            # Подпись воронки в списке: та же «актуальная» заявка, по которой
            # считается общий статус кандидата (самая свежая среди живых; отказ
            # и резерв — только если живых воронок нет).
            for eid, rows in _by_entity.items():
                funnel_count_map[eid] = len(rows)
                live = [r for r in rows if r.stage not in _INACTIVE]
                pool = live or rows
                def _when(r):
                    return (
                        (r.last_stage_change_at or r.applied_at) is not None,
                        r.last_stage_change_at or r.applied_at,
                        r.id,
                    )

                best = max(pool, key=_when)
                status_vacancy_map[eid] = best.title
                # Живые воронки впереди, внутри — свежие выше.
                ordered = sorted(live, key=_when, reverse=True) + sorted(
                    [r for r in rows if r.stage in _INACTIVE], key=_when, reverse=True
                )
                funnels_map[eid] = [
                    CandidateFunnelInfo(
                        vacancy_title=r.title,
                        stage=r.stage.value if hasattr(r.stage, "value") else str(r.stage),
                    )
                    for r in ordered
                ]
        except Exception as exc:
            logger.warning(f"Vacancy map query failed (non-critical): {exc}")

    # Ярлыки у имени — одним запросом на всю выдачу.
    headline_map: dict[int, list[dict]] = {}
    try:
        # С 21.09.2026 теги у ФИО — свой справочник, отдельный от меток.
        from ..models.database import NameTag, entity_name_tag_association
        ids = [e.id for e in display_entities]
        if ids:
            rows = await db.execute(
                select(
                    entity_name_tag_association.c.entity_id,
                    NameTag.name,
                    NameTag.color,
                )
                .join(NameTag, NameTag.id == entity_name_tag_association.c.tag_id)
                .where(entity_name_tag_association.c.entity_id.in_(ids))
                .order_by(NameTag.name)
            )
            for ent_id, name, color in rows.all():
                headline_map.setdefault(ent_id, []).append({"name": name, "color": color})
    except Exception as exc:
        logger.warning(f"Headline tags query failed (non-critical): {exc}")

    # «Был отказ» — только у тех, кто сейчас не во вкладке «Отказ»: там метка
    # ничего не добавляет. Связи — пометки дублей (по ним уже сверено, что это
    # тот же человек); свои воронки не берём — их этапы видны чипами в строке.
    prior_map: dict[int, dict] = {}
    try:
        from ..services.prior_rejection import prior_rejections, summary
        live_entities = [
            e for e in display_entities
            if board_column(e.status.value if hasattr(e.status, "value") else str(e.status)) != "rejected"
        ]
        for eid, items in (await prior_rejections(db, live_entities, scope_ids=scope_ids)).items():
            prior_map[eid] = summary(items)
    except Exception as exc:
        logger.warning(f"Prior rejection query failed (non-critical): {exc}")

    # Group by status (display_entities уже обрезаны до per_column на колонку)
    grouped: dict[str, list] = {s: [] for s in BOARD_COLUMNS}
    for e in display_entities:
        try:
            status_val = board_column(e.status.value if hasattr(e.status, "value") else str(e.status))
            tg = first_real_telegram(e.telegram_usernames)
            source_val = None
            ed = e.extra_data if isinstance(e.extra_data, dict) else {}
            source_url_val = None
            if ed:
                source_val = ed.get("source")
                source_url_val = ed.get("source_url")

            grouped[status_val].append(KanbanCard(
                id=e.id,
                name=e.name,
                email=e.email,
                phone=e.phone,
                telegram_username=tg,
                position=e.position,
                source=source_val,
                source_url=source_url_val,
                recruiter_id=e.created_by,
                recruiter_name=recruiter_map.get(e.created_by),
                created_at=e.created_at,
                status_changed_at=status_at.get(e.id),
                rank=rank_of.get(e.id),
                tags=e.tags or [],
                # Локальный URL предпочтительнее внешнего: hh.ru CDN может
                # отдавать 403 на чужой Referer / истечь срок ссылки. Локальный
                # /api/entities/.../files/.../download грузится по куке.
                photo_url=photo_file_map.get(e.id) or (ed.get("photo_url") if ed else None),
                company=getattr(e, 'company', None),
                # Импорт (ClickUp/CSV) кладёт location/birth_date, а карточка
                # показывает city/age — маппим с фолбэком, иначе шапка пустая.
                city=_as_str(ed.get("city")) or _as_str(ed.get("location")),
                age=_as_str(ed.get("age")) or _age_from_birthdate(ed.get("birth_date")),
                salary=_as_str(ed.get("salary")),
                total_experience=_as_str(ed.get("total_experience")),
                vacancy_name=vacancy_map.get(e.id),
                status_vacancy_name=status_vacancy_map.get(e.id),
                funnel_count=funnel_count_map.get(e.id, 0),
                funnels=funnels_map.get(e.id, []),
                rejection_reason=rejection_map.get(e.id),
                is_archived=bool(getattr(e, "is_archived", False)),
                extra_data=filter_extra_for_scope(ed, scope_ids) if ed else None,
                version=getattr(e, "version", None) or 1,
                headline_tags=headline_map.get(e.id, []),
                prior_rejection=prior_map.get(e.id),
            ))
        except Exception as exc:
            logger.warning(f"Skipping entity {e.id} in kanban: {exc}")

    # Org-level кастомизация лейблов/цветов этапов (если админ настроил
    # через UI в /all-candidates → ⚙️). Если не настроена — дефолты.
    stage_overrides: dict[str, dict] = {}
    if org_id:
        from ..models.database import Organization
        org_res = await db.execute(select(Organization).where(Organization.id == org_id))
        org_row = org_res.scalar_one_or_none()
        cfg = (org_row.settings or {}).get("stage_config") if org_row else None
        if isinstance(cfg, list):
            for s in cfg:
                if isinstance(s, dict) and s.get("key"):
                    stage_overrides[s["key"]] = s

    columns = []
    total = 0
    for s in BOARD_COLUMNS:
        all_cards = grouped.get(s, [])
        # count — ПОЛНОЕ число в колонке (по всему набору), cards — обрезанные.
        col_count = counts.get(s, len(all_cards))
        total += col_count
        override = stage_overrides.get(s) or {}
        columns.append(KanbanColumn(
            status=s,
            label=override.get("label") or KANBAN_STATUS_LABELS.get(s, s),
            color=override.get("color"),
            cards=all_cards[:per_column],
            count=col_count,
        ))

    return KanbanBoardResponse(columns=columns, total=total, nick_fallback=nick_fallback)


@router.get("/ids")
async def get_candidate_ids(
    q: Optional[str] = None,
    recruiter_id: Optional[int] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Полный список entity_id кандидатов по текущему фильтру доски — для «Выбрать всех».

    Доска грузит только per_column карточек на колонку, поэтому select-all на фронте
    видел лишь загруженных (бейдж «Все 115», а выбиралось 75). Этот лёгкий запрос
    отдаёт ВСЕ id того же набора (org/статусы/поиск/рекрутёр), с разумным потолком.
    """
    current_user = await db.merge(current_user)
    org_id = await _get_org_id(current_user, db)
    isolated_ids = await get_isolated_creator_ids(current_user, db) if org_id else []

    # Набор ДОЛЖЕН совпадать с доской (иначе «Выбрать всех» выделит не то):
    # там при поиске архив подмешивается — значит и здесь.
    scope_ids = await get_scope_vacancy_ids(current_user, db)
    base_q = _base_candidate_query(
        org_id, current_user, isolated_ids,
        include_archived=bool(q and q.strip()), scope_ids=scope_ids,
    )

    if recruiter_id:
        base_q = base_q.where(Entity.created_by == recruiter_id)
    if q and q.strip():
        # «Выбрать всех» обязан отбирать ТЕХ ЖЕ людей, что показал список, —
        # поэтому и условия, и откат с ника здесь те же (apply_text_search).
        from ..services.search_index import apply_text_search
        base_q, _ = await apply_text_search(db, base_q, q)

    # Вкладка — те же статусы, что показывает доска (hr_stages.statuses_in_column):
    # «Отказ» вместе с уволенными, «Все» — без фильтра, как и список. Раньше «Все»
    # брало только статусы колонок и теряло тех, кто во «Вне воронки».
    column_statuses = statuses_in_column(status or "all")
    if column_statuses is not None:
        base_q = base_q.where(Entity.status.in_([EntityStatus(s) for s in column_statuses]))

    id_q = base_q.with_only_columns(Entity.id).order_by(Entity.created_at.desc()).limit(5000)
    result = await db.execute(id_q)
    return {"ids": [row[0] for row in result.all()]}
