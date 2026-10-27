"""Отделы доски «Статусы» — свой справочник, не оргструктура Enceladus.

Названия совпадают, сущности разные (решение владельца 23.09.2026): правка на
доске не должна трогать отделы Enceladus с их участниками и правами.
"""
from datetime import datetime

import pytest

from api.models.database import (
    BoardDepartment, Department, Entity, EntityStatus, EntityType, OrgMember, OrgRole,
)
from api.services.auth import create_access_token


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


async def _person(db, org, creator):
    e = Entity(
        org_id=org.id, name="Отделов Олег", type=EntityType.candidate,
        status=EntityStatus.transferred, created_by=creator.id,
        created_at=datetime.utcnow(), extra_data={},
    )
    db.add(e)
    await db.commit()
    await db.refresh(e)
    return e


async def _row(client, user, eid):
    r = await client.get("/api/staff-board/rows", headers=_h(user))
    assert r.status_code == 200, r.text
    return next(x for x in r.json() if x["entity_id"] == eid)


@pytest.mark.asyncio
async def test_create_list_rename(client, db_session, organization, admin_user, org_owner):
    r = await client.post("/api/staff-board/departments", json={"name": "  Фарм  отдел "}, headers=_h(admin_user))
    assert r.status_code == 201, r.text
    dept_id = r.json()["id"]
    assert r.json()["name"] == "Фарм отдел"  # лишние пробелы схлопнуты

    # то же название второй раз — не плодим близнецов
    again = await client.post("/api/staff-board/departments", json={"name": "фарм отдел"}, headers=_h(admin_user))
    assert again.json()["id"] == dept_id

    r = await client.patch(f"/api/staff-board/departments/{dept_id}", json={"name": "RND отдел"}, headers=_h(admin_user))
    assert r.json()["name"] == "RND отдел"

    names = [d["name"] for d in (await client.get("/api/staff-board/departments", headers=_h(admin_user))).json()]
    assert names == ["RND отдел"]


@pytest.mark.asyncio
async def test_row_keeps_org_structure_untouched(client, db_session, organization, admin_user, org_owner):
    """Отдел на доске не трогает Enceladus: Entity.department_id остаётся пустым."""
    org_dept = Department(org_id=organization.id, name="Оргструктурный", is_active=True)
    db_session.add(org_dept)
    await db_session.commit()

    board_dept = (await client.post(
        "/api/staff-board/departments", json={"name": "Доскин"}, headers=_h(admin_user)
    )).json()
    e = await _person(db_session, organization, admin_user)

    r = await client.patch(
        f"/api/staff-board/rows/{e.id}", json={"department_id": board_dept["id"]}, headers=_h(admin_user)
    )
    assert r.status_code == 200, r.text
    assert r.json()["department_name"] == "Доскин"

    await db_session.refresh(e)
    assert e.department_id is None
    assert (await _row(client, admin_user, e.id))["department_id"] == board_dept["id"]


@pytest.mark.asyncio
async def test_org_department_is_not_accepted(client, db_session, organization, admin_user, org_owner):
    """Id отдела Enceladus на доске не принимается — справочники разные."""
    org_dept = Department(org_id=organization.id, name="Оргструктурный", is_active=True)
    db_session.add(org_dept)
    await db_session.commit()
    await db_session.refresh(org_dept)
    e = await _person(db_session, organization, admin_user)

    r = await client.patch(
        f"/api/staff-board/rows/{e.id}", json={"department_id": org_dept.id}, headers=_h(admin_user)
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_hide_and_show(client, db_session, organization, admin_user, org_owner):
    """Неактуальный отдел прячут, а не сносят: данные целы, глаза не мозолит."""
    dept = (await client.post(
        "/api/staff-board/departments", json={"name": "Неактуальный"}, headers=_h(admin_user)
    )).json()
    e = await _person(db_session, organization, admin_user)
    await client.patch(f"/api/staff-board/rows/{e.id}", json={"department_id": dept["id"]}, headers=_h(admin_user))

    r = await client.patch(
        f"/api/staff-board/departments/{dept['id']}", json={"hidden": True}, headers=_h(admin_user)
    )
    assert r.status_code == 200, r.text
    assert r.json()["hidden"] is True

    # отдел остался в базе и у человека — пропала только «актуальность»
    assert await db_session.get(BoardDepartment, dept["id"]) is not None
    row = await _row(client, admin_user, e.id)
    assert row["department_id"] == dept["id"] and row["department_name"] == "Неактуальный"

    back = await client.patch(
        f"/api/staff-board/departments/{dept['id']}", json={"hidden": False}, headers=_h(admin_user)
    )
    assert back.json()["hidden"] is False


@pytest.mark.asyncio
async def test_create_same_name_unhides(client, db_session, organization, admin_user, org_owner):
    """Заводят отдел с именем скрытого — он снова нужен, а не второй такой же."""
    dept = (await client.post(
        "/api/staff-board/departments", json={"name": "RND отдел"}, headers=_h(admin_user)
    )).json()
    await client.patch(
        f"/api/staff-board/departments/{dept['id']}", json={"hidden": True}, headers=_h(admin_user)
    )
    again = (await client.post(
        "/api/staff-board/departments", json={"name": "rnd отдел"}, headers=_h(admin_user)
    )).json()
    assert again["id"] == dept["id"]

    all_depts = (await client.get("/api/staff-board/departments", headers=_h(admin_user))).json()
    assert [d["hidden"] for d in all_depts] == [False]


@pytest.mark.asyncio
async def test_no_delete_endpoint(client, db_session, organization, admin_user, org_owner):
    """Удаления у отделов доски нет — только скрытие."""
    dept = (await client.post(
        "/api/staff-board/departments", json={"name": "Временный"}, headers=_h(admin_user)
    )).json()
    r = await client.delete(f"/api/staff-board/departments/{dept['id']}", headers=_h(admin_user))
    assert r.status_code in (404, 405)


@pytest.mark.asyncio
async def test_order_is_personal(client, db_session, organization, admin_user, second_user, org_owner):
    """Порядок отделов — личный: Мария разложила под себя, у других не поехало."""
    db_session.add(OrgMember(
        org_id=organization.id, user_id=second_user.id, role=OrgRole.hr, created_at=datetime.utcnow()
    ))
    await db_session.commit()
    names = ["А отдел", "Б отдел", "В отдел"]
    ids = [
        (await client.post("/api/staff-board/departments", json={"name": n}, headers=_h(admin_user))).json()["id"]
        for n in names
    ]

    mine = (await client.get("/api/staff-board/departments", headers=_h(admin_user))).json()
    assert [d["name"] for d in mine] == names  # по умолчанию по алфавиту

    r = await client.put(
        "/api/staff-board/departments/order",
        json={"ids": [ids[2], ids[0], ids[1]]},
        headers=_h(admin_user),
    )
    assert r.status_code == 200, r.text
    assert [d["name"] for d in r.json()] == ["В отдел", "А отдел", "Б отдел"]

    # перезагрузка страницы порядок не теряет
    again = (await client.get("/api/staff-board/departments", headers=_h(admin_user))).json()
    assert [d["name"] for d in again] == ["В отдел", "А отдел", "Б отдел"]

    # у другого HR — свой порядок, по умолчанию алфавитный
    other = (await client.get("/api/staff-board/departments", headers=_h(second_user))).json()
    assert [d["name"] for d in other] == names


@pytest.mark.asyncio
async def test_new_department_goes_last(client, db_session, organization, admin_user, org_owner):
    """Отдел, которого не было в сохранённом порядке, встаёт в конец."""
    a = (await client.post("/api/staff-board/departments", json={"name": "Альфа"}, headers=_h(admin_user))).json()
    b = (await client.post("/api/staff-board/departments", json={"name": "Бета"}, headers=_h(admin_user))).json()
    await client.put(
        "/api/staff-board/departments/order", json={"ids": [b["id"], a["id"]]}, headers=_h(admin_user)
    )
    await client.post("/api/staff-board/departments", json={"name": "Ааа новый"}, headers=_h(admin_user))

    listed = (await client.get("/api/staff-board/departments", headers=_h(admin_user))).json()
    assert [d["name"] for d in listed] == ["Бета", "Альфа", "Ааа новый"]
