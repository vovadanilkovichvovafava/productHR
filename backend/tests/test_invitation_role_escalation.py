"""Сторож: приглашение не выдаёт прав больше, чем у того, кто приглашает.

До 27.10.2026 лид отдела с ролью «сотрудник» приглашал с org_role=hr (доступ к
кандидатам) или ролью lead в отделе, сам принимал приглашение на второй адрес
и получал эти права. Отделы лида считались по всем организациям, срок
приглашения можно было сделать вечным или переполнить (500).
"""
from api.models.database import DepartmentMember, DeptRole, OrgMember, OrgRole
from api.services.auth import create_access_token


def _h(user):
    return {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}


async def _lead(db, org, department, user, role=DeptRole.lead):
    db.add(OrgMember(org_id=org.id, user_id=user.id, role=OrgRole.member))
    db.add(DepartmentMember(department_id=department.id, user_id=user.id, role=role))
    await db.commit()


async def _invite(client, user, org, **body):
    body.setdefault("expires_in_days", 7)
    return await client.post("/api/invitations", json=body, headers=_h(user), params={"org_id": org.id})


async def test_dept_lead_cannot_grant_hr(client, db_session, organization, department, regular_user):
    await _lead(db_session, organization, department, regular_user)

    resp = await _invite(client, regular_user, organization, org_role="hr",
                         department_ids=[{"id": department.id, "role": "member"}])

    assert resp.status_code == 403


async def test_dept_lead_cannot_grant_lead(client, db_session, organization, department, regular_user):
    await _lead(db_session, organization, department, regular_user)

    resp = await _invite(client, regular_user, organization, org_role="member",
                         department_ids=[{"id": department.id, "role": "lead"}])

    assert resp.status_code == 403


async def test_sub_admin_grants_only_member(client, db_session, organization, department, regular_user):
    await _lead(db_session, organization, department, regular_user, role=DeptRole.sub_admin)

    sub = await _invite(client, regular_user, organization, org_role="member",
                        department_ids=[{"id": department.id, "role": "sub_admin"}])
    member = await _invite(client, regular_user, organization, org_role="member",
                           department_ids=[{"id": department.id, "role": "member"}])

    assert sub.status_code == 403
    assert member.status_code == 200, member.text


async def test_lead_in_other_org_cannot_invite_here(
    client, db_session, organization, second_organization, regular_user,
):
    from api.models.database import Department
    other_dept = Department(name="Чужой", org_id=second_organization.id)
    db_session.add(other_dept)
    await db_session.flush()
    db_session.add(OrgMember(org_id=organization.id, user_id=regular_user.id, role=OrgRole.member))
    db_session.add(DepartmentMember(department_id=other_dept.id, user_id=regular_user.id, role=DeptRole.lead))
    await db_session.commit()

    resp = await _invite(client, regular_user, organization, org_role="member",
                         department_ids=[{"id": other_dept.id, "role": "member"}])

    assert resp.status_code == 403


async def test_admin_may_invite_recruiter(client, db_session, organization, org_admin, regular_user):
    resp = await _invite(client, regular_user, organization, org_role="hr")

    assert resp.status_code == 200, resp.text


async def test_expiry_bounds(client, db_session, organization, org_admin, regular_user):
    never = await _invite(client, regular_user, organization, expires_in_days=0)
    negative = await _invite(client, regular_user, organization, expires_in_days=-1)
    huge = await _invite(client, regular_user, organization, expires_in_days=10**9)

    assert never.status_code == 403  # бессрочное — только владельцу
    assert negative.status_code == 400
    assert huge.status_code == 400


async def test_new_account_needs_real_password(client, db_session, organization, org_owner, admin_user):
    inv = await _invite(client, admin_user, organization, email="fresh@test.com")
    token = inv.json()["token"]

    resp = await client.post(
        f"/api/invitations/accept/{token}",
        json={"email": "fresh@test.com", "name": "Новый", "password": "1"},
    )

    assert resp.status_code == 400
