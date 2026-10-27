"""API routes for department management"""
import secrets
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, EmailStr

from ..database import get_db
from ..models.database import (
    User, UserRole, Organization, OrgMember, OrgRole,
    Department, DepartmentMember, DeptRole
)
from typing import Union
from ..services.auth import get_current_user, get_user_org, hash_password

router = APIRouter()


# === Pydantic Schemas ===

class DepartmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    color: Optional[str] = None
    parent_id: Optional[int] = None  # For sub-departments


class DepartmentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    is_active: Optional[bool] = None


class DepartmentMemberAdd(BaseModel):
    user_id: int
    role: DeptRole = DeptRole.member


class DepartmentMemberUpdate(BaseModel):
    role: DeptRole


class QuickAddMemberRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    role: DeptRole = DeptRole.member
    telegram_username: Optional[str] = Field(None, max_length=64)


class QuickAddMemberResponse(BaseModel):
    user_id: int
    name: str
    email: str
    password_generated: Optional[str] = None
    already_existed: bool


class DepartmentResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    color: Optional[str] = None
    is_active: bool
    parent_id: Optional[int] = None
    parent_name: Optional[str] = None
    members_count: int = 0
    entities_count: int = 0
    children_count: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


class DepartmentMinimalResponse(BaseModel):
    """Minimal department info for admins viewing other departments"""
    id: int
    name: str

    class Config:
        from_attributes = True


class DepartmentMemberResponse(BaseModel):
    id: int
    user_id: int
    user_name: str
    user_email: str
    role: DeptRole
    created_at: datetime

    class Config:
        from_attributes = True


# === Helper Functions ===

async def is_org_owner(user: User, org: Organization, db: AsyncSession) -> bool:
    """Check if user is owner of organization (not admin)"""
    if user.role == UserRole.superadmin:
        return True

    # Use enum value for SQL comparison
    result = await db.execute(
        select(OrgMember).where(
            OrgMember.org_id == org.id,
            OrgMember.user_id == user.id,
            OrgMember.role == OrgRole.owner
        )
    )
    return result.scalar_one_or_none() is not None


async def is_org_admin_or_owner(user: User, org: Organization, db: AsyncSession) -> bool:
    """Check if user is admin or owner of organization"""
    if user.role == UserRole.superadmin:
        return True

    result = await db.execute(
        select(OrgMember).where(
            OrgMember.org_id == org.id,
            OrgMember.user_id == user.id,
            OrgMember.role.in_([OrgRole.owner, OrgRole.admin])
        )
    )
    return result.scalar_one_or_none() is not None


async def is_dept_lead(user: User, department_id: int, db: AsyncSession) -> bool:
    """Check if user is lead of department"""
    result = await db.execute(
        select(DepartmentMember).where(
            DepartmentMember.department_id == department_id,
            DepartmentMember.user_id == user.id,
            DepartmentMember.role == DeptRole.lead
        )
    )
    return result.scalar_one_or_none() is not None


async def is_dept_admin(user: User, department_id: int, db: AsyncSession) -> bool:
    """Check if user is lead or sub_admin of department.

    Used for member management operations.
    """
    result = await db.execute(
        select(DepartmentMember).where(
            DepartmentMember.department_id == department_id,
            DepartmentMember.user_id == user.id,
            DepartmentMember.role.in_([DeptRole.lead, DeptRole.sub_admin])
        )
    )
    return result.scalar_one_or_none() is not None


async def get_user_departments(user: User, org: Organization, db: AsyncSession) -> List[Department]:
    """Get all departments user belongs to"""
    result = await db.execute(
        select(Department)
        .join(DepartmentMember, DepartmentMember.department_id == Department.id)
        .where(
            Department.org_id == org.id,
            DepartmentMember.user_id == user.id,
            Department.is_active == True
        )
    )
    return list(result.scalars().all())


# === Routes ===

@router.get("", response_model=List[Union[DepartmentResponse, DepartmentMinimalResponse]])
async def list_departments(
    parent_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all departments in organization.

    Returns:
        - SUPERADMIN/OWNER: all departments with full details
        - ADMIN/SUB_ADMIN: own department with full details + other departments with minimal info (id, name only)
        - MEMBER: only own department with full details

    Args:
        parent_id: Filter by parent department. None = top-level departments only.
                   Use parent_id=-1 to get all departments.
    """
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        return []

    # Check if user is org owner or superadmin
    is_superadmin = current_user.role == UserRole.superadmin
    is_owner = False
    is_org_admin = False
    if not is_superadmin:
        # Роль в организации. Owner И org-admin видят ВСЕ отделы — это нужно, напр.,
        # для пикера отдела в «Взять в штат». Раньше org-admin без своего отдела
        # получал [] (пустой селект у HR-админов в проде).
        role_result = await db.execute(
            select(OrgMember.role).where(
                OrgMember.org_id == org.id,
                OrgMember.user_id == current_user.id,
            )
        )
        _org_role = role_result.scalar_one_or_none()
        is_owner = _org_role == OrgRole.owner
        is_org_admin = _org_role == OrgRole.admin

    # Get user's department if they have one
    user_dept_id = None
    if not is_superadmin and not is_owner:
        dept_member_result = await db.execute(
            select(DepartmentMember).where(DepartmentMember.user_id == current_user.id)
        )
        dept_member = dept_member_result.scalar_one_or_none()
        if dept_member:
            user_dept_id = dept_member.department_id

    # Build query
    query = select(Department).where(Department.org_id == org.id)

    # Filter by parent_id (-1 means all departments)
    if parent_id is None:
        query = query.where(Department.parent_id.is_(None))
    elif parent_id != -1:
        query = query.where(Department.parent_id == parent_id)

    query = query.order_by(Department.name)
    result = await db.execute(query)
    departments = result.scalars().all()

    if not departments:
        return []

    # SUPERADMIN/OWNER/ORG-ADMIN: return all departments with full details
    if is_superadmin or is_owner or is_org_admin:
        # Get all department IDs for batch queries
        dept_ids = [d.id for d in departments]

        # Pre-fetch all parent names
        parent_ids = [d.parent_id for d in departments if d.parent_id]
        parent_names = {}
        if parent_ids:
            parents_result = await db.execute(
                select(Department).where(Department.id.in_(parent_ids))
            )
            for p in parents_result.scalars().all():
                parent_names[p.id] = p.name

        # Batch query: Get member counts for all departments
        from sqlalchemy import func
        members_counts_result = await db.execute(
            select(DepartmentMember.department_id, func.count(DepartmentMember.id))
            .where(DepartmentMember.department_id.in_(dept_ids))
            .group_by(DepartmentMember.department_id)
        )
        members_counts = {row[0]: row[1] for row in members_counts_result.fetchall()}

        # Batch query: Get entity counts for all departments
        from ..models.database import Entity
        entities_counts_result = await db.execute(
            select(Entity.department_id, func.count(Entity.id))
            .where(Entity.department_id.in_(dept_ids), Entity.is_archived.is_not(True))
            .group_by(Entity.department_id)
        )
        entities_counts = {row[0]: row[1] for row in entities_counts_result.fetchall()}

        # Batch query: Get children counts for all departments
        children_counts_result = await db.execute(
            select(Department.parent_id, func.count(Department.id))
            .where(Department.parent_id.in_(dept_ids))
            .group_by(Department.parent_id)
        )
        children_counts = {row[0]: row[1] for row in children_counts_result.fetchall()}

        # Build response using the pre-fetched data
        response = []
        for dept in departments:
            response.append(DepartmentResponse(
                id=dept.id,
                name=dept.name,
                description=dept.description,
                color=dept.color,
                is_active=dept.is_active,
                parent_id=dept.parent_id,
                parent_name=parent_names.get(dept.parent_id) if dept.parent_id else None,
                members_count=members_counts.get(dept.id, 0),
                entities_count=entities_counts.get(dept.id, 0),
                children_count=children_counts.get(dept.id, 0),
                created_at=dept.created_at
            ))

        return response

    # ADMIN/SUB_ADMIN: own department full + others minimal
    elif current_user.role in (UserRole.admin, UserRole.sub_admin) and user_dept_id:
        response = []

        # Get stats only for own department
        from sqlalchemy import func
        own_dept = next((d for d in departments if d.id == user_dept_id), None)

        if own_dept:
            # Get parent name if exists
            parent_name = None
            if own_dept.parent_id:
                parent_result = await db.execute(
                    select(Department).where(Department.id == own_dept.parent_id)
                )
                parent = parent_result.scalar_one_or_none()
                if parent:
                    parent_name = parent.name

            # Get counts for own department
            members_count_result = await db.execute(
                select(func.count(DepartmentMember.id))
                .where(DepartmentMember.department_id == user_dept_id)
            )
            members_count = members_count_result.scalar() or 0

            from ..models.database import Entity
            entities_count_result = await db.execute(
                select(func.count(Entity.id))
                .where(Entity.department_id == user_dept_id)
            )
            entities_count = entities_count_result.scalar() or 0

            children_count_result = await db.execute(
                select(func.count(Department.id))
                .where(Department.parent_id == user_dept_id)
            )
            children_count = children_count_result.scalar() or 0

            response.append(DepartmentResponse(
                id=own_dept.id,
                name=own_dept.name,
                description=own_dept.description,
                color=own_dept.color,
                is_active=own_dept.is_active,
                parent_id=own_dept.parent_id,
                parent_name=parent_name,
                members_count=members_count,
                entities_count=entities_count,
                children_count=children_count,
                created_at=own_dept.created_at
            ))

        # Add other departments with minimal info
        for dept in departments:
            if dept.id != user_dept_id:
                response.append(DepartmentMinimalResponse(
                    id=dept.id,
                    name=dept.name
                ))

        return response

    # MEMBER or no department: only own department
    elif user_dept_id:
        own_dept = next((d for d in departments if d.id == user_dept_id), None)
        if not own_dept:
            return []

        # Get parent name if exists
        parent_name = None
        if own_dept.parent_id:
            parent_result = await db.execute(
                select(Department).where(Department.id == own_dept.parent_id)
            )
            parent = parent_result.scalar_one_or_none()
            if parent:
                parent_name = parent.name

        # Get counts
        from sqlalchemy import func
        members_count_result = await db.execute(
            select(func.count(DepartmentMember.id))
            .where(DepartmentMember.department_id == user_dept_id)
        )
        members_count = members_count_result.scalar() or 0

        from ..models.database import Entity
        entities_count_result = await db.execute(
            select(func.count(Entity.id))
            .where(Entity.department_id == user_dept_id)
        )
        entities_count = entities_count_result.scalar() or 0

        children_count_result = await db.execute(
            select(func.count(Department.id))
            .where(Department.parent_id == user_dept_id)
        )
        children_count = children_count_result.scalar() or 0

        return [DepartmentResponse(
            id=own_dept.id,
            name=own_dept.name,
            description=own_dept.description,
            color=own_dept.color,
            is_active=own_dept.is_active,
            parent_id=own_dept.parent_id,
            parent_name=parent_name,
            members_count=members_count,
            entities_count=entities_count,
            children_count=children_count,
            created_at=own_dept.created_at
        )]

    # No department access
    return []


@router.post("", response_model=DepartmentResponse, status_code=201)
async def create_department(
    data: DepartmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new department.

    - Only org owners can create top-level departments
    - Department leads can create sub-departments under their department
    """
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=403, detail="No organization access")

    is_owner = await is_org_owner(current_user, org, db)

    # Check permissions based on whether it's a sub-department
    if data.parent_id:
        # Creating sub-department - verify parent exists and user is lead of parent
        result = await db.execute(
            select(Department).where(
                Department.id == data.parent_id,
                Department.org_id == org.id
            )
        )
        parent_dept = result.scalar_one_or_none()
        if not parent_dept:
            raise HTTPException(status_code=404, detail="Parent department not found")

        # Check if user is lead of parent department or org owner
        is_parent_lead = await is_dept_lead(current_user, data.parent_id, db)
        if not is_owner and not is_parent_lead:
            raise HTTPException(
                status_code=403,
                detail="Only org owners or department leads can create sub-departments"
            )
    else:
        # Creating top-level department - only org owners
        if not is_owner:
            raise HTTPException(status_code=403, detail="Only owners can create top-level departments")

    department = Department(
        org_id=org.id,
        parent_id=data.parent_id,
        name=data.name,
        description=data.description,
        color=data.color
    )
    db.add(department)
    await db.commit()
    await db.refresh(department)

    # If a lead creates sub-department, automatically make them lead of the new department
    if data.parent_id and not is_owner:
        new_membership = DepartmentMember(
            department_id=department.id,
            user_id=current_user.id,
            role=DeptRole.lead
        )
        db.add(new_membership)
        await db.commit()

    # Get parent name if exists
    parent_name = None
    if data.parent_id:
        result = await db.execute(
            select(Department).where(Department.id == data.parent_id)
        )
        parent = result.scalar_one_or_none()
        if parent:
            parent_name = parent.name

    return DepartmentResponse(
        id=department.id,
        name=department.name,
        description=department.description,
        color=department.color,
        is_active=department.is_active,
        parent_id=department.parent_id,
        parent_name=parent_name,
        members_count=1 if data.parent_id and not is_owner else 0,
        entities_count=0,
        children_count=0,
        created_at=department.created_at
    )


@router.get("/{department_id}", response_model=DepartmentResponse)
async def get_department(
    department_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get department details"""
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=403, detail="No organization access")

    result = await db.execute(
        select(Department).where(Department.id == department_id, Department.org_id == org.id)
    )
    dept = result.scalar_one_or_none()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")

    # Count members using func.count (efficient single query)
    from sqlalchemy import func
    members_count_result = await db.execute(
        select(func.count(DepartmentMember.id)).where(DepartmentMember.department_id == dept.id)
    )
    members_count = members_count_result.scalar() or 0

    # Count entities using func.count
    from ..models.database import Entity
    entities_count_result = await db.execute(
        select(func.count(Entity.id)).where(Entity.department_id == dept.id)
    )
    entities_count = entities_count_result.scalar() or 0

    # Count children using func.count
    children_count_result = await db.execute(
        select(func.count(Department.id)).where(Department.parent_id == dept.id)
    )
    children_count = children_count_result.scalar() or 0

    # Get parent name
    parent_name = None
    if dept.parent_id:
        parent_result = await db.execute(
            select(Department).where(Department.id == dept.parent_id)
        )
        parent = parent_result.scalar_one_or_none()
        if parent:
            parent_name = parent.name

    return DepartmentResponse(
        id=dept.id,
        name=dept.name,
        description=dept.description,
        color=dept.color,
        is_active=dept.is_active,
        parent_id=dept.parent_id,
        parent_name=parent_name,
        members_count=members_count,
        entities_count=entities_count,
        children_count=children_count,
        created_at=dept.created_at
    )


@router.get("/{department_id}/children", response_model=List[DepartmentResponse])
async def get_department_children(
    department_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get child departments of a department"""
    from sqlalchemy import func

    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=403, detail="No organization access")

    # Verify parent department exists and belongs to org
    result = await db.execute(
        select(Department).where(Department.id == department_id, Department.org_id == org.id)
    )
    parent_dept = result.scalar_one_or_none()
    if not parent_dept:
        raise HTTPException(status_code=404, detail="Department not found")

    # Get children
    result = await db.execute(
        select(Department).where(
            Department.parent_id == department_id,
            Department.org_id == org.id
        ).order_by(Department.name)
    )
    children = result.scalars().all()

    if not children:
        return []

    # Get all department IDs for batch queries
    dept_ids = [d.id for d in children]

    # Batch query: Get member counts for all departments
    members_counts_result = await db.execute(
        select(DepartmentMember.department_id, func.count(DepartmentMember.id))
        .where(DepartmentMember.department_id.in_(dept_ids))
        .group_by(DepartmentMember.department_id)
    )
    members_counts = {row[0]: row[1] for row in members_counts_result.fetchall()}

    # Batch query: Get entity counts for all departments
    from ..models.database import Entity
    entities_counts_result = await db.execute(
        select(Entity.department_id, func.count(Entity.id))
        .where(Entity.department_id.in_(dept_ids), Entity.is_archived.is_not(True))
        .group_by(Entity.department_id)
    )
    entities_counts = {row[0]: row[1] for row in entities_counts_result.fetchall()}

    # Batch query: Get children counts for all departments
    children_counts_result = await db.execute(
        select(Department.parent_id, func.count(Department.id))
        .where(Department.parent_id.in_(dept_ids))
        .group_by(Department.parent_id)
    )
    children_counts = {row[0]: row[1] for row in children_counts_result.fetchall()}

    # Build response using the pre-fetched data
    response = []
    for dept in children:
        response.append(DepartmentResponse(
            id=dept.id,
            name=dept.name,
            description=dept.description,
            color=dept.color,
            is_active=dept.is_active,
            parent_id=dept.parent_id,
            parent_name=parent_dept.name,
            members_count=members_counts.get(dept.id, 0),
            entities_count=entities_counts.get(dept.id, 0),
            children_count=children_counts.get(dept.id, 0),
            created_at=dept.created_at
        ))

    return response


@router.patch("/{department_id}", response_model=DepartmentResponse)
async def update_department(
    department_id: int,
    data: DepartmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update department (org admin or dept lead)"""
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=403, detail="No organization access")

    result = await db.execute(
        select(Department).where(Department.id == department_id, Department.org_id == org.id)
    )
    dept = result.scalar_one_or_none()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")

    # Check permissions (org owner or dept lead only)
    is_owner = await is_org_owner(current_user, org, db)
    is_lead = await is_dept_lead(current_user, department_id, db)
    if not is_owner and not is_lead:
        raise HTTPException(status_code=403, detail="Permission denied")

    if data.name is not None:
        dept.name = data.name
    if data.description is not None:
        dept.description = data.description
    if data.color is not None:
        dept.color = data.color
    if data.is_active is not None and is_owner:  # Only owner can deactivate
        dept.is_active = data.is_active

    await db.commit()
    await db.refresh(dept)

    return await get_department(department_id, db, current_user)


@router.delete("/{department_id}")
async def delete_department(
    department_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete department (org owner only)"""
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=403, detail="No organization access")

    if not await is_org_owner(current_user, org, db):
        raise HTTPException(status_code=403, detail="Only owners can delete departments")

    result = await db.execute(
        select(Department).where(Department.id == department_id, Department.org_id == org.id)
    )
    dept = result.scalar_one_or_none()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")

    # Check if department has members
    members_result = await db.execute(
        select(DepartmentMember).where(DepartmentMember.department_id == department_id)
    )
    members_count = len(list(members_result.scalars().all()))
    if members_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete department with {members_count} member(s). Remove members first."
        )

    # Check if department has entities
    from ..models.database import Entity
    entities_result = await db.execute(
        select(Entity).where(Entity.department_id == department_id)
    )
    entities_count = len(list(entities_result.scalars().all()))
    if entities_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete department with {entities_count} entity/entities. Reassign entities first."
        )

    await db.delete(dept)
    await db.commit()

    return {"success": True}


# === Department Members ===

@router.get("/{department_id}/members", response_model=List[DepartmentMemberResponse])
async def list_department_members(
    department_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all members of a department"""
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=403, detail="No organization access")

    # Verify department exists and belongs to org
    result = await db.execute(
        select(Department).where(Department.id == department_id, Department.org_id == org.id)
    )
    dept = result.scalar_one_or_none()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")

    # Get members with User data in a single query (batch query to avoid N+1)
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(DepartmentMember)
        .options(selectinload(DepartmentMember.user))
        .where(DepartmentMember.department_id == department_id)
        .order_by(DepartmentMember.role, DepartmentMember.created_at)
    )
    members = result.scalars().all()

    response = []
    for member in members:
        if member.user:
            response.append(DepartmentMemberResponse(
                id=member.id,
                user_id=member.user.id,
                user_name=member.user.name,
                user_email=member.user.email,
                role=member.role,
                created_at=member.created_at
            ))

    return response


@router.post("/{department_id}/members", response_model=DepartmentMemberResponse)
async def add_department_member(
    department_id: int,
    data: DepartmentMemberAdd,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Add member to department.

    Permissions:
    - Org owner: can add any role (lead, sub_admin, member)
    - Department lead: can add sub_admin and member
    - Department sub_admin: can add only member
    """
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=403, detail="No organization access")

    # Verify department
    result = await db.execute(
        select(Department).where(Department.id == department_id, Department.org_id == org.id)
    )
    dept = result.scalar_one_or_none()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")

    # Check permissions - org admin/owner, lead, or sub_admin of THIS department
    is_org_admin = await is_org_admin_or_owner(current_user, org, db)
    is_lead = await is_dept_lead(current_user, department_id, db)
    is_sub_admin = await is_dept_admin(current_user, department_id, db) and not is_lead

    if not is_org_admin and not is_lead and not is_sub_admin:
        raise HTTPException(status_code=403, detail="Permission denied")

    # Only org owner can add leads
    is_owner = await is_org_owner(current_user, org, db)
    if data.role == DeptRole.lead and not is_owner:
        raise HTTPException(status_code=403, detail="Only org owners can add department leads")

    # Org admin/owner or department lead can add sub_admins
    if data.role == DeptRole.sub_admin and not is_org_admin and not is_lead:
        raise HTTPException(status_code=403, detail="Only org admins/owners or department leads can add sub_admins")

    # Verify user exists and is in org
    result = await db.execute(
        select(User).join(OrgMember, OrgMember.user_id == User.id)
        .where(User.id == data.user_id, OrgMember.org_id == org.id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found in organization")

    # Check if already member
    result = await db.execute(
        select(DepartmentMember).where(
            DepartmentMember.department_id == department_id,
            DepartmentMember.user_id == data.user_id
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        # Update role
        existing.role = data.role
        await db.commit()
        await db.refresh(existing)
        member = existing
    else:
        # Create new
        member = DepartmentMember(
            department_id=department_id,
            user_id=data.user_id,
            role=data.role
        )
        db.add(member)
        await db.commit()
        await db.refresh(member)

    return DepartmentMemberResponse(
        id=member.id,
        user_id=user.id,
        user_name=user.name,
        user_email=user.email,
        role=member.role,
        created_at=member.created_at
    )


@router.post("/{department_id}/quick-add-member", response_model=QuickAddMemberResponse)
async def quick_add_member(
    department_id: int,
    data: QuickAddMemberRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Quick-create a user and add them to a department in one step.

    If a user with the given email already exists, just adds them to the department.
    If the user is new, creates the account with a random password and adds to org + department.

    Returns the generated password (only for new users) so admin can share it once.
    """
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=403, detail="No organization access")

    # Verify department exists and belongs to org
    result = await db.execute(
        select(Department).where(Department.id == department_id, Department.org_id == org.id)
    )
    dept = result.scalar_one_or_none()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")

    # Check permissions - org admin/owner, lead, or sub_admin of THIS department
    is_org_admin = await is_org_admin_or_owner(current_user, org, db)
    is_lead = await is_dept_lead(current_user, department_id, db)
    is_sub = await is_dept_admin(current_user, department_id, db)

    if not is_org_admin and not is_lead and not is_sub:
        raise HTTPException(status_code=403, detail="Permission denied")

    # Check if user with this email already exists
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    already_existed = user is not None
    password_generated = None

    # Нормализуем Telegram-handle: без @, в нижнем регистре
    tg_handle = (data.telegram_username or "").lstrip("@").strip().lower() or None

    if not user:
        # Create new user
        password_generated = secrets.token_urlsafe(8)
        user = User(
            name=data.name,
            email=data.email,
            password_hash=hash_password(password_generated),
            role=UserRole.member,
            is_active=True,
            telegram_username=tg_handle,
        )
        db.add(user)
        await db.flush()  # get user.id
    elif tg_handle and not user.telegram_username:
        # Существующий аккаунт без TG — мягко проставим (не перетираем уже заполненный)
        user.telegram_username = tg_handle

    # Гарантируем членство в организации — идемпотентно, и для НОВЫХ, и для
    # существующих пользователей. Раньше добавление OrgMember по ошибке было
    # вложено в ветку `elif tg_handle`, из-за чего:
    #   * новый участник создавался БЕЗ org-membership → его не видно в команде,
    #     а его собственные org-scoped запросы (/projects и т.п.) падали с 400;
    #   * существующему юзеру с проставляемым TG OrgMember добавлялся без проверки
    #     дубля → IntegrityError на uq_org_member_user_org.
    result = await db.execute(
        select(OrgMember).where(
            OrgMember.org_id == org.id,
            OrgMember.user_id == user.id,
        )
    )
    if not result.scalar_one_or_none():
        db.add(OrgMember(
            org_id=org.id,
            user_id=user.id,
            role=OrgRole.member,
        ))

    # Check if already a department member
    result = await db.execute(
        select(DepartmentMember).where(
            DepartmentMember.department_id == department_id,
            DepartmentMember.user_id == user.id
        )
    )
    existing_member = result.scalar_one_or_none()
    if not existing_member:
        dept_member = DepartmentMember(
            department_id=department_id,
            user_id=user.id,
            role=data.role,
        )
        db.add(dept_member)

    await db.commit()

    return QuickAddMemberResponse(
        user_id=user.id,
        name=user.name,
        email=user.email,
        password_generated=password_generated,
        already_existed=already_existed,
    )


@router.patch("/{department_id}/members/{user_id}", response_model=DepartmentMemberResponse)
async def update_department_member(
    department_id: int,
    user_id: int,
    data: DepartmentMemberUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update member role in department.

    Permissions:
    - Org owner: can set any role
    - Department lead: can set sub_admin and member roles
    - Department sub_admin: can only set member role
    """
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=403, detail="No organization access")

    is_org_admin = await is_org_admin_or_owner(current_user, org, db)
    is_lead = await is_dept_lead(current_user, department_id, db)
    is_sub_admin = await is_dept_admin(current_user, department_id, db) and not is_lead

    if not is_org_admin and not is_lead and not is_sub_admin:
        raise HTTPException(status_code=403, detail="Permission denied")

    # Only org owner can set lead role
    is_owner = await is_org_owner(current_user, org, db)
    if data.role == DeptRole.lead and not is_owner:
        raise HTTPException(status_code=403, detail="Only org owners can set lead role")

    # Org admin/owner or department lead can set sub_admin role
    if data.role == DeptRole.sub_admin and not is_org_admin and not is_lead:
        raise HTTPException(status_code=403, detail="Only org admins/owners or department leads can set sub_admin role")

    result = await db.execute(
        select(DepartmentMember).where(
            DepartmentMember.department_id == department_id,
            DepartmentMember.user_id == user_id
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    member.role = data.role
    await db.commit()
    await db.refresh(member)

    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one()

    return DepartmentMemberResponse(
        id=member.id,
        user_id=user.id,
        user_name=user.name,
        user_email=user.email,
        role=member.role,
        created_at=member.created_at
    )


@router.delete("/{department_id}/members/{user_id}")
async def remove_department_member(
    department_id: int,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Remove member from department.

    Permissions:
    - Org admin/owner: can remove anyone except leads (only owner can remove leads)
    - Department lead: can remove sub_admins and members
    - Department sub_admin: can remove only members
    """
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=403, detail="No organization access")

    is_org_admin = await is_org_admin_or_owner(current_user, org, db)
    is_lead = await is_dept_lead(current_user, department_id, db)
    is_sub_admin = await is_dept_admin(current_user, department_id, db) and not is_lead

    if not is_org_admin and not is_lead and not is_sub_admin:
        raise HTTPException(status_code=403, detail="Permission denied")

    # Wrap in explicit transaction to prevent race conditions when checking last lead
    async with db.begin_nested():
        result = await db.execute(
            select(DepartmentMember).where(
                DepartmentMember.department_id == department_id,
                DepartmentMember.user_id == user_id
            )
        )
        member = result.scalar_one_or_none()
        if not member:
            raise HTTPException(status_code=404, detail="Member not found")

        # Sub_admin can only remove regular members
        # Use enum comparison since member.role comes from DB as DeptRole enum
        if is_sub_admin and member.role in (DeptRole.lead, DeptRole.sub_admin):
            raise HTTPException(status_code=403, detail="Sub-admins can only remove regular members")

        # Don't allow removing the last lead
        if member.role == DeptRole.lead:
            leads_result = await db.execute(
                select(DepartmentMember).where(
                    DepartmentMember.department_id == department_id,
                    DepartmentMember.role == DeptRole.lead
                )
            )
            leads_count = len(list(leads_result.scalars().all()))
            if leads_count <= 1:
                raise HTTPException(status_code=400, detail="Cannot remove the last department lead")

        await db.delete(member)
        await db.flush()

    await db.commit()

    return {"success": True}


# === User's Departments ===

@router.get("/my/departments", response_model=List[DepartmentResponse])
async def get_my_departments(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get departments current user belongs to"""
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        return []

    departments = await get_user_departments(current_user, org, db)

    # Pre-fetch parent names
    parent_ids = [d.parent_id for d in departments if d.parent_id]
    parent_names = {}
    if parent_ids:
        parents_result = await db.execute(
            select(Department).where(Department.id.in_(parent_ids))
        )
        for p in parents_result.scalars().all():
            parent_names[p.id] = p.name

    if not departments:
        return []

    # Get all department IDs for batch queries
    dept_ids = [d.id for d in departments]

    # Batch query: Get member counts for all departments
    from sqlalchemy import func
    members_counts_result = await db.execute(
        select(DepartmentMember.department_id, func.count(DepartmentMember.id))
        .where(DepartmentMember.department_id.in_(dept_ids))
        .group_by(DepartmentMember.department_id)
    )
    members_counts = {row[0]: row[1] for row in members_counts_result.fetchall()}

    # Batch query: Get entity counts for all departments
    from ..models.database import Entity
    entities_counts_result = await db.execute(
        select(Entity.department_id, func.count(Entity.id))
        .where(Entity.department_id.in_(dept_ids), Entity.is_archived.is_not(True))
        .group_by(Entity.department_id)
    )
    entities_counts = {row[0]: row[1] for row in entities_counts_result.fetchall()}

    # Batch query: Get children counts for all departments
    children_counts_result = await db.execute(
        select(Department.parent_id, func.count(Department.id))
        .where(Department.parent_id.in_(dept_ids))
        .group_by(Department.parent_id)
    )
    children_counts = {row[0]: row[1] for row in children_counts_result.fetchall()}

    # Build response using the pre-fetched data
    response = []
    for dept in departments:
        response.append(DepartmentResponse(
            id=dept.id,
            name=dept.name,
            description=dept.description,
            color=dept.color,
            is_active=dept.is_active,
            parent_id=dept.parent_id,
            parent_name=parent_names.get(dept.parent_id) if dept.parent_id else None,
            members_count=members_counts.get(dept.id, 0),
            entities_count=entities_counts.get(dept.id, 0),
            children_count=children_counts.get(dept.id, 0),
            created_at=dept.created_at
        ))

    return response


class MyDeptRoleResponse(BaseModel):
    department_id: int
    department_name: str
    role: DeptRole


@router.get("/my/roles", response_model=List[MyDeptRoleResponse])
async def get_my_dept_roles(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get current user's roles in their departments.

    Returns list of {department_id, department_name, role} for departments
    where user is lead or sub_admin (useful for permission checks).
    """
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        return []

    # Get all department memberships for current user with lead/sub_admin role
    result = await db.execute(
        select(DepartmentMember, Department)
        .join(Department, DepartmentMember.department_id == Department.id)
        .where(
            DepartmentMember.user_id == current_user.id,
            Department.org_id == org.id,
            DepartmentMember.role.in_([DeptRole.lead, DeptRole.sub_admin])
        )
    )
    rows = result.fetchall()

    return [
        MyDeptRoleResponse(
            department_id=membership.department_id,
            department_name=dept.name,
            role=membership.role
        )
        for membership, dept in rows
    ]


@router.get("/my/managed-users", response_model=List[int])
async def get_my_managed_user_ids(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get IDs of users that current user can manage (users in departments where current user is lead/sub_admin).

    This is useful for frontend to determine which users the current user can toggle full_access for.
    """
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        return []

    # Get departments where current user is lead or sub_admin
    result = await db.execute(
        select(DepartmentMember.department_id).where(
            DepartmentMember.user_id == current_user.id,
            DepartmentMember.role.in_([DeptRole.lead, DeptRole.sub_admin])
        )
    )
    managed_dept_ids = [r[0] for r in result.fetchall()]

    if not managed_dept_ids:
        return []

    # Get all user IDs in these departments (excluding current user)
    result = await db.execute(
        select(DepartmentMember.user_id).where(
            DepartmentMember.department_id.in_(managed_dept_ids),
            DepartmentMember.user_id != current_user.id
        ).distinct()
    )

    return [r[0] for r in result.fetchall()]
