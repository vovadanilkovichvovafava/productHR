"""Tests for the dynamic HR-tags service (api/services/hr_tags.py).

The HR-tag set is derived from VacancyApplication.created_by across a candidate's
ACTIVE applications (rejected/withdrawn excluded) and stored read-only in
entity.extra_data["system_hr_tags"], separate from manual Entity.tags.
"""
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from api.models.database import (
    Entity, EntityType, EntityStatus, Vacancy, VacancyStatus,
    VacancyApplication, ApplicationStage, User,
)
from api.services.hr_tags import (
    compute_hr_tags, sync_for_entity, backfill_all, EXTRA_KEY,
)


# ── helpers ─────────────────────────────────────────────────────────────────

async def _candidate(db, org, dept, creator) -> Entity:
    e = Entity(
        org_id=org.id, department_id=dept.id, created_by=creator.id,
        name="Иван Кандидат", type=EntityType.candidate,
        status=EntityStatus.active, created_at=datetime.utcnow(),
    )
    db.add(e)
    await db.commit()
    await db.refresh(e)
    return e


async def _vacancy(db, org, dept, creator, title="Vac") -> Vacancy:
    v = Vacancy(
        org_id=org.id, department_id=dept.id,
        created_by=(creator.id if creator else None),
        title=title, status=VacancyStatus.open, salary_currency="RUB",
        priority=1, tags=[], created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
    )
    db.add(v)
    await db.commit()
    await db.refresh(v)
    return v


async def _application(db, vac, entity, creator, stage=ApplicationStage.interview):
    a = VacancyApplication(
        vacancy_id=vac.id, entity_id=entity.id, stage=stage, stage_order=1000,
        created_by=creator.id if creator else None,
        applied_at=datetime.utcnow(), last_stage_change_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(a)
    await db.commit()
    await db.refresh(a)
    return a


async def _user(db, name, email) -> User:
    u = User(email=email, password_hash="x", name=name)
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


# ── tests ───────────────────────────────────────────────────────────────────

async def test_single_active_application_tags_creator(db_session: AsyncSession, organization, department, admin_user):
    cand = await _candidate(db_session, organization, department, admin_user)
    vac = await _vacancy(db_session, organization, department, admin_user)
    await _application(db_session, vac, cand, admin_user)

    changed = await sync_for_entity(db_session, cand.id)
    assert changed is True
    await db_session.refresh(cand)
    assert cand.extra_data[EXTRA_KEY] == [
        {"hr_id": admin_user.id, "name": admin_user.name, "vacancy_id": vac.id, "vacancy_title": "Vac"}
    ]


async def test_multiple_distinct_hrs_sorted(db_session: AsyncSession, organization, department, admin_user):
    cand = await _candidate(db_session, organization, department, admin_user)
    hr2 = await _user(db_session, "Настя", "nastya@example.com")
    v1 = await _vacancy(db_session, organization, department, admin_user, "V1")
    v2 = await _vacancy(db_session, organization, department, admin_user, "V2")
    await _application(db_session, v1, cand, admin_user)
    await _application(db_session, v2, cand, hr2)

    tags = await compute_hr_tags(db_session, cand.id)
    ids = [t["hr_id"] for t in tags]
    assert ids == sorted(ids)                       # стабильный порядок для diff
    assert {t["hr_id"] for t in tags} == {admin_user.id, hr2.id}


async def test_same_hr_two_funnels_one_entry_per_funnel(db_session: AsyncSession, organization, department, admin_user):
    cand = await _candidate(db_session, organization, department, admin_user)
    v1 = await _vacancy(db_session, organization, department, admin_user, "V1")
    v2 = await _vacancy(db_session, organization, department, admin_user, "V2")
    await _application(db_session, v1, cand, admin_user)
    await _application(db_session, v2, cand, admin_user)

    # один HR, две воронки → две метки (по одной на воронку), сортировка по vacancy_id
    assert await compute_hr_tags(db_session, cand.id) == [
        {"hr_id": admin_user.id, "name": admin_user.name, "vacancy_id": v1.id, "vacancy_title": "V1"},
        {"hr_id": admin_user.id, "name": admin_user.name, "vacancy_id": v2.id, "vacancy_title": "V2"},
    ]


async def test_rejected_and_withdrawn_excluded(db_session: AsyncSession, organization, department, admin_user):
    cand = await _candidate(db_session, organization, department, admin_user)
    hr2 = await _user(db_session, "Настя", "nastya2@example.com")
    v1 = await _vacancy(db_session, organization, department, admin_user, "V1")
    v2 = await _vacancy(db_session, organization, department, admin_user, "V2")
    await _application(db_session, v1, cand, admin_user, stage=ApplicationStage.rejected)
    await _application(db_session, v2, cand, hr2, stage=ApplicationStage.withdrawn)

    assert await compute_hr_tags(db_session, cand.id) == []


async def test_null_created_by_falls_back_to_vacancy_owner(db_session: AsyncSession, organization, department, admin_user):
    cand = await _candidate(db_session, organization, department, admin_user)
    # воронку создал «владелец» (отличный от админа) — доказываем fallback
    owner = await _user(db_session, "Владелец", "owner_fb@example.com")
    vac = await _vacancy(db_session, organization, department, owner, "Funnel")
    await _application(db_session, vac, cand, None)  # bulk-add без «кто добавил»

    # created_by заявки NULL → берём владельца воронки
    assert await compute_hr_tags(db_session, cand.id) == [
        {"hr_id": owner.id, "name": "Владелец", "vacancy_id": vac.id, "vacancy_title": "Funnel"}
    ]


async def test_no_hr_when_both_app_and_vacancy_creator_null(db_session: AsyncSession, organization, department, admin_user):
    cand = await _candidate(db_session, organization, department, admin_user)
    vac = await _vacancy(db_session, organization, department, None, "Ownerless")  # без создателя
    await _application(db_session, vac, cand, None)  # без «кто добавил»

    # оба NULL → метку вывести не из кого
    assert await compute_hr_tags(db_session, cand.id) == []


async def test_removal_clears_tag(db_session: AsyncSession, organization, department, admin_user):
    cand = await _candidate(db_session, organization, department, admin_user)
    vac = await _vacancy(db_session, organization, department, admin_user)
    app = await _application(db_session, vac, cand, admin_user)
    await sync_for_entity(db_session, cand.id)
    await db_session.refresh(cand)
    assert cand.extra_data.get(EXTRA_KEY)

    # кандидата сняли с воронки → заявка удалена → метка уходит
    await db_session.delete(app)
    await db_session.commit()
    changed = await sync_for_entity(db_session, cand.id)
    assert changed is True
    await db_session.refresh(cand)
    assert EXTRA_KEY not in (cand.extra_data or {})


async def test_diff_guard_no_op_on_second_run(db_session: AsyncSession, organization, department, admin_user):
    cand = await _candidate(db_session, organization, department, admin_user)
    vac = await _vacancy(db_session, organization, department, admin_user)
    await _application(db_session, vac, cand, admin_user)
    assert await sync_for_entity(db_session, cand.id) is True
    assert await sync_for_entity(db_session, cand.id) is False   # ничего не поменялось


async def test_does_not_touch_manual_tags_or_other_extra(db_session: AsyncSession, organization, department, admin_user):
    cand = await _candidate(db_session, organization, department, admin_user)
    cand.tags = ["python", "senior"]
    cand.extra_data = {"notes": [{"text": "keep me"}]}
    await db_session.commit()
    vac = await _vacancy(db_session, organization, department, admin_user)
    await _application(db_session, vac, cand, admin_user)

    await sync_for_entity(db_session, cand.id)
    await db_session.refresh(cand)
    assert cand.tags == ["python", "senior"]                       # ручные метки целы
    assert cand.extra_data["notes"] == [{"text": "keep me"}]       # прочий extra_data цел
    assert cand.extra_data[EXTRA_KEY] == [
        {"hr_id": admin_user.id, "name": admin_user.name, "vacancy_id": vac.id, "vacancy_title": "Vac"}
    ]


async def test_backfill_all_populates(db_session: AsyncSession, organization, department, admin_user):
    cand = await _candidate(db_session, organization, department, admin_user)
    vac = await _vacancy(db_session, organization, department, admin_user)
    await _application(db_session, vac, cand, admin_user)

    changed = await backfill_all(db_session)
    assert changed == 1
    await db_session.refresh(cand)
    assert cand.extra_data[EXTRA_KEY] == [
        {"hr_id": admin_user.id, "name": admin_user.name, "vacancy_id": vac.id, "vacancy_title": "Vac"}
    ]
