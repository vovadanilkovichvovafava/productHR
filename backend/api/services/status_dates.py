"""Дата перевода кандидата на ТЕКУЩИЙ статус.

Список «Все кандидаты» показывал рядом с этапом дату ДОБАВЛЕНИЯ карточки, и
рядом со статусом она выглядела случайной: «какие-то кандидаты стоят под
актуальным статусом, а какие-то — просто под рандомными числами» (Мария,
20.10.2026). Нужна дата, когда человека перевели на тот статус, под которым он
сейчас стоит; по ней же список сортируется — свежие сверху («отказали 09.10
должен стоять перед тем, кому отказали 08.10»).

Переводы лежат в ДВУХ местах, поэтому смотрим оба:
  • `stage_transitions` — история заявки, у кандидата в воронке;
  • записи о переводе в `extra_data.notes` (поле `stage`) — у кандидата ВНЕ
    воронок; такую же пишет доска «Штат».
Берём самую свежую запись, которая описывает текущий статус: этап заявки
отображается в статус кандидата через STAGE_SYNC_MAP, у записи в карточке
статус лежит прямо в поле `stage`.

Ничего не нашли — возвращаем None (статус мог быть выставлен правкой карточки,
она истории не пишет, см. «Известные долги» в CLAUDE.md). Тогда список
показывает дату добавления, как раньше.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import STAGE_SYNC_MAP, StageTransition
from .hr_stages import board_column

logger = logging.getLogger("hr-analyzer.status-dates")

# Сколько id кладём в один IN: на проде кандидатов под тысячу, но при поиске
# подмешивается архив, и запрос не должен распухать безгранично.
_CHUNK = 2000

# Этап заявки → статус кандидата, строками: to_stage хранится как VARCHAR.
_STAGE_TO_STATUS: Dict[str, str] = {
    stage.value: status.value for stage, status in STAGE_SYNC_MAP.items()
}


def _naive_utc(value: Any) -> Optional[datetime]:
    """К «наивному» UTC: в базе время без зоны, в заметках — ISO со смещением."""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _note_status_date(extra: Any, status: str) -> Optional[datetime]:
    """Самая свежая запись о переводе на ЭТОТ статус из ленты карточки."""
    if not isinstance(extra, dict):
        return None
    best: Optional[datetime] = None
    for note in extra.get("notes") or []:
        if not isinstance(note, dict) or note.get("stage") != status:
            continue
        at = _naive_utc(note.get("date"))
        if at is not None and (best is None or at > best):
            best = at
    return best


async def status_changed_at_map(db: AsyncSession, entities: Iterable[Any]) -> Dict[int, datetime]:
    """{entity_id: когда перевели на текущий статус}. Без записи — ключа нет."""
    items = [e for e in entities if getattr(e, "id", None) is not None]
    if not items:
        return {}

    status_of: Dict[int, str] = {}
    for e in items:
        st = getattr(e, "status", None)
        status_of[e.id] = st.value if hasattr(st, "value") else str(st or "")

    out: Dict[int, datetime] = {}

    ids: List[int] = [e.id for e in items]
    for start in range(0, len(ids), _CHUNK):
        chunk = ids[start:start + _CHUNK]
        rows = await db.execute(
            select(
                StageTransition.entity_id,
                StageTransition.to_stage,
                func.max(StageTransition.created_at),
            )
            .where(StageTransition.entity_id.in_(chunk))
            .group_by(StageTransition.entity_id, StageTransition.to_stage)
        )
        for ent_id, to_stage, at in rows.all():
            # Сравниваем по вкладке, а не по статусу дословно: уволенного доска
            # переводит в воронке в «Отказ» (запись истории — на rejected), а
            # статус у него «уволен» — это та же вкладка «Отказ» (hr_stages).
            stage_status = _STAGE_TO_STATUS.get(to_stage)
            if stage_status is None or board_column(stage_status) != board_column(status_of.get(ent_id, "")):
                continue
            when = _naive_utc(at)
            if when is not None and (ent_id not in out or when > out[ent_id]):
                out[ent_id] = when

    for e in items:
        when = _note_status_date(getattr(e, "extra_data", None), status_of.get(e.id, ""))
        if when is not None and (e.id not in out or when > out[e.id]):
            out[e.id] = when

    return out
