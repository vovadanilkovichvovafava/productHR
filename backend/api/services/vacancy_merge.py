"""Слияние двух вакансий-дублей в одну (решение владельца 21.09.2026).

Как появляются дубли: у двух рекрутёров были свои копии одной вакансии (с
одинаковым названием), один ушёл, его воронку передали второму — и у того
стало две одинаковые воронки. Кандидаты при этом частично пересекаются (раньше
«Забрать» добавлял кандидата в свою копию, не убирая из чужой).

Правила (согласованы с владельцем):
  • целевая вакансия — ГЛАВНАЯ, исходная закрывается (не удаляется);
  • кандидат только в исходной — переезжает как есть: этап, место в колонке,
    рекрутёр, источник, даты не меняются, меняется только vacancy_id заявки;
  • кандидат в обеих — остаётся заявка целевой (её этап и рекрутёр), история
    этапов и комментарии исходной приклеиваются к ней, лишняя заявка удаляется;
  • комментарии с пометкой исходной воронки перепомечаются на целевую;
  • HR-метки пересчитываются (дубль «HR: Имя · Вакансия» уходит сам).

dry_run собирает тот же отчёт, ничего не меняя.

Передача дел уходящего рекрутёра (26.10.2026) вливает его воронку в такую же
воронку получателя этим же слиянием, с двумя отличиями:
  • `only_application_ids` — переезжают только заявки уходящего, если в
    воронке работает ещё кто-то: тогда она остаётся у них и не закрывается;
  • `prefer_fresher` — у кандидата в обеих воронках остаётся этап, до которого
    его довели ПОЗЖЕ (работа уходящего не теряется); перевод пишется в историю.
"""
import logging
from datetime import datetime
from typing import Collection, Dict, List, Optional

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import (
    ApplicationCoRecruiter, Entity, FormTemplate, FormVacancy, OrgMember, SharedAccess,
    StageTransition, Vacancy, VacancyApplication, VacancyStatus,
)

logger = logging.getLogger("hr-analyzer.vacancy-merge")


def _source_is_fresher(src: VacancyApplication, tgt: VacancyApplication) -> bool:
    """Исходная заявка двигалась позже целевой (по дате последнего перевода)."""
    s = src.last_stage_change_at or src.applied_at
    t = tgt.last_stage_change_at or tgt.applied_at
    if s is None:
        return False
    return t is None or s > t


def _stage(app: VacancyApplication) -> Optional[str]:
    return app.stage.value if app.stage else None


def _merge_text(target: Optional[str], source: Optional[str]) -> Optional[str]:
    """Текст целевой главнее; текст исходной не теряем — дописываем ниже."""
    t = (target or "").strip()
    s = (source or "").strip()
    if not s or s == t:
        return target
    if not t:
        return source
    return f"{target}\n\n{source}"


async def merge_vacancies(
    db: AsyncSession, org_id: int, source_id: int, target_id: int,
    *, dry_run: bool = True, merged_by: Optional[int] = None,
    only_application_ids: Optional[Collection[int]] = None,
    prefer_fresher: bool = False,
    commit: bool = True,
) -> Dict[str, object]:
    """Влить вакансию source_id в target_id. Коммитит сам (если не dry_run и commit).

    only_application_ids — переносить только эти заявки исходной (частичное
    слияние: исходная остаётся открытой со своими участниками).
    """
    if source_id == target_id:
        raise ValueError("Нельзя слить вакансию саму с собой")

    source = await db.get(Vacancy, source_id)
    target = await db.get(Vacancy, target_id)
    for v, label in ((source, "исходная"), (target, "целевая")):
        if v is None or v.org_id != org_id or v.deleted_at is not None:
            raise LookupError(f"Вакансия ({label}) не найдена")

    src_query = select(VacancyApplication).where(VacancyApplication.vacancy_id == source_id)
    if only_application_ids is not None:
        src_query = src_query.where(VacancyApplication.id.in_(list(only_application_ids) or [-1]))
    src_apps = (await db.execute(src_query)).scalars().all()
    partial = only_application_ids is not None
    tgt_by_entity = {
        a.entity_id: a for a in (await db.execute(
            select(VacancyApplication).where(VacancyApplication.vacancy_id == target_id)
        )).scalars().all()
    }

    entity_ids = {a.entity_id for a in src_apps}
    names = {
        eid: name for eid, name in (await db.execute(
            select(Entity.id, Entity.name).where(Entity.id.in_(entity_ids))
        )).all()
    } if entity_ids else {}

    moved: List[Dict[str, object]] = []
    overlapping: List[Dict[str, object]] = []
    for a in src_apps:
        t = tgt_by_entity.get(a.entity_id)
        if t is None:
            moved.append({
                "entity_id": a.entity_id, "name": names.get(a.entity_id),
                "stage": _stage(a), "application_id": a.id,
            })
        else:
            take_source = prefer_fresher and a.stage != t.stage and _source_is_fresher(a, t)
            overlapping.append({
                "entity_id": a.entity_id, "name": names.get(a.entity_id),
                "target_stage": _stage(t), "source_stage": _stage(a),
                "same_stage": t.stage == a.stage,
                # Этап, который останется у кандидата после слияния.
                "result_stage": _stage(a) if take_source else _stage(t),
                "target_application_id": t.id, "source_application_id": a.id,
            })

    overlap_src_ids = [o["source_application_id"] for o in overlapping]
    transitions_to_reattach = 0
    if overlap_src_ids:
        transitions_to_reattach = len((await db.execute(
            select(StageTransition.id).where(
                StageTransition.application_id.in_(overlap_src_ids)
            )
        )).scalars().all())

    # Комментарии живут в extra_data.notes кандидата с пометкой vacancy_id.
    entities = (await db.execute(
        select(Entity).where(Entity.id.in_(entity_ids)).with_for_update()
    )).scalars().all() if (entity_ids and not dry_run) else (
        (await db.execute(select(Entity).where(Entity.id.in_(entity_ids)))).scalars().all()
        if entity_ids else []
    )

    def _is_source_note(n: object) -> bool:
        if not isinstance(n, dict) or n.get("vacancy_id") is None:
            return False
        try:
            return int(n["vacancy_id"]) == source_id
        except (TypeError, ValueError):
            return False

    notes_to_repoint = sum(
        1 for e in entities
        for n in ((e.extra_data or {}).get("notes") or [])
        if _is_source_note(n)
    )

    report: Dict[str, object] = {
        "dry_run": dry_run,
        "partial": partial,
        "source": {"id": source.id, "title": source.title, "status": source.status.value if source.status else None},
        "target": {"id": target.id, "title": target.title, "status": target.status.value if target.status else None},
        "moved_count": len(moved),
        "overlapping_count": len(overlapping),
        "overlapping_different_stage": sum(1 for o in overlapping if not o["same_stage"]),
        "transitions_reattached": transitions_to_reattach,
        "notes_repointed": notes_to_repoint,
        "moved": moved,
        "overlapping": overlapping,
    }
    if dry_run:
        return report

    # ---- Изменения ----
    # 1. Пересечения: история и со-рекрутёры исходной заявки → к целевой, затем
    # лишняя заявка удаляется (история уже перецеплена, каскад её не заденет).
    for o in overlapping:
        src_app_id = o["source_application_id"]
        tgt_app = tgt_by_entity[o["entity_id"]]
        src_app = next(a for a in src_apps if a.id == src_app_id)

        reattached = (await db.execute(
            update(StageTransition)
            .where(StageTransition.application_id == src_app_id)
            .values(application_id=tgt_app.id)
        )).rowcount or 0
        if o["result_stage"] != o["target_stage"]:
            # Кандидата в исходной довели дальше (позже) — этот этап и остаётся.
            # Запись в истории описывает перевод; она последняя, поэтому корзина
            # у неё честно вернёт прежний этап главной.
            old_stage = tgt_app.stage
            tgt_app.stage = src_app.stage
            tgt_app.stage_order = src_app.stage_order
            tgt_app.last_stage_change_at = src_app.last_stage_change_at or datetime.utcnow()
            db.add(StageTransition(
                application_id=tgt_app.id, entity_id=tgt_app.entity_id,
                from_stage=old_stage.value if old_stage else None, to_stage=src_app.stage.value,
                changed_by=merged_by,
                comment=f"Карточки объединены: этап из воронки «{source.title}»",
            ))
        elif reattached:
            # Последней записью ленты могла стать запись дубля: корзина у неё
            # («отмена перевода») вернула бы заявку на этап, где она в главной
            # воронке никогда не была (ревью 20.10.2026). Отметка слияния —
            # последняя и описывает текущий этап главной: её отмена ничего не
            # двигает.
            db.add(StageTransition(
                application_id=tgt_app.id, entity_id=tgt_app.entity_id,
                from_stage=tgt_app.stage.value, to_stage=tgt_app.stage.value,
                changed_by=merged_by,
                comment=f"Слияние вакансий: добавлена история «{source.title}»",
            ))

        tgt_co = set((await db.execute(
            select(ApplicationCoRecruiter.user_id).where(
                ApplicationCoRecruiter.application_id == tgt_app.id
            )
        )).scalars().all())
        src_co = (await db.execute(
            select(ApplicationCoRecruiter).where(
                ApplicationCoRecruiter.application_id == src_app_id
            )
        )).scalars().all()
        for co in src_co:
            if co.user_id in tgt_co or co.user_id == tgt_app.created_by:
                continue
            db.add(ApplicationCoRecruiter(application_id=tgt_app.id, user_id=co.user_id))
            tgt_co.add(co.user_id)

        # Закреп главной важнее; нет его — переносим закреп исходной (его запись
        # истории только что переехала сюда же, ключ остаётся рабочим).
        if not tgt_app.pinned_entry_key and src_app.pinned_entry_key:
            tgt_app.pinned_entry_key = src_app.pinned_entry_key
        if tgt_app.next_interview_at is None and src_app.next_interview_at is not None:
            tgt_app.next_interview_at = src_app.next_interview_at
        tgt_app.notes = _merge_text(tgt_app.notes, src_app.notes)
        tgt_app.interview_summary = _merge_text(tgt_app.interview_summary, src_app.interview_summary)
        if tgt_app.rating is None and src_app.rating is not None:
            tgt_app.rating = src_app.rating

        await db.flush()
        await db.execute(delete(ApplicationCoRecruiter).where(
            ApplicationCoRecruiter.application_id == src_app_id
        ))
        await db.execute(delete(VacancyApplication).where(VacancyApplication.id == src_app_id))

    # 2. Только в исходной — переезжают как есть (updated_at не трогаем).
    moved_ids = [m["application_id"] for m in moved]
    if moved_ids:
        await db.execute(
            update(VacancyApplication)
            .where(VacancyApplication.id.in_(moved_ids))
            .values(vacancy_id=target_id, updated_at=VacancyApplication.updated_at)
            .execution_options(synchronize_session=False)
        )

    # 3. Комментарии с пометкой исходной воронки → целевая.
    for e in entities:
        extra = dict(e.extra_data or {})
        notes = extra.get("notes") or []
        if not any(_is_source_note(n) for n in notes):
            continue
        extra["notes"] = [
            {**n, "vacancy_id": target_id} if _is_source_note(n) else n for n in notes
        ]
        e.extra_data = extra

    if partial:
        # Частичное слияние: исходная остаётся у своих участников — её анкеты,
        # доступы и состав не трогаем и не закрываем.
        await db.flush()
        db.expire_all()
        return await _finish(db, overlapping, entity_ids, report, commit)

    # 4. Анкеты и шаринги, привязанные к исходной вакансии.
    await db.execute(
        update(FormTemplate).where(FormTemplate.vacancy_id == source_id).values(vacancy_id=target_id)
    )
    tgt_forms = set((await db.execute(
        select(FormVacancy.form_id).where(FormVacancy.vacancy_id == target_id)
    )).scalars().all())
    for fv in (await db.execute(
        select(FormVacancy).where(FormVacancy.vacancy_id == source_id)
    )).scalars().all():
        if fv.form_id in tgt_forms:
            await db.delete(fv)
        else:
            fv.vacancy_id = target_id
            tgt_forms.add(fv.form_id)
    tgt_shares = set((await db.execute(
        select(SharedAccess.shared_with_id).where(SharedAccess.vacancy_id == target_id)
    )).scalars().all())
    for sh in (await db.execute(
        select(SharedAccess).where(SharedAccess.vacancy_id == source_id)
    )).scalars().all():
        if sh.shared_with_id in tgt_shares:
            await db.delete(sh)
        else:
            sh.vacancy_id = target_id
            sh.resource_id = target_id
            tgt_shares.add(sh.shared_with_id)

    # 5. Участники исходной добавляются в целевую (кроме тех, кто из целевой вышел).
    ted = dict(target.extra_data or {})
    dismissed = set(ted.get("dismissed_by") or [])
    assigned = list(target.assigned_to or [])
    for u in (source.assigned_to or []):
        if u not in assigned and u not in dismissed:
            assigned.append(u)
    target.assigned_to = assigned
    accepted = list(ted.get("accepted_by") or [])
    for u in ((source.extra_data or {}).get("accepted_by") or []):
        if u not in accepted and u not in dismissed:
            accepted.append(u)
    ted["accepted_by"] = accepted
    target.extra_data = ted
    if target.hiring_manager_id is None and source.hiring_manager_id is not None:
        target.hiring_manager_id = source.hiring_manager_id

    # 6. Исходная закрывается (не удаляется) с пометкой, куда слита.
    sed = dict(source.extra_data or {})
    sed["merged_into"] = target_id
    sed["merged_at"] = datetime.utcnow().isoformat()
    if merged_by is not None:
        sed["merged_by"] = merged_by
    source.extra_data = sed
    source.status = VacancyStatus.closed

    # Скоуп «вижу только эти воронки»: у кого была исходная — теперь главная,
    # иначе человек терял её кандидатов вместе с закрытой копией.
    for m in (await db.execute(
        select(OrgMember).where(OrgMember.org_id == org_id, OrgMember.scope_vacancy_ids.isnot(None))
    )).scalars().all():
        ids = list(m.scope_vacancy_ids or [])
        if source_id in ids:
            ids = [target_id if i == source_id else i for i in ids]
            m.scope_vacancy_ids = list(dict.fromkeys(ids))

    await db.flush()
    # Заявки меняли bulk-запросами мимо ORM: сбрасываем кэш сессии, чтобы пересчёт
    # статуса и меток читал из базы, а не старые vacancy_id.
    db.expire_all()

    return await _finish(db, overlapping, entity_ids, report, commit)


async def _finish(db: AsyncSession, overlapping, entity_ids, report, commit: bool):
    # 7. Общий статус кандидата (у пересечений пропала одна из заявок) и HR-метки.
    from ..routes.vacancies.common import recompute_entity_status
    from .hr_tags import sync_for_entity

    for o in overlapping:
        await recompute_entity_status(db, o["entity_id"])
    for eid in entity_ids:
        # Без savepoint упавший запрос в Postgres обрывает всю транзакцию, и
        # «except: pass» только прятал причину — коммит всё равно падал.
        try:
            async with db.begin_nested():
                await sync_for_entity(db, eid, commit=False)
        except Exception:  # noqa: BLE001 — одна битая карточка не должна валить слияние
            logger.exception("VACANCY_MERGE hr-tags sync failed entity=%s", eid)

    if commit:
        await db.commit()
    return report
