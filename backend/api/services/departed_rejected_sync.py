"""Разово: «Отказ» после практики/отдела → «Мы уволили» / «Сам уволился» (27.11.2026).

Правило Марии: кто был на практике или в отделе, тому «Отказ» не ставится —
только «Мы уволили» или «Сам уволился» (services/exit_status.py). До этого у 29
человек на проде после практики стоял «Отказ», и доска «Штат» сама относила их
к «Мы уволили»: на доске в этой секции было 37, в базе — 8.

Кого куда — решено по ЛЕНТЕ каждого (владелец: «посмотри, что написано в их
ленте событий, и на основе этого перемещай»): «не прошёл», «не вытянула»,
«рассчитали», «уволен» — «Мы уволили»; «отказался от практики», «принял другой
оффер», «перестал отвечать», «вышла из чата в первый день» — «Сам уволился».

Что меняется у человека: статус; запись ленты, которой закончилась работа
(последний перевод заявки в «Отказ» и/или запись-комментарий с этапом
«Отказ»), читается как «Мы уволили — <прежний текст>». Заявки уже закрыты
«Отказом» — их этап не трогаем. Меняем только тех, кто сейчас в «Отказе» /
«Отозван» и действительно работал (на случай, если HR уже поправил руками,
или это другая база с теми же номерами). Маркер `DEPARTED_REJECTED_SYNC`.
"""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from ..models.database import (
    ApplicationStage, DataMigrationMark, Entity, EntityStatus, StageTransition, VacancyApplication,
)
from .exit_status import has_worked
from .hr_stages import DEPARTED_LABELS, departure_of_comment

logger = logging.getLogger("hr-analyzer.departed_rejected_sync")

SYNC_MARK = "departed_rejected_by_feed_2026_11_27"

# Номер карточки на проде → статус по её ленте.
DISMISSED_IDS = (9174, 9248, 9273, 9366, 9397, 9421, 9542, 9591, 9774, 9856, 9959, 10013)
QUIT_IDS = (
    9106, 9184, 9279, 9325, 9338, 9363, 9448, 9490, 9845, 9938, 9940, 9977, 9980,
    9983, 9996, 10020, 10048,
)
PLAN = {
    **{i: EntityStatus.dismissed for i in DISMISSED_IDS},
    **{i: EntityStatus.quit for i in QUIT_IDS},
}
EXIT_NOW = (EntityStatus.rejected, EntityStatus.withdrawn)


def _relabel(comment: str | None, label: str) -> str:
    text = (comment or "").strip()
    if departure_of_comment(text):
        return text
    return f"{label} — {text}" if text else label


async def relabel_departed_rejected_once(db: AsyncSession, plan: dict | None = None) -> list[str]:
    if await db.get(DataMigrationMark, SYNC_MARK) is not None:
        return []
    plan = PLAN if plan is None else plan
    done: list[str] = []
    for entity_id, target in plan.items():
        entity = await db.get(Entity, entity_id)
        if entity is None or entity.status not in EXIT_NOW or not await has_worked(db, entity):
            continue
        label = DEPARTED_LABELS[target.value]
        # Перевод заявки, которым закончилась работа: последний в «Отказ» у
        # каждой заявки, что сейчас стоит в «Отказе».
        apps = (await db.execute(
            select(VacancyApplication.id).where(
                VacancyApplication.entity_id == entity_id,
                VacancyApplication.stage == ApplicationStage.rejected,
            )
        )).scalars().all()
        for app_id in apps:
            tr = (await db.execute(
                select(StageTransition)
                .where(
                    StageTransition.application_id == app_id,
                    StageTransition.to_stage == ApplicationStage.rejected.value,
                )
                .order_by(StageTransition.created_at.desc(), StageTransition.id.desc())
                .limit(1)
            )).scalar_one_or_none()
            if tr is not None:
                tr.comment = _relabel(tr.comment, label)
        # Запись-комментарий о переводе в «Отказ» (вне воронок или с доски).
        extra = dict(entity.extra_data or {})
        notes = [dict(n) if isinstance(n, dict) else n for n in extra.get("notes") or []]
        rejected_notes = [n for n in notes if isinstance(n, dict) and n.get("stage") == EntityStatus.rejected.value]
        if rejected_notes:
            last = max(rejected_notes, key=lambda n: str(n.get("date") or ""))
            last["stage"] = target.value
            last["stage_label"] = label
        extra["notes"] = notes
        entity.extra_data = extra
        flag_modified(entity, "extra_data")
        entity.status = target
        entity.updated_at = datetime.utcnow()
        done.append(f"{entity_id}:{target.value}")
    db.add(DataMigrationMark(key=SYNC_MARK))
    await db.commit()
    logger.info("DEPARTED_REJECTED_SYNC: переведено %s (кандидат:статус): %s", len(done), ", ".join(done))
    return done
