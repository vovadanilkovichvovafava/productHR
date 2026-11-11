"""Разовый пересчёт статуса у объединённых карточек (11.11.2026).

«Объединить» переносил заявки влитой карточки на выжившую, но общий статус не
пересчитывал (с 11.11 пересчитывает — `similarity.merge_entities`). Новую
карточку («Новые») сливали со старой, где был «Отказ» в «Трафике», и человек с
чипом «Отказ · Трафик» стоял во вкладке «Новые» (Мария: «на статусе „Новые“
висят отказники»). На проде таких было три: Никонов, Тихомиров, Стельников.

Берём карточки в «Новых», в которые что-то вливали (`extra_data.merged_from`),
и пересчитываем статус по их заявкам — тем же правилом, что и при слиянии.
Одноразово (отметка в data_migration_marks). Коммитит. Маркер `MERGE_STATUS_SYNC`.
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import DataMigrationMark, Entity, EntityStatus, EntityType

logger = logging.getLogger("hr-analyzer.merged_status_sync")

SYNC_MARK = "merged_new_status_2026_11_11"


async def resettle_merged_new_once(db: AsyncSession) -> list[int]:
    from ..routes.vacancies.common import recompute_entity_status

    if await db.get(DataMigrationMark, SYNC_MARK) is not None:
        return []
    people = (await db.execute(
        select(Entity).where(
            Entity.type == EntityType.candidate,
            Entity.status == EntityStatus.new,
        ).order_by(Entity.id)
    )).scalars().all()
    fixed: list[str] = []
    for entity in people:
        if not (entity.extra_data or {}).get("merged_from"):
            continue
        await recompute_entity_status(db, entity.id, undo=True)
        if entity.status != EntityStatus.new:
            fixed.append(f"{entity.id}:{entity.status.value}")
    db.add(DataMigrationMark(key=SYNC_MARK))
    await db.commit()
    logger.info("MERGE_STATUS_SYNC: пересчитано %s (кандидат:статус): %s", len(fixed), ", ".join(fixed))
    return [int(x.split(":")[0]) for x in fixed]
