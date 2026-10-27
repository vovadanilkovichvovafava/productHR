"""Сторож: «Моя команда» и свои заявки на отпуск в кабинете.

До 27.10.2026 обе страницы брали данные из ручек только для админов:
сотрудник после подачи заявки видел «Запланированных отпусков нет», у
руководителя-сотрудника всегда было «Нет подчинённых».
"""
from datetime import datetime

from api.models.database import Employee, LeaveRequest, OrgMember, OrgRole
from api.services.auth import create_access_token


def _h(user):
    return {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}


async def test_employee_sees_own_requests_all_statuses(
    client, db_session, organization, org_member, second_user,
):
    emp = Employee(user_id=second_user.id, org_id=organization.id, is_active=True)
    db_session.add(emp)
    await db_session.flush()
    for st in ("pending", "approved"):
        db_session.add(LeaveRequest(employee_id=emp.id, type="vacation", start_date=datetime(2026, 11, 2),
                                    end_date=datetime(2026, 11, 3), days=2, status=st))
    await db_session.commit()

    resp = await client.get(f"/api/employees/{emp.id}/leave-requests", headers=_h(second_user))

    assert resp.status_code == 200, resp.text
    assert {r["status"] for r in resp.json()} == {"pending", "approved"}


async def test_colleague_cannot_list_requests(
    client, db_session, organization, org_member, org_admin, second_user, regular_user,
):
    emp = Employee(user_id=regular_user.id, org_id=organization.id, is_active=True)
    db_session.add(emp)
    await db_session.commit()

    resp = await client.get(f"/api/employees/{emp.id}/leave-requests", headers=_h(second_user))

    assert resp.status_code == 404


async def test_manager_sees_reports_without_passport_data(
    client, db_session, organization, org_member, second_user, regular_user,
):
    db_session.add(OrgMember(org_id=organization.id, user_id=regular_user.id, role=OrgRole.member))
    boss = Employee(user_id=second_user.id, org_id=organization.id, is_active=True)
    db_session.add(boss)
    await db_session.flush()
    db_session.add(Employee(
        user_id=regular_user.id, org_id=organization.id, is_active=True, manager_id=boss.id,
        extra_data={"first_name": "Иван", "passport_number": "AB123", "address": "Минск",
                    "payment_details": "2200…", "emergency_contact_name": "Мама"},
    ))
    await db_session.commit()

    resp = await client.get("/api/employees/my-reports", headers=_h(second_user))

    assert resp.status_code == 200, resp.text
    [report] = resp.json()
    assert report["extra_data"] == {"first_name": "Иван", "emergency_contact_name": "Мама"}


async def test_no_reports_is_empty_list(client, db_session, organization, org_member, second_user):
    db_session.add(Employee(user_id=second_user.id, org_id=organization.id, is_active=True))
    await db_session.commit()

    resp = await client.get("/api/employees/my-reports", headers=_h(second_user))

    assert resp.status_code == 200
    assert resp.json() == []
