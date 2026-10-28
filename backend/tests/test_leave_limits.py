"""Сторож: лимиты больничных и семейных дней (решение владельца 27.10.2026).

Было два числа: кабинет показывал 7/2 (зашито в ручке баланса), запись
сотрудника хранила 10/3. Теперь правда — поля записи (умолчание 7/2), а
одобрение сверх лимита спрашивает «Одобрить всё равно?» (409 +
X-Leave-Over-Limit), повтор с force=true одобряет.
"""
from datetime import datetime

from sqlalchemy import select

from api.models.database import DataMigrationMark, Employee, LeaveRequest
from api.services.auth import create_access_token
from api.services.leave_limits import ALIGN_MARK, align_leave_limits_once


def _h(user):
    return {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}


async def _employee(db, org, user, **kw):
    emp = Employee(user_id=user.id, org_id=org.id, is_active=True,
                   department_start_date=datetime(2025, 1, 1), **kw)
    db.add(emp)
    await db.commit()
    return emp


async def test_balance_uses_employee_fields(client, db_session, organization, org_member, second_user):
    emp = await _employee(db_session, organization, second_user, sick_days_total=12, family_leave_days_total=0)

    resp = await client.get(f"/api/employees/{emp.id}/leave-balance", headers=_h(second_user))

    assert resp.status_code == 200
    assert resp.json()["sick_total"] == 12
    assert resp.json()["family_leave_total"] == 0  # ноль, вписанный HR, не превращается в умолчание


async def test_new_employee_defaults_7_and_2(client, db_session, organization, org_member, second_user):
    emp = await _employee(db_session, organization, second_user)

    resp = await client.get(f"/api/employees/{emp.id}", headers=_h(second_user))

    assert resp.json()["sick_days_total"] == 7
    assert resp.json()["family_leave_days_total"] == 2


async def test_over_limit_asks_then_force_approves(
    client, db_session, organization, org_owner, org_member, admin_user, second_user,
):
    emp = await _employee(db_session, organization, second_user, sick_days_total=7)
    lr = LeaveRequest(employee_id=emp.id, type="sick", start_date=datetime(2026, 10, 1),
                      end_date=datetime(2026, 10, 10), days=10, status="pending")
    db_session.add(lr)
    await db_session.commit()

    ask = await client.put(f"/api/employees/leave-requests/{lr.id}/approve", headers=_h(admin_user))
    assert ask.status_code == 409
    assert ask.headers.get("x-leave-over-limit") == "1"
    assert "Одобрить всё равно" in ask.json()["detail"]
    await db_session.refresh(lr)
    assert lr.status == "pending"

    ok = await client.put(f"/api/employees/leave-requests/{lr.id}/approve?force=true", headers=_h(admin_user))
    assert ok.status_code == 200, ok.text
    await db_session.refresh(lr)
    assert lr.status == "approved"


async def test_within_limit_approves_without_question(
    client, db_session, organization, org_owner, org_member, admin_user, second_user,
):
    emp = await _employee(db_session, organization, second_user)
    lr = LeaveRequest(employee_id=emp.id, type="family_leave", start_date=datetime(2026, 10, 1),
                      end_date=datetime(2026, 10, 2), days=2, status="pending")
    db_session.add(lr)
    await db_session.commit()

    resp = await client.put(f"/api/employees/leave-requests/{lr.id}/approve", headers=_h(admin_user))

    assert resp.status_code == 200, resp.text


async def test_align_old_defaults_once(db_session, organization, second_user, regular_user):
    old = Employee(user_id=second_user.id, org_id=organization.id, sick_days_total=10, family_leave_days_total=3)
    custom = Employee(user_id=regular_user.id, org_id=organization.id, sick_days_total=14, family_leave_days_total=5)
    db_session.add_all([old, custom])
    await db_session.commit()

    await align_leave_limits_once(db_session)

    rows = {e.user_id: e for e in (await db_session.execute(
        select(Employee).execution_options(populate_existing=True)
    )).scalars().all()}
    assert (rows[second_user.id].sick_days_total, rows[second_user.id].family_leave_days_total) == (7, 2)
    assert (rows[regular_user.id].sick_days_total, rows[regular_user.id].family_leave_days_total) == (14, 5)
    assert await db_session.get(DataMigrationMark, ALIGN_MARK) is not None
