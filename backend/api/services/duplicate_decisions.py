"""Решения по парам похожих кандидатов («это разные люди») — отдельная таблица.

Зачем (этап 2 переделки дублей). Раньше «разные люди» записывалось списком id в
``extra_data.dismissed_duplicate_ids`` обеих анкет. При объединении выживала
``extra_data`` одной стороны, влитая анкета удалялась — и её решения пропадали, а
соседи хранили id, которого больше нет. Итог: рекрутёр снова и снова решал уже
решённую пару.

Теперь пара хранится одной строкой ``duplicate_pair_decisions`` и при слиянии
переезжает на выжившую карточку (:func:`repoint_on_merge`). Старые списки из
``extra_data`` один раз переносятся сюда (:func:`import_legacy_once`) и ещё
читаются как запасной источник — на случай строк, которые перенос пропустил.
"""
import logging
from typing import Dict, Iterable, Optional, Set, Tuple

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import DataMigrationMark, DuplicatePairDecision, Entity, EntityType

logger = logging.getLogger("hr-analyzer.duplicate_decisions")

DIFFERENT = "different"
LEGACY_IMPORT_MARK = "dup_pair_decisions_import_2026_09_22"


def pair_key(a: int, b: int) -> Tuple[int, int]:
    """Пара без направления: (меньший id, больший id)."""
    return (a, b) if a < b else (b, a)


def legacy_dismissed(extra: Optional[dict]) -> Set[int]:
    """id из старого ``extra_data.dismissed_duplicate_ids`` (запасной источник)."""
    out: Set[int] = set()
    if not isinstance(extra, dict):
        return out
    for x in (extra.get("dismissed_duplicate_ids") or []):
        try:
            out.add(int(x))
        except (TypeError, ValueError):
            continue
    return out


async def different_map(db: AsyncSession, entity_ids: Iterable[int]) -> Dict[int, Set[int]]:
    """{id кандидата: id тех, с кем он признан «разными людьми»} — одним запросом."""
    ids = {int(i) for i in entity_ids if i is not None}
    out: Dict[int, Set[int]] = {i: set() for i in ids}
    if not ids:
        return out
    rows = (await db.execute(
        select(DuplicatePairDecision.entity_a_id, DuplicatePairDecision.entity_b_id).where(
            DuplicatePairDecision.decision == DIFFERENT,
            or_(
                DuplicatePairDecision.entity_a_id.in_(ids),
                DuplicatePairDecision.entity_b_id.in_(ids),
            ),
        )
    )).all()
    for a, b in rows:
        if a in out:
            out[a].add(b)
        if b in out:
            out[b].add(a)
    return out


async def dismissed_for(db: AsyncSession, entity) -> Set[int]:
    """С кем этот кандидат признан «разными людьми»: таблица + старый список."""
    if getattr(entity, "id", None) is None:
        return legacy_dismissed(getattr(entity, "extra_data", None))
    from_table = (await different_map(db, [entity.id])).get(entity.id, set())
    return from_table | legacy_dismissed(entity.extra_data)


async def mark_different(
    db: AsyncSession, org_id: int, a: int, b: int, user_id: Optional[int] = None,
) -> bool:
    """Записать «разные люди» для пары. Повторный вызов ничего не дублирует.
    Возвращает True, если строка добавлена. Не коммитит (flush — чтобы следующий
    поиск дубля в той же сессии уже видел решение)."""
    if a == b:
        return False
    lo, hi = pair_key(a, b)
    exists = (await db.execute(
        select(DuplicatePairDecision.id).where(
            DuplicatePairDecision.entity_a_id == lo,
            DuplicatePairDecision.entity_b_id == hi,
        )
    )).scalar_one_or_none()
    if exists is not None:
        return False
    db.add(DuplicatePairDecision(
        org_id=org_id, entity_a_id=lo, entity_b_id=hi, decision=DIFFERENT, decided_by=user_id,
    ))
    await db.flush()
    return True


async def repoint_on_merge(db: AsyncSession, source_id: int, target_id: int) -> int:
    """Слияние source → target: решения source переезжают на target.

    Пара «source ↔ X» становится «target ↔ X» (если такой ещё нет). Пара
    «source ↔ target» исчезает — это теперь один человек. Вызывать ДО удаления
    source: иначе каскад по внешнему ключу снесёт его решения раньше.
    Возвращает число перенесённых пар. Не коммитит.
    """
    rows = (await db.execute(
        select(DuplicatePairDecision).where(or_(
            DuplicatePairDecision.entity_a_id == source_id,
            DuplicatePairDecision.entity_b_id == source_id,
        ))
    )).scalars().all()
    have = set((await different_map(db, [target_id])).get(target_id, set()))
    moved = 0
    for row in rows:
        other = row.entity_b_id if row.entity_a_id == source_id else row.entity_a_id
        await db.delete(row)
        if other == target_id or other in have:
            continue
        lo, hi = pair_key(target_id, other)
        db.add(DuplicatePairDecision(
            org_id=row.org_id, entity_a_id=lo, entity_b_id=hi,
            decision=row.decision, decided_by=row.decided_by, created_at=row.created_at,
        ))
        have.add(other)
        moved += 1
    await db.flush()
    if rows:
        logger.info(
            f"DUP_DECISIONS merge {source_id}->{target_id}: moved={moved} dropped={len(rows) - moved}"
        )
    return moved


async def import_legacy_once(db: AsyncSession) -> int:
    """Один раз перенести старые ``dismissed_duplicate_ids`` в таблицу.

    Берутся только пары, где обе анкеты существуют и в одной организации (id
    влитых и удалённых анкет отбрасываются). Отметка в ``data_migration_marks``
    — чтобы не гонять перенос на каждом старте. Коммитит.
    """
    if await db.get(DataMigrationMark, LEGACY_IMPORT_MARK) is not None:
        return 0
    rows = (await db.execute(
        select(Entity.id, Entity.org_id, Entity.extra_data).where(Entity.type == EntityType.candidate)
    )).all()
    org_of = {eid: org for eid, org, _ in rows}
    wanted: Dict[Tuple[int, int], int] = {}
    for eid, org, extra in rows:
        for other in legacy_dismissed(extra):
            if other == eid or org_of.get(other) is None or org_of.get(other) != org:
                continue
            wanted.setdefault(pair_key(eid, other), org)
    existing = set((await db.execute(
        select(DuplicatePairDecision.entity_a_id, DuplicatePairDecision.entity_b_id)
    )).all())
    added = 0
    for (lo, hi), org in wanted.items():
        if (lo, hi) in existing or org is None:
            continue
        db.add(DuplicatePairDecision(org_id=org, entity_a_id=lo, entity_b_id=hi, decision=DIFFERENT))
        added += 1
    db.add(DataMigrationMark(key=LEGACY_IMPORT_MARK))
    await db.commit()
    logger.info(f"DUP_DECISIONS legacy import: {added} pairs from extra_data")
    return added
