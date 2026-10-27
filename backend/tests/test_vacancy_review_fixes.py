"""Исправления по ревью `routes/vacancies/` (20.10.2026).

Каждый тест — сценарий, который до правки давал неверный результат.
"""
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select

from api.models.database import (
    ApplicationCoRecruiter, ApplicationStage, DepartmentFeature, Entity, EntityStatus,
    EntityType, OrgMember, OrgRole, StageTransition, User, Vacancy, VacancyApplication,
    VacancyStatus,
)
from api.services.auth import create_access_token, hash_password


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


@pytest_asyncio.fixture(autouse=True)
async def candidate_database_feature(db_session, organization):
    db_session.add(DepartmentFeature(
        org_id=organization.id, department_id=None, feature_name="candidate_database", enabled=True,
    ))
    await db_session.commit()


async def _hr(db, org, email, name, *, scope=None) -> User:
    u = User(email=email, password_hash=hash_password("x"), name=name, is_active=True)
    db.add(u)
    await db.flush()
    db.add(OrgMember(org_id=org.id, user_id=u.id, role=OrgRole.hr, scope_vacancy_ids=scope))
    await db.commit()
    await db.refresh(u)
    return u


async def _vac(db, org, owner, title, *, visible=True, assigned=(), accepted=(), deleted=False):
    v = Vacancy(
        org_id=org.id, title=title, status=VacancyStatus.open, created_by=owner.id,
        visible_to_all=visible, assigned_to=list(assigned), salary_currency="RUB",
        extra_data={"accepted_by": list(accepted)},
        created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        deleted_at=datetime.utcnow() if deleted else None,
    )
    db.add(v)
    await db.commit()
    await db.refresh(v)
    return v


async def _cand(db, org, creator, name, status=EntityStatus.new) -> Entity:
    e = Entity(org_id=org.id, type=EntityType.candidate, name=name, status=status,
               created_by=creator.id, created_at=datetime.utcnow())
    db.add(e)
    await db.commit()
    await db.refresh(e)
    return e


async def _app(db, vac, ent, creator, stage, *, when=None) -> VacancyApplication:
    a = VacancyApplication(vacancy_id=vac.id, entity_id=ent.id, stage=stage, stage_order=0,
                           created_by=creator.id, applied_at=datetime.utcnow(),
                           last_stage_change_at=when or datetime.utcnow())
    db.add(a)
    await db.commit()
    await db.refresh(a)
    return a


@pytest.fixture
async def team(db_session, organization, admin_user, org_owner, regular_user, org_admin):
    """owner (admin_user), admin орга Мария (regular_user), два рекрутёра."""
    anna = await _hr(db_session, organization, "anna@test.local", "Анна")
    petr = await _hr(db_session, organization, "petr@test.local", "Пётр")
    t = {"owner": admin_user, "maria": regular_user, "anna": anna, "petr": petr}
    for u in t.values():
        await db_session.refresh(u)
    # id — отдельно: после expire_all() обращение к u.id в async упадёт.
    t["ids"] = {k: u.id for k, u in t.items()}
    return t


async def test_outsider_recruiter_cannot_close_vacancy_for_everyone(client, db_session, organization, team):
    v = await _vac(db_session, organization, team["anna"], "Трафик",
                   assigned=[team["anna"].id], accepted=[team["anna"].id])
    r = await client.put(f"/api/vacancies/{v.id}", json={"status": "closed"}, headers=_h(team["petr"]))
    assert r.status_code == 403, r.text
    assert (await db_session.get(Vacancy, v.id, populate_existing=True)).status == VacancyStatus.open


async def test_org_admin_edits_hidden_vacancy_of_recruiter(client, db_session, organization, team):
    v = await _vac(db_session, organization, team["anna"], "Скрытая", visible=False, assigned=[team["anna"].id])
    r = await client.put(f"/api/vacancies/{v.id}", json={"title": "Скрытая (правка)"}, headers=_h(team["maria"]))
    assert r.status_code == 200, r.text


async def test_form_save_does_not_erase_colleague_accepted_by(client, db_session, organization, team):
    ids = team["ids"]
    v = await _vac(db_session, organization, team["anna"], "Общая",
                   assigned=[ids["anna"], ids["petr"]], accepted=[ids["anna"], ids["petr"]])
    vid = v.id
    stale = {"accepted_by": [ids["anna"]], "positions_count": 3, "source_chat_id": 999}
    r = await client.put(f"/api/vacancies/{vid}", json={"extra_data": stale}, headers=_h(team["anna"]))
    assert r.status_code == 200, r.text
    extra = (await db_session.get(Vacancy, vid, populate_existing=True)).extra_data
    assert extra["accepted_by"] == [ids["anna"], ids["petr"]]
    assert extra["positions_count"] == 3
    assert "source_chat_id" not in extra


async def test_take_into_new_funnel_does_not_inherit_rejection(client, db_session, organization, team):
    v1 = await _vac(db_session, organization, team["anna"], "В1")
    v2 = await _vac(db_session, organization, team["petr"], "В2")
    e = await _cand(db_session, organization, team["anna"], "Отказник", EntityStatus.rejected)
    await _app(db_session, v1, e, team["anna"], ApplicationStage.rejected)
    r = await client.post(f"/api/vacancies/{v2.id}/applications/take",
                          json={"entity_id": e.id, "recruiter_id": team["petr"].id}, headers=_h(team["petr"]))
    assert r.status_code == 200, r.text
    assert r.json()["stage"] == "applied"


async def test_take_always_starts_new_and_keeps_previous_owner(client, db_session, organization, team):
    """«Забрать» в свою воронку: там кандидат на «Новом», у прежнего — как был."""
    a_vac = await _vac(db_session, organization, team["anna"], "Трафик")
    p_vac = await _vac(db_session, organization, team["petr"], "Продажи")
    e = await _cand(db_session, organization, team["anna"], "На интервью", EntityStatus.practice)
    old = await _app(db_session, a_vac, e, team["anna"], ApplicationStage.phone_screen)
    old_id, anna_id = old.id, team["ids"]["anna"]
    r = await client.post(f"/api/vacancies/{p_vac.id}/applications/take",
                          json={"entity_id": e.id, "recruiter_id": team["ids"]["petr"]}, headers=_h(team["petr"]))
    assert r.status_code == 200, r.text
    assert r.json()["stage"] == "applied"
    kept = await db_session.get(VacancyApplication, old_id, populate_existing=True)
    assert kept.stage == ApplicationStage.phone_screen and kept.created_by == anna_id


async def test_new_funnel_keeps_dismissed_person(client, db_session, organization, team):
    v = await _vac(db_session, organization, team["anna"], "В1")
    e = await _cand(db_session, organization, team["anna"], "Уволенный", EntityStatus.dismissed)
    r = await client.post(f"/api/vacancies/{v.id}/applications", json={"entity_id": e.id, "vacancy_id": v.id},
                          headers=_h(team["anna"]))
    assert r.status_code == 201, r.text
    assert (await db_session.get(Entity, e.id, populate_existing=True)).status == EntityStatus.dismissed


async def test_deleting_application_recomputes_status_from_remaining(client, db_session, organization, team):
    v1 = await _vac(db_session, organization, team["anna"], "В1")
    v2 = await _vac(db_session, organization, team["anna"], "В2")
    e = await _cand(db_session, organization, team["anna"], "Двое", EntityStatus.offer)
    a1 = await _app(db_session, v1, e, team["anna"], ApplicationStage.offer)
    await _app(db_session, v2, e, team["anna"], ApplicationStage.screening,
               when=datetime.utcnow() - timedelta(days=3))
    r = await client.delete(f"/api/vacancies/applications/{a1.id}", headers=_h(team["anna"]))
    assert r.status_code in (200, 204), r.text
    assert (await db_session.get(Entity, e.id, populate_existing=True)).status == EntityStatus.screening


async def test_deleted_vacancy_is_not_an_open_funnel(db_session, organization, team):
    from api.routes.vacancies.common import recompute_entity_status
    gone = await _vac(db_session, organization, team["anna"], "Удалена", deleted=True)
    live = await _vac(db_session, organization, team["anna"], "Живая")
    e = await _cand(db_session, organization, team["anna"], "Кандидат", EntityStatus.offer)
    await _app(db_session, gone, e, team["anna"], ApplicationStage.offer)
    await _app(db_session, live, e, team["anna"], ApplicationStage.screening,
               when=datetime.utcnow() - timedelta(days=5))
    await recompute_entity_status(db_session, e.id)
    await db_session.commit()
    assert (await db_session.get(Entity, e.id, populate_existing=True)).status == EntityStatus.screening


async def test_cannot_add_candidate_into_deleted_vacancy(client, db_session, organization, team):
    gone = await _vac(db_session, organization, team["anna"], "Удалена", deleted=True)
    e = await _cand(db_session, organization, team["anna"], "Кандидат")
    r = await client.post(f"/api/vacancies/{gone.id}/applications", json={"entity_id": e.id, "vacancy_id": gone.id},
                          headers=_h(team["anna"]))
    assert r.status_code == 404, r.text


async def test_scoped_recruiter_cannot_move_application_of_other_funnel(client, db_session, organization, team):
    mine = await _vac(db_session, organization, team["anna"], "Своя")
    other = await _vac(db_session, organization, team["anna"], "Чужая")
    scoped = await _hr(db_session, organization, "scoped@test.local", "Со скоупом", scope=[mine.id])
    e = await _cand(db_session, organization, team["anna"], "Чужой кандидат")
    a = await _app(db_session, other, e, team["anna"], ApplicationStage.applied)
    r = await client.put(f"/api/vacancies/applications/{a.id}", json={"stage": "screening"}, headers=_h(scoped))
    assert r.status_code == 404, r.text
    assert (await db_session.get(VacancyApplication, a.id, populate_existing=True)).stage == ApplicationStage.applied


async def test_co_recruiter_can_move_candidate_in_hidden_funnel(client, db_session, organization, team):
    v = await _vac(db_session, organization, team["anna"], "Скрытая", visible=False,
                   assigned=[team["anna"].id, team["petr"].id])
    e = await _cand(db_session, organization, team["anna"], "Общий")
    a = await _app(db_session, v, e, team["anna"], ApplicationStage.applied)
    db_session.add(ApplicationCoRecruiter(application_id=a.id, user_id=team["petr"].id))
    await db_session.commit()
    r = await client.put(f"/api/vacancies/applications/{a.id}", json={"stage": "screening"}, headers=_h(team["petr"]))
    assert r.status_code == 200, r.text


async def test_history_undo_by_colleague_in_hidden_funnel(client, db_session, organization, team):
    """Откат этапа — та же правка, что перевод: с 21.10.2026 коллега может
    править чужих кандидатов в любой воронке, которую видит."""
    v = await _vac(db_session, organization, team["anna"], "Скрытая", visible=False,
                   assigned=[team["anna"].id, team["petr"].id])
    e = await _cand(db_session, organization, team["anna"], "Чужой", EntityStatus.screening)
    a = await _app(db_session, v, e, team["anna"], ApplicationStage.screening)
    tr = StageTransition(application_id=a.id, entity_id=e.id, from_stage="applied", to_stage="screening",
                         changed_by=team["anna"].id, created_at=datetime.utcnow())
    db_session.add(tr)
    await db_session.commit()
    r = await client.delete(f"/api/vacancies/applications/{a.id}/history/{tr.id}", headers=_h(team["petr"]))
    assert r.status_code == 200, r.text
    assert (await db_session.get(VacancyApplication, a.id, populate_existing=True)).stage == ApplicationStage.applied


async def test_practice_notification_fires_on_probation_not_on_hr_interview(
    client, db_session, organization, team, monkeypatch,
):
    import api.services.hr_notifications as hn
    calls = []

    async def fake(db, application, entity, user):
        calls.append(application.stage)
    monkeypatch.setattr(hn, "notify_practice_started", fake)

    v = await _vac(db_session, organization, team["anna"], "В1")
    e = await _cand(db_session, organization, team["anna"], "Практикант")
    a = await _app(db_session, v, e, team["anna"], ApplicationStage.screening)
    H = _h(team["anna"])
    assert (await client.put(f"/api/vacancies/applications/{a.id}", json={"stage": "phone_screen"}, headers=H)).status_code == 200
    assert calls == []
    assert (await client.put(f"/api/vacancies/applications/{a.id}", json={"stage": "probation"}, headers=H)).status_code == 200
    assert calls == [ApplicationStage.probation]


async def test_transfer_moves_co_recruiter_rows_and_null_author_tags(db_session, organization, team):
    from api.services.recruiter_transfer import reassign_recruiter_split
    v = await _vac(db_session, organization, team["anna"], "Уходящей")
    e1 = await _cand(db_session, organization, team["anna"], "Без автора")
    a1 = VacancyApplication(vacancy_id=v.id, entity_id=e1.id, stage=ApplicationStage.applied,
                            stage_order=0, created_by=None, applied_at=datetime.utcnow())
    db_session.add(a1)
    other = await _vac(db_session, organization, team["maria"], "Чужая")
    e2 = await _cand(db_session, organization, team["maria"], "Со-рекрутёр")
    a2 = await _app(db_session, other, e2, team["maria"], ApplicationStage.applied)
    db_session.add(ApplicationCoRecruiter(application_id=a2.id, user_id=team["anna"].id))
    await db_session.commit()

    ids, a2_id, eids = team["ids"], a2.id, (e1.id, e2.id)
    # «Передать всё» (reassign-ownership) удалена 26.10.2026 — передача идёт по воронкам.
    await reassign_recruiter_split(
        db_session, organization.id, ids["anna"],
        [{"vacancy_id": v.id, "to_user_id": ids["petr"]}, {"vacancy_id": other.id, "to_user_id": ids["petr"]}],
    )
    co = (await db_session.execute(
        select(ApplicationCoRecruiter.user_id).where(ApplicationCoRecruiter.application_id == a2_id)
    )).scalars().all()
    assert co == [ids["petr"]]
    for eid in eids:
        tags = ((await db_session.get(Entity, eid, populate_existing=True)).extra_data or {}).get("system_hr_tags") or []
        assert ids["anna"] not in {t.get("hr_id") for t in tags}
        assert ids["petr"] in {t.get("hr_id") for t in tags}
