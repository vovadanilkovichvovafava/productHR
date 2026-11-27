"""«Отказ» или «Мы уволили» / «Сам уволился» — по истории человека (27.11.2026).

Мария: в истории есть «Практика» или «Перешёл в отдел» — доступны только
«Мы уволили» и «Сам уволился»; иначе — только «Отказ». Сервер проверяет это
сам (services/exit_status.py), доска «Штат» считает по статусам базы.
"""
from datetime import datetime

import pytest
from sqlalchemy import select

from api.models.database import (
    ApplicationStage, DataMigrationMark, Entity, EntityStatus, EntityType, StageTransition,
    Vacancy, VacancyApplication, VacancyStatus,
)
from api.services.auth import create_access_token
from api.services.departed_rejected_sync import SYNC_MARK, relabel_departed_rejected_once
from api.services.exit_status import NEED_DEPARTURE, NEED_REJECTION


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


async def _setup(db, org, user, status, worked: bool, app_stage=ApplicationStage.screening):
    now = datetime.utcnow()
    v = Vacancy(org_id=org.id, created_by=user.id, title="Трафик", status=VacancyStatus.open,
                salary_currency="RUB", created_at=now, updated_at=now, visible_to_all=True)
    e = Entity(org_id=org.id, created_by=user.id, name="Кандидат Тест", type=EntityType.candidate,
               status=status, created_at=now, extra_data={})
    db.add_all([v, e])
    await db.commit()
    a = VacancyApplication(vacancy_id=v.id, entity_id=e.id, stage=app_stage, stage_order=1,
                           created_by=user.id, applied_at=now, last_stage_change_at=now, updated_at=now)
    db.add(a)
    await db.commit()
    if worked:
        db.add(StageTransition(application_id=a.id, entity_id=e.id, from_stage="phone_screen",
                               to_stage="probation", changed_by=user.id, created_at=now))
        await db.commit()
    return e.id, a.id


@pytest.mark.asyncio
async def test_not_worked_only_rejection(client, db_session, organization, admin_user, org_owner):
    eid, app_id = await _setup(db_session, organization, admin_user, EntityStatus.screening, worked=False)
    headers = _h(admin_user)
    card = (await client.get(f"/api/entities/{eid}", headers=headers)).json()
    assert card["worked_here"] is False

    r = await client.patch(f"/api/candidates/{eid}/status",
                           json={"status": "dismissed", "comment": "причина"}, headers=headers)
    assert r.status_code == 400 and r.json()["detail"] == NEED_REJECTION
    r = await client.put(f"/api/vacancies/applications/{app_id}",
                         json={"stage": "rejected", "comment": "не подошёл", "expected_entity_id": eid},
                         headers=headers)
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_worked_only_departure(client, db_session, organization, admin_user, org_owner):
    eid, app_id = await _setup(db_session, organization, admin_user, EntityStatus.screening,
                               worked=True, app_stage=ApplicationStage.screening)
    headers = _h(admin_user)
    card = (await client.get(f"/api/entities/{eid}", headers=headers)).json()
    assert card["worked_here"] is True

    # «Отказ» не проходит ни через карточку, ни через воронку.
    r = await client.patch(f"/api/candidates/{eid}/status",
                           json={"status": "rejected", "comment": "x"}, headers=headers)
    assert r.status_code == 400 and r.json()["detail"] == NEED_DEPARTURE
    r = await client.put(f"/api/vacancies/applications/{app_id}",
                         json={"stage": "rejected", "comment": "x", "expected_entity_id": eid},
                         headers=headers)
    assert r.status_code == 400 and r.json()["detail"] == NEED_DEPARTURE
    # «Сам уволился» — проходит и закрывает заявку «Отказом».
    r = await client.patch(f"/api/candidates/{eid}/status",
                           json={"status": "quit", "comment": "принял другой оффер"}, headers=headers)
    assert r.status_code == 200, r.text
    db_session.expire_all()
    assert (await db_session.get(VacancyApplication, app_id)).stage == ApplicationStage.rejected


@pytest.mark.asyncio
async def test_board_counts_by_base_statuses(client, db_session, organization, admin_user, org_owner):
    # «Отказ» человека, который был на практике, на доске больше не
    # подмешивается в «Мы уволили»: доска — по статусам базы.
    eid, _ = await _setup(db_session, organization, admin_user, EntityStatus.rejected,
                          worked=True, app_stage=ApplicationStage.rejected)
    rows = (await client.get("/api/staff-board/rows", headers=_h(admin_user))).json()
    assert eid not in {r["entity_id"] for r in rows}


@pytest.mark.asyncio
async def test_relabel_rejected_after_practice_by_feed(db_session, organization, admin_user):
    eid, app_id = await _setup(db_session, organization, admin_user, EntityStatus.rejected,
                               worked=True, app_stage=ApplicationStage.rejected)
    db_session.add(StageTransition(application_id=app_id, entity_id=eid, from_stage="probation",
                                   to_stage="rejected", changed_by=admin_user.id, comment="не прошёл",
                                   created_at=datetime.utcnow()))
    ent = await db_session.get(Entity, eid)
    ent.extra_data = {"notes": [{"id": "n1", "text": "удалил чат", "stage": "rejected", "date": "2026-10-26T10:00:00"}]}
    # Не работал — даже если попал в план, не трогаем.
    other_id, _ = await _setup(db_session, organization, admin_user, EntityStatus.rejected,
                               worked=False, app_stage=ApplicationStage.rejected)
    await db_session.commit()

    done = await relabel_departed_rejected_once(
        db_session, {eid: EntityStatus.quit, other_id: EntityStatus.dismissed},
    )
    assert done == [f"{eid}:quit"]

    db_session.expire_all()
    ent = await db_session.get(Entity, eid)
    assert ent.status == EntityStatus.quit
    last = (await db_session.execute(
        select(StageTransition.comment).where(
            StageTransition.application_id == app_id, StageTransition.to_stage == "rejected",
        )
    )).scalars().all()
    assert last == ["Сам уволился — не прошёл"]
    assert ent.extra_data["notes"][0]["stage"] == "quit"
    assert ent.extra_data["notes"][0]["stage_label"] == "Сам уволился"
    assert (await db_session.get(Entity, other_id)).status == EntityStatus.rejected
    assert await db_session.get(DataMigrationMark, SYNC_MARK) is not None
    assert await relabel_departed_rejected_once(db_session, {eid: EntityStatus.quit}) == []
