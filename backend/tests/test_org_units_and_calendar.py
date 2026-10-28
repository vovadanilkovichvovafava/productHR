"""Сторож: оргсхема и календарь отпусков.

До 27.10.2026: перенос сотрудника в оргсхеме молча снимал роль лида (и права
на приглашения и отпуска отдела), ставил руководителя с циклом и стирал
ручного руководителя; синхронизация замыкала юниты в цикл и воскрешала
удалённые; любой участник своим GET писал в базу; календарь отпусков отдавал
всем все заявки организации, включая больничные.
"""
from datetime import datetime

from sqlalchemy import select

from api.models.database import (
    Department, DepartmentMember, DeptRole, Employee, OrgMember, OrgRole, OrgUnit, TimeOffRequest,
)
from api.services.auth import create_access_token


def _h(user):
    return {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}


async def test_move_keeps_lead_role(
    client, db_session, organization, department, second_department, org_owner, org_member, admin_user, second_user,
):
    db_session.add(DepartmentMember(department_id=department.id, user_id=second_user.id, role=DeptRole.lead))
    emp = Employee(user_id=second_user.id, org_id=organization.id, is_active=True)
    unit = OrgUnit(org_id=organization.id, name=second_department.name)
    db_session.add_all([emp, unit])
    await db_session.commit()

    resp = await client.put(f"/api/org-units/assign/{emp.id}", json={"org_unit_id": unit.id},
                            headers=_h(admin_user), params={"org_id": organization.id})

    assert resp.status_code == 200, resp.text
    roles = {(dm.department_id, dm.role) for dm in (await db_session.execute(
        select(DepartmentMember).where(DepartmentMember.user_id == second_user.id)
    )).scalars().all()}
    assert (department.id, DeptRole.lead) in roles


async def test_move_does_not_create_manager_cycle(
    client, db_session, organization, department, org_owner, org_member, org_admin,
    admin_user, second_user, regular_user,
):
    # regular_user — лид отдела department и подчинённый second_user.
    db_session.add(DepartmentMember(department_id=department.id, user_id=regular_user.id, role=DeptRole.lead))
    boss = Employee(user_id=second_user.id, org_id=organization.id, is_active=True)
    db_session.add(boss)
    await db_session.flush()
    lead = Employee(user_id=regular_user.id, org_id=organization.id, is_active=True, manager_id=boss.id)
    unit = OrgUnit(org_id=organization.id, name=department.name)
    db_session.add_all([lead, unit])
    await db_session.commit()

    resp = await client.put(f"/api/org-units/assign/{boss.id}", json={"org_unit_id": unit.id},
                            headers=_h(admin_user), params={"org_id": organization.id})

    assert resp.status_code == 200, resp.text
    await db_session.refresh(boss)
    assert boss.manager_id != lead.id  # иначе boss → lead → boss


async def test_unit_of_live_department_cannot_be_deleted(
    client, db_session, organization, department, org_owner, admin_user,
):
    unit = OrgUnit(org_id=organization.id, name=department.name)
    db_session.add(unit)
    await db_session.commit()

    resp = await client.delete(f"/api/org-units/{unit.id}", headers=_h(admin_user), params={"org_id": organization.id})

    assert resp.status_code == 409


async def test_member_view_does_not_write(client, db_session, organization, org_owner, org_member, second_user):
    resp = await client.get("/api/org-units", headers=_h(second_user), params={"org_id": organization.id})

    assert resp.status_code == 200
    assert (await db_session.execute(select(Employee))).scalars().all() == []


async def test_sync_skips_superadmin(
    client, db_session, organization, org_owner, superadmin_org_member, admin_user, superadmin_user,
):
    resp = await client.get("/api/org-units", headers=_h(admin_user), params={"org_id": organization.id})

    assert resp.status_code == 200
    emp = (await db_session.execute(
        select(Employee).where(Employee.user_id == superadmin_user.id)
    )).scalar_one_or_none()
    assert emp is None


async def test_calendar_is_scoped(
    client, db_session, organization, org_member, org_admin, second_user, regular_user,
):
    db_session.add_all([
        TimeOffRequest(org_id=organization.id, user_id=regular_user.id, type="sick",
                       date_from=datetime(2026, 11, 2), date_to=datetime(2026, 11, 3)),
        TimeOffRequest(org_id=organization.id, user_id=second_user.id,
                       date_from=datetime(2026, 11, 9), date_to=datetime(2026, 11, 10)),
    ])
    await db_session.commit()

    resp = await client.get("/api/timeoff/calendar", headers=_h(second_user))

    assert resp.status_code == 200
    assert len(resp.json()) == 1  # только своя заявка, чужого больничного не видно


async def test_sync_rollback_does_not_break_views(
    client, db_session, organization, org_owner, admin_user, monkeypatch,
):
    """Две вкладки синхронизируют разом → IntegrityError → rollback, который
    просрочивает объекты сессии; org.id после него грузился лениво → 500."""
    import api.routes.employees as employees_routes

    async def conflicting_sync(org_id, db):
        await db.rollback()  # как после IntegrityError у параллельного запроса
        return 1

    monkeypatch.setattr(employees_routes, "sync_org_employees", conflicting_sync)
    # В тестах приложение и фикстуры делят одну сессию: откат просрочит и их.
    headers, org_id = _h(admin_user), organization.id

    chart = await client.get("/api/org-units", headers=headers, params={"org_id": org_id})
    listing = await client.get("/api/employees", headers=headers)

    assert chart.status_code == 200, chart.text
    assert listing.status_code == 200, listing.text
