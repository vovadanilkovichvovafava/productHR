"""Пометки дубля (`extra_data.hidden_duplicate_id`), ведущие в никуда (22.10.2026).

Пометка указывает на «того же человека». Когда ту карточку вливали в третью
(`merge_entities` удаляет влитую), пометки у остальных продолжали смотреть на
удалённый id: плашка дубля молча не показывалась (профиль не грузится), а
проверка дубля при открытии карточки её не пересчитывала — у флага уже есть
уровень. На проде: у 2 из 7 помеченных среди 100 последних «Новых».

- `repoint_on_merge` — при слиянии пометки на влитую переводятся на выжившую
  (это тот же человек);
- `clear_dangling_once` — разово при старте снимает уже висящие; при открытии
  такой карточки детектор найдёт пару заново.
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import DataMigrationMark, Entity, EntityType

logger = logging.getLogger("hr-analyzer.duplicate_flags")

CLEANUP_MARK = "dangling_duplicate_flags_2026_10_22"


def _flag_of(extra) -> int | None:
    if not isinstance(extra, dict):
        return None
    try:
        v = extra.get("hidden_duplicate_id")
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


async def _flagged(db: AsyncSession, org_id: int | None = None):
    """(id, флаг) у всех помеченных: тянем только сам флаг, не весь extra_data."""
    flag = Entity.extra_data["hidden_duplicate_id"].as_string()
    q = select(Entity.id, flag).where(Entity.type == EntityType.candidate, flag.is_not(None))
    if org_id is not None:
        q = q.where(Entity.org_id == org_id)
    out = []
    for eid, raw in (await db.execute(q)).all():
        try:
            out.append((eid, int(raw)))
        except (TypeError, ValueError):
            continue
    return out


async def repoint_on_merge(db: AsyncSession, source_id: int, target_id: int, org_id: int | None) -> int:
    """Пометки на влитую карточку → на выжившую. Не коммитит."""
    ids = [eid for eid, flag in await _flagged(db, org_id) if flag == source_id and eid != target_id]
    if not ids:
        return 0
    for e in (await db.execute(select(Entity).where(Entity.id.in_(ids)))).scalars():
        extra = dict(e.extra_data or {})
        extra["hidden_duplicate_id"] = target_id
        meta = extra.get("hidden_duplicate_meta")
        if isinstance(meta, dict) and meta.get("matched_id") == source_id:
            extra["hidden_duplicate_meta"] = {**meta, "matched_id": target_id}
        e.extra_data = extra
    logger.info(f"DUP_FLAGS repoint {source_id} -> {target_id}: {ids}")
    return len(ids)


async def clear_dangling_once(db: AsyncSession) -> int:
    """Снять пометки, указывающие на несуществующие карточки. Коммитит."""
    if await db.get(DataMigrationMark, CLEANUP_MARK) is not None:
        return 0
    flagged = await _flagged(db)
    targets = {flag for _, flag in flagged}
    existing = set()
    if targets:
        existing = set((await db.execute(select(Entity.id).where(Entity.id.in_(targets)))).scalars())
    dangling = [eid for eid, flag in flagged if flag not in existing]
    if dangling:
        for e in (await db.execute(select(Entity).where(Entity.id.in_(dangling)))).scalars():
            extra = dict(e.extra_data or {})
            extra.pop("hidden_duplicate_id", None)
            extra.pop("hidden_duplicate_meta", None)
            e.extra_data = extra
    db.add(DataMigrationMark(key=CLEANUP_MARK))
    await db.commit()
    logger.info(f"DUP_FLAGS cleared dangling flags: {len(dangling)} {dangling[:50]}")
    return len(dangling)
