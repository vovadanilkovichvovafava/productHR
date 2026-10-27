"""Сторож: кто вправе одобрить или отклонить заявку на отпуск (/api/timeoff).

До 27.10.2026 approve/reject не проверяли ничего: любой залогиненный одобрял
свой отпуск, а перебором id — заявки всех организаций; уже отклонённую можно
было снова одобрить.
"""
from datetime import datetime, timedelta

from api.models.database import (
    DepartmentMember, DeptRole, OrgMember, OrgRole, TimeOffRequest, TimeOffStatus,
)
from api.services.auth import create_access_token


def _h(user):
    return {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}


async def _request(db, org, user, status=TimeOffStatus.pending):
    req = TimeOffRequest(
        org_id=org.id, user_id=user.id, status=status,
        date_from=datetime(2026, 11, 2), date_to=datetime(2026, 11, 6),
    )
    db.add(req)
    await db.commit()
    return req


async def test_member_cannot_approve_own_request(
    client, db_session, organization, org_member, second_user,
):
    req = await _request(db_session, organization, second_user)

    resp = await client.post(f"/api/timeoff/{req.id}/approve", headers=_h(second_user))

    assert resp.status_code == 403
    await db_session.refresh(req)
    assert req.status == TimeOffStatus.pending


async def test_admin_cannot_approve_own_request(
    client, db_session, organization, org_owner, admin_user,
):
    req = await _request(db_session, organization, admin_user)

    resp = await client.post(f"/api/timeoff/{req.id}/approve", headers=_h(admin_user))

    assert resp.status_code == 403


async def test_member_cannot_review_colleague(
    client, db_session, organization, org_member, org_admin, second_user, regular_user,
):
    # Рядовой сотрудник (не лид) не решает по заявке коллеги.
    req = await _request(db_session, organization, regular_user)

    resp = await client.post(f"/api/timeoff/{req.id}/reject", headers=_h(second_user))

    assert resp.status_code == 403


async def test_other_org_request_is_404(
    client, db_session, organization, second_organization, org_owner, admin_user, second_user,
):
    db_session.add(OrgMember(org_id=second_organization.id, user_id=second_user.id, role=OrgRole.member))
    await db_session.commit()
    req = await _request(db_session, second_organization, second_user)

    # admin_user — владелец ДРУГОЙ организации.
    resp = await client.post(f"/api/timeoff/{req.id}/approve", headers=_h(admin_user))

    assert resp.status_code == 404
    await db_session.refresh(req)
    assert req.status == TimeOffStatus.pending


async def test_org_admin_approves_employee(
    client, db_session, organization, org_owner, org_member, admin_user, second_user,
):
    req = await _request(db_session, organization, second_user)

    resp = await client.post(f"/api/timeoff/{req.id}/approve", headers=_h(admin_user))

    assert resp.status_code == 200
    await db_session.refresh(req)
    assert req.status == TimeOffStatus.approved
    assert req.reviewed_by == admin_user.id


async def test_dept_lead_reviews_own_department_only(
    client, db_session, organization, department, second_department,
    org_member, org_admin, second_user, regular_user, superadmin_user,
):
    # second_user — лид отдела department (роль в организации — member).
    db_session.add(DepartmentMember(department_id=department.id, user_id=second_user.id, role=DeptRole.lead))
    # regular_user состоит только во втором отделе.
    db_session.add(DepartmentMember(department_id=second_department.id, user_id=regular_user.id, role=DeptRole.member))
    db_session.add(OrgMember(org_id=organization.id, user_id=superadmin_user.id, role=OrgRole.member))
    db_session.add(DepartmentMember(department_id=department.id, user_id=superadmin_user.id, role=DeptRole.member))
    await db_session.commit()

    foreign = await _request(db_session, organization, regular_user)
    resp = await client.post(f"/api/timeoff/{foreign.id}/approve", headers=_h(second_user))
    assert resp.status_code == 403

    # Сотрудник своего отдела — можно.
    mine = await _request(db_session, organization, superadmin_user)
    resp = await client.post(f"/api/timeoff/{mine.id}/approve", headers=_h(second_user))
    assert resp.status_code == 200


async def test_decision_is_final(
    client, db_session, organization, org_owner, org_member, admin_user, second_user,
):
    req = await _request(db_session, organization, second_user, status=TimeOffStatus.rejected)

    resp = await client.post(f"/api/timeoff/{req.id}/approve", headers=_h(admin_user))

    assert resp.status_code == 409
    await db_session.refresh(req)
    assert req.status == TimeOffStatus.rejected
