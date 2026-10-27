"""Дата перевода на текущий статус: подпись в строке и порядок списка.

Мария, 20.10.2026: «какие-то кандидаты стоят под актуальным статусом, а
какие-то — просто под рандомными числами… видим статус „оффер принят“ и дату
его перевода на этот статус»; «если человеку отказали 08.10, перед ним должен
стоять тот, кому отказали 09.10».
"""
from datetime import datetime, timedelta, timezone

import pytest

from api.models.database import (
    ApplicationStage, Entity, EntityStatus, EntityType, STATUS_SYNC_MAP,
    StageTransition, Vacancy, VacancyApplication, VacancyStatus,
)
from api.services.auth import create_access_token
from api.services.status_dates import status_changed_at_map


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


async def _candidate(db, org, user, status, name, extra=None):
    e = Entity(
        org_id=org.id, name=name, type=EntityType.candidate, status=status,
        created_by=user.id, created_at=datetime(2026, 1, 1), extra_data=extra or {},
    )
    db.add(e)
    await db.commit()
    await db.refresh(e)
    return e


async def _moved(db, org, user, entity, stage, when):
    """Заявка + запись истории о переводе на этот этап."""
    v = Vacancy(
        org_id=org.id, created_by=user.id, title="Трафик", status=VacancyStatus.open,
        created_at=when, updated_at=when,
    )
    db.add(v)
    await db.commit()
    app = VacancyApplication(
        vacancy_id=v.id, entity_id=entity.id, stage=stage, stage_order=1,
        created_by=user.id, applied_at=when, last_stage_change_at=when, updated_at=when,
    )
    db.add(app)
    await db.commit()
    db.add(StageTransition(
        application_id=app.id, entity_id=entity.id, from_stage=ApplicationStage.applied.value,
        to_stage=stage.value, changed_by=user.id, created_at=when,
    ))
    await db.commit()
    return app


@pytest.mark.asyncio
async def test_date_comes_from_the_transition_to_current_status(
    db_session, organization, admin_user, org_owner
):
    e = await _candidate(db_session, organization, admin_user, EntityStatus.rejected, "Отказник")
    old = datetime(2026, 10, 1, 9, 0)
    fresh = datetime(2026, 10, 9, 9, 0)
    app = await _moved(db_session, organization, admin_user, e,
                       STATUS_SYNC_MAP[EntityStatus.rejected], fresh)
    # Более ранний перевод на ДРУГОЙ этап дату не определяет.
    db_session.add(StageTransition(
        application_id=app.id, entity_id=e.id, from_stage=None,
        to_stage=STATUS_SYNC_MAP[EntityStatus.offer].value,
        changed_by=admin_user.id, created_at=old + timedelta(days=3),
    ))
    db_session.add(StageTransition(
        application_id=app.id, entity_id=e.id, from_stage=None,
        to_stage=STATUS_SYNC_MAP[EntityStatus.rejected].value,
        changed_by=admin_user.id, created_at=old,
    ))
    await db_session.commit()

    got = await status_changed_at_map(db_session, [e])
    assert got[e.id] == fresh


@pytest.mark.asyncio
async def test_date_from_card_note_for_candidate_without_funnels(
    db_session, organization, admin_user, org_owner
):
    """Вне воронок перевод живёт записью в ленте карточки — её и берём."""
    when = datetime(2026, 10, 19, 12, 30, tzinfo=timezone.utc)
    e = await _candidate(
        db_session, organization, admin_user, EntityStatus.hired, "Принял оффер",
        {"notes": [
            {"id": "1", "text": "", "date": when.isoformat(), "stage": EntityStatus.hired.value},
            {"id": "2", "text": "просто комментарий", "date": "2026-10-20T08:00:00+00:00"},
        ]},
    )
    got = await status_changed_at_map(db_session, [e])
    assert got[e.id] == when.replace(tzinfo=None)


@pytest.mark.asyncio
async def test_no_transition_no_date(db_session, organization, admin_user, org_owner):
    """Статус выставлен правкой карточки — истории нет, даты не выдумываем."""
    e = await _candidate(db_session, organization, admin_user, EntityStatus.new, "Новый")
    assert await status_changed_at_map(db_session, [e]) == {}


@pytest.mark.asyncio
async def test_kanban_orders_by_created_at_shows_status_date(
    client, db_session, organization, admin_user, org_owner
):
    """Порядок — по дате ДОБАВЛЕНИЯ, свежие сверху (владелец, 21.10.2026), даже
    если другого перевели на этап позже; дата перевода — только подпись."""
    old = await _candidate(db_session, organization, admin_user, EntityStatus.rejected, "Добавлен давно")
    fresh = await _candidate(db_session, organization, admin_user, EntityStatus.rejected, "Добавлен недавно")
    await _moved(db_session, organization, admin_user, old,
                 STATUS_SYNC_MAP[EntityStatus.rejected], datetime(2026, 10, 9, 10, 0))
    await _moved(db_session, organization, admin_user, fresh,
                 STATUS_SYNC_MAP[EntityStatus.rejected], datetime(2026, 10, 8, 10, 0))
    old.created_at = datetime(2026, 9, 1)
    fresh.created_at = datetime(2026, 10, 15)
    await db_session.commit()

    r = await client.get("/api/candidates/kanban", headers=_h(admin_user))
    assert r.status_code == 200, r.text
    column = next(c for c in r.json()["columns"] if c["status"] == "rejected")
    names = [c["name"] for c in column["cards"]]
    assert names.index("Добавлен недавно") < names.index("Добавлен давно")
    ranks = {c["name"]: c["rank"] for c in column["cards"]}
    assert ranks["Добавлен недавно"] < ranks["Добавлен давно"]
    card = next(c for c in column["cards"] if c["name"] == "Добавлен давно")
    assert card["status_changed_at"].startswith("2026-10-09")


@pytest.mark.asyncio
async def test_dismissed_gets_date_of_board_rejection(
    client, db_session, organization, department, admin_user, org_owner,
):
    """Уволенного доска переводит в воронке в «Отказ» — эта дата и стоит в
    строке «Все кандидаты» (вкладка «Отказ»), а не дата добавления."""
    from api.models.database import (
        ApplicationStage, Entity, EntityStatus, EntityType, Vacancy, VacancyApplication,
        VacancyStatus,
    )
    from api.services.auth import create_access_token

    h = {"Authorization": f"Bearer {create_access_token(data={'sub': str(admin_user.id)})}"}
    now = datetime.utcnow()
    e = Entity(org_id=organization.id, name="Уволенов Урал", type=EntityType.candidate,
               status=EntityStatus.transferred, created_by=admin_user.id,
               created_at=now - timedelta(days=90), extra_data={})
    v = Vacancy(org_id=organization.id, department_id=department.id, created_by=admin_user.id,
                title="Трафик", status=VacancyStatus.open, salary_currency="RUB",
                created_at=now, updated_at=now)
    db_session.add_all([e, v])
    await db_session.commit()
    db_session.add(VacancyApplication(vacancy_id=v.id, entity_id=e.id, stage=ApplicationStage.transferred,
                                      stage_order=1, created_by=admin_user.id, applied_at=now,
                                      last_stage_change_at=now, updated_at=now))
    await db_session.commit()
    r = await client.patch(f"/api/staff-board/rows/{e.id}", json={"status": "dismissed"}, headers=h)
    assert r.status_code == 200, r.text
    cols = {c["status"]: c for c in (await client.get("/api/candidates/kanban", headers=h)).json()["columns"]}
    card = next(c for c in cols["rejected"]["cards"] if c["id"] == e.id)
    assert card["status_changed_at"] and card["status_changed_at"][:10] == now.date().isoformat()
