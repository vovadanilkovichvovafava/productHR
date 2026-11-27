"""Чем заканчивается работа с кандидатом: «Отказ» или увольнение (27.11.2026).

Правило Марии:
• в истории кандидата есть «Практика» или «Перешёл в отдел» — доступны только
  «Мы уволили» и «Сам уволился», «Отказ» недоступен;
• ничего из этого нет — доступен только «Отказ».

Иначе база и доска «Штат» расходились: человек после практики получал «Отказ»,
и доска сама относила его к «Мы уволили» (на проде таких было 29).

Одно правило для окна смены этапа («Все кандидаты» и воронка) и для сервера:
фронт показывает только разрешённое, сервер не пропускает остальное (прямой
запрос или старая вкладка).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import Entity, EntityStatus, StageTransition

# «Практика» и «Перешёл в отдел» — одинаковые ключи у статуса и у этапа заявки.
WORKED_STAGES = (EntityStatus.probation.value, EntityStatus.transferred.value)
# Записи ленты, которые бывают только у работавших (переводы с доски «Штат»).
WORKED_NOTE_STAGES = WORKED_STAGES + (EntityStatus.dismissed.value, EntityStatus.quit.value)
# Дата выхода на практику (поле доски «Штат», лежит в карточке).
PRACTICE_START_KEY = "practice_start_date"
# Сам статус уже говорит, что человек работал у нас.
WORKED_STATUSES = {
    EntityStatus.probation, EntityStatus.transferred, EntityStatus.dismissed, EntityStatus.quit,
}
DEPARTED_TARGETS = {EntityStatus.dismissed.value, EntityStatus.quit.value}

NEED_DEPARTURE = (
    "Кандидат был на практике или в отделе — выберите «Мы уволили» или «Сам уволился»"
)
NEED_REJECTION = (
    "Кандидат не был на практике и в отделе — выберите «Отказ»"
)


def _status_value(status) -> str:
    return status.value if hasattr(status, "value") else str(status or "")


async def has_worked(db: AsyncSession, entity: Entity) -> bool:
    """Был ли человек на практике или в отделе — по статусу, истории заявок,
    записям ленты (у кандидата вне воронок перевод живёт в notes) и дате выхода
    на практику. До 27.11.2026 это же правило жило в доске «Штат»
    (_reached_staff) — теперь одно место."""
    if entity.status in WORKED_STATUSES:
        return True
    extra = entity.extra_data if isinstance(entity.extra_data, dict) else {}
    if extra.get(PRACTICE_START_KEY):
        return True
    if any(isinstance(n, dict) and n.get("stage") in WORKED_NOTE_STAGES for n in extra.get("notes") or []):
        return True
    return bool((await db.execute(
        select(exists().where(
            StageTransition.entity_id == entity.id,
            StageTransition.to_stage.in_(WORKED_STAGES),
        ))
    )).scalar())


async def exit_status_problem(db: AsyncSession, entity: Entity, target) -> Optional[str]:
    """Текст отказа, если ``target`` (статус кандидата или этап заявки) нельзя
    поставить этому человеку по правилу выше; иначе None."""
    value = _status_value(target)
    if value == EntityStatus.rejected.value:
        return NEED_DEPARTURE if await has_worked(db, entity) else None
    if value in DEPARTED_TARGETS:
        return None if await has_worked(db, entity) else NEED_REJECTION
    return None
