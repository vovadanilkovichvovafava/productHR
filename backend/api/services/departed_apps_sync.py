"""Разовое закрытие заявок у тех, кого уволили до 20.10.2026 (11.11.2026).

До 20.10 увольнение с доски «Штат» меняло только статус человека, заявки
оставались как были. С 10.11 у «Мы уволили» / «Сам уволился» своя вкладка на
«Все кандидаты», и расхождение стало видно: Лушников (уволен Марией 13.10) в
«Мы уволили», а в воронке «Трафик» у него «Перешёл в отдел» (Мария, 11.11.2026).
На проде такой был один (второй уволенный — без воронок).

Здесь — то же, что делает увольнение сейчас
(`stage_change.close_applications_for_departure`): живые заявки уволенных
закрываются «Отказом», в истории заявки — запись с пометкой, что это сверка.
Статус человека не трогаем. Одноразово (отметка в data_migration_marks).
Коммитит. Маркер `DEPARTED_APPS_SYNC`.
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import DataMigrationMark, Entity, EntityStatus, EntityType, VacancyApplication
from .hr_stages import STATUS_LABELS

logger = logging.getLogger("hr-analyzer.departed_apps_sync")

SYNC_MARK = "departed_applications_2026_11_11"
DEPARTED = (EntityStatus.dismissed, EntityStatus.quit)


async def close_departed_applications_once(db: AsyncSession) -> list[int]:
    from .stage_change import close_applications_for_departure

    if await db.get(DataMigrationMark, SYNC_MARK) is not None:
        return []
    people = (await db.execute(
        select(Entity).where(
            Entity.type == EntityType.candidate,
            Entity.status.in_(DEPARTED),
        ).order_by(Entity.id)
    )).scalars().all()
    fixed: list[str] = []
    for entity in people:
        label = STATUS_LABELS.get(entity.status.value, entity.status.value)
        # Закрытие «Отказом» с комментарием пишет его в «Причину отказа»
        # карточки и заявки (remember_rejection_reason). Текст сверки — не
        # причина: возвращаем то, что там было.
        extra_before = dict(entity.extra_data or {})
        reasons_before = {
            a.id: a.rejection_reason for a in (await db.execute(
                select(VacancyApplication).where(VacancyApplication.entity_id == entity.id)
            )).scalars().all()
        }
        moves = await close_applications_for_departure(
            db, entity, entity.status, changed_by=None,
            comment=f"{label} — заявка закрыта при сверке (увольнение было раньше)",
        )
        entity.extra_data = extra_before
        for m in moves:
            app = await db.get(VacancyApplication, m.application_id)
            if app is not None:
                app.rejection_reason = reasons_before.get(app.id)
        fixed += [f"{entity.id}:{m.application_id}" for m in moves]
    db.add(DataMigrationMark(key=SYNC_MARK))
    await db.commit()
    logger.info("DEPARTED_APPS_SYNC: закрыто заявок %s (кандидат:заявка): %s", len(fixed), ", ".join(fixed))
    return [int(x.split(":")[0]) for x in fixed]
