"""
HR notification service — creates in-app notifications for candidate pipeline events.

Usage:
    from ..services.hr_notifications import notify_new_candidate, notify_stage_change, ...

All functions are fire-and-forget safe: they catch exceptions internally
so that a notification failure never breaks the main operation.
"""
import logging
import re
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import (
    Notification,
    VacancyApplication,
    ApplicationStage,
    Entity,
    User,
    Vacancy,
    OrgMember,
    OrgRole,
)
from .hr_stages import STAGE_LABELS_BY_ENUM

logger = logging.getLogger("hr-analyzer.notifications")

# Подписи этапов — общий справочник (services/hr_stages.py).
STAGE_LABELS = STAGE_LABELS_BY_ENUM


def _stage_label(stage: ApplicationStage) -> str:
    return STAGE_LABELS.get(stage, stage.value)


async def _get_org_admins_and_owners(db: AsyncSession, org_id: int) -> list[int]:
    """Return user IDs of org owners and admins."""
    result = await db.execute(
        select(OrgMember.user_id).where(
            OrgMember.org_id == org_id,
            OrgMember.role.in_([OrgRole.owner, OrgRole.admin]),
        )
    )
    return [row[0] for row in result.all()]


async def _create_notification(
    db: AsyncSession,
    user_id: int,
    type: str,
    title: str,
    message: Optional[str] = None,
    link: Optional[str] = None,
) -> None:
    """Insert a single Notification row."""
    notif = Notification(
        user_id=user_id,
        type=type,
        title=title,
        message=message,
        link=link,
    )
    db.add(notif)


# @-упоминания приходят внутри HTML комментария как
# <span class="hf-mention" data-uid="123">@Имя</span>. Достаём uid'ы отсюда.
_MENTION_UID_RE = re.compile(r'data-uid=["\']?(\d+)', re.IGNORECASE)


async def valid_handover_recipients(db: AsyncSession, org_id: int, user_ids) -> set[int]:
    """Кому можно отдать кандидатов: рекрутёры и админы организации (owner /
    admin / hr), но не наблюдатели — те только смотрят (ревью 26.10.2026: Егору
    и Владу с правами админа и флагом наблюдателя можно было «передать» людей)."""
    from ..models.database import OrgMember, OrgRole
    ids = [u for u in set(user_ids) if u]
    if not ids:
        return set()
    rows = (await db.execute(
        select(OrgMember.user_id).where(
            OrgMember.org_id == org_id,
            OrgMember.user_id.in_(ids),
            OrgMember.role.in_([OrgRole.owner, OrgRole.admin, OrgRole.hr]),
            OrgMember.is_readonly.isnot(True),
        )
    )).scalars().all()
    return set(rows)


async def notify_candidates_handed_over(
    db: AsyncSession, recipient_id: int, from_name: str, count: int, actor_id: Optional[int],
) -> None:
    """Получателю передачи дел: сколько кандидатов перешло и от кого. Имена —
    только в именительном падеже: склонять их мы не умеем."""
    if not recipient_id or not count or recipient_id == actor_id:
        return
    word = "кандидата" if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14 else (
        "кандидат" if count % 10 == 1 and count % 100 != 11 else "кандидатов")
    await _create_notification(
        db, recipient_id, "handover", "Вам передали кандидатов",
        f"Передано {count} {word}. Прежний рекрутёр: {from_name}", "/my-funnels",
    )


async def notify_candidate_taken(
    db: AsyncSession, *, entity_id: int, entity_name: str, vacancy_title: str,
    prev_owner_id: Optional[int], new_owner_id: int, new_owner_name: str,
    actor_id: int, actor_name: str,
) -> None:
    """«Забрать» с переносом: прежнему рекрутёру — что кандидата теперь ведёт
    другой, новому (если отдал кто-то другой) — что ему передали."""
    link = f"/all-candidates?entity={entity_id}"
    if prev_owner_id and prev_owner_id != actor_id:
        await _create_notification(
            db, prev_owner_id, "candidate_taken", "Кандидата забрали",
            f"{entity_name}, воронка «{vacancy_title}». Теперь ведёт: {new_owner_name}", link,
        )
    if new_owner_id != actor_id:
        await _create_notification(
            db, new_owner_id, "candidate_taken", "Вам передали кандидата",
            f"{entity_name}, воронка «{vacancy_title}». Кто передал: {actor_name}", link,
        )


async def notify_comment_mentions(
    db: AsyncSession,
    *,
    text: str,
    author: User,
    entity: Entity,
) -> None:
    """Уведомить @-упомянутых пользователей о комментарии к кандидату.

    Mention'ы едут внутри HTML комментария (data-uid у span.hf-mention).
    Оставляем только реальных членов ТОЙ ЖЕ организации (anti-spam), себя не
    уведомляем. Шлём in-app уведомление «как у анкет» (его подхватит 25-сек
    поллинг во фронте, клик → /all-candidates?entity=ID).

    Только добавляет строки в сессию — коммит на стороне вызывающего, поэтому
    уведомления и сам комментарий сохраняются одной транзакцией.
    """
    try:
        if not text:
            return
        author_id = int(getattr(author, "id", 0) or 0)
        ids: list[int] = []
        seen: set[int] = set()
        for raw in _MENTION_UID_RE.findall(text):
            try:
                uid = int(raw)
            except (TypeError, ValueError):
                continue
            if uid in seen or uid == author_id:  # себя не пингуем
                continue
            seen.add(uid)
            ids.append(uid)
        if not ids:
            return
        # Валидируем org-принадлежность: уведомляем только своих.
        org_id = getattr(entity, "org_id", None)
        if org_id is not None:
            res = await db.execute(
                select(OrgMember.user_id).where(
                    OrgMember.org_id == org_id,
                    OrgMember.user_id.in_(ids),
                )
            )
            valid = {int(row[0]) for row in res.all()}
            ids = [u for u in ids if u in valid]
        if not ids:
            return
        cand = getattr(entity, "name", None)
        suffix = f" к кандидату {cand}" if cand else ""
        author_name = getattr(author, "name", None) or "Коллега"
        link = f"/all-candidates?entity={entity.id}"
        for uid in ids:
            await _create_notification(
                db,
                uid,
                "comment_mentioned",
                "Вас упомянули в комментарии",
                f"{author_name} упомянул(а) вас в комментарии{suffix}",
                link,
            )
    except Exception:
        logger.exception("notify_comment_mentions failed")


# ---------------------------------------------------------------------------
# 1. New candidate added to a vacancy
# ---------------------------------------------------------------------------

async def notify_new_candidate(
    db: AsyncSession,
    entity: Entity,
    vacancy: Vacancy,
    added_by_user: User,
) -> None:
    """Notify relevant users when a new candidate is added to a vacancy.

    Recipients: vacancy creator + org admins/owners (excluding the actor).
    """
    try:
        link = f"/vacancies/{vacancy.id}"
        title = "Новый кандидат"
        message = (
            f"{entity.name} добавлен(а) в вакансию «{vacancy.title}» "
            f"пользователем {added_by_user.name}"
        )

        recipient_ids: set[int] = set()

        # Vacancy creator
        if vacancy.created_by:
            recipient_ids.add(vacancy.created_by)

        # Hiring manager
        if vacancy.hiring_manager_id:
            recipient_ids.add(vacancy.hiring_manager_id)

        # Org admins/owners
        if vacancy.org_id:
            admin_ids = await _get_org_admins_and_owners(db, vacancy.org_id)
            recipient_ids.update(admin_ids)

        # Don't notify the person who performed the action
        recipient_ids.discard(added_by_user.id)

        for uid in recipient_ids:
            await _create_notification(db, uid, "new_candidate", title, message, link)

        if recipient_ids:
            await db.commit()
            logger.info(
                f"notify_new_candidate: entity={entity.id} vacancy={vacancy.id} "
                f"notified {len(recipient_ids)} users"
            )
    except Exception:
        logger.exception("notify_new_candidate failed")
        await db.rollback()


# ---------------------------------------------------------------------------
# 1a. New request (vacancy) created — heads-up to HR admins/owners
# ---------------------------------------------------------------------------

async def notify_new_request(
    db: AsyncSession,
    vacancy: Vacancy,
    created_by_user: User,
) -> None:
    """Уведомить HR-админов/owner'ов о новой заявке.

    Заявки стекаются к админам (они распределяют между рекрутёрами), поэтому при
    создании заявки шлём «Новая заявка» всем owner/admin орга, КРОМЕ создателя
    (если её создал сам админ — себе не дублируем).
    """
    try:
        if not vacancy.org_id:
            return
        recipient_ids = set(await _get_org_admins_and_owners(db, vacancy.org_id))
        recipient_ids.discard(created_by_user.id)
        if not recipient_ids:
            return
        title = "Новая заявка"
        message = f"Создана заявка «{vacancy.title}» — назначьте рекрутёра"
        link = f"/vacancies/{vacancy.id}"
        for uid in recipient_ids:
            await _create_notification(db, uid, "new_request", title, message, link)
        await db.commit()
        logger.info(
            f"notify_new_request: vacancy={vacancy.id} notified {len(recipient_ids)} admins"
        )
    except Exception:
        logger.exception("notify_new_request failed")
        await db.rollback()


# ---------------------------------------------------------------------------
# 1c. Request assigned to recruiter(s) — distribution by admin
# ---------------------------------------------------------------------------

async def notify_request_assigned(
    db: AsyncSession,
    vacancy: Vacancy,
    recruiter_ids,
    assigned_by_user: User,
) -> None:
    """Уведомить ВНОВЬ назначенных рекрутёров, что им распределена заявка.

    Вызывающий передаёт только новых назначенцев (не дёргаем уже назначенных).
    Себя (того, кто назначил) не уведомляем.
    """
    try:
        recipient_ids = {int(u) for u in recruiter_ids if u}
        recipient_ids.discard(assigned_by_user.id)
        if not recipient_ids:
            return
        title = "Вам назначена заявка"
        message = f"Вам назначена заявка «{vacancy.title}»"
        link = f"/vacancies/{vacancy.id}"
        for uid in recipient_ids:
            await _create_notification(db, uid, "request_assigned", title, message, link)
        await db.commit()
        logger.info(
            f"notify_request_assigned: vacancy={vacancy.id} notified {len(recipient_ids)} recruiters"
        )
    except Exception:
        logger.exception("notify_request_assigned failed")
        await db.rollback()


# ---------------------------------------------------------------------------
# 1b. Form answer received (dispatch submitted by candidate)
# ---------------------------------------------------------------------------

async def form_answer_recipients(db: AsyncSession, dispatch, entity) -> list[int]:
    """Кому сообщить об ответе на анкету: отправителю ссылки и ТЕКУЩЕМУ
    рекрутёру кандидата — каждому по одному разу (владелец, 24.10.2026).

    Раньше уведомление уходило только отправителю: забрал кандидата другой
    рекрутёр — об ответе узнавал прежний. «Текущий рекрутёр» — по тому же
    правилу, что метка «HR: …» (services/hr_tags.py: автор живой заявки, без
    автора — владелец воронки, плюс со-рекрутёры); у кандидата без живых
    заявок — тот, за кем карточка. Один и тот же человек — одно уведомление.
    """
    from .hr_tags import compute_hr_tags

    recipients: list[int] = []

    def add(user_id) -> None:
        if user_id and user_id not in recipients:
            recipients.append(user_id)

    add(getattr(dispatch, "created_by", None))
    current = await compute_hr_tags(db, dispatch.entity_id)
    for tag in current:
        add(tag.get("hr_id"))
    if not current and entity is not None:
        add(getattr(entity, "created_by", None))
    return recipients


async def notify_form_submitted(db: AsyncSession, dispatch, entity, form) -> list[int]:
    """Уведомить об ответе кандидата на анкету (см. form_answer_recipients).
    Возвращает, кому ушло, — тем же людям страница шлёт realtime-событие."""
    try:
        recipients = await form_answer_recipients(db, dispatch, entity)
        if not recipients:
            logger.warning(
                "notify_form_submitted: dispatch %s — no sender and no current recruiter, nobody notified",
                getattr(dispatch, "id", None),
            )
            return []
        title = "Ответ на анкету"
        cand = (entity.name if entity else None) or "Кандидат"
        message = f"{cand} заполнил(а) анкету «{form.title}»"
        link = f"/all-candidates?entity={dispatch.entity_id}&tab=anketa"
        for user_id in recipients:
            await _create_notification(db, user_id, "form_submitted", title, message, link)
        await db.commit()
        logger.info("FORM_ANSWER_NOTIFY dispatch=%s entity=%s to=%s", dispatch.id, dispatch.entity_id, recipients)
        return recipients
    except Exception:
        logger.exception("notify_form_submitted failed")
        await db.rollback()
        return []


# ---------------------------------------------------------------------------
# 2. Candidate stage change
# ---------------------------------------------------------------------------

async def notify_stage_change(
    db: AsyncSession,
    application: VacancyApplication,
    entity: Entity,
    from_stage: ApplicationStage,
    to_stage: ApplicationStage,
    changed_by_user: User,
) -> None:
    """Notify relevant users when a candidate moves between pipeline stages.

    Recipients: application creator + vacancy creator/hiring manager (excluding actor).
    """
    try:
        # Load vacancy
        vac_result = await db.execute(
            select(Vacancy).where(Vacancy.id == application.vacancy_id)
        )
        vacancy = vac_result.scalar_one_or_none()
        vacancy_title = vacancy.title if vacancy else "?"

        link = f"/vacancies/{application.vacancy_id}"
        title = "Смена этапа"
        message = (
            f"{entity.name}: {_stage_label(from_stage)} → {_stage_label(to_stage)} "
            f"(вакансия «{vacancy_title}»)"
        )

        recipient_ids: set[int] = set()

        # Application creator
        if application.created_by:
            recipient_ids.add(application.created_by)

        if vacancy:
            if vacancy.created_by:
                recipient_ids.add(vacancy.created_by)
            if vacancy.hiring_manager_id:
                recipient_ids.add(vacancy.hiring_manager_id)

        recipient_ids.discard(changed_by_user.id)

        for uid in recipient_ids:
            await _create_notification(db, uid, "stage_change", title, message, link)

        if recipient_ids:
            await db.commit()
            logger.info(
                f"notify_stage_change: app={application.id} "
                f"{from_stage.value}->{to_stage.value} notified {len(recipient_ids)} users"
            )
    except Exception:
        logger.exception("notify_stage_change failed")
        await db.rollback()


# ---------------------------------------------------------------------------
# 3. Interview scheduled
# ---------------------------------------------------------------------------

async def notify_interview_scheduled(
    db: AsyncSession,
    application: VacancyApplication,
    entity: Entity,
    interview_date: datetime,
    scheduled_by_user: User,
) -> None:
    """Notify the recruiter when an interview date is set for a candidate."""
    try:
        vac_result = await db.execute(
            select(Vacancy).where(Vacancy.id == application.vacancy_id)
        )
        vacancy = vac_result.scalar_one_or_none()
        vacancy_title = vacancy.title if vacancy else "?"

        link = f"/vacancies/{application.vacancy_id}"
        formatted_date = interview_date.strftime("%d.%m.%Y %H:%M")
        title = "Собеседование назначено"
        message = (
            f"Собеседование с {entity.name} назначено на {formatted_date} "
            f"(вакансия «{vacancy_title}»)"
        )

        recipient_ids: set[int] = set()

        if application.created_by:
            recipient_ids.add(application.created_by)

        if vacancy:
            if vacancy.created_by:
                recipient_ids.add(vacancy.created_by)
            if vacancy.hiring_manager_id:
                recipient_ids.add(vacancy.hiring_manager_id)

        recipient_ids.discard(scheduled_by_user.id)

        for uid in recipient_ids:
            await _create_notification(
                db, uid, "interview_scheduled", title, message, link
            )

        if recipient_ids:
            await db.commit()
            logger.info(
                f"notify_interview_scheduled: app={application.id} "
                f"date={formatted_date} notified {len(recipient_ids)} users"
            )
    except Exception:
        logger.exception("notify_interview_scheduled failed")
        await db.rollback()


# ---------------------------------------------------------------------------
# 4. Practice stage started
# ---------------------------------------------------------------------------

async def notify_practice_started(
    db: AsyncSession,
    application: VacancyApplication,
    entity: Entity,
    started_by_user: User,
) -> None:
    """Notify org admins and recruiters when a candidate moves to practice stage."""
    try:
        vac_result = await db.execute(
            select(Vacancy).where(Vacancy.id == application.vacancy_id)
        )
        vacancy = vac_result.scalar_one_or_none()
        vacancy_title = vacancy.title if vacancy else "?"

        link = f"/vacancies/{application.vacancy_id}"
        title = "Практика начата"
        message = (
            f"{entity.name} переведён(а) на этап «Практика» "
            f"(вакансия «{vacancy_title}»)"
        )

        recipient_ids: set[int] = set()

        # Org admins/owners
        org_id = vacancy.org_id if vacancy else None
        if org_id:
            admin_ids = await _get_org_admins_and_owners(db, org_id)
            recipient_ids.update(admin_ids)

        # Application creator (recruiter)
        if application.created_by:
            recipient_ids.add(application.created_by)

        if vacancy:
            if vacancy.created_by:
                recipient_ids.add(vacancy.created_by)
            if vacancy.hiring_manager_id:
                recipient_ids.add(vacancy.hiring_manager_id)

        recipient_ids.discard(started_by_user.id)

        for uid in recipient_ids:
            await _create_notification(
                db, uid, "practice_started", title, message, link
            )

        if recipient_ids:
            await db.commit()
            logger.info(
                f"notify_practice_started: app={application.id} "
                f"notified {len(recipient_ids)} users"
            )
    except Exception:
        logger.exception("notify_practice_started failed")
        await db.rollback()


# ---------------------------------------------------------------------------
# 5. Probation period ending (scheduled check)
# ---------------------------------------------------------------------------

async def notify_probation_ending(
    db: AsyncSession,
    application: VacancyApplication,
    entity: Entity,
    end_date: datetime,
) -> None:
    """Send a reminder notification that a probation period is ending soon."""
    try:
        vac_result = await db.execute(
            select(Vacancy).where(Vacancy.id == application.vacancy_id)
        )
        vacancy = vac_result.scalar_one_or_none()
        vacancy_title = vacancy.title if vacancy else "?"

        link = f"/vacancies/{application.vacancy_id}"
        formatted_date = end_date.strftime("%d.%m.%Y")
        title = "Испытательный срок заканчивается"
        message = (
            f"У {entity.name} заканчивается испытательный срок {formatted_date} "
            f"(вакансия «{vacancy_title}»)"
        )

        recipient_ids: set[int] = set()

        org_id = vacancy.org_id if vacancy else None
        if org_id:
            admin_ids = await _get_org_admins_and_owners(db, org_id)
            recipient_ids.update(admin_ids)

        if application.created_by:
            recipient_ids.add(application.created_by)

        if vacancy:
            if vacancy.hiring_manager_id:
                recipient_ids.add(vacancy.hiring_manager_id)

        for uid in recipient_ids:
            await _create_notification(
                db, uid, "probation_ending", title, message, link
            )

        if recipient_ids:
            await db.commit()
            logger.info(
                f"notify_probation_ending: app={application.id} "
                f"end_date={formatted_date} notified {len(recipient_ids)} users"
            )
    except Exception:
        logger.exception("notify_probation_ending failed")
        await db.rollback()


# ---------------------------------------------------------------------------
# Scheduled task: check all probation endings within 7 days
# ---------------------------------------------------------------------------

async def check_probation_endings(db: AsyncSession) -> int:
    """Find candidates in 'hired' stage whose probation ends within 7 days.

    Probation end date is stored in entity.extra_data["probation_end_date"]
    (ISO format string).  We only send a notification once per application
    by checking for an existing notification with the same type + link.

    Returns the number of new notifications created.
    """
    now = datetime.utcnow()
    seven_days = now + timedelta(days=7)
    count = 0

    try:
        # Get all hired applications
        result = await db.execute(
            select(VacancyApplication, Entity)
            .join(Entity, VacancyApplication.entity_id == Entity.id)
            .where(VacancyApplication.stage == ApplicationStage.hired)
        )
        rows = result.all()

        for application, entity in rows:
            # Check if probation_end_date is set in extra_data
            extra = entity.extra_data or {}
            probation_end_str = extra.get("probation_end_date")
            if not probation_end_str:
                continue

            try:
                probation_end = datetime.fromisoformat(probation_end_str)
            except (ValueError, TypeError):
                continue

            # Only notify if ending within 7 days and not already passed
            if not (now <= probation_end <= seven_days):
                continue

            # Check if we already sent a notification for this
            link = f"/vacancies/{application.vacancy_id}"
            existing = await db.execute(
                select(Notification.id).where(
                    Notification.type == "probation_ending",
                    Notification.link == link,
                    Notification.message.contains(entity.name),
                ).limit(1)
            )
            if existing.scalar_one_or_none() is not None:
                continue

            await notify_probation_ending(db, application, entity, probation_end)
            count += 1

        logger.info(f"check_probation_endings: created {count} notification(s)")
        return count

    except Exception:
        logger.exception("check_probation_endings failed")
        await db.rollback()
        return 0
