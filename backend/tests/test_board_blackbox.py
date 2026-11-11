"""Случаи, найденные чёрным ящиком 12.11.2026 (локальная копия, скрипт по API):
каждый раньше проходил молча или падал 500-й."""
import pytest

from tests.test_board_placements import _dept, _h, _person, _rows


@pytest.mark.asyncio
async def test_department_rename_to_taken_name_is_refused(client, db_session, organization, admin_user, org_owner):
    a = await _dept(client, admin_user, "Альфа", kind="team")
    await _dept(client, admin_user, "Бета", kind="team")
    r = await client.patch(f"/api/staff-board/departments/{a['id']}", json={"name": " бета "}, headers=_h(admin_user))
    assert r.status_code == 409, r.text
    # своё же имя другим регистром — можно
    r = await client.patch(f"/api/staff-board/departments/{a['id']}", json={"name": "АЛЬФА"}, headers=_h(admin_user))
    assert r.status_code == 200 and r.json()["name"] == "АЛЬФА"


@pytest.mark.asyncio
async def test_department_name_too_long_is_400_not_500(client, db_session, organization, admin_user, org_owner):
    r = await client.post("/api/staff-board/departments", json={"name": "Д" * 101, "kind": "team"}, headers=_h(admin_user))
    assert r.status_code == 400, r.text
    a = await _dept(client, admin_user, "Альфа", kind="team")
    r = await client.patch(f"/api/staff-board/departments/{a['id']}", json={"name": "Д" * 101}, headers=_h(admin_user))
    assert r.status_code == 400, r.text


@pytest.mark.asyncio
async def test_assignee_must_be_org_member(client, db_session, organization, admin_user, org_owner):
    e = await _person(db_session, organization, admin_user)
    r = await client.patch(f"/api/staff-board/rows/{e.id}", json={"assignee_user_ids": [999999]}, headers=_h(admin_user))
    assert r.status_code == 400, r.text
    r = await client.patch(f"/api/staff-board/rows/{e.id}", json={"assignee_user_ids": [admin_user.id]}, headers=_h(admin_user))
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_assignee_who_left_org_does_not_block_editing(client, db_session, organization, admin_user, org_owner):
    """Уже стоящего HR, которого нет в организации, окно шлёт вместе с новым —
    это не должно ломать сохранение."""
    e = await _person(db_session, organization, admin_user)
    e.extra_data = {**(e.extra_data or {}), "assignee_user_ids": [999999]}
    await db_session.commit()
    r = await client.patch(f"/api/staff-board/rows/{e.id}", json={"assignee_user_ids": [999999, admin_user.id]}, headers=_h(admin_user))
    assert r.status_code == 200, r.text
    r = await client.patch(f"/api/staff-board/rows/{e.id}", json={"assignee_user_ids": [admin_user.id]}, headers=_h(admin_user))
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_sourcer_name_unique_ignoring_case(client, db_session, organization, admin_user, org_owner):
    r = await client.post("/api/tags", json={"name": "Сорсер Тест", "color": "#3b82f6"}, headers=_h(admin_user))
    assert r.status_code == 200, r.text
    r = await client.post("/api/tags", json={"name": "сорсер тест", "color": "#3b82f6"}, headers=_h(admin_user))
    assert r.status_code == 409, r.text


@pytest.mark.asyncio
async def test_custom_select_options_unique_ignoring_case(client, db_session, organization, admin_user, org_owner):
    r = await client.post("/api/staff-board/custom-fields", json={"name": "Грейд", "type": "select"}, headers=_h(admin_user))
    fid = [f for f in r.json() if f["name"] == "Грейд"][0]["id"]
    url = f"/api/staff-board/custom-fields/{fid}"
    assert (await client.patch(url, json={"options": ["Junior", "Middle"]}, headers=_h(admin_user))).status_code == 200
    assert (await client.patch(url, json={"options": ["Junior", "Middle", "junior"]}, headers=_h(admin_user))).status_code == 409
    r = await client.patch(url, json={"rename_option": {"from": "Junior", "to": "MIDDLE"}}, headers=_h(admin_user))
    assert r.status_code == 409, r.text
    r = await client.patch(url, json={"rename_option": {"from": "Junior", "to": "JUNIOR"}}, headers=_h(admin_user))
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_funnel_hr_outside_org_does_not_block_editing(client, db_session, organization, admin_user, org_owner):
    """HR из меток воронки (system_hr_tags) может быть уже не в организации —
    снять одного из них или добавить к ним своего это не мешает."""
    e = await _person(db_session, organization, admin_user)
    e.extra_data = {**(e.extra_data or {}), "system_hr_tags": [{"hr_id": 101, "name": "Лиза"}, {"hr_id": 102, "name": "Егор"}]}
    await db_session.commit()
    r = await client.patch(f"/api/staff-board/rows/{e.id}", json={"assignee_user_ids": [102, admin_user.id]}, headers=_h(admin_user))
    assert r.status_code == 200, r.text

