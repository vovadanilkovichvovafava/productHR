"""Сторож: ограничения ввода в «Управлении» (сотрудники, паспорт, оргструктура, отпуска).

До 27.10.2026: длинная должность/телефон давали 500 (и роняли весь импорт),
сотрудник через PUT /me подменял служебные метаданные скана паспорта и сам
переписывал себе должность, пустое поле формы не стиралось, скан паспорта
принимался любого типа и размера (base64 декодировался до проверки), число
документов не ограничивалось, неизвестный статус в фильтре отпусков давал 500.
"""
import base64

import pytest
from sqlalchemy import select

from api.models.database import Employee, OrgMember, OrgRole
from api.services.auth import create_access_token


def _h(user):
    return {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}


@pytest.fixture
async def me(db_session, organization, second_user):
    db_session.add(OrgMember(org_id=organization.id, user_id=second_user.id, role=OrgRole.member))
    emp = Employee(user_id=second_user.id, org_id=organization.id, is_active=True, position="Разработчик",
                   extra_data={"address": "Минск", "passport": {"filename": "p.png", "content_type": "image/png"}})
    db_session.add(emp)
    await db_session.commit()
    return emp


async def _fresh(db, emp_id):
    return (await db.execute(
        select(Employee).where(Employee.id == emp_id).execution_options(populate_existing=True)
    )).scalar_one()


async def test_self_edit_cannot_touch_passport_meta_or_position(client, db_session, me, second_user):
    resp = await client.put("/api/employees/me", json={
        "position": "CEO",
        "extra_data": {"passport": {"filename": "x", "content_type": 'image/x" onerror="alert(1)'}},
    }, headers=_h(second_user))

    assert resp.status_code == 200, resp.text
    emp = await _fresh(db_session, me.id)
    assert emp.position == "Разработчик"
    assert emp.extra_data["passport"]["content_type"] == "image/png"


async def test_null_clears_extra_field(client, db_session, me, second_user):
    resp = await client.put("/api/employees/me", json={"extra_data": {"address": None}}, headers=_h(second_user))

    assert resp.status_code == 200, resp.text
    assert "address" not in (await _fresh(db_session, me.id)).extra_data


async def test_too_long_values_rejected_not_500(client, db_session, me, second_user):
    long_phone = await client.put("/api/employees/me", json={"phone": "1" * 51}, headers=_h(second_user))
    long_extra = await client.put("/api/employees/me", json={"extra_data": {"address": "x" * 5000}}, headers=_h(second_user))

    assert long_phone.status_code == 422
    assert long_extra.status_code == 400


async def test_bulk_import_long_field_is_422(client, db_session, organization, org_owner, admin_user):
    resp = await client.post("/api/employees/bulk-import",
                             json=[{"email": "a@b.c", "position": "x" * 301}], headers=_h(admin_user))

    assert resp.status_code == 422


@pytest.mark.parametrize("ctype", ["text/html", 'image/x" onerror="alert(1)', "image/svg+xml"])
async def test_passport_type_whitelist(client, db_session, me, second_user, ctype):
    resp = await client.post("/api/employees/me/passport", json={
        "filename": "p", "content_type": ctype, "data_base64": base64.b64encode(b"abc").decode(),
    }, headers=_h(second_user))

    assert resp.status_code == 400


async def test_passport_not_base64_rejected(client, db_session, me, second_user):
    resp = await client.post("/api/employees/me/passport", json={
        "filename": "p.png", "content_type": "image/png", "data_base64": "не base64!!",
    }, headers=_h(second_user))

    assert resp.status_code == 400


async def test_org_unit_name_too_long(client, db_session, organization, org_owner, admin_user):
    resp = await client.post("/api/org-units", json={"name": "x" * 300}, headers=_h(admin_user),
                             params={"org_id": organization.id})

    assert resp.status_code == 422


async def test_timeoff_unknown_status_is_422(client, db_session, organization, org_owner, admin_user):
    resp = await client.get("/api/timeoff?status=whatever", headers=_h(admin_user))

    assert resp.status_code == 422
