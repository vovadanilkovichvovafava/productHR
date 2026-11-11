"""Общий вид доски «Штат» (клиент, 11.11.2026): одна настройка колонок на всех.

«Если Маша уберёт столбец „2 недели“, он уберётся у всех». Менять может любой HR.
"""
import pytest

from api.models.database import OrgMember, OrgRole
from api.services.auth import create_access_token


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(u.id)})}"}


@pytest.mark.asyncio
async def test_view_is_shared_between_hr(client, db_session, organization, admin_user, second_user, org_owner):
    db_session.add(OrgMember(org_id=organization.id, user_id=second_user.id, role=OrgRole.hr))
    await db_session.commit()

    empty = {"hidden": [], "order": [], "labels": {}, "widths": {}}
    assert (await client.get("/api/staff-board/board-view", headers=_h(admin_user))).json() == empty

    r = await client.put("/api/staff-board/board-view",
                         json={"hidden": ["w2", "w2_done", "мусор", "w2"]}, headers=_h(second_user))
    assert r.status_code == 200 and r.json()["hidden"] == ["w2", "w2_done"]

    # Другой HR видит то же самое
    assert (await client.get("/api/staff-board/board-view", headers=_h(admin_user))).json()["hidden"] == ["w2", "w2_done"]

    # «Показать все» — пустой список
    r = await client.put("/api/staff-board/board-view", json={"hidden": []}, headers=_h(admin_user))
    assert r.json()["hidden"] == []


@pytest.mark.asyncio
async def test_order_labels_widths_are_shared_and_partial(client, db_session, organization, admin_user, org_owner):
    """Порядок, свои названия и ширины — общие; не переданное поле не трогается."""
    h = _h(admin_user)
    await client.put("/api/staff-board/board-view", json={"hidden": ["w2"]}, headers=h)
    r = await client.put("/api/staff-board/board-view", json={
        "order": ["telegram", "position", "мусор", "name"],
        "labels": {"position": "  Роль ", "name": "Сотрудник", "мусор": "x", "telegram": ""},
        "widths": {"telegram": 20, "position": 999, "name": 300, "мусор": 100},
    }, headers=h)
    v = r.json()
    assert v["hidden"] == ["w2"]                      # бегунки не сбиты
    assert v["order"] == ["telegram", "position"]     # «ФИО» не двигается, мусор отсечён
    assert v["labels"] == {"position": "Роль", "name": "Сотрудник"}
    assert v["widths"] == {"telegram": 60, "position": 600, "name": 300}
    r = await client.put("/api/staff-board/board-view", json={"labels": {}}, headers=h)
    assert r.json()["labels"] == {} and r.json()["widths"]["name"] == 300
