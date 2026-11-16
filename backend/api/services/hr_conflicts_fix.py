"""Разово: расхождения «HR на доске ≠ HR в воронке» на проде (16.11.2026).

До одного HR у кандидата (services/candidate_hr.py) колонку HR на «Штате»
правили руками отдельно от воронки, и на проде (16.11.2026, 103 человека на
доске) у 4 они разошлись. Владелец посмотрел историю каждого:
- двое — HR тот, кто на доске (вёл этапы по истории): им делаем смену HR тем
  же путём, что кнопка «Сменить HR» (прежний — в сорсеры, если сорсера нет,
  строка «Сменился HR» в ленте, отмена корзиной);
- у третьего права воронка — с 16.11 доска сама берёт HR из воронки, делать
  нечего;
- четвёртый — ждём ответа Маши, не трогаем.

Номера карточек и людей — только числами (персональные данные в код не
кладём). Шаг срабатывает, только если у кандидата всё ещё прежний HR: если
его уже поменяли руками, ничего не делаем. Маркер `HR_CONFLICTS_FIX`.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import DataMigrationMark, Entity

logger = logging.getLogger("hr-analyzer.hr_conflicts_fix")

SYNC_MARK = "hr_board_funnel_conflicts_2026_11_16"
# (карточка, кто HR сейчас в воронке, кого сделать HR)
FIXES = (
    (9300, 86, 94),
    (9685, 94, 51),
)


async def fix_hr_conflicts_once(db: AsyncSession) -> list[int]:
    from .candidate_hr import change_hr, current_hr_id
    from .hr_tags import sync_for_entity

    if await db.get(DataMigrationMark, SYNC_MARK) is not None:
        return []
    actor = SimpleNamespace(id=None, name="Сверка HR (доска ↔ воронка)")
    fixed: list[int] = []
    for entity_id, expected_now, target in FIXES:
        entity = await db.get(Entity, entity_id)
        if entity is None:
            continue
        now = await current_hr_id(db, entity)
        if now != expected_now:
            logger.info("HR_CONFLICTS_FIX skip: entity=%s hr=%s (ждали %s)", entity_id, now, expected_now)
            continue
        await change_hr(db, entity, target, actor=actor, via="board_funnel_fix")
        fixed.append(entity_id)
    db.add(DataMigrationMark(key=SYNC_MARK))
    await db.commit()
    for entity_id in fixed:
        try:
            await sync_for_entity(db, entity_id)
        except Exception:  # noqa: BLE001
            logger.exception("HR_CONFLICTS_FIX tags sync failed: entity=%s", entity_id)
    logger.info("HR_CONFLICTS_FIX: выправлено %s: %s", len(fixed), fixed)
    return fixed
