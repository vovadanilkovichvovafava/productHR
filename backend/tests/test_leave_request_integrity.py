"""Сторож: заявки на отпуск в «Управлении» (/employees/.../leave-request).

До 27.10.2026 число дней присылал клиент и сервер ему верил: месяц отпуска с
days=0 списывался как ноль, days=-30 после одобрения ДОБАВЛЯЛ остаток. Даты не
проверялись, админ одобрял собственную заявку, уволенному заявка создавалась.
"""
from datetime import datetime

from sqlalchemy import select

from api.models.database import Employee, LeaveRequest, OrgMember, OrgRole
from api.services.auth import create_access_token


def _h(user):
    return {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}


async def _employee(db, org, user, **kw):
    emp = Employee(user_id=user.id, org_id=org.id, is_active=True,
                   department_start_date=datetime(2025, 1, 1), **kw)
    db.add(emp)
    await db.commit()
    return emp


async def test_days_are_computed_by_server(client, db_session, organization, org_member, second_user):
    emp = await _employee(db_session, organization, second_user)

    resp = await client.post(
        f"/api/employees/{emp.id}/leave-request",
        json={"type": "vacation", "start_date": "2026-11-02T00:00:00", "end_date": "2026-11-06T00:00:00", "days": -30},
        headers=_h(second_user),
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["days"] == 5


async def test_end_before_start_rejected(client, db_session, organization, org_member, second_user):
    emp = await _employee(db_session, organization, second_user)

    resp = await client.post(
        f"/api/employees/{emp.id}/leave-request",
        json={"type": "vacation", "start_date": "2026-11-06T00:00:00", "end_date": "2026-11-02T00:00:00"},
        headers=_h(second_user),
    )

    assert resp.status_code == 400


async def test_dismissed_employee_cannot_request(
    client, db_session, organization, org_owner, admin_user, second_user,
):
    emp = await _employee(db_session, organization, second_user)
    emp.is_active = False
    await db_session.commit()

    resp = await client.post(
        f"/api/employees/{emp.id}/leave-request",
        json={"type": "vacation", "start_date": "2026-11-02T00:00:00", "end_date": "2026-11-03T00:00:00"},
        headers=_h(admin_user),
    )

    assert resp.status_code == 400


async def test_colleague_cannot_request_for_other(
    client, db_session, organization, org_member, org_admin, second_user, regular_user,
):
    # regular_user — admin орга, second_user — рядовой; рядовой не подаёт за админа.
    emp = await _employee(db_session, organization, regular_user)

    resp = await client.post(
        f"/api/employees/{emp.id}/leave-request",
        json={"type": "vacation", "start_date": "2026-11-02T00:00:00", "end_date": "2026-11-03T00:00:00"},
        headers=_h(second_user),
    )

    assert resp.status_code == 404


async def test_admin_cannot_approve_own_request(client, db_session, organization, org_owner, admin_user):
    emp = await _employee(db_session, organization, admin_user)
    lr = LeaveRequest(employee_id=emp.id, type="vacation", start_date=datetime(2026, 11, 2),
                      end_date=datetime(2026, 11, 3), days=2, status="pending")
    db_session.add(lr)
    await db_session.commit()

    resp = await client.put(f"/api/employees/leave-requests/{lr.id}/approve", headers=_h(admin_user))

    assert resp.status_code == 403
    await db_session.refresh(lr)
    assert lr.status == "pending"


async def test_approve_recomputes_legacy_client_days(
    client, db_session, organization, org_owner, org_member, admin_user, second_user,
):
    # Заявка из старых данных: клиент прислал отрицательные дни.
    emp = await _employee(db_session, organization, second_user, vacation_days_used=0)
    lr = LeaveRequest(employee_id=emp.id, type="vacation", start_date=datetime(2026, 11, 2),
                      end_date=datetime(2026, 11, 3), days=-30, status="pending")
    db_session.add(lr)
    await db_session.commit()

    resp = await client.put(f"/api/employees/leave-requests/{lr.id}/approve", headers=_h(admin_user))

    assert resp.status_code == 200, resp.text
    emp = (await db_session.execute(
        select(Employee).where(Employee.id == emp.id).execution_options(populate_existing=True)
    )).scalar_one()
    assert emp.vacation_days_used == 2
