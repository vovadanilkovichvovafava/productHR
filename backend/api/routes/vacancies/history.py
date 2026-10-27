"""
Stage transition history endpoints for vacancy applications.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel

from .common import (
    logger, get_db, VacancyApplication, Vacancy, User,
    check_vacancy_access, can_access_vacancy, recompute_entity_status,
    is_org_admin_or_owner,
)
from ...models.database import StageTransition, ApplicationStage, Entity
from ...services.auth import get_user_org

router = APIRouter()


class StageTransitionResponse(BaseModel):
    id: int
    application_id: int
    entity_id: int
    from_stage: Optional[str] = None
    to_stage: str
    changed_by: Optional[int] = None
    changed_by_name: Optional[str] = None
    comment: Optional[str] = None
    created_at: datetime
    # Правка комментария: в строке остаётся автор и время написания, а это —
    # для пометки «Изменено» и подсказки «кто и когда правил».
    edited_at: Optional[datetime] = None
    edited_by_name: Optional[str] = None


class StageTransitionUpdate(BaseModel):
    """Правка комментария к переводу. Сам этап не трогаем: для этого есть
    смена этапа, а тут — исправить текст («созвон в четверг» → «в пятницу»)."""
    comment: Optional[str] = None


class PinUpdate(BaseModel):
    """Закреп записи ленты. null — снять закреп. Ключ строки: "e:<id>" —
    перевод, "n:<uuid>" — комментарий."""
    entry_key: Optional[str] = None

    class Config:
        from_attributes = True


async def get_application_history(
    application_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_vacancy_access),
) -> List[StageTransitionResponse]:
    """Get all stage transitions for an application, ordered by created_at desc."""
    org = await get_user_org(current_user, db)

    # Get the application
    app_result = await db.execute(
        select(VacancyApplication).where(VacancyApplication.id == application_id)
    )
    application = app_result.scalar()
    # Скоуп по воронкам: история заявки из чужой воронки не читается.
    if application is not None:
        from ...services.vacancy_scope import ensure_vacancy_visible
        await ensure_vacancy_visible(application.vacancy_id, current_user, db)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    # Get the vacancy for access check
    vacancy_result = await db.execute(
        select(Vacancy).where(Vacancy.id == application.vacancy_id)
    )
    vacancy = vacancy_result.scalar()
    if vacancy and not await can_access_vacancy(vacancy, current_user, org, db):
        raise HTTPException(status_code=403, detail="Access denied to this vacancy")

    # Fetch transitions
    result = await db.execute(
        select(StageTransition)
        .where(StageTransition.application_id == application_id)
        .order_by(StageTransition.created_at.desc())
    )
    transitions = result.scalars().all()

    # Bulk load user names for changed_by / edited_by
    user_ids = [t.changed_by for t in transitions if t.changed_by]
    user_ids += [t.edited_by for t in transitions if t.edited_by]
    user_names = {}
    if user_ids:
        users_result = await db.execute(
            select(User.id, User.name).where(User.id.in_(user_ids))
        )
        user_names = {row[0]: row[1] for row in users_result.all()}

    return [
        StageTransitionResponse(
            id=t.id,
            application_id=t.application_id,
            entity_id=t.entity_id,
            from_stage=t.from_stage,
            to_stage=t.to_stage,
            changed_by=t.changed_by,
            changed_by_name=user_names.get(t.changed_by),
            comment=t.comment,
            created_at=t.created_at,
            edited_at=t.edited_at,
            edited_by_name=user_names.get(t.edited_by),
        )
        for t in transitions
    ]


async def _load_application_for_history(
    application_id: int, db: AsyncSession, current_user: User,
) -> VacancyApplication:
    """Заявка + проверка доступа к её воронке. Один и тот же код у правки,
    удаления и закрепа — разъезжаться этим проверкам нельзя."""
    org = await get_user_org(current_user, db)

    application = (await db.execute(
        select(VacancyApplication).where(VacancyApplication.id == application_id)
    )).scalar()
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    vacancy = (await db.execute(
        select(Vacancy).where(Vacancy.id == application.vacancy_id)
    )).scalar()
    if vacancy and not await can_access_vacancy(vacancy, current_user, org, db):
        raise HTTPException(status_code=403, detail="Access denied to this vacancy")
    return application


async def update_application_history(
    application_id: int,
    history_id: int,
    data: StageTransitionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_vacancy_access),
):
    """Поправить комментарий к переводу.

    Правит автор записи или админ/владелец орга — как у комментариев карточки,
    чтобы правила не разъезжались. Автор и время НАПИСАНИЯ остаются прежними:
    в ленте показывается тот, кто написал, а «Изменено» и подсказка «кто и
    когда правил» берутся из edited_at/edited_by (24.09.2026, требование
    рекрутёров).
    """
    org = await get_user_org(current_user, db)
    application = await _load_application_for_history(application_id, db, current_user)

    transition = (await db.execute(
        select(StageTransition).where(
            StageTransition.id == history_id,
            StageTransition.application_id == application_id,
        )
    )).scalar()
    if not transition:
        raise HTTPException(status_code=404, detail="History entry not found")

    is_author = transition.changed_by == current_user.id
    if not (is_author or await is_org_admin_or_owner(current_user, org, db)):
        raise HTTPException(
            status_code=403, detail="Редактировать можно только свою запись",
        )

    transition.comment = (data.comment or "").strip() or None
    # Время правки берём из ТОГО ЖЕ источника, что и created_at записи (часы
    # БД, func.now()). С datetime.utcnow() два времени одной строки считались
    # по разным часам: если БД живёт не в UTC, «Изменено» оказывалось раньше
    # самой записи — так и вылезло на локальной машине (24.09.2026).
    transition.edited_at = func.now()
    transition.edited_by = current_user.id
    await db.commit()
    await db.refresh(transition)

    logger.info(
        "HISTORY_EDIT: user=%s app=%s entity=%s запись %s — комментарий изменён",
        current_user.id, application.id, application.entity_id, transition.id,
    )
    return {
        "success": True,
        "comment": transition.comment,
        "edited_at": transition.edited_at,
        "edited_by_name": current_user.name,
    }


async def set_pinned_entry(
    application_id: int,
    data: PinUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_vacancy_access),
):
    """Закрепить запись ленты наверху — или снять закреп (entry_key = null).

    Закреп ОДИН на воронку и общий для всех: это рабочая пометка по кандидату,
    а не личная закладка. Кандидат в двух воронках получает два закрепа —
    каждый в своём блоке карточки (решение владельца 24.09.2026).
    """
    application = await _load_application_for_history(application_id, db, current_user)

    key = (data.entry_key or "").strip() or None
    if key and len(key) > 64:
        raise HTTPException(status_code=400, detail="Слишком длинный ключ записи")

    application.pinned_entry_key = key
    await db.commit()

    logger.info(
        "ENTRY_PIN: user=%s app=%s entity=%s -> %s",
        current_user.id, application.id, application.entity_id, key or "снят",
    )
    return {"success": True, "pinned_entry_key": key}


async def delete_application_history(
    application_id: int,
    history_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_vacancy_access),
):
    """Удалить запись истории этапов.

    ПОСЛЕДНЯЯ запись = сам перевод, которым кандидат попал на текущий этап:
    удаляя её, рекрутёр отменяет ошибочный перевод, поэтому заявка едет обратно
    на from_stage (запрос рекрутёров 2026-09-23; до этого этап оставался на
    месте, и карточка Махровой висела в «Практике» без единой записи о том, как
    туда попала).

    СТАРЫЕ записи (выше по ленте) — только чистка лога: этап не трогаем, иначе
    удаление записи из середины истории отправляло бы кандидата в прошлое.
    """
    org = await get_user_org(current_user, db)

    # FOR UPDATE: откат этапа и одновременный перевод той же заявки иначе
    # затирали друг друга (кто записал последним, тот и прав).
    app_result = await db.execute(
        select(VacancyApplication).where(VacancyApplication.id == application_id).with_for_update()
    )
    application = app_result.scalar()
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    vacancy_result = await db.execute(
        select(Vacancy).where(Vacancy.id == application.vacancy_id)
    )
    vacancy = vacancy_result.scalar()
    if vacancy and not await can_access_vacancy(vacancy, current_user, org, db):
        raise HTTPException(status_code=403, detail="Access denied to this vacancy")
    # Удаление последней записи — это смена этапа (откат): правило то же, что у
    # перевода, — кто видит вакансию, тот и откатывает (21.10.2026).

    tr_result = await db.execute(
        select(StageTransition).where(
            StageTransition.id == history_id,
            StageTransition.application_id == application_id,
        )
    )
    transition = tr_result.scalar()
    if not transition:
        raise HTTPException(status_code=404, detail="History entry not found")

    # Самая свежая запись заявки. id вторым ключом: у импортов и быстрых
    # переводов created_at совпадает до секунды.
    latest = (await db.execute(
        select(StageTransition)
        .where(StageTransition.application_id == application_id)
        .order_by(StageTransition.created_at.desc(), StageTransition.id.desc())
        .limit(1)
    )).scalar()

    current_stage = application.stage.value if application.stage else None
    rollback_stage: Optional[ApplicationStage] = None
    if (
        latest is not None
        and latest.id == transition.id
        and transition.from_stage
        and transition.to_stage == current_stage
    ):
        # from_stage мог быть кастомным/устаревшим ключом — тогда отката нет,
        # просто удаляем запись (лучше оставить этап, чем уронить 500).
        try:
            rollback_stage = ApplicationStage(transition.from_stage)
        except ValueError:
            rollback_stage = None

    if rollback_stage is not None:
        max_order = (await db.execute(
            select(func.max(VacancyApplication.stage_order)).where(
                VacancyApplication.vacancy_id == application.vacancy_id,
                VacancyApplication.stage == rollback_stage,
            )
        )).scalar() or 0
        application.stage = rollback_stage
        application.stage_order = max_order + 1
        application.last_stage_change_at = datetime.utcnow()
        await db.flush()
        # Отмена перевода — тоже движение по воронке (см. recompute_entity_status).
        # undo=True: человек возвращается ровно туда, откуда его подняли, —
        # иначе откат перевода в отдел давал «Уволен» вместо «Отказа»
        # (Саленик, 21.10.2026: карточка «Отказ», доска «Перевёлся»).
        await recompute_entity_status(
            db, application.entity_id, moved_app_ids=[application.id], undo=True,
        )
        logger.info(
            "HISTORY_UNDO: user=%s app=%s entity=%s запись %s (%s -> %s) удалена, "
            "заявка возвращена на %s",
            current_user.id, application.id, application.entity_id, transition.id,
            transition.from_stage, transition.to_stage, rollback_stage.value,
        )
    else:
        logger.info(
            "HISTORY_DELETE: user=%s app=%s entity=%s запись %s (%s -> %s) удалена, "
            "этап заявки остаётся %s",
            current_user.id, application.id, application.entity_id, transition.id,
            transition.from_stage, transition.to_stage, current_stage,
        )

    # Закреп должен уйти вместе с записью: иначе pinned_entry_key указывает в
    # пустоту (прод 28.09.2026 — «закрепил, удалил не открепив»), а закрепить
    # что-то другое уже не получится, пока не тронешь закреп руками.
    if application.pinned_entry_key == f"e:{transition.id}":
        application.pinned_entry_key = None
        logger.info(
            "ENTRY_PIN снят вместе с записью: app=%s entry=e:%s",
            application.id, transition.id,
        )

    await db.delete(transition)
    await db.commit()

    entity_status = (await db.execute(
        select(Entity.status).where(Entity.id == application.entity_id)
    )).scalar()
    return {
        "success": True,
        # Фронт по этим полям переставляет карточку НА МЕСТЕ, без перезагрузки.
        "rolled_back": rollback_stage is not None,
        "stage": application.stage.value if application.stage else None,
        "entity_status": entity_status.value if entity_status else None,
    }
