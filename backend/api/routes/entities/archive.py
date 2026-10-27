"""
Теневая база (архив) и сверка дублей по всей базе (вынесено из crud.py,
20.10.2026).
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional

from .common import (
    get_db, Entity, EntityType, User, UserRole, get_current_user, get_user_org,
    broadcast_entity_updated, broadcast_entity_deleted, check_entity_access,
)

from ...services.entity_card import entity_broadcast_payload

router = APIRouter()


# ============================================================
# Теневая база (архив): список для суперадмина + действия архивации
# ============================================================

@router.get("/archive/list")
async def list_archived_candidates(
    q: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Теневая база: список архивных кандидатов. Только суперадмин."""
    current_user = await db.merge(current_user)
    if current_user.role != UserRole.superadmin:
        raise HTTPException(403, "Архив доступен только суперадмину")

    base = select(Entity).where(
        Entity.is_archived.is_(True),
        Entity.type == EntityType.candidate,
    )
    if q and q.strip():
        like = f"%{q.strip()}%"
        from ...services.search_index import name_search_conditions, ensure_pg_trgm_checked, contact_search_conditions
        await ensure_pg_trgm_checked(db)
        base = base.where(or_(
            *name_search_conditions(q),  # умный поиск по имени (транслит+порядок+опечатки)
            *contact_search_conditions(q),  # почта/телефон(норм.)/telegram + доп-списки
            Entity.position.ilike(like),
        ))

    count_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = count_result.scalar() or 0

    rows = await db.execute(
        base.order_by(Entity.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    items = []
    for e in rows.scalars().all():
        extra = e.extra_data or {}
        items.append({
            "id": e.id,
            "name": e.name,
            "email": e.email,
            "phone": e.phone,
            "position": e.position,
            "company": e.company,
            "status": e.status.value if e.status else None,
            "tags": e.tags or [],
            "photo_url": extra.get("photo_url"),
            "source": extra.get("source"),
            "created_at": e.created_at.isoformat() if e.created_at else None,
        })
    return {"items": items, "total": total, "page": page, "per_page": per_page}


@router.post("/{entity_id}/archive")
async def archive_entity(
    entity_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """«В архив»: убрать кандидата в теневую базу (скрыть из активных списков).
    Доступно тому, кто имеет доступ к карточке."""
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org and current_user.role != UserRole.superadmin:
        raise HTTPException(403, "No organization access")

    result = await db.execute(select(Entity).where(Entity.id == entity_id))
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(404, "Entity not found")

    # Org-граница: кандидат должен быть в орг вызывающего (или вызывающий —
    # суперадмин). Раньше check_entity_access получал entity.org_id (org ЦЕЛИ),
    # а не вызывающего → confused deputy: любой HR мог архивировать чужого.
    if current_user.role != UserRole.superadmin and (not org or entity.org_id != org.id):
        raise HTTPException(404, "Entity not found")
    has_access = await check_entity_access(entity, current_user, entity.org_id, db, required_level=None)
    if not has_access:
        raise HTTPException(403, "No access to this candidate")

    entity.is_archived = True
    await db.commit()
    # Кандидат исчезает из активных списков — уведомляем клиентов
    await broadcast_entity_deleted(entity.org_id, entity.id)
    return {"success": True, "is_archived": True}


@router.post("/{entity_id}/unarchive")
async def unarchive_entity(
    entity_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Вернуть кандидата из архива в активную базу. Только суперадмин."""
    current_user = await db.merge(current_user)
    if current_user.role != UserRole.superadmin:
        raise HTTPException(403, "Только суперадмин может возвращать из архива")

    result = await db.execute(select(Entity).where(Entity.id == entity_id))
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(404, "Entity not found")

    entity.is_archived = False
    await db.commit()
    await broadcast_entity_updated(entity.org_id, entity_broadcast_payload(entity))
    return {"success": True, "is_archived": False}


@router.post("/archive/rescan")
async def rescan_active_duplicates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Разовый прогон детекта по ВСЕМ активным кандидатам против всех остальных
    (активные + архив). Детект-на-создании покрывает только новых; этот прогон
    помечает уже существующих. Проставляет extra_data.hidden_duplicate_id — на
    карточках появится баннер «Проверить». Только суперадмин.

    Считает ЕДИНЫМ ядром (services/duplicate_matcher), тем же, что баннер и окно
    сравнения. Раньше здесь был свой индекс ключей, где ФИО сверялось точной
    строкой: «Векленко Кирилл» и «Векленко Кирилл Дмитриевич» пере-скан считал
    разными людьми, хотя детект-на-создании — одним.
    """
    current_user = await db.merge(current_user)
    if current_user.role != UserRole.superadmin:
        raise HTTPException(403, "Только для суперадмина")
    org = await get_user_org(current_user, db)

    from ...services.duplicate_matcher import scan_org_pairs, best_match
    from ...services.duplicate_decisions import different_map, legacy_dismissed

    items, pair_matches = await scan_org_pairs(db, org.id if org is not None else None)
    names = {it.entity_id: it.name for it in items}

    act_q = select(Entity).where(
        Entity.is_archived.is_not(True), Entity.type == EntityType.candidate
    )
    if org is not None:
        act_q = act_q.where(Entity.org_id == org.id)
    actives = (await db.execute(act_q)).scalars().all()
    decided = await different_map(db, [e.id for e in actives])

    matches = []
    scanned = 0
    changed = 0
    cleared = 0
    for e in actives:
        scanned += 1
        extra = e.extra_data if isinstance(e.extra_data, dict) else {}
        dismissed = decided.get(e.id, set()) | legacy_dismissed(extra)

        found = [m for m in pair_matches.get(e.id, []) if m.entity_id not in dismissed]
        chosen = best_match(found)
        dup_id = chosen.entity_id if chosen is not None else None

        cur = extra.get("hidden_duplicate_id")
        if chosen is not None:
            matches.append({
                "id": e.id,
                "name": e.name,
                "duplicate_id": dup_id,
                "duplicate_name": names.get(dup_id),
                "strength": chosen.strength,
                "confidence": chosen.confidence,
            })
            new_extra = dict(extra)
            meta = {
                "strength": chosen.strength,
                "confidence": chosen.confidence,
                "reasons": chosen.reasons,
                "matched_id": chosen.entity_id,
                "level": chosen.level,
            }
            if cur != dup_id or new_extra.get("hidden_duplicate_meta") != meta:
                new_extra["hidden_duplicate_id"] = dup_id
                new_extra["hidden_duplicate_meta"] = meta
                e.extra_data = new_extra
                if cur != dup_id:
                    changed += 1
        elif cur is not None:
            # Реального дубля больше нет (напр. ушло ложное совпадение по мусорному
            # telegram) — снимаем устаревший авто-флаг, чтобы баннер исчез.
            new_extra = dict(extra)
            new_extra.pop("hidden_duplicate_id", None)
            new_extra.pop("hidden_duplicate_meta", None)
            e.extra_data = new_extra
            cleared += 1

    if changed or cleared or matches:
        await db.commit()
    return {
        "scanned": scanned,
        "flagged": len(matches),
        "newly_flagged": changed,
        "cleared": cleared,
        "matches": matches,
    }


@router.post("/archive/find-duplicates")
async def find_archive_duplicates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Найти дубликаты ВНУТРИ архива: группы архивных кандидатов, которых единое
    ядро (services/duplicate_matcher) считает одним человеком. Возвращает группы
    из ≥2 профилей. Только суперадмин.

    Раньше группы строились собственным union-find по email/телефону/telegram/URL
    и ФИО не учитывали вовсе — архивные карточки одного человека, добавленные без
    контактов, в группу не попадали.
    """
    current_user = await db.merge(current_user)
    if current_user.role != UserRole.superadmin:
        raise HTTPException(403, "Только для суперадмина")
    org = await get_user_org(current_user, db)

    from ...services.duplicate_matcher import scan_org_pairs
    from ...services.duplicate_decisions import different_map, legacy_dismissed

    items, pair_matches = await scan_org_pairs(
        db, org.id if org is not None else None, archived_only=True,
    )

    # Union-find поверх пар, которые ядро признало дублями.
    parent: dict = {}

    def find(x):
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    info: dict = {}
    for it in items:
        parent.setdefault(it.entity_id, it.entity_id)
        ph = sorted(it.keys.get("phone_keys") or set())
        em = sorted(it.keys.get("emails") or set())
        tg = sorted(it.keys.get("tg_names") or set())
        info[it.entity_id] = {
            "id": it.entity_id,
            "name": it.name,
            "email": em[0] if em else None,
            "phone": ph[0] if ph else None,
            "telegram": tg[0] if tg else None,
            "position": (it.extra_data or {}).get("position"),
        }
    for eid, ms in pair_matches.items():
        for m in ms:
            if eid in parent and m.entity_id in parent:
                union(eid, m.entity_id)

    groups_map: dict = {}
    for rid in info:
        groups_map.setdefault(find(rid), []).append(info[rid])
    groups = [m for m in groups_map.values() if len(m) >= 2]
    groups.sort(key=lambda m: -len(m))

    # Помечаем участников групп флагом hidden_duplicate_id → при открытии карточки
    # архивного появится баннер сравнения (как у активных). Каждый указывает на
    # «соседа» по группе (первый — на второго, остальные — на первого).
    member_ids = [m["id"] for g in groups for m in g]
    if member_ids:
        ents = (await db.execute(
            select(Entity).where(Entity.id.in_(member_ids))
        )).scalars().all()
        by_id = {e.id: e for e in ents}
        decided = await different_map(db, by_id.keys())
        changed = False
        for g in groups:
            ids = [m["id"] for m in g]
            for idx, mid in enumerate(ids):
                sibling = ids[1] if idx == 0 else ids[0]
                ent = by_id.get(mid)
                if ent is None:
                    continue
                extra = ent.extra_data if isinstance(ent.extra_data, dict) else {}
                if (
                    sibling in decided.get(mid, set()) | legacy_dismissed(extra)
                    or extra.get("hidden_duplicate_id") == sibling
                ):
                    continue
                ne = dict(extra)
                ne["hidden_duplicate_id"] = sibling
                hit = next((m for m in pair_matches.get(mid, []) if m.entity_id == sibling), None)
                if hit is not None:
                    ne["hidden_duplicate_meta"] = {
                        "strength": hit.strength,
                        "confidence": hit.confidence,
                        "reasons": hit.reasons,
                        "matched_id": sibling,
                        "level": hit.level,
                    }
                ent.extra_data = ne
                changed = True
        if changed:
            await db.commit()

    return {
        "groups": groups,
        "total_groups": len(groups),
        "total_dupes": sum(len(g) for g in groups),
    }


class _MergeArchivedRequest(BaseModel):
    source_id: int


@router.post("/{entity_id}/merge-archived")
async def merge_archived_duplicate(
    entity_id: int,
    body: _MergeArchivedRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Объединить два АРХИВНЫХ профиля: source_id вливается в survivor (entity_id),
    survivor остаётся в архиве. Только суперадмин."""
    current_user = await db.merge(current_user)
    if current_user.role != UserRole.superadmin:
        raise HTTPException(403, "Только для суперадмина")

    survivor = (await db.execute(select(Entity).where(Entity.id == entity_id))).scalar_one_or_none()
    source = (await db.execute(select(Entity).where(Entity.id == body.source_id))).scalar_one_or_none()
    if not survivor or not survivor.is_archived:
        raise HTTPException(404, "Кандидат-приёмник не в архиве")
    if not source or not source.is_archived:
        raise HTTPException(404, "Кандидат-источник не в архиве")
    if survivor.id == source.id:
        raise HTTPException(400, "Нельзя объединить профиль сам с собой")

    from ...services.similarity import similarity_service
    await similarity_service.merge_entities(db=db, source_entity=source, target_entity=survivor)
    return {"success": True, "survivor_id": survivor.id}


@router.post("/{entity_id}/detect-duplicate")
async def detect_duplicate_now(
    entity_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Живой поиск дубля для кандидата (вызывается при ОТКРЫТИИ карточки) —
    ловит уже существующих дублей без ручного прогона. Помечает обе стороны
    (detect ставит обратную ссылку), возвращает id найденного дубля или null."""
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    result = await db.execute(select(Entity).where(Entity.id == entity_id))
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(404, "Entity not found")
    # Org-граница (раньше отсутствовала вовсе — любой HR мог запускать дедуп на
    # чужом кандидате и ставить hidden_duplicate_id).
    if current_user.role != UserRole.superadmin and (not org or entity.org_id != org.id):
        raise HTTPException(404, "Entity not found")
    has_access = await check_entity_access(entity, current_user, entity.org_id, db, required_level=None)
    if not has_access:
        raise HTTPException(403, "No access to this candidate")

    from ...services.similarity import detect_archived_duplicate
    dup_id = await detect_archived_duplicate(db, entity)
    if dup_id:
        extra = dict(entity.extra_data) if isinstance(entity.extra_data, dict) else {}
        if extra.get("hidden_duplicate_id") != dup_id:
            extra["hidden_duplicate_id"] = dup_id
            entity.extra_data = extra
        await db.commit()
    return {
        "duplicate_id": dup_id,
        "hidden_duplicate_meta": (entity.extra_data or {}).get("hidden_duplicate_meta"),
    }
