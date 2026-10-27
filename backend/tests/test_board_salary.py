"""Колонка «Сумма» на доске «Штат» — только для владельцев организации.

Владелец 09.10.2026: «добавить столбец Сумма, который будет видеть только
Настя». Настя заведена owner'ом, Мария — admin, поэтому право привязано к роли
владельца: имена меняются, а право остаётся у того, кто отвечает за деньги.
"""
from datetime import datetime

import pytest

from api.models.database import (
    Entity, EntityStatus, EntityType, OrgMember, OrgRole,
)
from api.services.auth import create_access_token


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


async def _person(db, org, creator, name="Штатный Сергей"):
    e = Entity(
        org_id=org.id, name=name, type=EntityType.candidate,
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
async def test_owner_sets_and_sees_salary(
    client, db_session, organization, admin_user, org_owner
):
    """Владелец вписывает сумму и видит её в строке."""
    e = await _person(db_session, organization, admin_user)

    r = await client.patch(
        f"/api/staff-board/rows/{e.id}", json={"salary": 2500.5}, headers=_h(admin_user)
    )
    assert r.status_code == 200, r.text
    assert r.json()["salary"] == 2500.5
    assert r.json()["salary_visible"] is True

    row = await _row(client, admin_user, e.id)
    assert row["salary"] == 2500.5

    # Пустое значение стирает сумму.
    r = await client.patch(
        f"/api/staff-board/rows/{e.id}", json={"salary": None}, headers=_h(admin_user)
    )
    assert r.json()["salary"] is None


@pytest.mark.asyncio
async def test_admin_neither_sees_nor_sets(
    client, db_session, organization, admin_user, second_user, org_owner
):
    """Админу (Мария) сумма не видна и менять её нельзя."""
    db_session.add(OrgMember(
        org_id=organization.id, user_id=second_user.id, role=OrgRole.admin,
        created_at=datetime.utcnow(),
    ))
    await db_session.commit()
    e = await _person(db_session, organization, admin_user)
    await client.patch(
        f"/api/staff-board/rows/{e.id}", json={"salary": 1000}, headers=_h(admin_user)
    )

    row = await _row(client, second_user, e.id)
    assert row["salary"] is None
    assert row["salary_visible"] is False

    r = await client.patch(
        f"/api/staff-board/rows/{e.id}", json={"salary": 999}, headers=_h(second_user)
    )
    assert r.status_code == 403
    # Чужая правка не прошла — сумма прежняя.
    assert (await _row(client, admin_user, e.id))["salary"] == 1000


@pytest.mark.asyncio
async def test_salary_belongs_to_person_not_placement(
    client, db_session, organization, admin_user, org_owner
):
    """Сумма одна на человека: в обеих его строках она одинаковая.

    Иначе в итоге по доске человек в песочнице и в отделе посчитался бы дважды.
    """
    sandbox = (await client.post(
        "/api/staff-board/departments", json={"name": "SANDBOX", "kind": "sandbox"},
        headers=_h(admin_user),
    )).json()
    team = (await client.post(
        "/api/staff-board/departments",
        json={"name": "Facebook", "kind": "team", "parent_id": sandbox["id"]},
        headers=_h(admin_user),
    )).json()
    e = await _person(db_session, organization, admin_user)
    for d in (sandbox, team):
        await client.post(
            "/api/staff-board/placements",
            json={"entity_id": e.id, "department_id": d["id"]}, headers=_h(admin_user),
        )
    await client.patch(
        f"/api/staff-board/rows/{e.id}", json={"salary": 1500}, headers=_h(admin_user)
    )

    rows = [x for x in (await client.get(
        "/api/staff-board/rows", headers=_h(admin_user)
    )).json() if x["entity_id"] == e.id]
    assert len(rows) == 2
    assert {x["salary"] for x in rows} == {1500.0}


@pytest.mark.asyncio
async def test_bad_salary_is_ignored_not_crashes(
    client, db_session, organization, admin_user, org_owner
):
    """Мусор вместо числа — пусто, а не ошибка на всю строку."""
    e = await _person(db_session, organization, admin_user)
    r = await client.patch(
        f"/api/staff-board/rows/{e.id}", json={"salary": 0}, headers=_h(admin_user)
    )
    assert r.status_code == 200, r.text
    assert r.json()["salary"] == 0
