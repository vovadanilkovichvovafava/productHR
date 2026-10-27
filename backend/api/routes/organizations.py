"""
Organization Management Routes.

Provides:
- GET /organizations/current - Get current user's organization
- PUT /organizations/current - Update organization settings
- GET /organizations/current/members - List organization members
- POST /organizations/current/members - Invite new member
- PUT /organizations/current/members/{user_id} - Update member role
- DELETE /organizations/current/members/{user_id} - Remove member
"""
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete, update
from sqlalchemy.orm import selectinload
from pydantic import BaseModel, EmailStr, Field

from ..database import get_db
from ..models.database import (
    User, UserRole, Organization, OrgMember, OrgRole,
    Entity, Chat, CallRecording, AnalysisHistory,
    AIConversation, EntityTransfer, Invitation, CriteriaPreset,
    Department, DepartmentMember, DeptRole, SharedAccess,
    UserCustomRole, CustomRole, ReportSubscription, EntityAIConversation, Vacancy
)
from ..services.auth import get_current_user, get_user_org, get_user_org_role, hash_password

router = APIRouter()


# Schemas
class OrganizationResponse(BaseModel):
    id: int
    name: str
    slug: str
    subscription_plan: str
    settings: dict
    is_active: bool
    created_at: datetime
    members_count: int = 0
    entities_count: int = 0
    chats_count: int = 0
    calls_count: int = 0

    class Config:
        from_attributes = True


class OrganizationUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    settings: Optional[dict] = None


class OrgMemberResponse(BaseModel):
    id: int
    user_id: int
    user_email: str
    user_name: str
    role: str
    has_full_access: bool = False  # Full database access (can see all vacancies/candidates)
    invited_by_name: Optional[str] = None
    created_at: datetime
    custom_role_id: Optional[int] = None
    custom_role_name: Optional[str] = None
    # Department info
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    department_role: Optional[str] = None  # lead, sub_admin, member

    class Config:
        from_attributes = True


class InviteMemberRequest(BaseModel):
    email: EmailStr
    name: str
    password: str = Field(min_length=8)
    role: str = "member"  # owner, admin, member
    department_ids: Optional[List[int]] = None  # Departments to add user to
    department_role: str = "member"  # Role in departments: lead, member


class UpdateMemberRoleRequest(BaseModel):
    role: str  # owner, admin, member
    is_readonly: Optional[bool] = None  # «Наблюдатель»: видит всё, ничего не меняет
    # Скоуп по воронкам (01.10.2026): список id вакансий, которыми ограничена
    # видимость кандидатов. Пустой список — ограничения нет (видит весь пул).
    scope_vacancy_ids: Optional[List[int]] = None


# Helper to check org access
async def get_current_org(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Organization:
    """Get current user's organization or raise 403."""
    user = await db.merge(user)

    # Superadmin can access any organization
    if user.role == UserRole.superadmin:
        # Return first available organization for superadmin
        result = await db.execute(
            select(Organization).order_by(Organization.created_at).limit(1)
        )
        org = result.scalar_one_or_none()
        if not org:
            raise HTTPException(status_code=404, detail="No organizations exist")
        return org

    org = await get_user_org(user, db)
    if not org:
        raise HTTPException(status_code=403, detail="No organization access")
    return org


async def require_org_admin(
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db)
) -> tuple:
    """Require user to be org admin or owner."""
    user = await db.merge(user)

    # Superadmin bypasses org role checks
    if user.role == UserRole.superadmin:
        # Return a special role marker for superadmin
        return user, org, OrgRole.owner

    role = await get_user_org_role(user, org.id, db)
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user, org, role


async def require_org_owner(
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db)
) -> tuple:
    """Require user to be org owner."""
    user = await db.merge(user)
    role = await get_user_org_role(user, org.id, db)
    if role != "owner":
        raise HTTPException(status_code=403, detail="Owner access required")
    return user, org


@router.get("/current", response_model=OrganizationResponse)
async def get_current_organization(
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db)
):
    """Get current user's organization with stats."""
    # Get counts
    members_count = await db.scalar(
        select(func.count(OrgMember.id)).where(OrgMember.org_id == org.id)
    )
    entities_count = await db.scalar(
        select(func.count(Entity.id)).where(Entity.org_id == org.id)
    )
    chats_count = await db.scalar(
        select(func.count(Chat.id)).where(Chat.org_id == org.id, Chat.deleted_at.is_(None))
    )
    calls_count = await db.scalar(
        select(func.count(CallRecording.id)).where(CallRecording.org_id == org.id)
    )

    return OrganizationResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        subscription_plan=org.subscription_plan.value,
        settings=org.settings or {},
        is_active=org.is_active,
        created_at=org.created_at,
        members_count=members_count or 0,
        entities_count=entities_count or 0,
        chats_count=chats_count or 0,
        calls_count=calls_count or 0
    )


@router.put("/current", response_model=OrganizationResponse)
async def update_organization(
    data: OrganizationUpdate,
    db: AsyncSession = Depends(get_db),
    auth: tuple = Depends(require_org_owner)
):
    """Update organization settings (owner only)."""
    user, org = auth

    if data.name:
        org.name = data.name
    if data.settings:
        org.settings = {**(org.settings or {}), **data.settings}

    await db.commit()
    await db.refresh(org)

    return await get_current_organization(org, db)


@router.get("/current/members", response_model=List[OrgMemberResponse])
async def list_organization_members(
    org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List organization members based on user's role.

    - Superadmin/Owner: sees all members
    - Admin (department lead/sub_admin): sees own department members + other department leads
    - Member: sees only own department members
    """
    current_user = await db.merge(current_user)

    # Get current user's org role and department info
    org_role = await get_user_org_role(current_user, org.id, db)

    # Get current user's department membership
    current_user_dept_result = await db.execute(
        select(DepartmentMember).where(DepartmentMember.user_id == current_user.id)
    )
    current_user_dept = current_user_dept_result.scalar_one_or_none()
    current_user_dept_id = current_user_dept.department_id if current_user_dept else None
    current_user_dept_role = current_user_dept.role if current_user_dept else None

    # Determine visibility scope
    is_superadmin = current_user.role == UserRole.superadmin
    is_owner = org_role == OrgRole.owner
    is_admin = org_role == OrgRole.admin
    is_dept_lead = current_user_dept_role in [DeptRole.lead, DeptRole.sub_admin] if current_user_dept_role else False

    # Get all members first
    result = await db.execute(
        select(OrgMember)
        .options(selectinload(OrgMember.user))
        .where(OrgMember.org_id == org.id)
        .order_by(OrgMember.created_at)
    )
    all_members = result.scalars().all()

    # Pre-fetch department memberships for all users
    user_ids = [m.user_id for m in all_members]
    dept_memberships_result = await db.execute(
        select(DepartmentMember, Department)
        .join(Department, Department.id == DepartmentMember.department_id)
        .where(DepartmentMember.user_id.in_(user_ids))
    )

    # Build map: user_id -> (department_id, department_name, department_role)
    user_dept_map = {}
    for dept_member, dept in dept_memberships_result.all():
        if dept_member.user_id not in user_dept_map:
            user_dept_map[dept_member.user_id] = (dept.id, dept.name, dept_member.role)

    # Filter members based on role
    if is_superadmin or is_owner:
        # Superadmin/Owner sees everyone
        filtered_members = all_members
    elif is_admin:
        # HR admin видит: всех лидов/sub_admin любого отдела + членов своего отдела
        filtered_members = []
        for m in all_members:
            user_dept_info = user_dept_map.get(m.user_id)
            if user_dept_info:
                member_dept_id, _, member_dept_role = user_dept_info
                if member_dept_role in [DeptRole.lead, DeptRole.sub_admin]:
                    filtered_members.append(m)
                elif current_user_dept_id and member_dept_id == current_user_dept_id:
                    filtered_members.append(m)
    elif is_dept_lead:
        # Лид/sub_admin видит ТОЛЬКО членов своих отделов (любых, где он lead/sub_admin).
        # Не показываем лидов чужих отделов — раньше показывали, но это противоречит
        # ожиданию «команда лида = его люди».
        lead_dept_ids_result = await db.execute(
            select(DepartmentMember.department_id).where(
                DepartmentMember.user_id == current_user.id,
                DepartmentMember.role.in_([DeptRole.lead, DeptRole.sub_admin]),
            )
        )
        lead_dept_ids = {r for r in lead_dept_ids_result.scalars().all()}
        # Все user_id-ы из этих отделов
        dept_users_result = await db.execute(
            select(DepartmentMember.user_id).where(
                DepartmentMember.department_id.in_(lead_dept_ids)
            )
        )
        allowed_user_ids = {uid for uid in dept_users_result.scalars().all()}
        allowed_user_ids.add(current_user.id)
        filtered_members = [m for m in all_members if m.user_id in allowed_user_ids]
    else:
        # Regular member sees only own department members
        filtered_members = []
        if current_user_dept_id:
            for m in all_members:
                user_dept_info = user_dept_map.get(m.user_id)
                if user_dept_info and user_dept_info[0] == current_user_dept_id:
                    filtered_members.append(m)

    # Pre-fetch invited_by names
    invited_by_ids = [m.invited_by for m in filtered_members if m.invited_by]
    inviter_names = {}
    if invited_by_ids:
        inviters_result = await db.execute(select(User).where(User.id.in_(invited_by_ids)))
        for inviter in inviters_result.scalars().all():
            inviter_names[inviter.id] = inviter.name

    # Pre-fetch custom role assignments for filtered members
    filtered_user_ids = [m.user_id for m in filtered_members]
    custom_roles_map = {}
    if filtered_user_ids:
        custom_roles_result = await db.execute(
            select(UserCustomRole, CustomRole)
            .join(CustomRole, CustomRole.id == UserCustomRole.role_id)
            .where(
                UserCustomRole.user_id.in_(filtered_user_ids),
                CustomRole.is_active == True
            )
        )
        for assignment, role in custom_roles_result.all():
            custom_roles_map[assignment.user_id] = {
                "id": role.id,
                "name": role.name
            }

    return [
        OrgMemberResponse(
            id=m.id,
            user_id=m.user_id,
            user_email=m.user.email,
            user_name=m.user.name,
            role=m.role.value,
            has_full_access=m.has_full_access if hasattr(m, 'has_full_access') and m.has_full_access else False,
            invited_by_name=inviter_names.get(m.invited_by) if m.invited_by else None,
            created_at=m.created_at,
            custom_role_id=custom_roles_map.get(m.user_id, {}).get("id"),
            custom_role_name=custom_roles_map.get(m.user_id, {}).get("name"),
            department_id=user_dept_map.get(m.user_id, (None, None, None))[0],
            department_name=user_dept_map.get(m.user_id, (None, None, None))[1],
            department_role=user_dept_map.get(m.user_id, (None, None, None))[2].value if user_dept_map.get(m.user_id, (None, None, None))[2] else None
        )
        for m in filtered_members
    ]


@router.post("/current/members", response_model=OrgMemberResponse)
async def invite_member(
    data: InviteMemberRequest,
    db: AsyncSession = Depends(get_db),
    auth: tuple = Depends(require_org_admin)
):
    """Invite a new member to organization (creates user account)."""
    user, org, role = auth

    # Check if email already exists
    result = await db.execute(select(User).where(User.email == data.email))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        # Check if already member
        result = await db.execute(
            select(OrgMember).where(
                OrgMember.org_id == org.id,
                OrgMember.user_id == existing_user.id
            )
        )
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="User is already a member")

        # Add existing user to org
        new_user = existing_user
    else:
        # Create new user with member role (access determined by OrgRole and DeptRole)
        new_user = User(
            email=data.email,
            password_hash=hash_password(data.password),
            name=data.name,
            role=UserRole.member  # Regular user - access via OrgRole/DeptRole
        )
        db.add(new_user)
        await db.flush()

    # Validate role
    try:
        member_role = OrgRole(data.role)
    except ValueError:
        member_role = OrgRole.member

    # Only owner can add other owners
    if member_role == OrgRole.owner and role != "owner":
        raise HTTPException(status_code=403, detail="Only owner can add owners")

    # Create membership
    membership = OrgMember(
        org_id=org.id,
        user_id=new_user.id,
        role=member_role,
        invited_by=user.id
    )
    db.add(membership)
    await db.flush()

    # Add to departments if specified
    if data.department_ids:
        # Validate department role
        try:
            dept_role = DeptRole(data.department_role)
        except ValueError:
            dept_role = DeptRole.member

        # Only org admins/owners can set lead role
        if dept_role == DeptRole.lead and role not in ("owner", "admin"):
            dept_role = DeptRole.member

        for dept_id in data.department_ids:
            # Verify department belongs to org
            result = await db.execute(
                select(Department).where(
                    Department.id == dept_id,
                    Department.org_id == org.id
                )
            )
            dept = result.scalar_one_or_none()
            if dept:
                # Create department membership
                dept_membership = DepartmentMember(
                    department_id=dept_id,
                    user_id=new_user.id,
                    role=dept_role
                )
                db.add(dept_membership)

    await db.commit()

    return OrgMemberResponse(
        id=membership.id,
        user_id=new_user.id,
        user_email=new_user.email,
        user_name=new_user.name,
        role=membership.role.value,
        has_full_access=False,
        created_at=membership.created_at
    )


@router.patch("/current/members/{user_id}/role")
async def update_member_role(
    user_id: int,
    data: UpdateMemberRoleRequest,
    db: AsyncSession = Depends(get_db),
    auth: tuple = Depends(require_org_admin)
):
    """Update member's role in organization."""
    current_user, org, current_role = auth

    # Can't change own role
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot change own role")

    # Get membership
    result = await db.execute(
        select(OrgMember).where(
            OrgMember.org_id == org.id,
            OrgMember.user_id == user_id
        )
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=404, detail="Member not found")

    # Validate new role
    try:
        new_role = OrgRole(data.role)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid role")

    # Only owner can change to/from owner
    # Use enum comparison since membership.role comes from DB as OrgRole enum
    if (new_role == OrgRole.owner or membership.role == OrgRole.owner) and current_role != "owner":
        raise HTTPException(status_code=403, detail="Only owner can manage owner roles")

    membership.role = new_role
    if data.is_readonly is not None:
        membership.is_readonly = bool(data.is_readonly)
    if data.scope_vacancy_ids is not None:
        # Чужие вакансии в скоуп не берём: иначе галочкой можно было бы выдать
        # доступ к воронке другой организации.
        allowed = (await db.execute(
            select(Vacancy.id).where(
                Vacancy.org_id == org.id,
                Vacancy.id.in_([int(v) for v in data.scope_vacancy_ids]),
            )
        )).scalars().all() if data.scope_vacancy_ids else []
        membership.scope_vacancy_ids = [int(v) for v in allowed] or None
    await db.commit()

    return {
        "success": True,
        "role": new_role.value,
        "is_readonly": membership.is_readonly,
        "scope_vacancy_ids": membership.scope_vacancy_ids or [],
    }


@router.put("/current/members/{user_id}/full-access")
async def toggle_member_full_access(
    user_id: int,
    has_full_access: bool,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org)
):
    """
    Toggle full database access for a member.

    When enabled, the member can see all vacancies and candidates in the organization
    without being an admin. This is useful for recruiters who need to see all data
    but shouldn't have admin permissions.

    Can be set by: superadmin, owner, admin, OR department lead/sub_admin (for their dept members)

    NOTE: This feature requires the has_full_access migration to be applied.
    """
    # Feature temporarily disabled until migration is applied
    raise HTTPException(
        status_code=501,
        detail="Full access feature is temporarily unavailable. Please run database migrations."
    )


@router.delete("/current/members/{user_id}")
async def remove_member(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    auth: tuple = Depends(require_org_admin)
):
    """
    Remove member from organization.

    Permission rules:
    - Superadmin: can remove anyone
    - Owner: can remove admins and members (not other owners)
    - Admin: can only remove members from their own department
    """
    current_user, org, current_role = auth

    # Can't remove self
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot remove yourself")

    # Get membership
    result = await db.execute(
        select(OrgMember)
        .options(selectinload(OrgMember.user))
        .where(
            OrgMember.org_id == org.id,
            OrgMember.user_id == user_id
        )
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=404, detail="Member not found")

    # Permission checks based on roles
    # Superadmin can remove anyone
    if current_user.role == UserRole.superadmin:
        pass  # No restrictions for superadmin
    # Owner can remove admins and members, but not other owners
    elif current_role == "owner" or current_role == OrgRole.owner:
        if membership.role == OrgRole.owner:
            raise HTTPException(status_code=403, detail="Cannot remove other owners")
    # Admin can only remove members from their own department
    elif current_role == "admin" or current_role == OrgRole.admin:
        if membership.role in (OrgRole.owner, OrgRole.admin):
            raise HTTPException(status_code=403, detail="Admins can only remove members")

        # Get current user's department membership with role
        current_user_dept_result = await db.execute(
            select(DepartmentMember.department_id, DepartmentMember.role)
            .where(DepartmentMember.user_id == current_user.id)
        )
        current_user_depts = {row[0]: row[1] for row in current_user_dept_result}

        # Get target user's department membership with role
        target_user_dept_result = await db.execute(
            select(DepartmentMember.department_id, DepartmentMember.role)
            .where(DepartmentMember.user_id == user_id)
        )
        target_user_depts = {row[0]: row[1] for row in target_user_dept_result}

        # Check if they share any department
        shared_depts = set(current_user_depts.keys()).intersection(target_user_depts.keys())
        if not shared_depts:
            raise HTTPException(
                status_code=403,
                detail="You can only remove members from your own department"
            )

        # Check role hierarchy: sub_admin cannot remove lead
        for dept_id in shared_depts:
            current_dept_role = current_user_depts[dept_id]
            target_dept_role = target_user_depts[dept_id]

            # Sub_admin cannot remove lead or other sub_admins
            if current_dept_role == DeptRole.sub_admin:
                if target_dept_role in [DeptRole.lead, DeptRole.sub_admin]:
                    raise HTTPException(
                        status_code=403,
                        detail="Sub-admins cannot remove department leads or other sub-admins"
                    )

            # Lead can remove sub_admins and members, but not other leads
            if current_dept_role == DeptRole.lead:
                if target_dept_role == DeptRole.lead:
                    raise HTTPException(
                        status_code=403,
                        detail="Department leads cannot remove other leads"
                    )
    else:
        raise HTTPException(status_code=403, detail="No permission to remove members")

    target_user = membership.user
    user_deleted = False

    # Wrap in explicit transaction to prevent race conditions
    async with db.begin_nested():
        # Check if user is member of any other orgs
        result = await db.execute(
            select(func.count(OrgMember.id)).where(OrgMember.user_id == user_id)
        )
        other_memberships = result.scalar()

        # Remove membership
        await db.delete(membership)
        await db.flush()

        # If no other memberships (count was 1, just this membership) and not superadmin, delete user entirely
        if other_memberships <= 1 and target_user.role != UserRole.superadmin:
            # Delete records where user is required (NOT NULL) - order matters for foreign keys
            await db.execute(delete(DepartmentMember).where(DepartmentMember.user_id == user_id))
            await db.execute(delete(SharedAccess).where(SharedAccess.shared_with_id == user_id))
            await db.execute(delete(SharedAccess).where(SharedAccess.shared_by_id == user_id))
            await db.execute(delete(AnalysisHistory).where(AnalysisHistory.user_id == user_id))
            await db.execute(delete(AIConversation).where(AIConversation.user_id == user_id))

            # Delete orphan records that would be left behind
            await db.execute(delete(ReportSubscription).where(ReportSubscription.user_id == user_id))
            await db.execute(delete(EntityAIConversation).where(EntityAIConversation.user_id == user_id))

            # Nullify optional foreign keys
            await db.execute(update(Chat).where(Chat.owner_id == user_id).values(owner_id=None))
            await db.execute(update(CallRecording).where(CallRecording.owner_id == user_id).values(owner_id=None))
            await db.execute(update(Entity).where(Entity.created_by == user_id).values(created_by=None))
            await db.execute(update(EntityTransfer).where(EntityTransfer.from_user_id == user_id).values(from_user_id=None))
            await db.execute(update(EntityTransfer).where(EntityTransfer.to_user_id == user_id).values(to_user_id=None))
            await db.execute(update(OrgMember).where(OrgMember.invited_by == user_id).values(invited_by=None))
            await db.execute(update(Invitation).where(Invitation.invited_by_id == user_id).values(invited_by_id=None))
            await db.execute(update(Invitation).where(Invitation.used_by_id == user_id).values(used_by_id=None))
            await db.execute(update(CriteriaPreset).where(CriteriaPreset.created_by == user_id).values(created_by=None))

            await db.delete(target_user)
            user_deleted = True

    await db.commit()

    return {"success": True, "user_deleted": user_deleted}


@router.get("/current/my-role")
async def get_my_role(
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db)
):
    """Get current user's role in organization."""
    user = await db.merge(user)
    role = await get_user_org_role(user, org.id, db)
    return {
        "role": role.value if role else None,
        "org_id": org.id,
        "org_name": org.name
    }
