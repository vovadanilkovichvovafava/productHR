"""«Был отказ» — прошлые отказы человека в списке, воронке, карточке и расширении
(владелец, 22.10.2026). Сервис — api/services/prior_rejection.py.
"""
from datetime import datetime, timedelta

import pytest

from api.models.database import (
    ApplicationStage, Entity, EntityStatus, EntityType, StageTransition,
    Vacancy, VacancyApplication, VacancyStatus,
)
from api.services.auth import create_access_token


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


async def _vacancy(db, org, dept, user, title, **kw):
    now = datetime.utcnow()
    v = Vacancy(org_id=org.id, department_id=dept.id, created_by=user.id, title=title,
                status=VacancyStatus.open, salary_currency="RUB", created_at=now, updated_at=now, **kw)
    db.add(v)
    await db.commit()
    return v


async def _entity(db, org, user, name, status=EntityStatus.new, **kw):
    e = Entity(org_id=org.id, name=name, type=EntityType.candidate, status=status,
               created_by=user.id, **kw)
    db.add(e)
    await db.commit()
    return e


async def _reject(db, entity, vacancy, user, *, comment="Не сдал тестовое", reason=None, when=None):
    when = when or datetime(2026, 8, 28, 12, 0)
    app = VacancyApplication(vacancy_id=vacancy.id, entity_id=entity.id, stage=ApplicationStage.rejected,
                             stage_order=1, created_by=user.id, applied_at=when - timedelta(days=5),
                             last_stage_change_at=when, updated_at=when, rejection_reason=reason)
    db.add(app)
    await db.commit()
    db.add(StageTransition(application_id=app.id, entity_id=entity.id, from_stage="screening",
                           to_stage="rejected", changed_by=user.id, comment=comment, created_at=when))
    await db.commit()
    return app


@pytest.fixture
async def setup(db_session, organization, department, admin_user, org_owner):
    traffic = await _vacancy(db_session, organization, department, admin_user, "Трафик")
    old = await _entity(db_session, organization, admin_user, "Иванова Полина", EntityStatus.rejected)
    await _reject(db_session, old, traffic, admin_user, reason="Слабая аналитика")
    new = await _entity(db_session, organization, admin_user, "Иванова Полина",
                        extra_data={"hidden_duplicate_id": old.id})
    return {"traffic": traffic, "old_id": old.id, "new_id": new.id, "admin_name": admin_user.name}


async def _kanban_card(client, H, eid):
    data = (await client.get("/api/candidates/kanban?per_column=2000", headers=H)).json()
    return next(c for col in data["columns"] for c in col["cards"] if c["id"] == eid)


async def test_list_row_shows_rejection_of_the_other_card(client, admin_user, setup):
    H = _h(admin_user)
    card = await _kanban_card(client, H, setup["new_id"])
    pr = card["prior_rejection"]
    assert pr["kind"] == "rejected" and pr["source"] == "funnel"
    assert pr["vacancy_title"] == "Трафик"
    assert pr["recruiter_name"] == setup["admin_name"]
    assert pr["comment"] == "Не сдал тестовое" and pr["reason"] == "Слабая аналитика"
    assert pr["from_stage"] == "Выполняет ТЗ" and pr["date"].startswith("2026-08-28")
    # Сама отклонённая карточка — во вкладке «Отказ», метки у неё нет.
    assert (await _kanban_card(client, H, setup["old_id"]))["prior_rejection"] is None


async def test_archive_clickup_statuses(client, db_session, organization, admin_user, setup):
    arch = await _entity(db_session, organization, admin_user, "Петров Пётр", EntityStatus.reserve,
                         is_archived=True, extra_data={"participations": [
                             {"vacancy_title": "UA Manager", "recruiter": "Влада",
                              "status": "собес (1): нет", "date": "2025-03-12 10:41:00"},
                             {"vacancy_title": "SMM", "recruiter": "Влада",
                              "status": "анкета: да", "date": "2025-05-01 09:00:00"},
                         ]})
    noshow = await _entity(db_session, organization, admin_user, "Сидоров", EntityStatus.reserve,
                           is_archived=True, extra_data={"participations": [
                               {"vacancy_title": "Трафик", "status": "неявка (1)", "date": "2025-06-01 09:00:00"},
                           ]})
    a = await _entity(db_session, organization, admin_user, "Петров Пётр", extra_data={"hidden_duplicate_id": arch.id})
    b = await _entity(db_session, organization, admin_user, "Сидоров С", extra_data={"hidden_duplicate_id": noshow.id})
    H = _h(admin_user)
    pa = (await _kanban_card(client, H, a.id))["prior_rejection"]
    assert (pa["kind"], pa["source"], pa["vacancy_title"], pa["from_stage"]) == (
        "rejected", "archive", "UA Manager", "собес (1): нет")
    assert pa["date"] == "2025-03-12T10:41:00" and pa["archived"] is True and pa["count"] == 1
    pb = (await _kanban_card(client, H, b.id))["prior_rejection"]
    assert pb["kind"] == "no_show"


async def test_funnel_row_shows_rejection_in_another_funnel(client, db_session, organization, department, admin_user, setup):
    ua = await _vacancy(db_session, organization, department, admin_user, "UA Manager", visible_to_all=True)
    person = await _entity(db_session, organization, admin_user, "Кузнецов Сергей")
    await _reject(db_session, person, setup["traffic"], admin_user, comment="Нет опыта")
    now = datetime.utcnow()
    db_session.add(VacancyApplication(vacancy_id=ua.id, entity_id=person.id, stage=ApplicationStage.applied,
                                      stage_order=1, created_by=admin_user.id, applied_at=now,
                                      last_stage_change_at=now, updated_at=now))
    await db_session.commit()
    pid, traffic_id, ua_id = person.id, setup["traffic"].id, ua.id
    H = _h(admin_user)

    rows = (await client.get(f"/api/vacancies/{ua_id}/applications?all_recruiters=true", headers=H)).json()
    pr = next(r for r in rows if r["entity_id"] == pid)["prior_rejection"]
    assert pr["vacancy_title"] == "Трафик" and pr["comment"] == "Нет опыта"
    # В самой «Трафик» он на «Отказе» — это не «прошлый» отказ.
    rows = (await client.get(f"/api/vacancies/{traffic_id}/applications?all_recruiters=true", headers=H)).json()
    assert next(r for r in rows if r["entity_id"] == pid)["prior_rejection"] is None


async def test_card_endpoint_and_deleted_funnel(client, db_session, organization, department, admin_user, setup):
    H = _h(admin_user)
    items = (await client.get(f"/api/entities/{setup['new_id']}/prior-rejections", headers=H)).json()["items"]
    assert [(i["vacancy_title"], i["entity_id"]) for i in items] == [("Трафик", setup["old_id"])]

    # Отказ в УДАЛЁННОЙ воронке не считается — её нет нигде в интерфейсе.
    gone = await _vacancy(db_session, organization, department, admin_user, "Удалённая",
                          deleted_at=datetime.utcnow())
    person = await _entity(db_session, organization, admin_user, "Орлов")
    await _reject(db_session, person, gone, admin_user)
    items = (await client.get(f"/api/entities/{person.id}/prior-rejections", headers=H)).json()["items"]
    assert items == []


async def test_extension_check_duplicate_reports_rejection(client, db_session, organization, admin_user, setup):
    old = await db_session.get(Entity, setup["old_id"])
    old.email = "polina@mail.test"
    await db_session.commit()
    r = await client.post("/api/magic-button/check-duplicate", headers=_h(admin_user),
                          json={"full_name": "Полина Иванова", "email": "polina@mail.test"})
    assert r.status_code == 200, r.text
    pr = r.json()["prior_rejection"]
    assert pr["vacancy_title"] == "Трафик" and pr["comment"] == "Не сдал тестовое"


async def test_web_check_before_create(client, admin_user, setup):
    """Окна «Новый кандидат» / «Загрузка из файла» — тот же ответ, что расширению."""
    r = await client.post("/api/entities/check-duplicate", headers=_h(admin_user),
                          json={"full_name": "Иванова Полина"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["prior_rejection"]["vacancy_title"] == "Трафик"
    assert {d["entity_id"] for d in body["duplicates"]} >= {setup["new_id"]}


async def test_dangling_flags(db_session, organization, admin_user, org_owner):
    from sqlalchemy import select
    from api.models.database import DataMigrationMark
    from api.services.duplicate_flags import clear_dangling_once, repoint_on_merge

    a = await _entity(db_session, organization, admin_user, "А")
    b = await _entity(db_session, organization, admin_user, "Б")
    c = await _entity(db_session, organization, admin_user, "В", extra_data={
        "hidden_duplicate_id": a.id, "hidden_duplicate_meta": {"matched_id": a.id, "level": "exact"}})
    gone = await _entity(db_session, organization, admin_user, "Г", extra_data={"hidden_duplicate_id": 999999})
    a_id, b_id, c_id, gone_id = a.id, b.id, c.id, gone.id

    # Слияние А → Б: пометка у В смотрела на А и переезжает на Б.
    assert await repoint_on_merge(db_session, a_id, b_id, organization.id) == 1
    await db_session.commit()
    c = (await db_session.execute(select(Entity).where(Entity.id == c_id))).scalar_one()
    assert c.extra_data["hidden_duplicate_id"] == b_id
    assert c.extra_data["hidden_duplicate_meta"]["matched_id"] == b_id

    # Висящая пометка на несуществующую карточку снимается разово.
    assert await clear_dangling_once(db_session) == 1
    gone = (await db_session.execute(select(Entity).where(Entity.id == gone_id))).scalar_one()
    assert "hidden_duplicate_id" not in gone.extra_data
    assert await db_session.get(DataMigrationMark, "dangling_duplicate_flags_2026_10_22") is not None
    assert await clear_dangling_once(db_session) == 0
