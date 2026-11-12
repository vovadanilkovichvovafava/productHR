"""«Штат» → окно «Перемещения»: прежний отдел убирается из истории на «×».

Владелец, 12.11.2026: «тут ещё можно убирать отделы на крестик» — запись бывает
ошибочной («тест» на один день). Убирается только запись истории, где человек
стоит сейчас — не меняется.
"""
from datetime import datetime

import pytest
from sqlalchemy import select

from api.models.database import (
    BoardDepartment, BoardPlacement, Entity, EntityStatus, EntityType,
)
from api.services.auth import create_access_token

pytestmark = pytest.mark.asyncio


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


async def _setup(db, org, creator):
    test = BoardDepartment(org_id=org.id, name="тест", kind="team")
    seo = BoardDepartment(org_id=org.id, name="SEO team", kind="team")
    push = BoardDepartment(org_id=org.id, name="Push team", kind="team")
    db.add_all([test, seo, push])
    await db.commit()
    e = Entity(
        org_id=org.id, name="Третий Тест", type=EntityType.candidate,
        status=EntityStatus.transferred, created_by=creator.id, created_at=datetime.utcnow(),
        extra_data={"board_team_history": [
            {"department_id": test.id, "name": "тест", "from": "2026-11-10", "to": "2026-11-10"},
            {"department_id": seo.id, "name": "SEO team", "from": "2026-11-11", "to": "2026-11-12"},
        ]},
    )
    db.add(e)
    await db.commit()
    db.add(BoardPlacement(org_id=org.id, entity_id=e.id, department_id=push.id))
    await db.commit()
    return e.id, test.id, seo.id, push.id


async def test_remove_one_stint(client, db_session, organization, admin_user, org_owner):
    eid, test_id, seo_id, push_id = await _setup(db_session, organization, admin_user)
    r = await client.post(
        f"/api/staff-board/rows/{eid}/team-history/remove",
        json={"department_id": test_id, "name": "тест", "date_from": "2026-11-10", "date_to": "2026-11-10"},
        headers=_h(admin_user),
    )
    assert r.status_code == 200, r.text
    assert [h["name"] for h in r.json()["team_history"]] == ["SEO team"]

    db_session.expire_all()
    e = (await db_session.execute(select(Entity).where(Entity.id == eid))).scalar_one()
    assert [h["name"] for h in e.extra_data["board_team_history"]] == ["SEO team"]
    # Где человек стоит сейчас — не тронуто.
    pl = (await db_session.execute(select(BoardPlacement).where(BoardPlacement.entity_id == eid))).scalars().all()
    assert [p.department_id for p in pl] == [push_id]


async def test_wrong_dates_is_404_and_nothing_removed(client, db_session, organization, admin_user, org_owner):
    eid, test_id, *_ = await _setup(db_session, organization, admin_user)
    r = await client.post(
        f"/api/staff-board/rows/{eid}/team-history/remove",
        json={"department_id": test_id, "date_from": "2026-01-01", "date_to": "2026-01-02"},
        headers=_h(admin_user),
    )
    assert r.status_code == 404, r.text
    db_session.expire_all()
    e = (await db_session.execute(select(Entity).where(Entity.id == eid))).scalar_one()
    assert len(e.extra_data["board_team_history"]) == 2


async def test_member_without_hr_cannot_remove(client, db_session, organization, admin_user, org_owner, second_user, org_member):
    eid, test_id, *_ = await _setup(db_session, organization, admin_user)
    r = await client.post(
        f"/api/staff-board/rows/{eid}/team-history/remove",
        json={"department_id": test_id, "date_from": "2026-11-10", "date_to": "2026-11-10"},
        headers=_h(second_user),
    )
    assert r.status_code == 403, r.text
