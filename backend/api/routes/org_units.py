"""HR org-chart units — изолировано от рекрутинговых departments/прав."""
import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.database import OrgUnit, Employee, User, Organization
from api.services.auth import get_current_user
from .organizations import get_current_org, require_org_admin

logger = logging.getLogger("hr-analyzer.org_units")

router = APIRouter()


class OrgUnitCreate(BaseModel):
    # Длины — как у колонок (String(255)/String(20)): длиннее давало 500.
    name: str = Field(..., min_length=1, max_length=255)
    parent_id: Optional[int] = None
    color: Optional[str] = Field(None, max_length=20)


class OrgUnitUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    color: Optional[str] = Field(None, max_length=20)
    sort_order: Optional[int] = None
    parent_id: Optional[int] = None


class AssignEmployee(BaseModel):
    org_unit_id: Optional[int] = None


class EmployeeMini(BaseModel):
    id: int
    user_name: Optional[str] = None
    position: Optional[str] = None


class OrgUnitNode(BaseModel):
    id: int
    name: str
    parent_id: Optional[int] = None
    color: Optional[str] = None
    sort_order: int = 0
    employees: List[EmployeeMini] = []


class PersonNode(BaseModel):
    id: int
    user_name: Optional[str] = None
    position: Optional[str] = None
    manager_id: Optional[int] = None
    org_unit_id: Optional[int] = None
    hired_at: Optional[str] = None


class AssignManager(BaseModel):
    manager_id: Optional[int] = None


class OrgChartResponse(BaseModel):
    units: List[OrgUnitNode]
    unassigned: List[EmployeeMini]
    people: List[PersonNode] = []


@router.get("", response_model=OrgChartResponse)
async def get_org_chart(
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from .employees import _is_admin_or_owner, sync_org_employees, sync_org_departments
    # Синхронизация ПИШЕТ в базу — запускаем её только у админа. Раньше любой
    # участник (и наблюдатель) своим просмотром создавал записи и юниты.
    if await _is_admin_or_owner(current_user, org.id, db):
        try:
            await sync_org_employees(org.id, db)
            await sync_org_departments(org.id, db)
        except Exception:
            logger.exception("ORG_SYNC failed for org=%s", org.id)
            await db.rollback()
    units = (await db.execute(
        select(OrgUnit).where(OrgUnit.org_id == org.id).order_by(OrgUnit.sort_order, OrgUnit.id)
    )).scalars().all()
    rows = (await db.execute(
        select(Employee, User).join(User, Employee.user_id == User.id)
        .where(Employee.org_id == org.id, Employee.is_active == True)  # noqa: E712
    )).all()
    by_unit: dict = {}
    unassigned: List[EmployeeMini] = []
    people: List[PersonNode] = []
    for emp, user in rows:
        mini = EmployeeMini(id=emp.id, user_name=user.name, position=emp.position)
        people.append(PersonNode(id=emp.id, user_name=user.name, position=emp.position,
                                 manager_id=emp.manager_id, org_unit_id=emp.org_unit_id,
                                 hired_at=emp.department_start_date.isoformat() if emp.department_start_date else None))
        if emp.org_unit_id:
            by_unit.setdefault(emp.org_unit_id, []).append(mini)
        else:
            unassigned.append(mini)
    nodes = [
        OrgUnitNode(id=u.id, name=u.name, parent_id=u.parent_id, color=u.color,
                    sort_order=u.sort_order or 0, employees=by_unit.get(u.id, []))
        for u in units
    ]
    return OrgChartResponse(units=nodes, unassigned=unassigned, people=people)


@router.post("", response_model=OrgUnitNode)
async def create_unit(data: OrgUnitCreate, auth: tuple = Depends(require_org_admin), db: AsyncSession = Depends(get_db)):
    user, org, role = auth
    if data.parent_id is not None:
        parent = (await db.execute(
            select(OrgUnit).where(OrgUnit.id == data.parent_id, OrgUnit.org_id == org.id)
        )).scalar_one_or_none()
        if not parent:
            raise HTTPException(status_code=404, detail="Parent unit not found")
    unit = OrgUnit(org_id=org.id, name=data.name, parent_id=data.parent_id, color=data.color, sort_order=0)
    db.add(unit)
    await db.commit()
    await db.refresh(unit)
    return OrgUnitNode(id=unit.id, name=unit.name, parent_id=unit.parent_id, color=unit.color,
                       sort_order=unit.sort_order or 0, employees=[])


@router.patch("/{unit_id}", response_model=OrgUnitNode)
async def update_unit(unit_id: int, data: OrgUnitUpdate, auth: tuple = Depends(require_org_admin), db: AsyncSession = Depends(get_db)):
    user, org, role = auth
    unit = (await db.execute(
        select(OrgUnit).where(OrgUnit.id == unit_id, OrgUnit.org_id == org.id)
    )).scalar_one_or_none()
    if not unit:
        raise HTTPException(status_code=404, detail="Unit not found")
    if data.name is not None:
        unit.name = data.name
    if data.color is not None:
        unit.color = data.color
    if data.sort_order is not None:
        unit.sort_order = data.sort_order
    # reparent (drag отдела) с защитой от циклов; отличаем "parent=null" от "поле отсутствует"
    fset = getattr(data, 'model_fields_set', None)
    if fset is None:
        fset = getattr(data, '__fields_set__', set())
    if 'parent_id' in fset:
        new_parent = data.parent_id
        if new_parent == unit_id:
            raise HTTPException(status_code=400, detail="Unit cannot be its own parent")
        if new_parent is not None:
            all_units = {u.id: u.parent_id for u in (await db.execute(
                select(OrgUnit).where(OrgUnit.org_id == org.id)
            )).scalars().all()}
            if new_parent not in all_units:
                raise HTTPException(status_code=404, detail="Parent unit not found")
            cur = new_parent
            seen = set()
            while cur is not None and cur not in seen:
                if cur == unit_id:
                    raise HTTPException(status_code=400, detail="Cannot move a unit under its own descendant")
                seen.add(cur)
                cur = all_units.get(cur)
        unit.parent_id = new_parent
    await db.commit()
    await db.refresh(unit)
    return OrgUnitNode(id=unit.id, name=unit.name, parent_id=unit.parent_id, color=unit.color,
                       sort_order=unit.sort_order or 0, employees=[])


@router.delete("/{unit_id}")
async def delete_unit(unit_id: int, auth: tuple = Depends(require_org_admin), db: AsyncSession = Depends(get_db)):
    user, org, role = auth
    unit = (await db.execute(
        select(OrgUnit).where(OrgUnit.id == unit_id, OrgUnit.org_id == org.id)
    )).scalar_one_or_none()
    if not unit:
        raise HTTPException(status_code=404, detail="Unit not found")
    # Юнит с именем действующего департамента синхронизация создаст заново при
    # следующем открытии оргсхемы (вместе с людьми) — удаление было бы мнимым.
    from api.models.database import Department
    twin = (await db.execute(
        select(Department.id).where(
            Department.org_id == org.id, Department.name == unit.name, Department.is_active == True  # noqa: E712
        )
    )).first()
    if twin:
        raise HTTPException(
            status_code=409,
            detail="Этот отдел ведётся в «Управление → Департаменты» — удалите или переименуйте его там",
        )
    # детей поднимаем на уровень вверх (на parent удаляемого)
    children = (await db.execute(select(OrgUnit).where(OrgUnit.parent_id == unit_id))).scalars().all()
    for c in children:
        c.parent_id = unit.parent_id
    # сотрудников — в «не распределены»
    emps = (await db.execute(select(Employee).where(Employee.org_unit_id == unit_id))).scalars().all()
    for e in emps:
        e.org_unit_id = None
    await db.delete(unit)
    await db.commit()
    return {"success": True}


async def _manager_creates_cycle(db: AsyncSession, org_id: int, employee_id: int, manager_id: int) -> bool:
    """Станет ли employee своим же начальником, если назначить ему manager_id."""
    rows = (await db.execute(select(Employee.id, Employee.manager_id).where(Employee.org_id == org_id))).all()
    mp = {r[0]: r[1] for r in rows}
    cur, seen = manager_id, set()
    while cur is not None and cur not in seen:
        if cur == employee_id:
            return True
        seen.add(cur)
        cur = mp.get(cur)
    return False


@router.put("/assign/{employee_id}")
async def assign_employee(employee_id: int, data: AssignEmployee, auth: tuple = Depends(require_org_admin), db: AsyncSession = Depends(get_db)):
    user, org, role = auth
    emp = (await db.execute(
        select(Employee).where(Employee.id == employee_id, Employee.org_id == org.id)
    )).scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    unit = None
    if data.org_unit_id is not None:
        unit = (await db.execute(
            select(OrgUnit).where(OrgUnit.id == data.org_unit_id, OrgUnit.org_id == org.id)
        )).scalar_one_or_none()
        if not unit:
            raise HTTPException(status_code=404, detail="Org unit not found")
    emp.org_unit_id = data.org_unit_id
    # Write-through в реальные департаменты (единый источник): перемещение в
    # оргсхеме отражается в «Управление → Департаменты» (department_members +
    # Employee.department_id) и ставит руководителем lead целевого отдела.
    # До 27.10.2026 здесь же молча снимались роли lead/sub_admin (а с ними —
    # права на приглашения и отпуска отдела), руководитель ставился без проверки
    # на цикл, ручной руководитель стирался, а ошибки глотал голый except.
    from api.models.database import Department, DepartmentMember, DeptRole
    all_depts = (await db.execute(select(Department).where(Department.org_id == org.id))).scalars().all()
    org_dept_ids = [d.id for d in all_depts]
    target_dept = next((d for d in all_depts if unit is not None and d.name == unit.name and d.is_active), None)
    emp.department_id = target_dept.id if target_dept else None
    if org_dept_ids:
        memberships = (await db.execute(
            select(DepartmentMember).where(
                DepartmentMember.user_id == emp.user_id, DepartmentMember.department_id.in_(org_dept_ids)
            )
        )).scalars().all()
        # Рядовое членство переезжает; руководящие роли — только явным действием.
        for dm in memberships:
            if dm.role == DeptRole.member and (target_dept is None or dm.department_id != target_dept.id):
                await db.delete(dm)
        if target_dept and not any(dm.department_id == target_dept.id for dm in memberships):
            db.add(DepartmentMember(department_id=target_dept.id, user_id=emp.user_id, role=DeptRole.member))
    if target_dept:
        lead = (await db.execute(
            select(DepartmentMember).where(
                DepartmentMember.department_id == target_dept.id, DepartmentMember.role == DeptRole.lead
            )
        )).scalars().first()
        lead_emp = None
        if lead and lead.user_id != emp.user_id:
            lead_emp = (await db.execute(
                select(Employee).where(Employee.user_id == lead.user_id, Employee.org_id == org.id)
            )).scalar_one_or_none()
        if lead_emp is not None and not await _manager_creates_cycle(db, org.id, emp.id, lead_emp.id):
            emp.manager_id = lead_emp.id
    return {"success": True, "employee_id": employee_id, "org_unit_id": data.org_unit_id}


@router.put("/manager/{employee_id}")
async def set_manager(employee_id: int, data: AssignManager, auth: tuple = Depends(require_org_admin), db: AsyncSession = Depends(get_db)):
    user, org, role = auth
    emp = (await db.execute(
        select(Employee).where(Employee.id == employee_id, Employee.org_id == org.id)
    )).scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    new_mgr = data.manager_id
    if new_mgr is not None:
        if new_mgr == employee_id:
            raise HTTPException(status_code=400, detail="Employee cannot be their own manager")
        mgr = (await db.execute(
            select(Employee).where(Employee.id == new_mgr, Employee.org_id == org.id)
        )).scalar_one_or_none()
        if not mgr:
            raise HTTPException(status_code=404, detail="Manager not found")
        # защита от циклов: идём вверх по цепочке руководителей от нового менеджера
        if await _manager_creates_cycle(db, org.id, employee_id, new_mgr):
            raise HTTPException(status_code=400, detail="Cannot set manager to a subordinate (cycle)")
    emp.manager_id = new_mgr
    await db.commit()
    return {"success": True, "employee_id": employee_id, "manager_id": new_mgr}
