"""Передача всего владения одного рекрутёра другому («Передать всё от X к Y»).

Сценарий: рекрутёр увольняется, его аккаунт удалят. При удалении все ссылки на
него обнуляются (created_by→NULL у заявок/вакансий/кандидатов), и работа
осиротеет. Поэтому ПЕРЕД удалением админ передаёт всё владение живому рекрутёру:

  • заявки (VacancyApplication.created_by)  X → Y  — это же чинит HR-метки,
    т.к. они производны от created_by заявок (пересчитываем sync_for_entity);
  • вакансии: created_by, hiring_manager_id, а также участие в общей воронке
    (assigned_to / extra_data.accepted_by / dismissed_by)  X → Y;
  • кандидаты (Entity.created_by)  X → Y  — «мои кандидаты» уходящего.

Историю (кто менял этап, автор старых комментариев) НЕ переписываем — это факты,
а имя автора у заметок хранится снимком и переживает удаление.

Всё строго в рамках ОДНОЙ организации.
"""
import logging
import re
from typing import Dict, List, Optional, Set

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import ApplicationCoRecruiter, Entity, EntityType, Vacancy, VacancyApplication

logger = logging.getLogger("hr-analyzer.handover")


def norm_title(title: Optional[str]) -> str:
    """Название воронки для сравнения «та же вакансия»: без регистра, «ё», лишних пробелов."""
    return re.sub(r"\s+", " ", (title or "").lower().replace("ё", "е")).strip()


def is_vacancy_participant(v: Vacancy, uid: int) -> bool:
    """Человек работает в воронке: создатель, ведущий, назначен или «взял»,
    и при этом не вышел из неё (dismissed_by)."""
    ed = v.extra_data or {}
    if uid in (ed.get("dismissed_by") or []):
        return False
    return (
        v.created_by == uid or v.hiring_manager_id == uid
        or uid in (v.assigned_to or []) or uid in (ed.get("accepted_by") or [])
        or bool(getattr(v, "assigned_to_all", False))
    )


def _own_live_apps_subquery(from_user_id: int):
    """Кандидаты, у которых есть заявка уходящего в живой воронке: они уедут
    вместе с воронками. Остальные его карточки — «без воронки» для передачи."""
    return (
        select(VacancyApplication.entity_id)
        .join(Vacancy, Vacancy.id == VacancyApplication.vacancy_id)
        .where(VacancyApplication.created_by == from_user_id, Vacancy.deleted_at.is_(None))
    )


async def _move_side_links(
    db: AsyncSession, from_user_id: int, to_user_id: int, vacancy_ids,
) -> Set[int]:
    """То, что тоже даёт метку «HR: X», но не лежит в created_by заявки
    (до 20.10.2026 после передачи такие метки так и оставались на уходящем):

    • заявки БЕЗ автора (NULL) в вакансиях X — их HR = владелец вакансии;
    • строки со-рекрутёра X — переходят на Y (если Y там уже есть — снимаются).

    Возвращает карточки, которым пересчитать метки. Вызывать ДО смены
    владельца вакансии.
    """
    affected = set((await db.execute(
        select(VacancyApplication.entity_id)
        .join(Vacancy, Vacancy.id == VacancyApplication.vacancy_id)
        .where(
            VacancyApplication.vacancy_id.in_(vacancy_ids),
            VacancyApplication.created_by.is_(None),
            Vacancy.created_by == from_user_id,
        )
    )).scalars().all())
    rows = (await db.execute(
        select(ApplicationCoRecruiter, VacancyApplication)
        .join(VacancyApplication, VacancyApplication.id == ApplicationCoRecruiter.application_id)
        .where(
            ApplicationCoRecruiter.user_id == from_user_id,
            VacancyApplication.vacancy_id.in_(vacancy_ids),
        )
    )).all()
    for co, app in rows:
        affected.add(app.entity_id)
        has_to = (await db.execute(
            select(ApplicationCoRecruiter.id).where(
                ApplicationCoRecruiter.application_id == app.id,
                ApplicationCoRecruiter.user_id == to_user_id,
            )
        )).scalar() is not None
        if has_to or app.created_by == to_user_id:
            await db.delete(co)
        else:
            co.user_id = to_user_id
    return affected


def _participant_of(v: Vacancy, uid: int) -> bool:
    """Уходящий — участник этой воронки: создатель / ведущий менеджер / назначен."""
    if v.created_by == uid or v.hiring_manager_id == uid:
        return True
    if uid in (v.assigned_to or []):
        return True
    acc = (v.extra_data or {}).get("accepted_by") or []
    return uid in acc


async def get_handover_summary(
    db: AsyncSession, org_id: int, from_user_id: int
) -> Dict[str, object]:
    """Что можно передать от уходящего: его воронки (с числом ЕГО кандидатов) +
    кандидаты ВНЕ воронок. Для UI раздельной передачи."""
    # Только живые воронки: мягко удалённые (deleted_at) не показываем.
    vacs = (
        await db.execute(
            select(Vacancy).where(
                Vacancy.org_id == org_id, Vacancy.deleted_at.is_(None)
            )
        )
    ).scalars().all()

    # Число кандидатов уходящего (created_by) в каждой вакансии — то, что уедет.
    own_counts_rows = (
        await db.execute(
            select(VacancyApplication.vacancy_id, func.count(VacancyApplication.id))
            .join(Vacancy, Vacancy.id == VacancyApplication.vacancy_id)
            .where(
                Vacancy.org_id == org_id,
                VacancyApplication.created_by == from_user_id,
            )
            .group_by(VacancyApplication.vacancy_id)
        )
    ).all()
    own_counts = {vid: n for vid, n in own_counts_rows}

    total_counts = {vid: n for vid, n in (await db.execute(
        select(VacancyApplication.vacancy_id, func.count(VacancyApplication.id))
        .join(Vacancy, Vacancy.id == VacancyApplication.vacancy_id)
        .where(Vacancy.org_id == org_id, Vacancy.deleted_at.is_(None))
        .group_by(VacancyApplication.vacancy_id)
    )).all()}
    by_title: Dict[str, List[Vacancy]] = {}
    for v in vacs:
        by_title.setdefault(norm_title(v.title), []).append(v)

    funnels: List[Dict[str, object]] = []
    for v in vacs:
        if _participant_of(v, from_user_id) or v.id in own_counts:
            # Такие же воронки (то же название) — куда можно влить кандидатов
            # уходящего у получателя. Окно само выбирает по получателю.
            matches = [
                {
                    "vacancy_id": m.id,
                    "title": m.title,
                    "status": m.status.value if m.status else None,
                    "candidates": int(total_counts.get(m.id, 0)),
                    "participants": sorted({
                        u for u in (
                            [m.created_by, m.hiring_manager_id]
                            + list(m.assigned_to or [])
                            + list((m.extra_data or {}).get("accepted_by") or [])
                        ) if u and is_vacancy_participant(m, u)
                    }),
                }
                for m in by_title.get(norm_title(v.title), [])
                if m.id != v.id
            ]
            funnels.append({
                "vacancy_id": v.id,
                "title": v.title,
                "status": v.status.value if v.status else None,
                "candidates": int(own_counts.get(v.id, 0)),
                # Кто в ней работает: если получатель уже здесь, сливать незачем —
                # это и так его воронка, второй копии у него не появится.
                "participants": sorted({
                    u for u in (
                        [v.created_by, v.hiring_manager_id]
                        + list(v.assigned_to or [])
                        + list((v.extra_data or {}).get("accepted_by") or [])
                    ) if u and is_vacancy_participant(v, u)
                }),
                "matches": matches,
            })
    # Сначала воронки с кандидатами уходящего (их и передают в первую очередь).
    funnels.sort(key=lambda f: (-int(f["candidates"]), (f["title"] or "").lower()))

    # Карточки уходящего, которые не уедут вместе с его воронками: без заявок,
    # только в чужих воронках, только в удалённых. Раньше считались лишь «без
    # единой заявки», и остальные так и оставались за ушедшим (ревью 26.10.2026).
    pool = (
        await db.execute(
            select(func.count(Entity.id)).where(
                Entity.org_id == org_id,
                Entity.type == EntityType.candidate,
                Entity.created_by == from_user_id,
                ~Entity.id.in_(_own_live_apps_subquery(from_user_id)),
            )
        )
    ).scalar() or 0

    return {"funnels": funnels, "pool_candidates": int(pool)}


async def _reassign_one_vacancy(
    db: AsyncSession, org_id: int, from_user_id: int, to_user_id: int, vacancy: Vacancy,
    counts: Dict[str, int], affected: Set[int],
) -> None:
    """Перенести владение ОДНОЙ воронкой X → Y: заявки X, кандидаты этих заявок,
    авторство/участие вакансии."""
    eids = (
        await db.execute(
            select(VacancyApplication.entity_id).where(
                VacancyApplication.vacancy_id == vacancy.id,
                VacancyApplication.created_by == from_user_id,
            )
        )
    ).scalars().all()
    affected.update(eids)
    affected.update(await _move_side_links(db, from_user_id, to_user_id, [vacancy.id]))

    res = await db.execute(
        update(VacancyApplication)
        .where(
            VacancyApplication.vacancy_id == vacancy.id,
            VacancyApplication.created_by == from_user_id,
        )
        .values(created_by=to_user_id)
    )
    counts["applications"] += res.rowcount or 0

    if eids:
        res = await db.execute(
            update(Entity)
            .where(Entity.id.in_(eids), Entity.created_by == from_user_id)
            .values(created_by=to_user_id)
        )
        counts["candidates"] += res.rowcount or 0

    if vacancy.created_by == from_user_id:
        vacancy.created_by = to_user_id
    if vacancy.hiring_manager_id == from_user_id:
        vacancy.hiring_manager_id = to_user_id

    # Получатель СТАНОВИТСЯ ведущим воронки: убираем X, добавляем Y в assigned_to
    # И в accepted_by. accepted_by критичен — сайдбар «Мои вакансии» группирует
    # строго по нему; без Y там воронка «повисла бы» в «Без исполнителя» и
    # визуально перенос был бы незаметен.
    at = [u for u in (vacancy.assigned_to or []) if u != from_user_id]
    if to_user_id not in at:
        at.append(to_user_id)
    vacancy.assigned_to = at

    ed = dict(vacancy.extra_data or {})
    acc = [u for u in (ed.get("accepted_by") or []) if u != from_user_id]
    if to_user_id not in acc:
        acc.append(to_user_id)
    ed["accepted_by"] = acc
    ed["dismissed_by"] = [
        u for u in (ed.get("dismissed_by") or []) if u not in (from_user_id, to_user_id)
    ]
    vacancy.extra_data = ed

    counts["vacancies"] += 1


async def reassign_recruiter_split(
    db: AsyncSession,
    org_id: int,
    from_user_id: int,
    assignments: List[Dict[str, Optional[int]]],
    pool_to_user_id: Optional[int] = None,
    *,
    dry_run: bool = False,
    acted_by: Optional[int] = None,
) -> Dict[str, object]:
    """Раздельная передача: каждую воронку — своему получателю, кандидатов вне
    воронок — отдельному. assignments: [{vacancy_id, to_user_id, merge_into_vacancy_id?}].

    merge_into_vacancy_id — такая же воронка получателя: кандидаты уходящего
    вливаются в неё (vacancy_merge с «более свежим этапом»), а не появляется
    вторая одинаковая воронка (владелец, 26.10.2026). Если в воронке уходящего
    работает кто-то ещё, переезжают только заявки уходящего, воронка остаётся.

    dry_run — ничего не меняя, вернуть итог для окна: сколько кому перейдёт и
    кто уже есть во вливаемой воронке (с этапом, который останется).
    """
    from .vacancy_merge import merge_vacancies

    counts: Dict[str, object] = {"vacancies": 0, "applications": 0, "candidates": 0, "merged": 0}
    per_recipient: Dict[int, int] = {}
    merges: List[Dict[str, object]] = []
    affected: Set[int] = set()

    # Воронки, которые сами вливаются в этом запросе: в них ничего не вливаем,
    # иначе две копии сливались бы друг в друга.
    merging_ids = {a.get("vacancy_id") for a in assignments if a.get("merge_into_vacancy_id")}
    for a in assignments:
        vid = a.get("vacancy_id")
        to = a.get("to_user_id")
        into = a.get("merge_into_vacancy_id")
        if not vid or not to or to == from_user_id:
            continue
        v = await db.get(Vacancy, vid)
        if v is None or v.org_id != org_id or v.deleted_at is not None:
            continue
        own_ids = (await db.execute(
            select(VacancyApplication.id).where(
                VacancyApplication.vacancy_id == v.id,
                VacancyApplication.created_by == from_user_id,
            )
        )).scalars().all()
        per_recipient[to] = per_recipient.get(to, 0) + len(own_ids)

        target = await db.get(Vacancy, into) if into else None
        if target is not None and (
            target.org_id != org_id or target.deleted_at is not None or target.id == v.id
            or target.id in merging_ids
        ):
            target = None

        if dry_run:
            if target is not None:
                rep = await merge_vacancies(
                    db, org_id, v.id, target.id, dry_run=True,
                    only_application_ids=own_ids, prefer_fresher=True,
                )
                merges.append({
                    "vacancy_id": v.id, "into_vacancy_id": target.id, "into_title": target.title,
                    "to_user_id": to,
                    "overlapping": [
                        {"entity_id": o["entity_id"], "name": o["name"], "stage": o["result_stage"]}
                        for o in rep["overlapping"]
                    ],
                })
            continue

        was_participant = is_vacancy_participant(v, to)
        await _reassign_one_vacancy(db, org_id, from_user_id, to, v, counts, affected)
        if target is not None:
            # Работает ли в воронке кто-то кроме получателя — тогда переносим
            # только заявки уходящего (они уже записаны на получателя).
            others = (await db.execute(
                select(func.count(VacancyApplication.id)).where(
                    VacancyApplication.vacancy_id == v.id,
                    VacancyApplication.id.notin_(list(own_ids) or [-1]),
                )
            )).scalar() or 0
            await db.flush()
            # Слияние сбрасывает кэш сессии (expire_all) — номера и название
            # запоминаем до него, а воронку перечитываем после.
            v_id, target_id, target_title = v.id, target.id, target.title
            rep = await merge_vacancies(
                db, org_id, v_id, target_id, dry_run=False, merged_by=acted_by,
                only_application_ids=own_ids if others else None,
                prefer_fresher=True, commit=False,
            )
            v = await db.get(Vacancy, v_id, populate_existing=True)
            if others and not was_participant:
                # Воронка остаётся у других, а заявки получателя уехали в его
                # воронку — участником этой копии ему быть незачем, иначе в
                # «Мои вакансии» снова две одинаковые.
                v.assigned_to = [u for u in (v.assigned_to or []) if u != to]
                ved = dict(v.extra_data or {})
                ved["accepted_by"] = [u for u in (ved.get("accepted_by") or []) if u != to]
                v.extra_data = ved
            counts["merged"] = int(counts["merged"]) + 1
            merges.append({
                "vacancy_id": v_id, "into_vacancy_id": target_id, "into_title": target_title,
                "to_user_id": to, "partial": bool(others),
                "overlapping": [
                    {"entity_id": o["entity_id"], "name": o["name"], "stage": o["result_stage"]}
                    for o in rep["overlapping"]
                ],
            })

    # Карточки уходящего, которые не уезжают с его воронками → отдельному получателю.
    pool_ids: List[int] = []
    if pool_to_user_id and pool_to_user_id != from_user_id:
        pool_ids = (
            await db.execute(
                select(Entity.id).where(
                    Entity.org_id == org_id,
                    Entity.type == EntityType.candidate,
                    Entity.created_by == from_user_id,
                    ~Entity.id.in_(_own_live_apps_subquery(from_user_id)),
                )
            )
        ).scalars().all()
        per_recipient[pool_to_user_id] = per_recipient.get(pool_to_user_id, 0) + len(pool_ids)
        if pool_ids and not dry_run:
            res = await db.execute(
                update(Entity)
                .where(Entity.id.in_(pool_ids))
                .values(created_by=pool_to_user_id)
            )
            counts["candidates"] = int(counts["candidates"]) + (res.rowcount or 0)
            affected.update(pool_ids)

    counts["per_recipient"] = {str(k): v for k, v in per_recipient.items()}
    counts["pool"] = len(pool_ids)
    counts["merges"] = merges
    if dry_run:
        return counts

    await db.flush()

    from .hr_tags import sync_for_entity
    for eid in affected:
        try:
            async with db.begin_nested():
                await sync_for_entity(db, eid, commit=False)
        except Exception:  # noqa: BLE001
            logger.exception("HANDOVER hr-tags sync failed entity=%s", eid)

    await db.commit()
    logger.info(
        "HANDOVER from=%s by=%s recipients=%s merged=%s pool=%s",
        from_user_id, acted_by, counts["per_recipient"], counts["merged"], counts["pool"],
    )
    return counts
