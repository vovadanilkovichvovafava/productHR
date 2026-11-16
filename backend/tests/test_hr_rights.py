"""Права HR: у кандидата один HR, прежний — сорсер, участники (тикет Маши 13.11.2026).

Таблица «трек АТС», «права HR»: «нет возможности самостоятельно изменить
основного HR, открепить второго HR или передать кандидата другому сотруднику
без потери истории работы». Решение владельца 16.11.2026: «должен быть только
один HR… если Влада забирает себе кандидата, а работу начала Эльвира, то
Эльвира автоматически становится сорсером, и это должно отображаться в штате».
Правила — services/candidate_hr.py.
"""
from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy import select

from api.models.database import (
    ApplicationCoRecruiter, ApplicationStage, DepartmentFeature, Entity, EntityStatus, EntityTag, EntityType,
    OrgMember, OrgRole, StageTransition, User, UserRole, Vacancy, VacancyApplication,
    VacancyStatus, entity_tag_association,
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


async def _vac(db, org, owner, title):
    v = Vacancy(org_id=org.id, title=title, status=VacancyStatus.open, created_by=owner.id,
                visible_to_all=True, created_at=datetime.utcnow())
    db.add(v)
    await db.commit()
    return v


@pytest_asyncio.fixture
async def s(db_session, organization, admin_user, org_owner):
    """Диана: нашла и ведёт Эльвира в «Трафике» (этап «Практика»)."""
    db_session.add(DepartmentFeature(org_id=organization.id, department_id=None,
                                     feature_name="candidate_database", enabled=True))
    elv = await _recruiter(db_session, organization, "elv@t.ru", "Эльвира")
    vlada = await _recruiter(db_session, organization, "vlada@t.ru", "Влада")
    maria = await _recruiter(db_session, organization, "maria@t.ru", "Мария")
    traffic = await _vac(db_session, organization, admin_user, "Трафик")
    seo = await _vac(db_session, organization, admin_user, "SEO")
    e = Entity(org_id=organization.id, name="Диана", type=EntityType.candidate,
               status=EntityStatus.probation, created_by=elv.id, created_at=datetime.utcnow())
    db_session.add(e)
    await db_session.commit()
    app = VacancyApplication(vacancy_id=traffic.id, entity_id=e.id, stage=ApplicationStage.probation,
                             stage_order=1, created_by=elv.id, applied_at=datetime.utcnow())
    db_session.add(app)
    await db_session.commit()
    db_session.add(StageTransition(application_id=app.id, entity_id=e.id, from_stage="phone_screen",
                                   to_stage="probation", changed_by=elv.id, comment="Перформер, вовлечённая"))
    await db_session.commit()
    return {"elv": elv, "vlada": vlada, "maria": maria, "traffic": traffic, "seo": seo,
            "e": e, "eid": e.id, "app_id": app.id}


async def _team(client, user, eid):
    r = await client.get(f"/api/entities/{eid}/team", headers=_h(user))
    assert r.status_code == 200, r.text
    return r.json()


async def _owners(db, eid):
    return sorted((await db.execute(
        select(VacancyApplication.created_by).where(VacancyApplication.entity_id == eid)
        .execution_options(populate_existing=True)
    )).scalars().all())


@pytest.mark.asyncio
async def test_take_makes_one_hr_prev_becomes_sourcer_and_undo(client, db_session, admin_user, s):
    r = await client.post(f"/api/vacancies/{s['traffic'].id}/applications/take",
                          json={"entity_id": s["eid"], "recruiter_id": s["vlada"].id}, headers=_h(s["vlada"]))
    assert r.status_code == 200, r.text
    assert r.json()["take_outcome"] == "transferred"
    team = await _team(client, admin_user, s["eid"])
    assert team["hr"]["name"] == "Влада"
    assert [x["name"] for x in team["sourcers"]] == ["Эльвира"]
    assert team["participants"] == []
    # Метка «HR: …» — одна.
    ent = await db_session.get(Entity, s["eid"], populate_existing=True)
    assert [t["name"] for t in ent.extra_data["system_hr_tags"]] == ["Влада"]

    # История собеседования не тронута, этап тот же; смена — отдельной строкой.
    hist = (await db_session.execute(
        select(StageTransition).where(StageTransition.application_id == s["app_id"]).order_by(StageTransition.id)
    )).scalars().all()
    assert hist[0].comment == "Перформер, вовлечённая"
    assert hist[-1].comment == "Сменился HR: теперь Влада, раньше Эльвира. Эльвира — сорсер"
    assert hist[-1].from_stage == hist[-1].to_stage == "probation"

    # Корзина у строки «Сменился HR» — отмена: HR Эльвира, сорсера нет.
    r = await client.delete(f"/api/vacancies/applications/{s['app_id']}/history/{hist[-1].id}", headers=_h(s["vlada"]))
    assert r.status_code == 200, r.text
    assert r.json()["hr_change"] == "undone" and r.json()["stage"] == "probation"
    team = await _team(client, admin_user, s["eid"])
    assert team["hr"]["name"] == "Эльвира" and team["sourcers"] == []
    assert await _owners(db_session, s["eid"]) == [s["elv"].id]
    ent = await db_session.get(Entity, s["eid"], populate_existing=True)
    assert ent.created_by == s["elv"].id
    left = (await db_session.execute(
        select(StageTransition.comment).where(StageTransition.application_id == s["app_id"])
    )).scalars().all()
    assert left == ["Перформер, вовлечённая"]


@pytest.mark.asyncio
async def test_existing_sourcer_is_kept_and_chain(client, db_session, admin_user, organization, s):
    """Сорсер уже есть — не меняем: Эльвира → Влада → Мария, сорсер — Эльвира."""
    for who in ("vlada", "maria"):
        r = await client.post(f"/api/entities/{s['eid']}/hr", json={"user_id": s[who].id}, headers=_h(admin_user))
        assert r.status_code == 200, r.text
    team = await _team(client, admin_user, s["eid"])
    assert team["hr"]["name"] == "Мария"
    assert [x["name"] for x in team["sourcers"]] == ["Эльвира"]


@pytest.mark.asyncio
async def test_hr_is_one_across_funnels_and_adding_makes_participant(client, db_session, admin_user, s):
    # Мария добавляет Диану в свою воронку SEO — HR остаётся Эльвира, Мария — участник.
    r = await client.post(f"/api/vacancies/{s['seo'].id}/applications",
                          json={"entity_id": s["eid"], "vacancy_id": s["seo"].id}, headers=_h(s["maria"]))
    assert r.status_code in (200, 201), r.text
    assert await _owners(db_session, s["eid"]) == [s["elv"].id, s["elv"].id]
    team = await _team(client, admin_user, s["eid"])
    assert team["hr"]["name"] == "Эльвира"
    assert [p["name"] for p in team["participants"]] == ["Мария"]
    # Мария видит её в «своих» в SEO (участник считается своим).
    r = await client.get(f"/api/vacancies/{s['seo'].id}/applications?created_by={s['maria'].id}", headers=_h(s["maria"]))
    assert [a["entity_id"] for a in r.json()] == [s["eid"]]

    # «Сменить HR» на Владу с «оставить участником» — HR во ВСЕХ воронках.
    r = await client.post(f"/api/entities/{s['eid']}/hr",
                          json={"user_id": s["vlada"].id, "keep_prev_as_participant": True}, headers=_h(admin_user))
    assert r.status_code == 200, r.text
    assert await _owners(db_session, s["eid"]) == [s["vlada"].id, s["vlada"].id]
    team = r.json()["team"]
    assert team["hr"]["name"] == "Влада"
    assert sorted(p["name"] for p in team["participants"]) == ["Мария", "Эльвира"]
    assert [x["name"] for x in team["sourcers"]] == ["Эльвира"]

    # Снять участника.
    r = await client.delete(f"/api/entities/{s['eid']}/participants/{s['maria'].id}", headers=_h(admin_user))
    assert [p["name"] for p in r.json()["team"]["participants"]] == ["Эльвира"]
    r = await client.post(f"/api/entities/{s['eid']}/participants", json={"user_id": s["maria"].id}, headers=_h(admin_user))
    assert sorted(p["name"] for p in r.json()["team"]["participants"]) == ["Мария", "Эльвира"]


@pytest.mark.asyncio
async def test_board_hr_follows_funnel_and_edit_changes_hr(client, db_session, admin_user, s):
    # Расхождение как на проде: на доске руками Влада, в воронке Эльвира.
    ent = await db_session.get(Entity, s["eid"])
    ent.extra_data = {"assignee_user_ids": [s["vlada"].id], "assignee_user_id": str(s["vlada"].id)}
    await db_session.commit()
    from api.services.hr_tags import sync_for_entity
    await sync_for_entity(db_session, s["eid"])

    rows = (await client.get("/api/staff-board/rows", headers=_h(admin_user))).json()
    row = next(x for x in rows if x["entity_id"] == s["eid"])
    assert [a["name"] for a in row["assignees"]] == ["Эльвира"]  # доска = воронка

    # На доске добавили Марию — это смена HR кандидата.
    r = await client.patch(f"/api/staff-board/rows/{s['eid']}",
                           json={"assignee_user_ids": [s["elv"].id, s["maria"].id]}, headers=_h(admin_user))
    assert r.status_code == 200, r.text
    assert [a["name"] for a in r.json()["assignees"]] == ["Мария"]
    assert [x["name"] for x in r.json()["sourcers"]] == ["Эльвира"]
    assert await _owners(db_session, s["eid"]) == [s["maria"].id]

    # Снять HR совсем у человека в воронке нельзя.
    r = await client.patch(f"/api/staff-board/rows/{s['eid']}", json={"assignee_user_ids": []}, headers=_h(admin_user))
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_hr_and_participant_must_be_recruiters(client, db_session, admin_user, organization, s):
    stranger = User(email="x@t.ru", password_hash=hash_password("x"), name="Сотрудник", role=UserRole.admin)
    db_session.add(stranger)
    await db_session.flush()
    db_session.add(OrgMember(org_id=organization.id, user_id=stranger.id, role=OrgRole.member))
    await db_session.commit()
    r = await client.post(f"/api/entities/{s['eid']}/hr", json={"user_id": stranger.id}, headers=_h(admin_user))
    assert r.status_code == 400
    r = await client.post(f"/api/entities/{s['eid']}/participants", json={"user_id": stranger.id}, headers=_h(admin_user))
    assert r.status_code == 400
    # Сорсер-метка не появилась от неудачной попытки.
    tags = (await db_session.execute(
        select(EntityTag.name).join(entity_tag_association, entity_tag_association.c.tag_id == EntityTag.id)
        .where(entity_tag_association.c.entity_id == s["eid"])
    )).scalars().all()
    assert tags == []
    assert ApplicationCoRecruiter  # импорт для читаемости моделей


@pytest.mark.asyncio
async def test_remove_from_funnel_keeps_history_in_card_and_restore_drops_copy(client, db_session, admin_user, s):
    """«Удалить с воронки» не стирает историю: этапы и комментарии остаются в
    карточке (extra_data.removed_funnels), вернули из корзины — копия убрана."""
    r = await client.delete(f"/api/vacancies/applications/{s['app_id']}", headers=_h(admin_user))
    assert r.status_code in (200, 204), r.text
    ent = await db_session.get(Entity, s["eid"], populate_existing=True)
    removed = ent.extra_data["removed_funnels"]
    assert len(removed) == 1 and removed[0]["vacancy_title"] == "Трафик"
    assert [e["comment"] for e in removed[0]["events"]] == ["Перформер, вовлечённая"]
    assert removed[0]["removed_by_name"] and removed[0]["stage"] == "probation"

    trash = (await client.get("/api/entities/trash", headers=_h(admin_user))).json()
    rec = next(t for t in (trash if isinstance(trash, list) else trash["items"]) if t.get("kind") == "application")
    r = await client.post(f"/api/entities/trash/{rec['id']}/restore", headers=_h(admin_user))
    assert r.status_code == 200, r.text
    ent = await db_session.get(Entity, s["eid"], populate_existing=True)
    assert ent.extra_data.get("removed_funnels") == []


@pytest.mark.asyncio
async def test_analytics_counts_candidate_for_main_hr_not_vacancy_owner(client, db_session, admin_user, s):
    """«Основной HR — тот, кто учитывается в аналитике». Воронка «Трафик» создана
    админом, кандидат — Эльвиры: в разбивке по рекрутёрам он у Эльвиры; после
    «Забрать» — у Влады, у Эльвиры его больше нет."""
    async def by_rec():
        r = await client.get("/api/analytics/reports/funnel-by-recruiter?period=current&vacancy_status=all",
                             headers=_h(admin_user))
        assert r.status_code == 200, r.text
        return {x["recruiter_name"]: x["total_candidates"] for x in r.json()["by_recruiter"]}

    app = await db_session.get(VacancyApplication, s["app_id"])
    app.stage = ApplicationStage.screening  # этап воронки, который считает отчёт
    await db_session.commit()
    got = await by_rec()
    assert got.get("Эльвира") == 1 and not got.get(admin_user.name)
    await client.post(f"/api/vacancies/{s['traffic'].id}/applications/take",
                      json={"entity_id": s["eid"], "recruiter_id": s["vlada"].id}, headers=_h(admin_user))
    got = await by_rec()
    assert got.get("Влада") == 1 and not got.get("Эльвира")


@pytest.mark.asyncio
async def test_conflicts_fix_only_when_hr_still_as_expected(db_session, admin_user, s, monkeypatch):
    from api.services import hr_conflicts_fix as F
    from api.services.candidate_hr import current_hr_id

    other = Entity(org_id=s["e"].org_id, name="Другой", type=EntityType.candidate,
                   status=EntityStatus.probation, created_by=s["vlada"].id, created_at=datetime.utcnow())
    db_session.add(other)
    await db_session.commit()
    monkeypatch.setattr(F, "FIXES", (
        (s["eid"], s["elv"].id, s["vlada"].id),     # HR как ждали — меняем
        (other.id, s["maria"].id, s["elv"].id),     # HR другой — не трогаем
    ))
    assert await F.fix_hr_conflicts_once(db_session) == [s["eid"]]
    ent = await db_session.get(Entity, s["eid"], populate_existing=True)
    assert await current_hr_id(db_session, ent) == s["vlada"].id
    assert await F.fix_hr_conflicts_once(db_session) == []  # одноразово


@pytest.mark.asyncio
async def test_card_mentor_is_board_mentor_and_board_row_flags_funnel(client, db_session, admin_user, s):
    """«Ментор практики» в карточке = «Рук. практики» на «Штате» (тикет 13.11.2026);
    строка доски человека в воронке помечена hr_in_funnel (ячейка HR — один выбор)."""
    from api.services.hr_tags import sync_for_entity
    await sync_for_entity(db_session, s["eid"])
    r = await client.put(f"/api/entities/{s['eid']}/mentor", json={"name": "Егор"}, headers=_h(admin_user))
    assert r.status_code == 200, r.text
    assert r.json()["team"]["mentor"] == "Егор" and "Влад" in r.json()["team"]["mentor_options"]
    rows = (await client.get("/api/staff-board/rows", headers=_h(admin_user))).json()
    row = next(x for x in rows if x["entity_id"] == s["eid"])
    assert row["manager"] == "Егор" and row["hr_in_funnel"] is True
    r = await client.put(f"/api/entities/{s['eid']}/mentor", json={"name": "Незнакомец"}, headers=_h(admin_user))
    assert r.status_code == 400
    r = await client.put(f"/api/entities/{s['eid']}/mentor", json={"name": None}, headers=_h(admin_user))
    assert r.json()["team"]["mentor"] is None
