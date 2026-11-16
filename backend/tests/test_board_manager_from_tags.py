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


# --- Тикет Маши 13.11.2026: ментор в карточке = ментор на доске ---------------

async def _name_tags(client, user, eid):
    r = await client.get(f"/api/tags/entities/{eid}/name-tags", headers=_h(user))
    assert r.status_code == 200, r.text
    return sorted(t["name"] for t in r.json())


@pytest.mark.asyncio
async def test_board_pick_sets_card_tag_and_card_change_follows(client, db_session, organization, admin_user, org_owner):
    """Выбор на доске ставит тег в карточке; смена тега в карточке потом видна
    на доске — выбор доски её больше не перебивает (с 11.11 по 16.11 перебивал)."""
    e = await _person(db_session, organization, admin_user)
    perf = await _tag(db_session, organization, e, "Перформер")  # обычный тег не трогаем
    r = await client.patch(f"/api/staff-board/rows/{e.id}", json={"manager": "Егор"}, headers=_h(admin_user))
    assert r.status_code == 200, r.text
    assert r.json()["manager"] == "Егор"
    assert await _name_tags(client, admin_user, e.id) == ["Егор", "Перформер"]

    # В карточке сменили ментора: сняли Егора, поставили Влада.
    tags = {t["name"]: t["id"] for t in (await client.get("/api/tags/name-tags", headers=_h(admin_user))).json()}
    await client.delete(f"/api/tags/entities/{e.id}/name-tags/{tags['Егор']}", headers=_h(admin_user))
    vlad = tags.get("Влад") or (await client.post("/api/tags/name-tags", json={"name": "Влад"}, headers=_h(admin_user))).json()["id"]
    await client.post(f"/api/tags/entities/{e.id}/name-tags/{vlad}", headers=_h(admin_user))
    assert (await _row(client, admin_user, e.id))["manager"] == "Влад"

    # С доски сняли — снят и тег; обычный тег на месте.
    r = await client.patch(f"/api/staff-board/rows/{e.id}", json={"manager": None}, headers=_h(admin_user))
    assert r.json()["manager"] is None
    assert await _name_tags(client, admin_user, e.id) == ["Перформер"]
    assert perf.id


@pytest.mark.asyncio
async def test_migration_moves_old_values_into_tags(db_session, organization, admin_user, client, org_owner):
    from api.services.practice_mentor import migrate_board_mentors_once

    clickup = await _person(db_session, organization, admin_user, {"manager_name": "Егор"})
    picked = await _person(db_session, organization, admin_user, {"board_manager": "Влад", "manager_name": "Егор"})
    tagged = await _person(db_session, organization, admin_user, {"manager_name": "Влад"})
    await _tag(db_session, organization, tagged, "Егор")
    stranger = await _person(db_session, organization, admin_user, {"manager_name": "Тестовый лид"})
    ids = (clickup.id, picked.id, tagged.id, stranger.id)

    assert await migrate_board_mentors_once(db_session) == 2
    assert await _name_tags(client, admin_user, ids[0]) == ["Егор"]   # ClickUp → тег
    assert await _name_tags(client, admin_user, ids[1]) == ["Влад"]   # выбор на доске главнее
    assert await _name_tags(client, admin_user, ids[2]) == ["Егор"]   # тег уже был — он главнее
    assert await _name_tags(client, admin_user, ids[3]) == []         # не ментор из списка — не тег
    rows = {x["entity_id"]: x["manager"] for x in (await client.get("/api/staff-board/rows", headers=_h(admin_user))).json()}
    assert rows[ids[0]] == "Егор" and rows[ids[1]] == "Влад" and rows[ids[2]] == "Егор"
    assert rows[ids[3]] == "Тестовый лид"  # старое значение — запасным показом
    assert await migrate_board_mentors_once(db_session) == 0  # одноразово
