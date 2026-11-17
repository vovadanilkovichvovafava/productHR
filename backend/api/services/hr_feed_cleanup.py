"""Разово: убрать строки «Сменился HR» из лент карточек (17.11.2026).

16.11.2026 смена HR писалась в ленту каждой воронки кандидата строкой
«Сменился HR: теперь X, раньше Y». Маша (17.11.2026): «это поле нужно, чтобы
видеть историю жизненного цикла (взаимодействия с кандидатом), а не отражать,
кто его вёл из HR — комментарии, ОС, фидбек, личные мысли HR на разных
этапах». С 17.11 смена в ленту не пишется (история смен и отмена — в строке
«HR» карточки, extra_data.hr_changes); здесь убираются уже записанные строки:
переводы истории, на которые ссылаются записи hr_changes, и такие же заметки у
кандидатов без воронок. Сами записи hr_changes остаются (история и отмена).
Маркер `HR_FEED_CLEANUP`.
"""
from __future__ import annotations

import logging

from sqlalchemy import String, cast, delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from ..models.database import DataMigrationMark, Entity, StageTransition

logger = logging.getLogger("hr-analyzer.hr_feed_cleanup")

SYNC_MARK = "hr_change_feed_rows_removed_2026_11_17"
_PREFIX = "Сменился HR:"


async def remove_hr_change_rows_once(db: AsyncSession) -> int:
    if await db.get(DataMigrationMark, SYNC_MARK) is not None:
        return 0
    people = (await db.execute(
        select(Entity).where(cast(Entity.extra_data, String).like("%hr_changes%"))
    )).scalars().all()
    removed = 0
    for e in people:
        ex = dict(e.extra_data) if isinstance(e.extra_data, dict) else {}
        changes = list(ex.get("hr_changes") or [])
        tr_ids = [t for r in changes for t in (r.get("transitions") or [])]
        if tr_ids:
            res = await db.execute(delete(StageTransition).where(
                StageTransition.id.in_(tr_ids),
                StageTransition.comment.like(f"{_PREFIX}%"),
            ))
            removed += res.rowcount or 0
            for r in changes:
                r["transitions"] = []
            ex["hr_changes"] = changes
        notes = list(ex.get("notes") or [])
        kept = [n for n in notes if not str((n or {}).get("text") or "").startswith(_PREFIX)]
        removed += len(notes) - len(kept)
        if len(kept) != len(notes):
            ex["notes"] = kept
        e.extra_data = ex
        flag_modified(e, "extra_data")
    db.add(DataMigrationMark(key=SYNC_MARK))
    await db.commit()
    logger.info("HR_FEED_CLEANUP: убрано строк «Сменился HR» из лент: %s (кандидатов %s)", removed, len(people))
    return removed
