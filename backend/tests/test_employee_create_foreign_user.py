"""Сторож: сотрудника заводят только из участника своей организации.

`POST /employees` проверял лишь, что `user_id` существует. Владелец любой
организации заводил «сотрудника» из чужого аккаунта (хоть суперадмина), дальше
reset-password отдавал пароль от него, а увольнение гасило аккаунт на всей
платформе. Отдел и карточка кандидата тоже не сверялись с организацией
(до 27.10.2026).
"""
from sqlalchemy import select

from api.models.database import Department, Employee, Entity, EntityStatus, EntityType
from api.services.auth import create_access_token


def _h(user):
    return {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}


async def test_foreign_user_cannot_become_employee(
    client, db_session, organization, org_owner, admin_user, regular_user, superadmin_user,
):
    for target in (regular_user, superadmin_user):  # оба не в организации
        resp = await client.post("/api/employees", json={"user_id": target.id}, headers=_h(admin_user))
        assert resp.status_code == 404
        emp = (await db_session.execute(
            select(Employee).where(Employee.user_id == target.id)
        )).scalar_one_or_none()
        assert emp is None


async def test_other_org_department_and_entity_rejected(
    client, db_session, organization, second_organization, org_owner, org_member, admin_user, second_user,
):
    dept = Department(name="Чужой", org_id=second_organization.id)
    ent = Entity(org_id=second_organization.id, type=EntityType.candidate, name="Чужой", status=EntityStatus.new)
    db_session.add_all([dept, ent])
    await db_session.commit()

    r1 = await client.post(
        "/api/employees", json={"user_id": second_user.id, "department_id": dept.id}, headers=_h(admin_user),
    )
    r2 = await client.post(
        "/api/employees", json={"user_id": second_user.id, "entity_id": ent.id}, headers=_h(admin_user),
    )

    assert r1.status_code == 400
    assert r2.status_code == 400


async def test_update_rejects_other_org_department(
    client, db_session, organization, second_organization, org_owner, org_member, admin_user, second_user,
):
    dept = Department(name="Чужой", org_id=second_organization.id)
    emp = Employee(user_id=second_user.id, org_id=organization.id, is_active=True)
    db_session.add_all([dept, emp])
    await db_session.commit()

    resp = await client.put(f"/api/employees/{emp.id}", json={"department_id": dept.id}, headers=_h(admin_user))

    assert resp.status_code == 400


async def test_org_member_becomes_employee(
    client, db_session, organization, department, org_owner, org_member, admin_user, second_user,
):
    resp = await client.post(
        "/api/employees", json={"user_id": second_user.id, "department_id": department.id}, headers=_h(admin_user),
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["user_id"] == second_user.id
