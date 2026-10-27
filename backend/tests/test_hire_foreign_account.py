"""Сторож: «Взять в штат» не привязывает чужой аккаунт и не трогает чужую организацию.

`POST /entities/{id}/hire` искал пользователя по email по всей платформе и
молча добавлял его в организацию; дальше админ выдавал ему пароль из
«Сотрудников» — захват аккаунта по одному email. Уволенную запись сотрудника
ДРУГОЙ организации ручка «реактивировала» и включала аккаунт, который та
организация отключила (до 27.10.2026).
"""
from datetime import datetime

from sqlalchemy import select

from api.models.database import (
    Department, Employee, Entity, EntityStatus, EntityType, OrgMember, OrgRole, User,
)
from api.services.auth import create_access_token


def _h(user):
    return {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}


async def _candidate(db, org):
    ent = Entity(org_id=org.id, type=EntityType.candidate, name="Кандидат", status=EntityStatus.hired)
    db.add(ent)
    await db.commit()
    return ent


async def test_foreign_account_is_not_bound(
    client, db_session, organization, org_owner, admin_user, regular_user,
):
    # regular_user в организации не состоит.
    ent = await _candidate(db_session, organization)

    resp = await client.post(
        f"/api/entities/{ent.id}/hire",
        json={"email": regular_user.email.upper()},
        headers=_h(admin_user),
    )

    assert resp.status_code == 409
    member = (await db_session.execute(
        select(OrgMember).where(OrgMember.org_id == organization.id, OrgMember.user_id == regular_user.id)
    )).scalar_one_or_none()
    assert member is None
    emp = (await db_session.execute(
        select(Employee).where(Employee.user_id == regular_user.id)
    )).scalar_one_or_none()
    assert emp is None


async def test_dismissed_employee_of_other_org_not_reactivated(
    client, db_session, organization, second_organization, org_owner, admin_user, regular_user,
):
    # regular_user уволен во второй организации, но всё ещё состоит и в нашей.
    db_session.add(OrgMember(org_id=organization.id, user_id=regular_user.id, role=OrgRole.member))
    other = Employee(
        user_id=regular_user.id, org_id=second_organization.id,
        is_active=False, dismissed_at=datetime.utcnow(),
    )
    db_session.add(other)
    regular_user.is_active = False
    await db_session.commit()
    ent = await _candidate(db_session, organization)

    resp = await client.post(
        f"/api/entities/{ent.id}/hire",
        json={"email": regular_user.email},
        headers=_h(admin_user),
    )

    assert resp.status_code == 409
    await db_session.refresh(other)
    assert other.is_active is False
    assert other.entity_id is None
    user = (await db_session.execute(
        select(User).where(User.id == regular_user.id).execution_options(populate_existing=True)
    )).scalar_one()
    assert user.is_active is False


async def test_other_org_department_rejected(
    client, db_session, organization, second_organization, org_owner, admin_user,
):
    foreign_dept = Department(name="Чужой", org_id=second_organization.id)
    db_session.add(foreign_dept)
    await db_session.commit()
    ent = await _candidate(db_session, organization)

    resp = await client.post(
        f"/api/entities/{ent.id}/hire",
        json={"email": "fresh@staff.com", "department_id": foreign_dept.id},
        headers=_h(admin_user),
    )

    assert resp.status_code == 400


async def test_existing_org_member_is_hired(
    client, db_session, organization, org_owner, org_member, admin_user, second_user,
):
    # Человек уже в организации (например, практикант с аккаунтом) — оформляется.
    ent = await _candidate(db_session, organization)

    resp = await client.post(
        f"/api/entities/{ent.id}/hire",
        json={"email": second_user.email},
        headers=_h(admin_user),
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["user_existed"] is True
