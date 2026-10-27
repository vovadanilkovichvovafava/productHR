"""
Похожие кандидаты и дубли: поиск, сравнение, слияние и его отмена, «Разные
люди» (вынесено из search.py, 20.10.2026).
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel

from .common import (
    logger, get_db, Entity, EntityType, EntityStatus, Chat, CallRecording, User,
    UserRole, OrgRole, get_current_user, get_user_org, get_user_org_role,
    check_entity_access,
)

from ...services.entity_card import entity_broadcast_payload

router = APIRouter()


# === Similar Candidates & Duplicates ===

class SimilarCandidateResponse(BaseModel):
    """Response with similar candidate info."""
    entity_id: int
    entity_name: str
    similarity_score: int  # 0-100
    common_skills: List[str] = []
    similar_experience: bool = False
    similar_salary: bool = False
    similar_location: bool = False
    match_reasons: List[str] = []
    # Detailed comparison data for both candidates
    entity1_skills: List[str] = []
    entity2_skills: List[str] = []
    entity1_experience: Optional[int] = None
    entity2_experience: Optional[int] = None
    entity1_salary_min: Optional[int] = None
    entity1_salary_max: Optional[int] = None
    entity2_salary_min: Optional[int] = None
    entity2_salary_max: Optional[int] = None
    entity1_location: Optional[str] = None
    entity2_location: Optional[str] = None
    entity1_position: Optional[str] = None
    entity2_position: Optional[str] = None

    class Config:
        from_attributes = True


class DuplicateCandidateResponse(BaseModel):
    """Response with potential duplicate info."""
    entity_id: int
    entity_name: str
    confidence: int  # 0-100 — единая шкала с баннером «Похожий кандидат»
    match_reasons: List[str] = []
    matched_fields: dict = {}  # {field: [value1, value2]}
    strength: str = ""         # тир: source|email|telegram|name|phone|soft|text
    level: str = "possible"    # exact — совпало ≥2 признака (красный), possible — жёлтый
    signals: List[dict] = []   # все сработавшие сигналы — подсветка полей в окне

    class Config:
        from_attributes = True


class MergeEntitiesRequest(BaseModel):
    """Request for merging entities."""
    source_entity_id: int  # Will be deleted
    keep_source_data: bool = False  # Priority for source data


class MergeEntitiesResponse(BaseModel):
    """Response after merging entities."""
    success: bool
    message: str
    merged_entity_id: int
    deleted_entity_id: int


@router.get("/{entity_id}/similar", response_model=List[SimilarCandidateResponse])
async def get_similar_candidates(
    entity_id: int,
    limit: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get list of similar candidates.
    """
    from ...services.similarity import similarity_service

    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    # Get entity
    result = await db.execute(
        select(Entity).where(Entity.id == entity_id, Entity.org_id == org.id)
    )
    entity = result.scalar_one_or_none()

    if not entity:
        raise HTTPException(404, "Entity not found")

    # Check user has access to this entity
    has_access = await check_entity_access(entity, current_user, org.id, db, required_level=None)
    if not has_access:
        raise HTTPException(403, "No access to this entity")

    if entity.type != EntityType.candidate:
        raise HTTPException(400, "Similar search is only available for candidates")

    # Find similar (filtered by user's access rights for security)
    similar = await similarity_service.find_similar(
        db=db,
        entity=entity,
        limit=limit,
        org_id=org.id,
        user=current_user
    )

    return [
        SimilarCandidateResponse(
            entity_id=s.entity_id,
            entity_name=s.entity_name,
            similarity_score=s.similarity_score,
            common_skills=s.common_skills,
            similar_experience=s.similar_experience,
            similar_salary=s.similar_salary,
            similar_location=s.similar_location,
            match_reasons=s.match_reasons
        )
        for s in similar
    ]


@router.get("/{entity_id}/duplicates", response_model=List[DuplicateCandidateResponse])
async def get_duplicate_candidates(
    entity_id: int,
    include_archived: bool = Query(False, description="Include archived entities in duplicate detection"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get list of potential duplicates.
    """
    from ...services.similarity import similarity_service

    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    # Get entity
    result = await db.execute(
        select(Entity).where(Entity.id == entity_id, Entity.org_id == org.id)
    )
    entity = result.scalar_one_or_none()

    if not entity:
        raise HTTPException(404, "Entity not found")

    # Check user has access to this entity
    has_access = await check_entity_access(entity, current_user, org.id, db, required_level=None)
    if not has_access:
        raise HTTPException(403, "No access to this entity")

    # Единое ядро: те же правила и тот же confidence, что у баннера «Похожий
    # кандидат». include_text подмешивает пары, связанные только текстом резюме —
    # они показываются в карусели как подсказка, но слияние по ним не предлагается.
    duplicates = await similarity_service.detect_duplicates(
        db=db,
        entity=entity,
        org_id=org.id,
        user=current_user,
        include_archived=include_archived,
        include_text=True,
    )

    return [
        DuplicateCandidateResponse(
            entity_id=d.entity_id,
            entity_name=d.entity_name,
            confidence=d.confidence,
            match_reasons=d.match_reasons,
            matched_fields={k: list(v) for k, v in d.matched_fields.items()},
            strength=d.strength,
            level=d.level,
            signals=[s.to_dict() for s in d.signals],
        )
        for d in duplicates
    ]


@router.post("/{entity_id}/merge", response_model=MergeEntitiesResponse)
async def merge_entities(
    entity_id: int,
    request: MergeEntitiesRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Merge two duplicates.
    """
    from ...services.similarity import similarity_service, MergeIdentityConflict
    from .common import broadcast_entity_updated, broadcast_entity_deleted

    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    # Check permissions (only admin/owner can merge)
    org_role = await get_user_org_role(current_user, org.id, db)
    if org_role not in [OrgRole.admin, OrgRole.owner]:
        raise HTTPException(403, "Only administrators can merge duplicates")

    if entity_id == request.source_entity_id:
        raise HTTPException(400, "Cannot merge entity with itself")

    # Get target entity
    target_result = await db.execute(
        select(Entity).where(Entity.id == entity_id, Entity.org_id == org.id)
    )
    target_entity = target_result.scalar_one_or_none()

    if not target_entity:
        raise HTTPException(404, "Target entity not found")

    # Get source entity
    source_result = await db.execute(
        select(Entity).where(Entity.id == request.source_entity_id, Entity.org_id == org.id)
    )
    source_entity = source_result.scalar_one_or_none()

    if not source_entity:
        raise HTTPException(404, "Source entity not found")

    # Merge
    try:
        merged = await similarity_service.merge_entities(
            db=db,
            source_entity=source_entity,
            target_entity=target_entity,
            keep_source_data=request.keep_source_data
        )

        # Broadcast updates
        await broadcast_entity_updated(org.id, entity_broadcast_payload(merged))
        await broadcast_entity_deleted(org.id, request.source_entity_id)

        return MergeEntitiesResponse(
            success=True,
            message=f"Entities merged successfully. {source_entity.name} was deleted.",
            merged_entity_id=merged.id,
            deleted_entity_id=request.source_entity_id
        )
    except MergeIdentityConflict as e:
        raise HTTPException(
            409,
            f"Похоже, это РАЗНЫЕ люди: {e.reason}. Слияние отменено — проверьте телефон/дату рождения.",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error merging entities: {e}")
        raise HTTPException(500, f"Error merging: {str(e)}")


# === Теневая дедупликация: действия по баннеру «Похожий кандидат есть в базе» ===

class ShadowDuplicateActionRequest(BaseModel):
    duplicate_id: int  # id архивного (теневого) кандидата-совпадения


@router.post("/{entity_id}/merge-shadow")
async def merge_shadow_duplicate(
    entity_id: int,
    request: ShadowDuplicateActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """«Объединить»: слить активного кандидата с его теневым (архивным) дубликатом.

    Survivor = активный кандидат (entity_id); архивный (duplicate_id) удаляется,
    вся его история переносится на активного (единый таймлайн). Флаг
    hidden_duplicate_id снимается. Доступно тому, кто имеет доступ к карточке
    (а не только admin/owner) — баннер показывается добавившему кандидата HR.
    """
    from ...services.similarity import similarity_service, MergeIdentityConflict
    from .common import broadcast_entity_updated, broadcast_entity_deleted

    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    target_result = await db.execute(
        select(Entity).where(Entity.id == entity_id, Entity.org_id == org.id)
    )
    target_entity = target_result.scalar_one_or_none()
    if not target_entity:
        raise HTTPException(404, "Candidate not found")

    has_access = await check_entity_access(target_entity, current_user, org.id, db, required_level=None)
    if not has_access:
        raise HTTPException(403, "No access to this candidate")

    source_result = await db.execute(
        select(Entity).where(Entity.id == request.duplicate_id, Entity.org_id == org.id)
    )
    source_entity = source_result.scalar_one_or_none()
    if not source_entity:
        # Дубль может быть и активным, и архивным — объединяем в survivor (target),
        # is_archived survivor не меняется.
        raise HTTPException(404, "Duplicate not found")

    try:
        merged = await similarity_service.merge_entities(
            db=db, source_entity=source_entity, target_entity=target_entity,
            merged_by_name=current_user.name,
        )
        # merge_entities снял флаг целиком — возвращаем баннер на следующий
        # нерешённый дубль, если такие остались.
        next_duplicate_id = await _repoint_duplicate_flag(db, merged)
        await db.commit()
        await broadcast_entity_updated(org.id, entity_broadcast_payload(merged))
        await broadcast_entity_deleted(org.id, request.duplicate_id)
        return {
            "success": True,
            "merged_entity_id": merged.id,
            "deleted_entity_id": request.duplicate_id,
            "next_duplicate_id": next_duplicate_id,
        }
    except MergeIdentityConflict as e:
        raise HTTPException(
            409,
            f"Похоже, это РАЗНЫЕ люди: {e.reason}. Слияние отменено — проверьте телефон/дату рождения.",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"shadow merge failed: {e}")
        raise HTTPException(500, f"Merge failed: {str(e)}")


class UnmergeRequest(BaseModel):
    source_entity_id: int  # id влитого профиля из extra_data.merged_from — вернуть отдельной карточкой


@router.post("/{entity_id}/unmerge")
async def unmerge_entity(
    entity_id: int,
    request: UnmergeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """«Разъединить»: вернуть один ОШИБОЧНО влитый профиль (из extra_data.merged_from)
    отдельной карточкой. Пересоздаёт entity из снапшота контейнера (id переиспользуется —
    он свободен после слияния), возвращает захваченные диспатчи/файлы и убирает контейнер
    из merged_from. Только admin/owner/superadmin. Идемпотентно: если id уже существует — 409.
    Восстановленная карточка — is_archived=True (как были влитые reserve-профили); при
    необходимости разархивировать вручную."""
    from sqlalchemy import update as _sql_update
    from ...models.database import FormDispatch, EntityFile

    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")
    org_role = await get_user_org_role(current_user, org.id, db)
    if current_user.role != UserRole.superadmin and org_role not in (OrgRole.admin, OrgRole.owner):
        raise HTTPException(403, "Only administrators can unmerge")

    target = (await db.execute(
        select(Entity).where(Entity.id == entity_id, Entity.org_id == org.id)
    )).scalar_one_or_none()
    if not target:
        raise HTTPException(404, "Target entity not found")

    mf = target.extra_data.get("merged_from") if isinstance(target.extra_data, dict) else None
    if not isinstance(mf, list):
        raise HTTPException(400, "У карточки нет объединённых профилей")
    container = next(
        (c for c in mf if isinstance(c, dict) and c.get("entity_id") == request.source_entity_id),
        None,
    )
    if container is None:
        raise HTTPException(404, "Такой объединённый профиль не найден в карточке")

    exists = (await db.execute(
        select(Entity.id).where(Entity.id == request.source_entity_id)
    )).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(409, "Профиль с таким id уже существует")

    # Снапшот extra_data источника: убираем служебные флаги дедупа, чтобы
    # восстановленная карточка не тянула баннер обратно на target.
    src_extra = dict(container.get("extra_data") or {})
    for _k in ("hidden_duplicate_id", "hidden_duplicate_meta", "text_twin", "merged_from"):
        src_extra.pop(_k, None)

    try:
        status_val = EntityStatus(container.get("status")) if container.get("status") else EntityStatus.reserve
    except ValueError:
        status_val = EntityStatus.reserve

    restored = Entity(
        id=request.source_entity_id,
        org_id=target.org_id,
        type=EntityType.candidate,
        name=container.get("name") or f"Профиль #{request.source_entity_id}",
        status=status_val,
        extra_data=src_extra,
        is_archived=True,
    )
    _added = container.get("added_at")
    if isinstance(_added, str):
        try:
            restored.created_at = datetime.fromisoformat(_added)
        except ValueError:
            pass
    db.add(restored)
    await db.flush()

    # Возвращаем захваченные при слиянии диспатчи и файлы обратно на восстановленный профиль
    def _ids(vals):
        out = []
        for x in (vals or []):
            try:
                out.append(int(x))
            except (TypeError, ValueError):
                continue
        return out

    disp_ids = _ids(container.get("form_dispatch_ids"))
    if disp_ids:
        await db.execute(
            _sql_update(FormDispatch).where(FormDispatch.id.in_(disp_ids)).values(entity_id=restored.id)
        )
    file_ids = _ids(container.get("file_ids"))
    if file_ids:
        await db.execute(
            _sql_update(EntityFile).where(EntityFile.id.in_(file_ids)).values(entity_id=restored.id)
        )

    # Убираем контейнер из merged_from у target
    new_mf = [
        c for c in mf
        if not (isinstance(c, dict) and c.get("entity_id") == request.source_entity_id)
    ]
    ne = dict(target.extra_data)
    if new_mf:
        ne["merged_from"] = new_mf
    else:
        ne.pop("merged_from", None)
    target.extra_data = ne

    await db.commit()
    return {
        "success": True,
        "restored_entity_id": restored.id,
        "restored_name": restored.name,
        "target_entity_id": target.id,
        "remaining_merged": len(new_mf),
    }


async def _repoint_duplicate_flag(db: AsyncSession, entity: Entity) -> Optional[int]:
    """После решения по ОДНОЙ паре переставить баннер на следующий нерешённый дубль.

    Раньше «объединить»/«разные люди» по любой одной анкете снимали флаг
    hidden_duplicate_id целиком: из 4 похожих решили одну — баннер пропал, остальные
    три так и остались непроверенными (2026-09-15, Эльвира, «Иванов Кирилл»).
    Теперь флаг снимается, только когда нерешённых совпадений не осталось.
    Best-effort: сбой детектора не ломает само решение. Не коммитит.
    """
    from ...services.similarity import detect_archived_duplicate
    try:
        next_id = await detect_archived_duplicate(db, entity)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"shadow-dedup repoint failed for entity {entity.id}: {e}")
        return None
    extra = dict(entity.extra_data or {})
    if next_id:
        extra["hidden_duplicate_id"] = next_id
    else:
        extra.pop("hidden_duplicate_id", None)
        extra.pop("hidden_duplicate_meta", None)
    entity.extra_data = extra
    return next_id


@router.post("/{entity_id}/dismiss-duplicate")
async def dismiss_shadow_duplicate(
    entity_id: int,
    request: ShadowDuplicateActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """«Нет, это разные люди»: разорвать связь с теневым дубликатом.

    Пишет пару в duplicate_pair_decisions (повторный детект её не поднимет, решение
    переживает слияние) и снимает флаг hidden_duplicate_id — баннер исчезает.
    Оба профиля остаются: активный — в работе, архивный — в архиве.
    """
    from .common import broadcast_entity_updated

    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    result = await db.execute(
        select(Entity).where(Entity.id == entity_id, Entity.org_id == org.id)
    )
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(404, "Candidate not found")

    has_access = await check_entity_access(entity, current_user, org.id, db, required_level=None)
    if not has_access:
        raise HTTPException(403, "No access to this candidate")

    other = (await db.execute(
        select(Entity).where(Entity.id == request.duplicate_id, Entity.org_id == org.id)
    )).scalar_one_or_none()
    if other is None:
        raise HTTPException(404, "Duplicate candidate not found")

    from ...services.duplicate_decisions import mark_different
    # Одна строка на пару — решение видно с обеих сторон и переживает слияние.
    await mark_different(db, org.id, entity.id, other.id, current_user.id)
    logger.info(
        f"DUP_DIFFERENT pair {entity.id}<->{other.id} by user {current_user.id}"
    )

    extra = dict(entity.extra_data or {})
    extra.pop("hidden_duplicate_id", None)
    entity.extra_data = extra
    # Остальные похожие анкеты по-прежнему ждут решения — баннер на следующую.
    next_duplicate_id = await _repoint_duplicate_flag(db, entity)

    # У второго профиля флаг смотрел на нас — переводим его на следующее
    # нерешённое совпадение (или снимаем), иначе баннер там остался бы.
    oextra = dict(other.extra_data or {})
    if oextra.get("hidden_duplicate_id") == entity_id:
        oextra.pop("hidden_duplicate_id", None)
        other.extra_data = oextra
        await _repoint_duplicate_flag(db, other)

    await db.commit()

    await broadcast_entity_updated(org.id, entity_broadcast_payload(entity))
    if other is not None:
        await broadcast_entity_updated(org.id, entity_broadcast_payload(other))
    return {
        "success": True,
        "dismissed_duplicate_id": request.duplicate_id,
        "next_duplicate_id": next_duplicate_id,
    }


@router.get("/{entity_id}/compare/{other_entity_id}", response_model=SimilarCandidateResponse)
async def compare_candidates(
    entity_id: int,
    other_entity_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Compare two candidates.
    """
    from ...services.similarity import similarity_service

    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    if entity_id == other_entity_id:
        raise HTTPException(400, "Cannot compare entity with itself")

    # Get first entity
    result1 = await db.execute(
        select(Entity).where(Entity.id == entity_id, Entity.org_id == org.id)
    )
    entity1 = result1.scalar_one_or_none()

    if not entity1:
        raise HTTPException(404, "First entity not found")

    # Check access to first entity
    has_access1 = await check_entity_access(entity1, current_user, org.id, db, required_level=None)
    if not has_access1:
        raise HTTPException(403, "No access to first entity")

    # Get second entity
    result2 = await db.execute(
        select(Entity).where(Entity.id == other_entity_id, Entity.org_id == org.id)
    )
    entity2 = result2.scalar_one_or_none()

    if not entity2:
        raise HTTPException(404, "Second entity not found")

    # Check access to second entity
    has_access2 = await check_entity_access(entity2, current_user, org.id, db, required_level=None)
    if not has_access2:
        raise HTTPException(403, "No access to second entity")

    # Compare
    comparison = similarity_service.calculate_similarity(entity1, entity2)

    return SimilarCandidateResponse(
        entity_id=comparison.entity_id,
        entity_name=comparison.entity_name,
        similarity_score=comparison.similarity_score,
        common_skills=comparison.common_skills,
        similar_experience=comparison.similar_experience,
        similar_salary=comparison.similar_salary,
        similar_location=comparison.similar_location,
        match_reasons=comparison.match_reasons,
        # Detailed comparison data
        entity1_skills=comparison.entity1_skills,
        entity2_skills=comparison.entity2_skills,
        entity1_experience=comparison.entity1_experience,
        entity2_experience=comparison.entity2_experience,
        entity1_salary_min=comparison.entity1_salary_min,
        entity1_salary_max=comparison.entity1_salary_max,
        entity2_salary_min=comparison.entity2_salary_min,
        entity2_salary_max=comparison.entity2_salary_max,
        entity1_location=comparison.entity1_location,
        entity2_location=comparison.entity2_location,
        entity1_position=comparison.entity1_position,
        entity2_position=comparison.entity2_position
    )


@router.get("/{entity_id}/compare/{other_entity_id}/ai")
async def compare_candidates_ai(
    entity_id: int,
    other_entity_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    AI-powered comparison of two candidates using full context.

    Returns a streaming response with markdown-formatted comparison.
    """
    from ...services.comparison_ai import comparison_ai_service
    from ...models.database import EntityFile

    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    if entity_id == other_entity_id:
        raise HTTPException(400, "Cannot compare candidate with themselves")

    # Load both entities with related data
    async def load_entity_with_context(eid: int):
        # Entity
        result = await db.execute(
            select(Entity).where(Entity.id == eid, Entity.org_id == org.id)
        )
        entity = result.scalar_one_or_none()
        if not entity:
            return None, [], [], []

        # Chats with messages
        chats_result = await db.execute(
            select(Chat)
            .options(selectinload(Chat.messages))
            .where(Chat.entity_id == eid)
        )
        chats = list(chats_result.scalars().all())

        # Calls
        calls_result = await db.execute(
            select(CallRecording).where(CallRecording.entity_id == eid)
        )
        calls = list(calls_result.scalars().all())

        # Files
        files_result = await db.execute(
            select(EntityFile).where(EntityFile.entity_id == eid)
        )
        files = list(files_result.scalars().all())

        return entity, chats, calls, files

    entity1, chats1, calls1, files1 = await load_entity_with_context(entity_id)
    if not entity1:
        raise HTTPException(404, "First candidate not found")

    # Check access to first entity
    has_access1 = await check_entity_access(entity1, current_user, org.id, db, required_level=None)
    if not has_access1:
        raise HTTPException(403, "No access to first entity")

    entity2, chats2, calls2, files2 = await load_entity_with_context(other_entity_id)
    if not entity2:
        raise HTTPException(404, "Second candidate not found")

    # Check access to second entity
    has_access2 = await check_entity_access(entity2, current_user, org.id, db, required_level=None)
    if not has_access2:
        raise HTTPException(403, "No access to second entity")

    async def generate():
        try:
            async for chunk in comparison_ai_service.compare_stream(
                entity1, chats1, calls1, files1,
                entity2, chats2, calls2, files2
            ):
                yield chunk
        except Exception as e:
            logger.error(f"AI comparison error: {e}")
            yield f"\n\nError during comparison: {str(e)}"

    return StreamingResponse(
        generate(),
        media_type="text/plain; charset=utf-8"
    )


@router.post("/{entity_id}/compare/{other_entity_id}/report")
async def compare_candidates_report(
    entity_id: int,
    other_entity_id: int,
    format: str = Query("pdf", description="Report format: pdf, docx, markdown"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Generate downloadable comparison report for two candidates.

    Returns PDF, DOCX, or Markdown file with detailed comparison.
    """
    from ...services.comparison_ai import comparison_ai_service
    from ...services.reports import generate_pdf_report, generate_docx_report
    from ...models.database import EntityFile
    from fastapi.responses import Response

    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    if entity_id == other_entity_id:
        raise HTTPException(400, "Cannot compare candidate with themselves")

    if format not in ("pdf", "docx", "markdown"):
        raise HTTPException(400, "Format must be pdf, docx, or markdown")

    # Load both entities with related data
    async def load_entity_with_context(eid: int):
        result = await db.execute(
            select(Entity).where(Entity.id == eid, Entity.org_id == org.id)
        )
        entity = result.scalar_one_or_none()
        if not entity:
            return None, [], [], []

        chats_result = await db.execute(
            select(Chat)
            .options(selectinload(Chat.messages))
            .where(Chat.entity_id == eid)
        )
        chats = list(chats_result.scalars().all())

        calls_result = await db.execute(
            select(CallRecording).where(CallRecording.entity_id == eid)
        )
        calls = list(calls_result.scalars().all())

        files_result = await db.execute(
            select(EntityFile).where(EntityFile.entity_id == eid)
        )
        files = list(files_result.scalars().all())

        return entity, chats, calls, files

    entity1, chats1, calls1, files1 = await load_entity_with_context(entity_id)
    if not entity1:
        raise HTTPException(404, "First candidate not found")

    # Check access to first entity
    has_access1 = await check_entity_access(entity1, current_user, org.id, db, required_level=None)
    if not has_access1:
        raise HTTPException(403, "No access to first entity")

    entity2, chats2, calls2, files2 = await load_entity_with_context(other_entity_id)
    if not entity2:
        raise HTTPException(404, "Second candidate not found")

    # Check access to second entity
    has_access2 = await check_entity_access(entity2, current_user, org.id, db, required_level=None)
    if not has_access2:
        raise HTTPException(403, "No access to second entity")

    # Generate comparison content (non-streaming)
    comparison_text = ""
    try:
        async for chunk in comparison_ai_service.compare_stream(
            entity1, chats1, calls1, files1,
            entity2, chats2, calls2, files2
        ):
            comparison_text += chunk
    except Exception as e:
        logger.error(f"AI comparison error: {e}")
        raise HTTPException(500, f"Failed to generate comparison: {str(e)}")

    # Generate report file
    title = f"Сравнение: {entity1.name} vs {entity2.name}"

    if format == "pdf":
        file_bytes = generate_pdf_report(title, comparison_text, title)
        return Response(
            content=file_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="comparison_{entity_id}_vs_{other_entity_id}.pdf"'
            }
        )
    elif format == "docx":
        file_bytes = generate_docx_report(title, comparison_text, title)
        return Response(
            content=file_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={
                "Content-Disposition": f'attachment; filename="comparison_{entity_id}_vs_{other_entity_id}.docx"'
            }
        )
    else:
        return Response(
            content=comparison_text,
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="comparison_{entity_id}_vs_{other_entity_id}.md"'
            }
        )


@router.get("/{entity_id}/prior-rejections")
async def get_prior_rejections(
    entity_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Все прошлые отказы человека: свои воронки + связанные карточки-дубли +
    архив ClickUp (services/prior_rejection.py). Карточка рисует по ним плашку
    «Уже был у нас — отказ …», окна «Добавить в воронку» / «Забрать» —
    вопрос «Всё равно добавить?» (владелец, 22.10.2026)."""
    from ...services.prior_rejection import prior_rejections
    from ...services.vacancy_scope import get_scope_vacancy_ids

    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")
    entity = (await db.execute(
        select(Entity).where(Entity.id == entity_id, Entity.org_id == org.id)
    )).scalar_one_or_none()
    if not entity or not await check_entity_access(entity, current_user, org.id, db, required_level=None):
        raise HTTPException(404, "Entity not found")

    # Связи на два шага: пометка дубля у этой карточки и у той, на кого она
    # указывает (у старой копии пометка бывает на третью карточку того же человека).
    ed = entity.extra_data if isinstance(entity.extra_data, dict) else {}
    linked: set = set()
    try:
        first = int(ed["hidden_duplicate_id"]) if ed.get("hidden_duplicate_id") else None
    except (TypeError, ValueError):
        first = None
    if first and first != entity.id:
        linked.add(first)
        other = (await db.execute(select(Entity.extra_data).where(
            Entity.id == first, Entity.org_id == org.id,
        ))).scalar_one_or_none()
        second = (other or {}).get("hidden_duplicate_id") if isinstance(other, dict) else None
        try:
            if second and int(second) != entity.id:
                linked.add(int(second))
        except (TypeError, ValueError):
            pass

    found = await prior_rejections(
        db, [entity], own_except_vacancy={entity.id: None},
        scope_ids=await get_scope_vacancy_ids(current_user, db),
        extra_links={entity.id: linked},
    )
    return {"items": found.get(entity.id, [])}


@router.post("/check-duplicate")
async def check_duplicate_before_create(
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Проверка ДО создания карточки — окна «Новый кандидат» и «Загрузка из
    файла» (22.10.2026). Те же правила и тот же ответ, что у расширения
    (`/magic-button/check-duplicate`): активные совпадения с этапами по
    воронкам, архив, «возможно тот же», «Был отказ». До этого окно загрузки
    искало похожих обычным поиском по имени (без архива, а рядовой рекрутёр —
    только среди своих), а ручная форма не проверяла ничего."""
    from ..magic_button import DuplicateCheckRequest, check_duplicate
    req = DuplicateCheckRequest(
        full_name=(data.get("full_name") or "").strip() or "—",
        email=data.get("email") or None,
        phone=data.get("phone") or None,
        telegram=data.get("telegram") or None,
        source_url=data.get("source_url") or None,
    )
    return await check_duplicate(req, db=db, current_user=current_user)
