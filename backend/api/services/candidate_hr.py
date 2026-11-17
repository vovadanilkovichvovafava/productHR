"""HR кандидата — один человек; сорсер; участники (тикет Маши 13.11.2026).

Тикет «права HR» (таблица «трек АТС»): «В ATS нет возможности самостоятельно
изменить основного HR, открепить второго HR или передать кандидата другому
сотруднику без потери истории работы». Решение владельца 16.11.2026:
- у кандидата ОДИН HR — во всех его живых воронках (`VacancyApplication.created_by`);
- «Забрать» / «Сменить HR» делает человека HR кандидата во всех воронках, а
  прежний HR АВТОМАТИЧЕСКИ становится сорсером — если сорсера ещё нет («кто
  нашёл» не меняется при каждой передаче);
- добавить кандидата в свою воронку ≠ забрать: добавивший — участник
  (`ApplicationCoRecruiter`), HR прежний;
- этапы, комментарии, интервью не трогаются; отмена — корзиной у строки
  «Сменился HR» в ленте: возвращаются прежний HR, сорсер, участники, доска.

До этого HR жил в трёх местах (владелец заявки, колонка HR на «Штате»,
аналитика по автору вакансии), и в карточке бывало два HR (на проде 16.11 —
4 расхождения из 103 на «Штате»). «Штат» теперь берёт HR отсюда.

Маркер в логах — `HR_CHANGE` (смена) и `HR_CHANGE_UNDO` (отмена).
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from ..models.database import (
    ApplicationCoRecruiter,
    ApplicationStage,
    Entity,
    EntityTag,
    StageTransition,
    User,
    Vacancy,
    VacancyApplication,
    entity_tag_association,
)

logger = logging.getLogger("hr-analyzer.candidate_hr")

INACTIVE_STAGES = (ApplicationStage.rejected, ApplicationStage.withdrawn)
# Ключи доски «Штат» с HR, вписанным руками (routes/staff_board.py). У человека
# в воронках HR берётся из воронки, поэтому при смене HR они снимаются.
BOARD_HR_KEYS = ("assignee_user_ids", "assignee_user_id", "board_hr_tags")
HR_CHANGES_KEY = "hr_changes"
HR_CHANGES_KEEP = 20
SOURCER_COLOR = "var(--hf-status-blue)"


async def active_applications(db: AsyncSession, entity_id: int, *, lock: bool = False) -> list[VacancyApplication]:
    """Живые заявки кандидата (не отказ/отозван, воронка не удалена) — те же,
    что дают метку «HR: …» (services/hr_tags.py)."""
    q = (
        select(VacancyApplication)
        .join(Vacancy, Vacancy.id == VacancyApplication.vacancy_id)
        .where(
            VacancyApplication.entity_id == entity_id,
            VacancyApplication.stage.not_in(INACTIVE_STAGES),
            Vacancy.deleted_at.is_(None),
        )
        .order_by(VacancyApplication.id)
    )
    if lock:
        q = q.with_for_update(of=VacancyApplication)
    return list((await db.execute(q)).scalars().all())


def _board_hr_ids(entity: Entity) -> list[int]:
    ex = entity.extra_data if isinstance(entity.extra_data, dict) else {}
    raw = ex.get("assignee_user_ids")
    if isinstance(raw, list):
        return [int(x) for x in raw if str(x).isdigit()]
    one = ex.get("assignee_user_id")
    return [int(one)] if one not in (None, "") and str(one).isdigit() else []


async def current_hr_id(db: AsyncSession, entity: Entity, apps: Optional[list[VacancyApplication]] = None) -> Optional[int]:
    """HR кандидата: владелец «актуальной» живой заявки (без автора — владелец
    воронки). Без воронок — HR, вписанный на «Штате»."""
    from ..routes.vacancies.common import pick_primary_application

    apps = apps if apps is not None else await active_applications(db, entity.id)
    if apps:
        primary = pick_primary_application(apps)
        if primary.created_by:
            return primary.created_by
        vacancy = await db.get(Vacancy, primary.vacancy_id)
        return vacancy.created_by if vacancy else None
    ids = _board_hr_ids(entity)
    return ids[0] if ids else None


async def participant_ids(db: AsyncSession, apps: list[VacancyApplication], hr_id: Optional[int]) -> list[int]:
    if not apps:
        return []
    rows = (await db.execute(
        select(ApplicationCoRecruiter.user_id)
        .where(ApplicationCoRecruiter.application_id.in_([a.id for a in apps]))
        .distinct()
    )).scalars().all()
    return sorted({int(u) for u in rows if u and u != hr_id})


async def sourcer_tags(db: AsyncSession, entity_id: int) -> list[EntityTag]:
    """Метки кандидата. С 21.09.2026 любая метка — сорсер (CLAUDE.md, «Метки»)."""
    return list((await db.execute(
        select(EntityTag)
        .join(entity_tag_association, entity_tag_association.c.tag_id == EntityTag.id)
        .where(entity_tag_association.c.entity_id == entity_id)
        .order_by(EntityTag.name)
    )).scalars().all())


async def _sourcer_tag_for(db: AsyncSession, org_id: int, name: str, actor_id: Optional[int]) -> EntityTag:
    tags = (await db.execute(select(EntityTag).where(EntityTag.org_id == org_id))).scalars().all()
    tag = next((t for t in tags if (t.name or "").strip().lower() == name.strip().lower()), None)
    if tag is None:
        tag = EntityTag(org_id=org_id, name=name.strip(), color=SOURCER_COLOR, kind="sourcer", created_by=actor_id)
        db.add(tag)
        await db.flush()
    elif getattr(tag, "archived_at", None) is not None:
        tag.archived_at = None
    return tag


async def _user_names(db: AsyncSession, ids) -> dict[int, str]:
    ids = [i for i in set(ids) if i]
    if not ids:
        return {}
    return {uid: name for uid, name in (await db.execute(select(User.id, User.name).where(User.id.in_(ids)))).all()}


@dataclass
class HrChange:
    prev_hr_id: Optional[int]
    new_hr_id: int
    application_ids: list[int] = field(default_factory=list)
    sourcer_name: Optional[str] = None
    changed: bool = False
    vacancy_titles: list[str] = field(default_factory=list)


async def change_hr(
    db: AsyncSession,
    entity: Entity,
    new_hr_id: int,
    *,
    actor: User,
    keep_prev_as_participant: bool = False,
    via: str = "change",
) -> HrChange:
    """Сделать человека HR кандидата во всех живых воронках. Прежний HR — в
    сорсеры, если сорсера нет; по желанию — в участники. Запись о смене (для
    истории в строке «HR» и отмены) — в extra_data.hr_changes. В ЛЕНТУ карточки
    смена не пишется (Маша, 17.11.2026: «это поле нужно, чтобы видеть историю
    взаимодействия с кандидатом — комментарии, ОС, фидбек, — а не кто его вёл»).
    Не коммитит."""
    apps = await active_applications(db, entity.id, lock=True)
    prev = await current_hr_id(db, entity, apps)
    owners_before = {a.id: a.created_by for a in apps}
    result = HrChange(prev_hr_id=prev, new_hr_id=new_hr_id, application_ids=[a.id for a in apps])
    if prev == new_hr_id and all(o == new_hr_id for o in owners_before.values()):
        return result
    result.changed = True

    # Кто из затронутых был участником — чтобы отмена вернула как было.
    co_rows = (await db.execute(
        select(ApplicationCoRecruiter.application_id, ApplicationCoRecruiter.user_id)
        .where(ApplicationCoRecruiter.application_id.in_([a.id for a in apps] or [0]))
    )).all()
    new_was_participant = sorted({app_id for app_id, uid in co_rows if uid == new_hr_id})
    prev_was_participant = sorted({app_id for app_id, uid in co_rows if uid == prev})

    for app in apps:
        app.created_by = new_hr_id
        app.updated_at = datetime.utcnow()
    if apps:
        await db.execute(delete(ApplicationCoRecruiter).where(
            ApplicationCoRecruiter.application_id.in_([a.id for a in apps]),
            ApplicationCoRecruiter.user_id == new_hr_id,
        ))
    participant_added: list[int] = []
    if keep_prev_as_participant and prev and prev != new_hr_id:
        for app in apps:
            if app.id not in prev_was_participant:
                db.add(ApplicationCoRecruiter(application_id=app.id, user_id=prev))
                participant_added.append(app.id)

    entity_owner_moved = bool(prev and entity.created_by == prev)
    if entity_owner_moved:
        entity.created_by = new_hr_id

    names = await _user_names(db, [prev, new_hr_id])
    new_name = names.get(new_hr_id) or "новый HR"
    prev_name = names.get(prev) if prev else None

    # Прежний HR — сорсер, если сорсера ещё нет (решение владельца 16.11.2026).
    sourcer_tag_id = None
    if prev and prev != new_hr_id and prev_name and not await sourcer_tags(db, entity.id):
        tag = await _sourcer_tag_for(db, entity.org_id, prev_name, actor.id)
        await db.execute(entity_tag_association.insert().values(entity_id=entity.id, tag_id=tag.id))
        sourcer_tag_id = tag.id
        result.sourcer_name = tag.name

    ex = dict(entity.extra_data) if isinstance(entity.extra_data, dict) else {}
    board_prev = {k: ex[k] for k in BOARD_HR_KEYS if k in ex}
    if apps:
        for k in BOARD_HR_KEYS:
            ex.pop(k, None)
    else:
        # Без воронок HR живёт на доске — там и меняем.
        ex["assignee_user_ids"] = [new_hr_id]
        ex["assignee_user_id"] = new_hr_id
        ex["board_hr_tags"] = [{"hr_id": new_hr_id, "name": new_name}]

    transition_ids: list[int] = []
    vacancy_titles = []
    if apps:
        vacancy_titles = [t for t, in (await db.execute(
            select(Vacancy.title).where(Vacancy.id.in_([a.vacancy_id for a in apps])).order_by(Vacancy.title)
        )).all()]
    result.vacancy_titles = vacancy_titles

    record = {
        "id": uuid.uuid4().hex[:12],
        "at": datetime.utcnow().isoformat(),
        "by": actor.id,
        "via": via,
        "prev": prev,
        "new": new_hr_id,
        "owners_before": {str(k): v for k, v in owners_before.items()},
        "transitions": transition_ids,
        "sourcer_tag_id": sourcer_tag_id,
        "participant_added": participant_added,
        "new_was_participant": new_was_participant,
        "entity_owner_moved": entity_owner_moved,
        "board_prev": board_prev,
    }
    ex[HR_CHANGES_KEY] = [*list(ex.get(HR_CHANGES_KEY) or [])[-(HR_CHANGES_KEEP - 1):], record]
    entity.extra_data = ex
    flag_modified(entity, "extra_data")
    entity.updated_at = datetime.utcnow()
    logger.info(
        "HR_CHANGE: entity=%s from=%s to=%s apps=%s sourcer=%s via=%s by=%s",
        entity.id, prev, new_hr_id, [a.id for a in apps], result.sourcer_name or "-", via, actor.id,
    )
    return result


def hr_change_for_transition(entity: Entity, transition_id: int) -> Optional[dict]:
    ex = entity.extra_data if isinstance(entity.extra_data, dict) else {}
    for rec in reversed(list(ex.get(HR_CHANGES_KEY) or [])):
        if transition_id in (rec.get("transitions") or []):
            return rec
    return None


async def undo_hr_change(db: AsyncSession, entity: Entity, transition_id: int, *, actor: User) -> Optional[str]:
    """Корзина у строки «Сменился HR». Отменяет, только если это ПОСЛЕДНЯЯ смена
    и HR с тех пор не менялся; иначе просто убирает запись из ленты (как
    удаление старой записи истории). Возвращает 'undone' / 'deleted' / None
    (запись не про смену HR). Не коммитит."""
    rec = hr_change_for_transition(entity, transition_id)
    if rec is None:
        return None
    ex = dict(entity.extra_data) if isinstance(entity.extra_data, dict) else {}
    history = list(ex.get(HR_CHANGES_KEY) or [])
    is_last = bool(history) and history[-1].get("id") == rec.get("id")
    apps = await active_applications(db, entity.id, lock=True)
    still_current = _still_current(rec, apps, entity)
    tr_ids = list(rec.get("transitions") or [])
    if not (is_last and still_current):
        await db.execute(delete(StageTransition).where(StageTransition.id == transition_id))
        rec["transitions"] = [t for t in tr_ids if t != transition_id]
        ex[HR_CHANGES_KEY] = history
        entity.extra_data = ex
        flag_modified(entity, "extra_data")
        return "deleted"

    await _revert(db, entity, rec, apps, ex, history, actor)
    return "undone"


async def _revert(db, entity, rec, apps, ex, history, actor) -> None:
    """Вернуть всё, что сделала смена rec (она последняя в history)."""
    tr_ids = list(rec.get("transitions") or [])
    owners = {int(k): v for k, v in (rec.get("owners_before") or {}).items()}
    for app in apps:
        if app.id in owners:
            app.created_by = owners[app.id]
            app.updated_at = datetime.utcnow()
    if rec.get("participant_added"):
        await db.execute(delete(ApplicationCoRecruiter).where(
            ApplicationCoRecruiter.application_id.in_(rec["participant_added"]),
            ApplicationCoRecruiter.user_id == rec.get("prev"),
        ))
    for app_id in rec.get("new_was_participant") or []:
        db.add(ApplicationCoRecruiter(application_id=app_id, user_id=rec.get("new")))
    if rec.get("entity_owner_moved") and entity.created_by == rec.get("new"):
        entity.created_by = rec.get("prev")
    if rec.get("sourcer_tag_id"):
        await db.execute(delete(entity_tag_association).where(
            entity_tag_association.c.entity_id == entity.id,
            entity_tag_association.c.tag_id == rec["sourcer_tag_id"],
        ))
    for k in BOARD_HR_KEYS:
        ex.pop(k, None)
    ex.update(rec.get("board_prev") or {})
    if tr_ids:
        await db.execute(delete(StageTransition).where(StageTransition.id.in_(tr_ids)))
    ex[HR_CHANGES_KEY] = history[:-1]
    entity.extra_data = ex
    flag_modified(entity, "extra_data")
    entity.updated_at = datetime.utcnow()
    logger.info(
        "HR_CHANGE_UNDO: entity=%s back to=%s (was %s) by=%s",
        entity.id, rec.get("prev"), rec.get("new"), actor.id,
    )


async def undo_last_hr_change(db: AsyncSession, entity: Entity, *, actor: User) -> Optional[str]:
    """«Отменить последнюю смену» в строке «HR». None — отменено; иначе текст,
    почему нельзя (смен нет / HR с тех пор поменяли в воронке). Не коммитит."""
    ex = dict(entity.extra_data) if isinstance(entity.extra_data, dict) else {}
    history = list(ex.get(HR_CHANGES_KEY) or [])
    if not history:
        return "Смен HR у кандидата не было"
    rec = history[-1]
    apps = await active_applications(db, entity.id, lock=True)
    if not _still_current(rec, apps, entity):
        return "HR с тех пор поменяли — отменить последнюю смену уже нельзя"
    await _revert(db, entity, rec, apps, ex, history, actor)
    return None


def _still_current(rec: dict, apps: list, entity: Entity) -> bool:
    owners = rec.get("owners_before") or {}
    if owners:
        return all(a.created_by == rec.get("new") for a in apps if str(a.id) in owners)
    # Без воронок HR живёт на доске.
    return _board_hr_ids(entity)[:1] == [rec.get("new")]


async def add_participant(db: AsyncSession, entity: Entity, user_id: int, *, actor: User) -> list[int]:
    """Участник — во всех живых воронках кандидата (кроме HR). Не коммитит."""
    apps = await active_applications(db, entity.id, lock=True)
    hr = await current_hr_id(db, entity, apps)
    if user_id == hr or not apps:
        return []
    have = set((await db.execute(
        select(ApplicationCoRecruiter.application_id).where(
            ApplicationCoRecruiter.application_id.in_([a.id for a in apps]),
            ApplicationCoRecruiter.user_id == user_id,
        )
    )).scalars().all())
    added = []
    for app in apps:
        if app.id not in have:
            db.add(ApplicationCoRecruiter(application_id=app.id, user_id=user_id))
            added.append(app.id)
    logger.info("HR_PARTICIPANT add: entity=%s user=%s apps=%s by=%s", entity.id, user_id, added, actor.id)
    return added


async def remove_participant(db: AsyncSession, entity: Entity, user_id: int, *, actor: User) -> int:
    apps = await active_applications(db, entity.id, lock=True)
    if not apps:
        return 0
    res = await db.execute(delete(ApplicationCoRecruiter).where(
        ApplicationCoRecruiter.application_id.in_([a.id for a in apps]),
        ApplicationCoRecruiter.user_id == user_id,
    ))
    logger.info("HR_PARTICIPANT remove: entity=%s user=%s by=%s", entity.id, user_id, actor.id)
    return res.rowcount or 0


async def team(db: AsyncSession, entity: Entity) -> dict:
    """Кто работает с кандидатом: HR, сорсеры, участники — для карточки."""
    apps = await active_applications(db, entity.id)
    hr = await current_hr_id(db, entity, apps)
    parts = await participant_ids(db, apps, hr)
    names = await _user_names(db, [hr, *parts])
    tags = await sourcer_tags(db, entity.id)
    ex = entity.extra_data if isinstance(entity.extra_data, dict) else {}
    changes = list(ex.get(HR_CHANGES_KEY) or [])
    who = await _user_names(db, [x for r in changes for x in (r.get("prev"), r.get("new"), r.get("by"))])
    history = [
        {
            "at": r.get("at"),
            "prev": who.get(r.get("prev")) if r.get("prev") else None,
            "new": who.get(r.get("new")),
            "by": who.get(r.get("by")) if r.get("by") else None,
        }
        for r in reversed(changes[-10:])
    ]
    can_undo = bool(changes) and _still_current(changes[-1], apps, entity)
    from .practice_mentor import load_mentors, org_mentor_names
    mentors = (await load_mentors(db, entity.org_id, [entity.id])).get(entity.id) or []
    return {
        "mentor": mentors[0] if mentors else None,
        "mentor_options": await org_mentor_names(db, entity.org_id),
        "hr": {"id": hr, "name": names.get(hr)} if hr else None,
        "hr_from_board": not apps,
        "participants": [{"id": u, "name": names.get(u)} for u in parts],
        "sourcers": [{"id": t.id, "name": t.name, "color": t.color} for t in tags],
        "in_funnels": bool(apps),
        # Смены HR — не в ленте, а здесь: строка «HR» показывает историю и
        # «Отменить последнюю смену» (17.11.2026).
        "hr_history": history,
        "can_undo_hr": can_undo,
    }
