"""Сторож: кто видит паспорт и документы сотрудника («Управление»).

До 27.10.2026 любой рекрутёр (OrgRole.hr) — в том числе со скоупом «вижу
только Трафик» и наблюдатель — скачивал сканы паспортов и документы всех
сотрудников, включая владельца, и удалял документы, положенные админом.
Просмотры паспортов не оставляли следа в журнале.
"""
import base64

import pytest
from sqlalchemy import select

from api.models.database import AuditEvent, Employee, EmployeeDocument, OrgMember, OrgRole
from api.services.auth import create_access_token
from main import app


def _h(user):
    return {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}


@pytest.fixture
async def staff(db_session, organization, org_owner, admin_user, regular_user, second_user):
    """admin_user — owner; second_user — сотрудник; regular_user — по сценарию."""
    db_session.add(OrgMember(org_id=organization.id, user_id=second_user.id, role=OrgRole.member))
    emp = Employee(user_id=second_user.id, org_id=organization.id, is_active=True)
    db_session.add(emp)
    await db_session.commit()
    return emp


async def _upload_passport(client, employee_user):
    resp = await client.post(
        "/api/employees/me/passport",
        json={"filename": "p.png", "content_type": "image/png",
              "data_base64": base64.b64encode(b"\x89PNG\r\n\x1a\n").decode()},
        headers=_h(employee_user),
    )
    assert resp.status_code == 200, resp.text


async def _as_role(db, org, user, role, readonly=False):
    db.add(OrgMember(org_id=org.id, user_id=user.id, role=role, is_readonly=readonly))
    await db.commit()


async def test_recruiter_cannot_read_passport_or_documents(
    client, db_session, organization, staff, regular_user, second_user,
):
    await _as_role(db_session, organization, regular_user, OrgRole.hr)
    await _upload_passport(client, second_user)

    passport = await client.get(f"/api/employees/{staff.id}/passport", headers=_h(regular_user))
    docs = await client.get(f"/api/employees/{staff.id}/documents", headers=_h(regular_user))

    assert passport.status_code == 404
    assert docs.status_code == 404


async def test_observer_admin_cannot_read_passport_or_export(
    client, db_session, organization, staff, regular_user, second_user,
):
    await _as_role(db_session, organization, regular_user, OrgRole.admin, readonly=True)
    await _upload_passport(client, second_user)

    passport = await client.get(f"/api/employees/{staff.id}/passport", headers=_h(regular_user))
    export = await client.get("/api/employees/import-template?filled=1", headers=_h(regular_user))

    assert passport.status_code == 404
    assert export.status_code == 403


async def test_owner_and_self_read_passport(
    client, db_session, organization, staff, admin_user, second_user,
):
    await _upload_passport(client, second_user)

    by_owner = await client.get(f"/api/employees/{staff.id}/passport", headers=_h(admin_user))
    by_self = await client.get(f"/api/employees/{staff.id}/passport", headers=_h(second_user))

    assert by_owner.status_code == 200
    assert by_self.status_code == 200


async def test_manager_reads_documents_but_not_passport(
    client, db_session, organization, staff, regular_user, second_user,
):
    await _as_role(db_session, organization, regular_user, OrgRole.member)
    mgr = Employee(user_id=regular_user.id, org_id=organization.id, is_active=True)
    db_session.add(mgr)
    await db_session.flush()
    staff.manager_id = mgr.id
    await db_session.commit()
    await _upload_passport(client, second_user)

    docs = await client.get(f"/api/employees/{staff.id}/documents", headers=_h(regular_user))
    passport = await client.get(f"/api/employees/{staff.id}/passport", headers=_h(regular_user))

    assert docs.status_code == 200
    assert passport.status_code == 404


async def test_employee_cannot_delete_document_uploaded_by_admin(
    client, db_session, organization, staff, admin_user, second_user,
):
    up = await client.post(
        f"/api/employees/{staff.id}/documents",
        files={"file": ("contract.pdf", b"%PDF-1.4 test", "application/pdf")},
        headers=_h(admin_user),
    )
    assert up.status_code == 200, up.text
    doc_id = up.json()["id"]

    resp = await client.delete(f"/api/employees/{staff.id}/documents/{doc_id}", headers=_h(second_user))

    assert resp.status_code == 403
    assert (await db_session.execute(
        select(EmployeeDocument).where(EmployeeDocument.id == doc_id)
    )).scalar_one_or_none() is not None


async def test_passport_read_is_audited(
    client, db_session, organization, staff, admin_user, second_user,
):
    await _upload_passport(client, second_user)
    app.state.audit_in_tests = True
    try:
        resp = await client.get(f"/api/employees/{staff.id}/passport", headers=_h(admin_user))
    finally:
        app.state.audit_in_tests = False

    assert resp.status_code == 200
    events = (await db_session.execute(
        select(AuditEvent).where(AuditEvent.path == f"/api/employees/{staff.id}/passport")
    )).scalars().all()
    assert events and events[-1].user_id == admin_user.id
    assert events[-1].action == "Открыл скан паспорта сотрудника"


async def test_other_org_employee_card_is_404(
    client, db_session, organization, second_organization, org_owner, admin_user, regular_user,
):
    db_session.add(OrgMember(org_id=second_organization.id, user_id=regular_user.id, role=OrgRole.member))
    emp = Employee(user_id=regular_user.id, org_id=second_organization.id, is_active=True)
    db_session.add(emp)
    await db_session.commit()

    card = await client.get(f"/api/employees/{emp.id}", headers=_h(admin_user))
    reset = await client.post(f"/api/employees/{emp.id}/reset-password", headers=_h(admin_user))

    assert card.status_code == 404
    assert reset.status_code == 404


async def test_observer_admin_sees_employees_without_pii(
    client, db_session, organization, staff, regular_user, second_user,
):
    await _as_role(db_session, organization, regular_user, OrgRole.admin, readonly=True)
    staff.extra_data = {"first_name": "Иван", "payment_details": "2200…", "passport_number": "AB1"}
    await db_session.commit()

    listing = await client.get("/api/employees", headers=_h(regular_user))
    card = await client.get(f"/api/employees/{staff.id}", headers=_h(regular_user))

    assert listing.status_code == 200
    row = next(r for r in listing.json() if r["id"] == staff.id)
    assert row["extra_data"] == {"first_name": "Иван"}
    assert card.status_code == 200
    assert card.json()["extra_data"] == {"first_name": "Иван"}
