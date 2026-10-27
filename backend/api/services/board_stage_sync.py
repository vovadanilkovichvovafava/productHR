"""Разовое выравнивание заявок за доской «Штат» (20.10.2026).

До правки доска переводила человека в «Перешёл в отдел», не трогая его
заявку: заявка оставалась на «Практике». На «Все кандидаты» он стоял в колонке
«Перешёл в отдел» с чипом «Практика · воронка» (жалоба Марии 20.10.2026), а
первое же действие в этой воронке пересчитывало его статус обратно в
«Практику». На проде 20.10 таких было 19 (чтение API /candidates/kanban).

Новые переводы с доски двигают заявку сами (staff_board._move_board_application).
Здесь — уже накопленные: статус «Перешёл в отдел», актуальная открытая заявка на
«Практике» → заявка на «Перешёл в отдел». Запись в историю НЕ пишем: перевод
был раньше (с 06.10 доска уже оставила о нём запись в ленте), и строка
«Перешёл в отдел» с сегодняшней датой и без автора вводила бы в заблуждение.
Одноразово (отметка в data_migration_marks). Коммитит.
"""
import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import (
    ApplicationStage,
    DataMigrationMark,
    Entity,
    EntityStatus,
    EntityType,
    Vacancy,
    VacancyApplication,
    VacancyStatus,
)

logger = logging.getLogger("hr-analyzer.board_stage_sync")

SYNC_MARK = "board_transferred_applications_2026_10_20"


async def sync_transferred_applications_once(db: AsyncSession) -> list[int]:
    from ..routes.vacancies.common import pick_primary_application

    if await db.get(DataMigrationMark, SYNC_MARK) is not None:
        return []
    people = (await db.execute(
        select(Entity.id).where(
            Entity.type == EntityType.candidate,
            Entity.status == EntityStatus.transferred,
        )
    )).scalars().all()
    fixed: list[tuple[int, int]] = []
    for entity_id in people:
        apps = (await db.execute(
            select(VacancyApplication)
            .join(Vacancy, VacancyApplication.vacancy_id == Vacancy.id)
            .where(
                VacancyApplication.entity_id == entity_id,
                Vacancy.status != VacancyStatus.closed,
                Vacancy.deleted_at.is_(None),
            )
        )).scalars().all()
        app = pick_primary_application(list(apps))
        if app is None or app.stage != ApplicationStage.probation:
            continue
        max_order = (await db.execute(
            select(func.max(VacancyApplication.stage_order)).where(
                VacancyApplication.vacancy_id == app.vacancy_id,
                VacancyApplication.stage == ApplicationStage.transferred,
            )
        )).scalar() or 0
        app.stage = ApplicationStage.transferred
        app.stage_order = max_order + 1
        fixed.append((entity_id, app.id))
    db.add(DataMigrationMark(key=SYNC_MARK))
    await db.commit()
    logger.info(
        "BOARD_STAGE_SYNC: заявок выровнено %s (кандидат:заявка): %s",
        len(fixed), ", ".join(f"{e}:{a}" for e, a in fixed),
    )
    return [e for e, _ in fixed]
