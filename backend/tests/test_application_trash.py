"""«Удалить с воронки» — тоже в корзину на 7 дней (владелец, 21.10.2026).

Раньше кнопка стирала навсегда этап, автора заявки, историю переводов с
комментариями и закреп. С фильтром «Рекрутёры» коллега видит чужих кандидатов
и может промахнуться — теперь админ возвращает заявку как была.
"""
from datetime import datetime

import pytest
from sqlalchemy import select

from api.models.database import (
    ApplicationStage, DeletedEntity, Entity, EntityStatus, EntityType, StageTransition,
    Vacancy, VacancyApplication, VacancyStatus,
)
from api.services.auth import create_access_token


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


@pytest.fixture
async def in_funnel(db_session, organization, department, admin_user, org_owner):
    now = datetime.utcnow()
    e = Entity(org_id=organization.id, name="Иванов Иван", type=EntityType.candidate,
               status=EntityStatus.interview, created_by=admin_user.id, created_at=now)
    v = Vacancy(org_id=organization.id, department_id=department.id, created_by=admin_user.id,
                title="Трафик", status=VacancyStatus.open, salary_currency="RUB",
                created_at=now, updated_at=now)
    db_session.add_all([e, v])
    await db_session.commit()
    app = VacancyApplication(vacancy_id=v.id, entity_id=e.id, stage=ApplicationStage.interview,
                             stage_order=1, created_by=admin_user.id, applied_at=now,
                             last_stage_change_at=now, updated_at=now)
    db_session.add(app)
    await db_session.commit()
    db_session.add(StageTransition(application_id=app.id, entity_id=e.id, from_stage="screening",
                                   to_stage="interview", changed_by=admin_user.id,
                                   comment="прислал тестовое", created_at=now))
    await db_session.commit()
    return {"eid": e.id, "vid": v.id, "app_id": app.id}


async def _remove(client, H, app_id):
    r = await client.delete(f"/api/vacancies/applications/{app_id}", headers=H)
    assert r.status_code in (200, 204), r.text


async def _trash_item(client, H, eid):
    # Заголовок считаем заранее: после expire_all() обращение к user.id в async падает.
    items = (await client.get("/api/entities/trash", headers=H)).json()["items"]
    return next(i for i in items if i["entity_id"] == eid and i["kind"] == "application")


async def test_removed_from_funnel_goes_to_trash_and_comes_back(client, db_session, admin_user, in_funnel):
    H = _h(admin_user)
    eid, vid, app_id = in_funnel["eid"], in_funnel["vid"], in_funnel["app_id"]
    admin_name, admin_id = admin_user.name, admin_user.id
    await _remove(client, H, app_id)

    db_session.expire_all()
    assert (await db_session.get(VacancyApplication, app_id)) is None
    assert (await db_session.get(Entity, eid)) is not None  # карточка осталась

    item = await _trash_item(client, H, eid)
    assert item["vacancy_title"] == "Трафик"
    assert item["stage"] == "interview"
    assert item["owner_name"] == admin_name
    assert item["deleted_by_name"] == admin_name
    assert item["restorable"] is True
    assert item["summary"]["history"] == 1

    r = await client.post(f"/api/entities/trash/{item['id']}/restore", headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["kind"] == "application" and r.json()["vacancy_id"] == vid

    db_session.expire_all()
    app = await db_session.get(VacancyApplication, app_id)
    assert app is not None and app.stage == ApplicationStage.interview
    assert app.created_by == admin_id
    history = (await db_session.execute(
        select(StageTransition).where(StageTransition.application_id == app_id)
    )).scalars().all()
    assert [h.comment for h in history] == ["прислал тестовое"]
    # Снятие с последней воронки сбрасывало статус в «Новый» — возврат его чинит.
    assert (await db_session.get(Entity, eid)).status != EntityStatus.new


async def test_restore_refused_if_candidate_added_again(client, db_session, admin_user, in_funnel):
    H = _h(admin_user)
    eid, vid, app_id = in_funnel["eid"], in_funnel["vid"], in_funnel["app_id"]
    await _remove(client, H, app_id)
    db_session.add(VacancyApplication(vacancy_id=vid, entity_id=eid, stage=ApplicationStage.applied,
                                      stage_order=1, created_by=admin_user.id, applied_at=datetime.utcnow()))
    await db_session.commit()
    item = await _trash_item(client, H, eid)
    r = await client.post(f"/api/entities/trash/{item['id']}/restore", headers=H)
    assert r.status_code == 409
    assert "снова добавили" in r.json()["detail"]


async def test_restore_refused_if_candidate_deleted(client, db_session, admin_user, in_funnel):
    H = _h(admin_user)
    eid, app_id = in_funnel["eid"], in_funnel["app_id"]
    await _remove(client, H, app_id)
    r = await client.delete(f"/api/entities/{eid}", headers=H)
    assert r.status_code in (200, 204), r.text
    item = await _trash_item(client, H, eid)
    r = await client.post(f"/api/entities/trash/{item['id']}/restore", headers=H)
    assert r.status_code == 409
    assert "удалили целиком" in r.json()["detail"]


async def test_entity_trash_rows_still_say_entity(client, db_session, admin_user, in_funnel):
    H = _h(admin_user)
    eid = in_funnel["eid"]
    r = await client.delete(f"/api/entities/{eid}", headers=H)
    assert r.status_code in (200, 204), r.text
    items = (await client.get("/api/entities/trash", headers=H)).json()["items"]
    row = next(i for i in items if i["entity_id"] == eid)
    assert row["kind"] == "entity"
    rec = (await db_session.execute(select(DeletedEntity).where(DeletedEntity.entity_id == eid))).scalar_one()
    assert (rec.kind or "entity") == "entity"


async def test_removed_application_opens_as_card(client, db_session, admin_user, in_funnel):
    """Удалённую из воронки заявку тоже можно открыть: живая карточка + блок
    этой воронки с историей из слепка (23.10.2026)."""
    H = _h(admin_user)
    eid, app_id = in_funnel["eid"], in_funnel["app_id"]
    await _remove(client, H, app_id)
    item = await _trash_item(client, H, eid)
    view = (await client.get(f"/api/entities/trash/{item['id']}/card", headers=H)).json()
    assert view["card"]["name"] == "Иванов Иван"
    assert view["trash"]["kind"] == "application"
    [block] = view["blocks"]
    assert (block["vacancy_title"], block["current_stage"]) == ("Трафик", "interview")
    assert [ev["comment"] for ev in block["events"]] == ["прислал тестовое"]
