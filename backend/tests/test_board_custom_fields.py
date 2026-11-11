"""Свои поля доски «Штат» (клиент, 11.11.2026: «добавьте возможность
создавать сущности самим»). Поле — у организации, значение — у человека."""
from datetime import datetime

import pytest

from api.models.database import Entity, EntityStatus, EntityType, OrgMember, OrgRole
from api.services.auth import create_access_token


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


async def _person(db, org, creator):
    e = Entity(org_id=org.id, name="Полевой Пётр", type=EntityType.candidate,
               status=EntityStatus.transferred, created_by=creator.id,
               created_at=datetime.utcnow(), extra_data={})
    db.add(e)
    await db.commit()
    await db.refresh(e)
    return e


async def _row(client, user, eid):
    rows = (await client.get("/api/staff-board/rows", headers=_h(user))).json()
    return next(r for r in rows if r["entity_id"] == eid)


@pytest.mark.asyncio
async def test_create_fill_and_types(client, db_session, organization, admin_user, org_owner):
    h = _h(admin_user)
    e = await _person(db_session, organization, admin_user)
    for name, t in [("Грейд", "select"), ("Ставка", "number"), ("Дата ревью", "date"),
                    ("Ноутбук выдан", "checkbox"), ("Комментарий лида", "text")]:
        r = await client.post("/api/staff-board/custom-fields", json={"name": name, "type": t}, headers=h)
        assert r.status_code == 201, r.text
    fields = {f["name"]: f for f in r.json()}
    assert (await client.post("/api/staff-board/custom-fields", json={"name": "грейд", "type": "text"}, headers=h)).status_code == 409
    assert (await client.post("/api/staff-board/custom-fields", json={"name": "X", "type": "bad"}, headers=h)).status_code == 400

    g = fields["Грейд"]["id"]
    r = await client.patch(f"/api/staff-board/custom-fields/{g}", json={"options": ["Junior", "Middle"]}, headers=h)
    assert next(f for f in r.json() if f["id"] == g)["options"] == ["Junior", "Middle"]

    body = {"custom": {
        g: "Middle",
        fields["Ставка"]["id"]: "1 500,5",
        fields["Дата ревью"]["id"]: "2026-12-01",
        fields["Ноутбук выдан"]["id"]: True,
        fields["Комментарий лида"]["id"]: "  молодец  ",
    }}
    r = await client.patch(f"/api/staff-board/rows/{e.id}", json=body, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["custom"] == {
        g: "Middle", fields["Ставка"]["id"]: 1500.5, fields["Дата ревью"]["id"]: "2026-12-01",
        fields["Ноутбук выдан"]["id"]: True, fields["Комментарий лида"]["id"]: "молодец",
    }
    # неверное значение по типу / несуществующий вариант / чужое поле
    assert (await client.patch(f"/api/staff-board/rows/{e.id}", json={"custom": {g: "Senior"}}, headers=h)).status_code == 400
    assert (await client.patch(f"/api/staff-board/rows/{e.id}", json={"custom": {fields["Ставка"]["id"]: "много"}}, headers=h)).status_code == 400
    assert (await client.patch(f"/api/staff-board/rows/{e.id}", json={"custom": {"nope": 1}}, headers=h)).status_code == 400
    # очистить
    r = await client.patch(f"/api/staff-board/rows/{e.id}", json={"custom": {fields["Ноутбук выдан"]["id"]: None}}, headers=h)
    assert fields["Ноутбук выдан"]["id"] not in r.json()["custom"]

    # вариант, который стоит, не убрать; переименовать — и у человека
    r = await client.patch(f"/api/staff-board/custom-fields/{g}", json={"options": ["Junior"]}, headers=h)
    assert r.status_code == 409
    r = await client.patch(f"/api/staff-board/custom-fields/{g}",
                           json={"rename_option": {"from": "Middle", "to": "Middle+"}}, headers=h)
    assert r.status_code == 200
    assert (await _row(client, admin_user, e.id))["custom"][g] == "Middle+"

    # колонка своего поля входит в общий вид
    r = await client.put("/api/staff-board/board-view", json={"hidden": [f"cf:{g}", "cf:nope"],
                                                               "widths": {f"cf:{g}": 90}}, headers=h)
    assert r.json()["hidden"] == [f"cf:{g}"] and r.json()["widths"] == {f"cf:{g}": 90}


@pytest.mark.asyncio
async def test_delete_used_field_only_admin(client, db_session, organization, admin_user, second_user, org_owner):
    db_session.add(OrgMember(org_id=organization.id, user_id=second_user.id, role=OrgRole.hr))
    await db_session.commit()
    e = await _person(db_session, organization, admin_user)
    hr = _h(second_user)
    fid = (await client.post("/api/staff-board/custom-fields", json={"name": "Пустое", "type": "text"}, headers=hr)).json()[0]["id"]
    used = (await client.post("/api/staff-board/custom-fields", json={"name": "Заполненное", "type": "text"}, headers=hr)).json()[1]["id"]
    await client.patch(f"/api/staff-board/rows/{e.id}", json={"custom": {used: "да"}}, headers=hr)

    assert (await client.delete(f"/api/staff-board/custom-fields/{fid}", headers=hr)).status_code == 200
    assert (await client.delete(f"/api/staff-board/custom-fields/{used}", headers=hr)).status_code == 403
    assert (await client.delete(f"/api/staff-board/custom-fields/{used}", headers=_h(admin_user))).status_code == 200
