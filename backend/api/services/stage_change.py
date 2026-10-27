"""Смена этапа кандидата — ОДНО место на весь HR (рефакторинг 20.10.2026).

До этого этап меняли четыре эндпоинта, и каждый по-своему: один писал историю,
другой нет; один выравнивал под новый этап ВСЕ заявки кандидата (так смена в
одной воронке меняла его во всех — 17.09.2026), другой трогал заявку, только
если она одна; песочница при выходе на практику ставилась в одном и не
ставилась в соседнем; массовый перевод сообщал в уведомлении, что кандидат
пришёл из «Новый», откуда бы он ни шёл. Каждая починка доходила до одного пути.

Здесь два действия:
- move_application — перевести ЗАЯВКУ (воронку) на этап: история, порядок в
  колонке, выход из теневого архива; общий статус кандидата пересчитывает
  settle_entities;
- change_status_without_application — перевести кандидата ВНЕ воронок: заявки
  нет, поэтому перевод живёт записью в ленте (extra_data.notes) с from_status,
  по которому удаление записи возвращает кандидата назад (NOTE_STAGE_UNDO).

Ничего не коммитят. Строку STAGE_CHANGE пишет log_moves ПОСЛЕ коммита: до него
запись врала бы про переход, который мог откатиться.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import (
    ApplicationStage,
    Entity,
    EntityStatus,
    User,
    VacancyApplication,
)
from .stage_transitions import record_transition

logger = logging.getLogger("hr-analyzer.stage_change")

# Предел текста записи ленты — один на комментарии и записи о переводе
# (routes/entities/crud.py берёт его отсюда). Заметки хранят СЫРОЙ HTML из
# редактора (форматирование, @-упоминания) — видимый текст заметно короче.
# Было 5000 — рекрутёры не могли дописать длинный комментарий при смене этапа.
NOTE_TEXT_MAX_LENGTH = 20000


def _value(stage) -> Optional[str]:
    if stage is None:
        return None
    return stage.value if hasattr(stage, "value") else str(stage)


@dataclass
class StageMove:
    application_id: int
    entity_id: int
    vacancy_id: int
    from_stage: Optional[ApplicationStage]
    to_stage: ApplicationStage


async def move_application(
    db: AsyncSession,
    application: VacancyApplication,
    to_stage: ApplicationStage,
    *,
    changed_by: Optional[User],
    comment: Optional[str] = None,
    order: Optional[int] = None,
) -> Optional[StageMove]:
    """Перевести заявку на этап. None — заявка уже на нём (ничего не пишем).

    order — место в колонке; по умолчанию в конец колонки нового этапа.
    """
    if application.stage == to_stage:
        return None
    from_stage = application.stage

    if order is None:
        # Без FOR UPDATE: Postgres не даёт его с агрегатом, а stage_order —
        # только порядок показа, гонка тут допустима. Сама заявка у вызывающего
        # уже заблокирована, поэтому дублей перехода в истории не будет.
        max_order = (await db.execute(
            select(func.max(VacancyApplication.stage_order)).where(
                VacancyApplication.vacancy_id == application.vacancy_id,
                VacancyApplication.stage == to_stage,
            )
        )).scalar() or 0
        order = max_order + 1

    application.stage = to_stage
    application.stage_order = order
    application.last_stage_change_at = datetime.utcnow()

    # Активно работаемый кандидат не должен оставаться в теневом архиве дедупа.
    entity = (await db.execute(
        select(Entity).where(Entity.id == application.entity_id)
    )).scalar()
    if entity is not None and entity.is_archived:
        entity.is_archived = False

    await record_transition(
        db=db,
        application_id=application.id,
        entity_id=application.entity_id,
        from_stage=_value(from_stage),
        to_stage=_value(to_stage),
        changed_by_id=changed_by.id if changed_by else None,
        comment=comment,
    )
    return StageMove(
        application_id=application.id,
        entity_id=application.entity_id,
        vacancy_id=application.vacancy_id,
        from_stage=from_stage,
        to_stage=to_stage,
    )


async def settle_entities(
    db: AsyncSession,
    entity_ids: Iterable[int],
    moves: Iterable[Optional[StageMove]] = (),
) -> None:
    """Пересчитать общий статус кандидатов по их «актуальной» заявке.

    moves — переводы этого действия: только они могут сменить «Уволен» /
    «Уволился» (повторный найм), а не пересчёт по старой заявке.
    """
    from ..routes.vacancies.common import recompute_entity_status

    moved = [m.application_id for m in moves if m is not None]
    await db.flush()  # пересчёт должен увидеть новые этапы
    for entity_id in dict.fromkeys(entity_ids):
        await recompute_entity_status(db, entity_id, moved_app_ids=moved)


def log_moves(
    moves: Iterable[Optional[StageMove]],
    user: Optional[User],
    *,
    via: str,
    expected_entity: Optional[int] = None,
) -> None:
    """STAGE_CHANGE — по одной строке на перевод. Звать после коммита."""
    for m in moves:
        if m is None:
            continue
        logger.info(
            "STAGE_CHANGE: user=%s (%s) app=%s entity=%s vacancy=%s %s -> %s "
            "expected_entity=%s via=%s",
            user.id if user else None, user.name if user else None,
            m.application_id, m.entity_id, m.vacancy_id,
            _value(m.from_stage), _value(m.to_stage), expected_entity, via,
        )


async def change_status_without_application(
    db: AsyncSession,
    entity: Entity,
    new_status: EntityStatus,
    *,
    changed_by: User,
    comment: Optional[str] = None,
    stage_label: Optional[str] = None,
) -> Optional[dict]:
    """Перевести кандидата, у которого нет открытых заявок.

    Запись в ленте и сам перевод — ОДНА транзакция. Раньше фронт слал их двумя
    запросами: упади второй — в ленте остался бы перевод, которого не было.
    Возвращает добавленную запись ленты (None — статус уже такой).
    """
    text = (comment or "").strip()
    if len(text) > NOTE_TEXT_MAX_LENGTH:
        raise ValueError("Comment too long")
    old_status = entity.status
    if old_status == new_status:
        return None

    note = {
        "id": str(uuid.uuid4()),
        "text": text,
        "date": datetime.now(timezone.utc).isoformat(),
        "stage": new_status.value,
        "stage_label": stage_label,
        "author_id": changed_by.id,
        "author_name": changed_by.name,
        # По нему удаление записи вернёт кандидата назад (NOTE_STAGE_UNDO).
        "from_status": _value(old_status),
    }
    extra = dict(entity.extra_data or {})
    extra["notes"] = [*(extra.get("notes") or []), note]
    entity.extra_data = extra
    entity.status = new_status
    entity.updated_at = datetime.utcnow()
    if entity.is_archived:
        entity.is_archived = False

    # Практика ведёт в песочницу — как и при переводе по воронке
    # (recompute_entity_status). Воронки нет, поэтому песочницу не угадываем:
    # человек ждёт в «Без отдела».
    if new_status == EntityStatus.probation:
        try:
            from .board_placements import ensure_sandbox_placement

            await ensure_sandbox_placement(db, entity.id, None, org_id=entity.org_id)
        except Exception:
            logger.exception("Не удалось поставить entity=%s в песочницу", entity.id)

    return note


async def apply_entity_status(
    db: AsyncSession,
    entity: Entity,
    new_status: EntityStatus,
    *,
    changed_by: User,
    unarchive: bool = True,
) -> Optional[StageMove]:
    """Статус, поставленный кандидату НАПРЯМУЮ (правка карточки, PATCH /status).

    Раньше это были две копии в routes/entities/crud.py, и разъехались они так:
    песочница при выходе на практику и выход из теневого архива были только в
    PATCH /status, а сохранение карточки со статусом «Практика» человека в
    песочницу не ставило. Теперь одно правило:
    - статус ставится кандидату;
    - если у него ровно одна открытая заявка — она переводится тем же
      move_application (история, отмена корзиной). Заявок несколько — не
      трогаем ни одну: непонятно, в какой воронке менять этап;
    - практика ведёт в песочницу (воронка одна — её песочница, иначе «Без отдела»).
    Возвращает перевод заявки для log_moves (или None).
    """
    from ..models.database import STATUS_SYNC_MAP, Vacancy, VacancyStatus

    entity.status = new_status
    if unarchive and entity.is_archived:
        entity.is_archived = False

    open_apps = (await db.execute(
        select(VacancyApplication)
        .join(Vacancy, VacancyApplication.vacancy_id == Vacancy.id)
        .where(
            VacancyApplication.entity_id == entity.id,
            Vacancy.status != VacancyStatus.closed,
            Vacancy.deleted_at.is_(None),
        )
    )).scalars().all()

    move = None
    if new_status in STATUS_SYNC_MAP and len(open_apps) == 1:
        move = await move_application(
            db, open_apps[0], STATUS_SYNC_MAP[new_status], changed_by=changed_by,
        )

    if new_status == EntityStatus.probation:
        try:
            from .board_placements import ensure_sandbox_placement

            vacancy = None
            if len(open_apps) == 1:
                vacancy = await db.get(Vacancy, open_apps[0].vacancy_id)
            await ensure_sandbox_placement(db, entity.id, vacancy, org_id=entity.org_id)
        except Exception:
            logger.exception("Не удалось поставить entity=%s в песочницу", entity.id)
    return move


def log_out_of_funnel(user: User, entity_id: int, note: Optional[dict]) -> None:
    """STAGE_CHANGE для перевода вне воронок. Звать после коммита."""
    if not note:
        return
    logger.info(
        "STAGE_CHANGE: user=%s (%s) app=- entity=%s vacancy=- %s -> %s via=out_of_funnel",
        user.id, user.name, entity_id, note.get("from_status"), note.get("stage"),
    )
