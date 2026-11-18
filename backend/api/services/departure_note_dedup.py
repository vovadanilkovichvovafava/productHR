"""Разово: убрать задвоенные записи «Мы уволили» из лент карточек (18.11.2026).

До cdc67a4 увольнение из карточки «Все кандидаты» (stage_change.depart_entity)
писало ДВЕ строки: перевод заявки в «Отказ» с комментарием «Мы уволили —
причина» и отдельную запись-комментарий «Мы уволили — причина». С cdc67a4
пишется только перевод, а лента показывает его как «Мы уволили — причина», —
поэтому у уже уволенных две одинаковые строки (Мария, 18.11.2026: «а зачем
дублировать?»). Корзиной лишнюю не убрать: удаление любой из двух откатывает
статус.

Убираем ЗАПИСЬ-КОММЕНТАРИЙ, только если у того же кандидата есть перевод
заявки в «Отказ» с тем же текстом («Мы уволили — причина») в пределах двух
минут (без учёта пояса, см. _same_moment) — это и есть пара от одного действия. Перевод остаётся (его корзина
откатывает и заявку, и статус). Уволенных без воронок, у которых запись
единственная, не трогаем. Маркер `DEPARTURE_NOTE_DEDUP`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import String, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from ..models.database import DataMigrationMark, Entity, StageTransition
from .hr_stages import DEPARTED_LABELS

logger = logging.getLogger("hr-analyzer.departure_note_dedup")

SYNC_MARK = "departure_note_dedup_2026_11_18"
PAIR_WINDOW = timedelta(minutes=2)


def _utc(value) -> datetime | None:
    """Время записи ленты (ISO с поясом) и перевода (naive UTC из базы) — в
    одной системе отсчёта."""
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _same_moment(a: datetime, b: datetime) -> bool:
    """Одно действие: разница не больше двух минут С ТОЧНОСТЬЮ ДО ЦЕЛЫХ ЧАСОВ.
    Время записи ленты — UTC из кода, а у перевода его иногда ставит база
    (func.now()) в своём поясе: локально Москва, и пара расходится ровно на
    3 часа. Пояс прод-базы не проверялся — сравниваем без него."""
    diff = abs((a - b).total_seconds())
    if diff > 15 * 3600:
        return False
    rest = diff % 3600
    return min(rest, 3600 - rest) <= PAIR_WINDOW.total_seconds()


def _expected_comment(note: dict) -> str:
    label = note.get("stage_label") or DEPARTED_LABELS.get(note.get("stage"), "")
    text = str(note.get("text") or "").strip()
    return f"{label} — {text}" if text else label


async def dedup_departure_notes_once(db: AsyncSession) -> int:
    if await db.get(DataMigrationMark, SYNC_MARK) is not None:
        return 0
    people = (await db.execute(
        select(Entity).where(or_(*(
            cast(Entity.extra_data, String).like(f"%{status}%") for status in DEPARTED_LABELS
        )))
    )).scalars().all()
    removed = 0
    touched: list[int] = []
    for e in people:
        ex = dict(e.extra_data) if isinstance(e.extra_data, dict) else {}
        notes = list(ex.get("notes") or [])
        candidates = [
            n for n in notes
            if isinstance(n, dict) and n.get("stage") in DEPARTED_LABELS
        ]
        if not candidates:
            continue
        transitions = (await db.execute(
            select(StageTransition.comment, StageTransition.created_at).where(
                StageTransition.entity_id == e.id,
                StageTransition.to_stage == "rejected",
            )
        )).all()
        drop_ids: set[str] = set()
        for n in candidates:
            when = _utc(n.get("date"))
            want = _expected_comment(n)
            if when is None or not want:
                continue
            if any(
                (comment or "").strip() == want
                and (at := _utc(created)) is not None
                and _same_moment(at, when)
                for comment, created in transitions
            ):
                drop_ids.add(str(n.get("id")))
        if not drop_ids:
            continue
        ex["notes"] = [n for n in notes if not (isinstance(n, dict) and str(n.get("id")) in drop_ids)]
        if str(ex.get("pinned_entry_key") or "").removeprefix("n:") in drop_ids:
            ex.pop("pinned_entry_key", None)
        e.extra_data = ex
        flag_modified(e, "extra_data")
        removed += len(drop_ids)
        touched.append(e.id)
    db.add(DataMigrationMark(key=SYNC_MARK))
    await db.commit()
    logger.info(
        "DEPARTURE_NOTE_DEDUP: убрано задвоенных записей «Мы уволили»: %s, кандидаты: %s",
        removed, touched,
    )
    return removed
