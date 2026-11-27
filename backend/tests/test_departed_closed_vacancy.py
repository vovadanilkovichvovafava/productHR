"""Уволенный — «Мы уволили» везде (Мария, 27.11.2026).

1) Наумович: вакансию закрыли после найма, и увольнение не трогало заявку в
   ней — в списке «Мы уволили», в карточке зелёный «Перешёл в отдел».
   Теперь увольнение закрывает заявки и в закрытых вакансиях; уже уволенных
   выравнивает разовый шаг, в ленте остаётся одна строка.
2) Пищ: «Отказ», который поставило увольнение, подписан в строке списка
   «Мы уволили», а не «Отказ».
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from api.models.database import (
    ApplicationStage, DataMigrationMark, Entity, EntityStatus, EntityType, StageTransition,
    Vacancy, VacancyApplication, VacancyStatus,
)
from api.services.auth import create_access_token
from api.services.departed_closed_vacancy_sync import SYNC_MARK, close_departed_closed_vacancy_apps_once
from api.services.hr_stages import departure_of_comment


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


async def _vac(db, org, user, title, status=VacancyStatus.open):
    now = datetime.utcnow()
    v = Vacancy(org_id=org.id, created_by=user.id, title=title, status=status,
                salary_currency="RUB", created_at=now, updated_at=now, visible_to_all=True)
    db.add(v)
    await db.commit()
    await db.refresh(v)
    return v


async def _person(db, org, user, status, notes=None):
    e = Entity(org_id=org.id, created_by=user.id, name="Наумович Тест", type=EntityType.candidate,
               status=status, created_at=datetime.utcnow(), extra_data={"notes": notes or []})
    db.add(e)
    await db.commit()
    await db.refresh(e)
    return e


async def _app(db, vacancy, entity, user, stage):
    now = datetime.utcnow()
    a = VacancyApplication(vacancy_id=vacancy.id, entity_id=entity.id, stage=stage, stage_order=1,
                           created_by=user.id, applied_at=now, last_stage_change_at=now, updated_at=now)
    db.add(a)
    await db.commit()
    await db.refresh(a)
    return a


def test_departure_of_comment():
    assert departure_of_comment("Мы уволили — не тянул") == "dismissed"
    assert departure_of_comment("Сам уволился") == "quit"
    assert departure_of_comment("Не подошёл") is None
    assert departure_of_comment(None) is None


@pytest.mark.asyncio
async def test_depart_closes_application_in_closed_vacancy(client, db_session, organization, admin_user, org_owner):
    closed = await _vac(db_session, organization, admin_user, "Creative Production Manager", VacancyStatus.closed)
    e = await _person(db_session, organization, admin_user, EntityStatus.transferred)
    await _app(db_session, closed, e, admin_user, ApplicationStage.transferred)
    eid = e.id

    r = await client.patch(f"/api/candidates/{eid}/status",
                           json={"status": "dismissed", "comment": "не показал результатов"},
                           headers=_h(admin_user))
    assert r.status_code == 200, r.text
    assert r.json()["note"] is None  # строка в ленте — перевод заявки

    db_session.expire_all()
    stage = (await db_session.execute(
        select(VacancyApplication.stage).where(VacancyApplication.entity_id == eid)
    )).scalar_one()
    assert stage == ApplicationStage.rejected
    comments = (await db_session.execute(
        select(StageTransition.comment).where(StageTransition.entity_id == eid)
    )).scalars().all()
    assert comments == ["Мы уволили — не показал результатов"]
    ent = await db_session.get(Entity, eid)
    assert not [n for n in ent.extra_data.get("notes") or [] if n.get("stage")]


@pytest.mark.asyncio
async def test_sync_turns_departure_note_into_transition(db_session, organization, admin_user):
    closed = await _vac(db_session, organization, admin_user, "Creative Production Manager", VacancyStatus.closed)
    when = datetime(2026, 11, 27, 14, 28, 53)
    note = {"id": "n1", "text": "Не показал результатов", "stage": "dismissed", "from_status": "transferred",
            "author_id": admin_user.id, "date": when.replace(tzinfo=timezone.utc).isoformat()}
    plain = {"id": "n0", "text": "обычный комментарий", "date": (when - timedelta(days=1)).isoformat()}
    e = await _person(db_session, organization, admin_user, EntityStatus.dismissed, [plain, note])
    e.extra_data = {**e.extra_data, "pinned_entry_key": "n:n1"}
    await db_session.commit()
    app = await _app(db_session, closed, e, admin_user, ApplicationStage.transferred)
    # Уволенный без живых заявок — не трогаем.
    other = await _person(db_session, organization, admin_user, EntityStatus.quit,
                          [{**note, "id": "n2", "stage": "quit"}])
    eid, app_id, other_id, uid = e.id, app.id, other.id, admin_user.id

    assert await close_departed_closed_vacancy_apps_once(db_session) == [f"{eid}:{app_id}"]

    db_session.expire_all()
    a = await db_session.get(VacancyApplication, app_id)
    assert a.stage == ApplicationStage.rejected
    assert a.last_stage_change_at == when
    tr = (await db_session.execute(
        select(StageTransition).where(StageTransition.application_id == app_id)
    )).scalar_one()
    assert (tr.from_stage, tr.to_stage) == ("transferred", "rejected")
    assert tr.comment == "Мы уволили — Не показал результатов"
    assert tr.created_at == when and tr.changed_by == uid
    ent = await db_session.get(Entity, eid)
    assert [n["id"] for n in ent.extra_data["notes"]] == ["n0"]   # одна строка в ленте
    assert "pinned_entry_key" not in ent.extra_data
    assert ent.status == EntityStatus.dismissed
    assert [n["id"] for n in (await db_session.get(Entity, other_id)).extra_data["notes"]] == ["n2"]
    assert await db_session.get(DataMigrationMark, SYNC_MARK) is not None
    assert await close_departed_closed_vacancy_apps_once(db_session) == []


@pytest.mark.asyncio
async def test_list_chip_says_dismissed_not_rejected(client, db_session, organization, admin_user, org_owner):
    traffic = await _vac(db_session, organization, admin_user, "Трафик")
    seo = await _vac(db_session, organization, admin_user, "SEO")
    e = await _person(db_session, organization, admin_user, EntityStatus.probation)
    await _app(db_session, traffic, e, admin_user, ApplicationStage.probation)
    # Настоящий отказ в другой воронке (был раньше практики) так и остаётся «Отказом».
    seo_app = await _app(db_session, seo, e, admin_user, ApplicationStage.rejected)
    db_session.add(StageTransition(application_id=seo_app.id, entity_id=e.id, from_stage="screening",
                                   to_stage="rejected", comment="не подошёл", created_at=datetime(2026, 9, 1)))
    await db_session.commit()
    eid = e.id
    headers = _h(admin_user)
    r = await client.patch(f"/api/candidates/{eid}/status",
                           json={"status": "dismissed", "comment": "скорость"}, headers=headers)
    assert r.status_code == 200, r.text

    board = (await client.get("/api/candidates/kanban?per_column=500", headers=headers)).json()
    card = next(c for col in board["columns"] for c in col["cards"] if c["id"] == eid)
    by_title = {f["vacancy_title"]: f for f in card["funnels"]}
    assert by_title["Трафик"]["stage"] == "rejected" and by_title["Трафик"]["departed"] == "dismissed"
    assert by_title["SEO"]["stage"] == "rejected" and by_title["SEO"]["departed"] is None
