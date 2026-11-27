"""Разово: заявки уволенных в ЗАКРЫТЫХ вакансиях (27.11.2026).

Увольнение («Мы уволили» / «Сам уволился») закрывает «Отказом» все живые
заявки человека, но до 27.11.2026 — только в ОТКРЫТЫХ вакансиях. Вакансию
закрывают, когда человека наняли, поэтому его заявка «Перешёл в отдел»
оставалась живой: в списке «Мы уволили», а в карточке зелёный блок «Перешёл в
отдел» (Мария, 27.11.2026, Наумович). Увольнение при этом писало запись в
ленту карточки («Мы уволили — причина»), раз заявок «не нашлось».

Здесь делаем то, что сделало бы увольнение сейчас, и так, чтобы в ленте
осталась ОДНА строка: живая заявка закрывается «Отказом» с тем же текстом,
автором и временем, что у записи об увольнении, а сама запись убирается
(её корзина откатывала бы только статус, а не заявку). Нет записи — заявка
закрывается с пометкой, что это сверка (как departed_apps_sync). Статус
человека не трогаем. Одноразово. Маркер `DEPARTED_CLOSED_VACANCY_SYNC`.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from ..models.database import (
    ApplicationStage, DataMigrationMark, Entity, EntityStatus, EntityType, StageTransition,
    User, Vacancy, VacancyApplication,
)
from .departure_note_dedup import _utc
from .hr_stages import DEPARTED_LABELS

logger = logging.getLogger("hr-analyzer.departed_closed_vacancy_sync")

SYNC_MARK = "departed_closed_vacancy_apps_2026_11_27"
DEPARTED = (EntityStatus.dismissed, EntityStatus.quit)
CLOSED_STAGES = (ApplicationStage.rejected, ApplicationStage.withdrawn)


def _latest_departure_note(entity: Entity) -> dict | None:
    """Последняя запись об увольнении на ТЕКУЩИЙ статус человека."""
    notes = (entity.extra_data or {}).get("notes") or []
    mine = [
        n for n in notes
        if isinstance(n, dict) and n.get("stage") == entity.status.value and _utc(n.get("date"))
    ]
    return max(mine, key=lambda n: _utc(n.get("date"))) if mine else None


async def close_departed_closed_vacancy_apps_once(db: AsyncSession) -> list[str]:
    from .stage_change import move_application

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
        apps = (await db.execute(
            select(VacancyApplication)
            .join(Vacancy, VacancyApplication.vacancy_id == Vacancy.id)
            .where(
                VacancyApplication.entity_id == entity.id,
                Vacancy.deleted_at.is_(None),
                VacancyApplication.stage.notin_(CLOSED_STAGES),
            )
            .order_by(VacancyApplication.id)
        )).scalars().all()
        if not apps:
            continue
        label = DEPARTED_LABELS[entity.status.value]
        note = _latest_departure_note(entity)
        extra_before = dict(entity.extra_data or {})
        if note is not None:
            text = str(note.get("text") or "").strip()
            comment = f"{label} — {text}" if text else label
            when = _utc(note.get("date"))
            author_id = note.get("author_id")
            author = await db.get(User, author_id) if isinstance(author_id, int) else None
        else:
            comment = f"{label} — заявка закрыта при сверке (увольнение было раньше)"
            when, author = None, None
        for app in apps:
            reason_before = app.rejection_reason
            move = await move_application(db, app, ApplicationStage.rejected, changed_by=None, comment=comment)
            if move is None:
                continue
            await db.flush()
            tr = (await db.execute(
                select(StageTransition)
                .where(StageTransition.application_id == app.id)
                .order_by(StageTransition.id.desc())
                .limit(1)
            )).scalar_one_or_none()
            if tr is not None and when is not None:
                tr.created_at = when
                tr.changed_by = author.id if author else None
                app.last_stage_change_at = when
            if note is None:
                app.rejection_reason = reason_before
            fixed.append(f"{entity.id}:{app.id}")
        # Запись об увольнении теперь — перевод заявки; в ленте одна строка.
        if note is not None:
            extra_before["notes"] = [
                n for n in (extra_before.get("notes") or []) if n is not note and n != note
            ]
            if str(extra_before.get("pinned_entry_key") or "").removeprefix("n:") == str(note.get("id")):
                extra_before.pop("pinned_entry_key", None)
        entity.extra_data = extra_before
        flag_modified(entity, "extra_data")
    db.add(DataMigrationMark(key=SYNC_MARK))
    await db.commit()
    logger.info(
        "DEPARTED_CLOSED_VACANCY_SYNC: закрыто заявок %s (кандидат:заявка): %s",
        len(fixed), ", ".join(fixed),
    )
    return fixed
