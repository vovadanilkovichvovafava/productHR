"""«Забрать» кандидата = ПЕРЕНОС к другому рекрутёру (решение владельца 21.09.2026).

Кнопка задумана для кандидатов уходящих рекрутёров: другой рекрутёр забирает
их себе. С 28.08 она работала аддитивно — новый добавлялся со-рекрутёром, а
прежний владелец оставался, т.е. у уходящего ничего не забиралось.
"""
from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy import select

from api.models.database import (
    ApplicationCoRecruiter, ApplicationStage, Entity, EntityStatus, EntityType,
    OrgMember, OrgRole, User, UserRole, Vacancy, VacancyApplication, VacancyStatus,
)
from api.services.auth import create_access_token, hash_password


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


async def _recruiter(db, org, email, name):
    u = User(email=email, password_hash=hash_password("x"), name=name, role=UserRole.admin)
    db.add(u)
    await db.flush()
    db.add(OrgMember(org_id=org.id, user_id=u.id, role=OrgRole.hr))
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture
async def setup(db_session, organization, admin_user, org_owner):
    """Воронка админа, кандидат Марии в ней; Пётр и Олег — ещё рекрутёры."""
    maria = await _recruiter(db_session, organization, "maria@t.ru", "Мария")
    petr = await _recruiter(db_session, organization, "petr@t.ru", "Пётр")
    oleg = await _recruiter(db_session, organization, "oleg@t.ru", "Олег")

    v = Vacancy(
        org_id=organization.id, title="Трафик", status=VacancyStatus.open,
        created_by=admin_user.id, visible_to_all=True, created_at=datetime.utcnow(),
    )
    e = Entity(
        org_id=organization.id, name="Рейтерович Александр", type=EntityType.candidate,
        status=EntityStatus.practice, created_by=maria.id, created_at=datetime.utcnow(),
    )
    db_session.add_all([v, e])
    await db_session.commit()
    app = VacancyApplication(
        vacancy_id=v.id, entity_id=e.id, stage=ApplicationStage.probation,
        stage_order=1, created_by=maria.id, applied_at=datetime.utcnow(),
    )
    db_session.add(app)
    await db_session.commit()
    return {"v": v, "e": e, "app": app, "maria": maria, "petr": petr, "oleg": oleg}


async def _take(client, admin_user, s, recruiter):
    r = await client.post(
        f"/api/vacancies/{s['v'].id}/applications/take",
        json={"entity_id": s["e"].id, "recruiter_id": recruiter.id},
        headers=_h(admin_user),
    )
    assert r.status_code == 200, r.text
    return r.json()


async def _funnel_of(client, admin_user, s, recruiter):
    r = await client.get(
        f"/api/vacancies/{s['v'].id}/applications?created_by={recruiter.id}",
        headers=_h(admin_user),
    )
    assert r.status_code == 200, r.text
    return {a["entity_id"] for a in r.json()}


@pytest.mark.asyncio
async def test_take_moves_candidate_to_new_recruiter(client, db_session, admin_user, setup):
    s = setup
    body = await _take(client, admin_user, s, s["petr"])
    assert body["created_by"] == s["petr"].id

    # В воронке — у Петра, у Марии больше нет.
    assert s["e"].id in await _funnel_of(client, admin_user, s, s["petr"])
    assert s["e"].id not in await _funnel_of(client, admin_user, s, s["maria"])

    # Карточка тоже перешла; этап не тронут.
    await db_session.refresh(s["e"])
    await db_session.refresh(s["app"])
    assert s["e"].created_by == s["petr"].id
    assert s["app"].stage == ApplicationStage.probation

    # Метка «HR: …» — только Пётр.
    tags = (s["e"].extra_data or {}).get("system_hr_tags") or []
    assert [t["name"] for t in tags] == ["Пётр"]


@pytest.mark.asyncio
async def test_take_by_co_recruiter_makes_him_owner_and_keeps_others(
    client, db_session, admin_user, setup,
):
    s = setup
    db_session.add_all([
        ApplicationCoRecruiter(application_id=s["app"].id, user_id=s["petr"].id),
        ApplicationCoRecruiter(application_id=s["app"].id, user_id=s["oleg"].id),
    ])
    await db_session.commit()

    await _take(client, admin_user, s, s["petr"])

    co = set((await db_session.execute(
        select(ApplicationCoRecruiter.user_id).where(
            ApplicationCoRecruiter.application_id == s["app"].id
        )
    )).scalars().all())
    assert co == {s["oleg"].id}  # Пётр стал владельцем, Олег остался
    await db_session.refresh(s["app"])
    assert s["app"].created_by == s["petr"].id


@pytest.mark.asyncio
async def test_take_keeps_card_owner_if_it_was_someone_else(client, db_session, admin_user, setup):
    """Карточку добавил Олег, в воронку взяла Мария → забрал Пётр: карточка
    остаётся за Олегом, переходит только заявка."""
    s = setup
    s["e"].created_by = s["oleg"].id
    await db_session.commit()

    await _take(client, admin_user, s, s["petr"])

    await db_session.refresh(s["e"])
    assert s["e"].created_by == s["oleg"].id


@pytest.mark.asyncio
async def test_take_into_funnel_without_candidate_creates_application(
    client, db_session, organization, admin_user, setup,
):
    s = setup
    v2 = Vacancy(
        org_id=organization.id, title="Сорсер", status=VacancyStatus.open,
        created_by=admin_user.id, visible_to_all=True, created_at=datetime.utcnow(),
    )
    db_session.add(v2)
    await db_session.commit()

    r = await client.post(
        f"/api/vacancies/{v2.id}/applications/take",
        json={"entity_id": s["e"].id, "recruiter_id": s["petr"].id},
        headers=_h(admin_user),
    )
    assert r.status_code == 200, r.text
    assert r.json()["created_by"] == s["petr"].id

    # В первой воронке кандидат по-прежнему у Марии.
    await db_session.refresh(s["app"])
    assert s["app"].created_by == s["maria"].id


@pytest.mark.asyncio
async def test_take_to_current_owner_changes_nothing(client, db_session, admin_user, setup):
    s = setup
    await _take(client, admin_user, s, s["maria"])
    await db_session.refresh(s["app"])
    await db_session.refresh(s["e"])
    assert s["app"].created_by == s["maria"].id
    assert s["e"].created_by == s["maria"].id


# --- 26.10.2026: «Забрать» говорит, что сделал, оставляет след и проверяет получателя ---

@pytest.mark.asyncio
async def test_take_transfer_leaves_trace_and_notifies(client, db_session, admin_user, setup):
    from api.models.database import Notification, StageTransition
    s = setup
    body = await _take(client, admin_user, s, s["petr"])
    assert body["take_outcome"] == "transferred" and body["taken_from"] == s["maria"].id
    last = (await db_session.execute(
        select(StageTransition).where(StageTransition.application_id == s["app"].id)
        .order_by(StageTransition.id.desc())
    )).scalars().first()
    assert last.comment == "Сменился рекрутёр: теперь Пётр, раньше Мария"
    assert last.from_stage == last.to_stage == "probation"  # этап не двигали
    for uid, title in ((s["maria"].id, "Кандидата забрали"), (s["petr"].id, "Вам передали кандидата")):
        n = (await db_session.execute(select(Notification).where(
            Notification.user_id == uid, Notification.type == "candidate_taken"))).scalars().all()
        assert [x.title for x in n] == [title]

    again = await _take(client, admin_user, s, s["petr"])
    assert again["take_outcome"] == "unchanged"


@pytest.mark.asyncio
async def test_take_rejects_observer_recipient(client, db_session, admin_user, setup):
    s = setup
    m = (await db_session.execute(select(OrgMember).where(OrgMember.user_id == s["oleg"].id))).scalar_one()
    m.is_readonly = True
    await db_session.commit()
    r = await client.post(
        f"/api/vacancies/{s['v'].id}/applications/take",
        json={"entity_id": s["e"].id, "recruiter_id": s["oleg"].id},
        headers=_h(admin_user),
    )
    assert r.status_code == 400, r.text
