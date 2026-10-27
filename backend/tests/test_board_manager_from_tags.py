"""«Рук-ль» на «Статусах» = наставник практики из тегов у ФИО (встреча 23.09.2026).

Влад и Егор ведут практику, теги у ФИО им и так проставляют. Нет тега — колонка
пустая: руководителя отдела сюда больше не подставляем.
"""
from datetime import datetime

import pytest

from api.models.database import (
    Entity, EntityStatus, EntityType, NameTag, entity_name_tag_association,
)
from api.services.auth import create_access_token


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


async def _person(db, org, creator, extra=None):
    e = Entity(
        org_id=org.id, name="Практиков Пётр", type=EntityType.candidate,
        status=EntityStatus.probation, created_by=creator.id,
        created_at=datetime.utcnow(), extra_data=extra or {},
    )
    db.add(e)
    await db.commit()
    await db.refresh(e)
    return e


async def _tag(db, org, entity, name):
    t = NameTag(org_id=org.id, name=name)
    db.add(t)
    await db.commit()
    await db.refresh(t)
    await db.execute(entity_name_tag_association.insert().values(entity_id=entity.id, tag_id=t.id))
    await db.commit()
    return t


async def _row(client, user, eid):
    r = await client.get("/api/staff-board/rows", headers=_h(user))
    assert r.status_code == 200, r.text
    return next(x for x in r.json() if x["entity_id"] == eid)


@pytest.mark.asyncio
async def test_mentor_tag_fills_manager(client, db_session, organization, admin_user, org_owner):
    e = await _person(db_session, organization, admin_user)
    await _tag(db_session, organization, e, "Влад")
    assert (await _row(client, admin_user, e.id))["manager"] == "Влад"


@pytest.mark.asyncio
async def test_no_tag_no_manager(client, db_session, organization, admin_user, org_owner):
    e = await _person(db_session, organization, admin_user)
    await _tag(db_session, organization, e, "перформер")
    assert not (await _row(client, admin_user, e.id))["manager"]


@pytest.mark.asyncio
async def test_two_mentors_both_shown(client, db_session, organization, admin_user, org_owner):
    e = await _person(db_session, organization, admin_user)
    await _tag(db_session, organization, e, "Влад")
    await _tag(db_session, organization, e, "Егор")
    assert (await _row(client, admin_user, e.id))["manager"] == "Влад, Егор"


@pytest.mark.asyncio
async def test_tag_wins_over_manual(client, db_session, organization, admin_user, org_owner):
    """Тег главнее: он актуальнее того, что вбили руками когда-то."""
    e = await _person(db_session, organization, admin_user, {"manager_name": "Старый Рук"})
    await _tag(db_session, organization, e, "Егор")
    assert (await _row(client, admin_user, e.id))["manager"] == "Егор"
