"""
Custom role management endpoints - CRUD operations for custom roles and permission overrides.
"""

from typing import List, Optional
from sqlalchemy import select, delete, case
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from .common import (
    get_db,
    get_superadmin,
    get_current_user,
    User,
    Organization,
    CustomRole,
    RolePermissionOverride,
    UserCustomRole,
    PermissionAuditLog,
    DepartmentMember,
    DeptRole,
    CustomRoleCreate,
    CustomRoleUpdate,
    PermissionOverride,
    CustomRoleResponse,
    PermissionAuditLogResponse,
    EffectivePermissionsResponse,
    get_role_permissions,
)


router = APIRouter()


@router.post("/custom-roles", response_model=CustomRoleResponse)
async def create_custom_role(
    request_body: CustomRoleCreate,
    superadmin: User = Depends(get_superadmin),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new custom role.

    Custom roles inherit permissions from a base role (owner, admin, sub_admin, member)
    and can have specific permission overrides.

    **Only SUPERADMIN can access this endpoint.**
    """
    # Re-fetch superadmin to avoid detached instance issues
    superadmin_result = await db.execute(
        select(User).where(User.id == superadmin.id)
    )
    superadmin = superadmin_result.scalar_one_or_none()
    if not superadmin:
        raise HTTPException(status_code=401, detail="Superadmin not found")

    # Validate base_role
    valid_base_roles = ["owner", "admin", "sub_admin", "member"]
    if request_body.base_role not in valid_base_roles:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid base_role. Must be one of: {', '.join(valid_base_roles)}"
        )

    # If org_id provided, validate it exists
    if request_body.org_id:
        org_result = await db.execute(
            select(Organization).where(Organization.id == request_body.org_id)
        )
        org = org_result.scalar_one_or_none()
        if not org:
            raise HTTPException(
                status_code=404,
                detail=f"Organization with id {request_body.org_id} not found"
            )

    # Create custom role
    custom_role = CustomRole(
        name=request_body.name,
        description=request_body.description,
        base_role=request_body.base_role,
        org_id=request_body.org_id,
        is_active=True
    )
    db.add(custom_role)
    await db.flush()

    # Create audit log entry
    audit_log = PermissionAuditLog(
        role_id=custom_role.id,
        action="create_custom_role",
        changed_by_id=superadmin.id,
        details={
            "name": request_body.name,
            "base_role": request_body.base_role,
            "org_id": request_body.org_id
        }
    )
    db.add(audit_log)

    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Custom role with name '{request_body.name}' already exists"
        )

    # Get base role permissions
    base_permissions = get_role_permissions(request_body.base_role)

    return CustomRoleResponse(
        id=custom_role.id,
        name=custom_role.name,
        description=custom_role.description,
        base_role=custom_role.base_role,
        org_id=custom_role.org_id,
        is_active=custom_role.is_active,
        created_at=custom_role.created_at,
        permissions=base_permissions
    )


@router.get("/custom-roles", response_model=List[CustomRoleResponse])
async def list_custom_roles(
    org_id: Optional[int] = Query(None, description="Filter by organization ID"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    _: User = Depends(get_superadmin),
    db: AsyncSession = Depends(get_db)
):
    """
    List all custom roles with optional filters.

    **Query Parameters:**
    - `org_id` (optional): Filter by organization ID
    - `is_active` (optional): Filter by active status

    **Only SUPERADMIN can access this endpoint.**
    """
    query = select(CustomRole)

    # Apply filters
    if org_id is not None:
        query = query.where(CustomRole.org_id == org_id)
    if is_active is not None:
        query = query.where(CustomRole.is_active == is_active)

    result = await db.execute(query.order_by(CustomRole.created_at.desc()))
    custom_roles = result.scalars().all()

    # Build response with merged permissions
    response = []
    for role in custom_roles:
        # Get base permissions
        base_permissions = get_role_permissions(role.base_role)

        # Get permission overrides
        overrides_result = await db.execute(
            select(RolePermissionOverride)
            .where(RolePermissionOverride.role_id == role.id)
        )
        overrides = overrides_result.scalars().all()

        # Merge permissions
        merged_permissions = base_permissions.copy()
        for override in overrides:
            merged_permissions[override.permission] = override.allowed

        response.append(CustomRoleResponse(
            id=role.id,
            name=role.name,
            description=role.description,
            base_role=role.base_role,
            org_id=role.org_id,
            is_active=role.is_active,
            created_at=role.created_at,
            permissions=merged_permissions
        ))

    return response


@router.get("/custom-roles/{role_id}", response_model=CustomRoleResponse)
async def get_custom_role(
    role_id: int,
    _: User = Depends(get_superadmin),
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific custom role with all merged permissions.

    Returns the custom role with permissions merged from:
    - Base role default permissions
    - Custom permission overrides

    **Only SUPERADMIN can access this endpoint.**
    """
    # Get custom role
    result = await db.execute(
        select(CustomRole).where(CustomRole.id == role_id)
    )
    custom_role = result.scalar_one_or_none()

    if not custom_role:
        raise HTTPException(
            status_code=404,
            detail=f"Custom role with id {role_id} not found"
        )

    # Get base permissions
    base_permissions = get_role_permissions(custom_role.base_role)

    # Get permission overrides
    overrides_result = await db.execute(
        select(RolePermissionOverride)
        .where(RolePermissionOverride.role_id == role_id)
    )
    overrides = overrides_result.scalars().all()

    # Merge permissions
    merged_permissions = base_permissions.copy()
    for override in overrides:
        merged_permissions[override.permission] = override.allowed

    return CustomRoleResponse(
        id=custom_role.id,
        name=custom_role.name,
        description=custom_role.description,
        base_role=custom_role.base_role,
        org_id=custom_role.org_id,
        is_active=custom_role.is_active,
        created_at=custom_role.created_at,
        permissions=merged_permissions
    )


@router.patch("/custom-roles/{role_id}", response_model=CustomRoleResponse)
async def update_custom_role(
    role_id: int,
    request_body: CustomRoleUpdate,
    superadmin: User = Depends(get_superadmin),
    db: AsyncSession = Depends(get_db)
):
    """
    Update a custom role's basic information.

    Can update:
    - Name
    - Description
    - Active status

    **Only SUPERADMIN can access this endpoint.**
    """
    # Re-fetch superadmin to avoid detached instance issues
    superadmin_result = await db.execute(
        select(User).where(User.id == superadmin.id)
    )
    superadmin = superadmin_result.scalar_one_or_none()
    if not superadmin:
        raise HTTPException(status_code=401, detail="Superadmin not found")

    # Get custom role
    result = await db.execute(
        select(CustomRole).where(CustomRole.id == role_id)
    )
    custom_role = result.scalar_one_or_none()

    if not custom_role:
        raise HTTPException(
            status_code=404,
            detail=f"Custom role with id {role_id} not found"
        )

    # Track changes for audit log
    changes = {}

    # Update fields
    if request_body.name is not None:
        changes["name"] = {"old": custom_role.name, "new": request_body.name}
        custom_role.name = request_body.name

    if request_body.description is not None:
        changes["description"] = {"old": custom_role.description, "new": request_body.description}
        custom_role.description = request_body.description

    if request_body.is_active is not None:
        changes["is_active"] = {"old": custom_role.is_active, "new": request_body.is_active}
        custom_role.is_active = request_body.is_active

    # Create audit log entry
    audit_log = PermissionAuditLog(
        role_id=role_id,
        action="update_custom_role",
        changed_by_id=superadmin.id,
        details={"changes": changes}
    )
    db.add(audit_log)
    await db.commit()

    # Get merged permissions for response
    base_permissions = get_role_permissions(custom_role.base_role)
    overrides_result = await db.execute(
        select(RolePermissionOverride)
        .where(RolePermissionOverride.role_id == role_id)
    )
    overrides = overrides_result.scalars().all()
    merged_permissions = base_permissions.copy()
    for override in overrides:
        merged_permissions[override.permission] = override.allowed

    return CustomRoleResponse(
        id=custom_role.id,
        name=custom_role.name,
        description=custom_role.description,
        base_role=custom_role.base_role,
        org_id=custom_role.org_id,
        is_active=custom_role.is_active,
        created_at=custom_role.created_at,
        permissions=merged_permissions
    )


@router.delete("/custom-roles/{role_id}")
async def delete_custom_role(
    role_id: int,
    superadmin: User = Depends(get_superadmin),
    db: AsyncSession = Depends(get_db)
):
    """
    Soft delete a custom role (set is_active=False).

    This will not delete the role from the database, but will make it
    inactive and prevent it from being assigned to new users.

    **Only SUPERADMIN can access this endpoint.**
    """
    # Re-fetch superadmin to avoid detached instance issues
    superadmin_result = await db.execute(
        select(User).where(User.id == superadmin.id)
    )
    superadmin = superadmin_result.scalar_one_or_none()
    if not superadmin:
        raise HTTPException(status_code=401, detail="Superadmin not found")

    # Get custom role
    result = await db.execute(
        select(CustomRole).where(CustomRole.id == role_id)
    )
    custom_role = result.scalar_one_or_none()

    if not custom_role:
        raise HTTPException(
            status_code=404,
            detail=f"Custom role with id {role_id} not found"
        )

    # Soft delete
    custom_role.is_active = False

    # Create audit log entry
    audit_log = PermissionAuditLog(
        role_id=role_id,
        action="delete_custom_role",
        changed_by_id=superadmin.id,
        details={"role_name": custom_role.name}
    )
    db.add(audit_log)
    await db.commit()

    return {
        "message": f"Custom role '{custom_role.name}' has been deactivated",
        "role_id": role_id,
        "is_active": False
    }


@router.post("/custom-roles/{role_id}/permissions")
async def add_permission_override(
    role_id: int,
    request_body: PermissionOverride,
    superadmin: User = Depends(get_superadmin),
    db: AsyncSession = Depends(get_db)
):
    """
    Add or update a permission override for a custom role.

    This allows you to grant or deny specific permissions that differ
    from the base role's default permissions.

    **Only SUPERADMIN can access this endpoint.**
    """
    # Re-fetch superadmin to avoid detached instance issues
    superadmin_result = await db.execute(
        select(User).where(User.id == superadmin.id)
    )
    superadmin = superadmin_result.scalar_one_or_none()
    if not superadmin:
        raise HTTPException(status_code=401, detail="Superadmin not found")

    # Get custom role
    result = await db.execute(
        select(CustomRole).where(CustomRole.id == role_id)
    )
    custom_role = result.scalar_one_or_none()

    if not custom_role:
        raise HTTPException(
            status_code=404,
            detail=f"Custom role with id {role_id} not found"
        )

    # Validate permission key exists in base permissions
    base_permissions = get_role_permissions(custom_role.base_role)
    if request_body.permission not in base_permissions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid permission key: {request_body.permission}. "
                   f"Valid permissions: {', '.join(base_permissions.keys())}"
        )

    # Check if override already exists
    override_result = await db.execute(
        select(RolePermissionOverride)
        .where(RolePermissionOverride.role_id == role_id)
        .where(RolePermissionOverride.permission == request_body.permission)
    )
    existing_override = override_result.scalar_one_or_none()

    if existing_override:
        # Update existing override
        old_value = existing_override.allowed
        existing_override.allowed = request_body.allowed
        action = "update_permission_override"
    else:
        # Create new override
        new_override = RolePermissionOverride(
            role_id=role_id,
            permission=request_body.permission,
            allowed=request_body.allowed
        )
        db.add(new_override)
        old_value = base_permissions.get(request_body.permission)
        action = "add_permission_override"

    # Create audit log entry
    audit_log = PermissionAuditLog(
        role_id=role_id,
        action=action,
        changed_by_id=superadmin.id,
        details={
            "permission": request_body.permission,
            "old_value": old_value,
            "new_value": request_body.allowed
        }
    )
    db.add(audit_log)
    await db.commit()

    return {
        "message": f"Permission '{request_body.permission}' override {'updated' if existing_override else 'added'}",
        "role_id": role_id,
        "permission": request_body.permission,
        "allowed": request_body.allowed
    }


@router.delete("/custom-roles/{role_id}/permissions/{permission}")
async def remove_permission_override(
    role_id: int,
    permission: str,
    superadmin: User = Depends(get_superadmin),
    db: AsyncSession = Depends(get_db)
):
    """
    Remove a permission override from a custom role.

    This will revert the permission back to the base role's default value.

    **Only SUPERADMIN can access this endpoint.**
    """
    # Re-fetch superadmin to avoid detached instance issues
    superadmin_result = await db.execute(
        select(User).where(User.id == superadmin.id)
    )
    superadmin = superadmin_result.scalar_one_or_none()
    if not superadmin:
        raise HTTPException(status_code=401, detail="Superadmin not found")

    # Get custom role
    role_result = await db.execute(
        select(CustomRole).where(CustomRole.id == role_id)
    )
    custom_role = role_result.scalar_one_or_none()

    if not custom_role:
        raise HTTPException(
            status_code=404,
            detail=f"Custom role with id {role_id} not found"
        )

    # Get permission override
    override_result = await db.execute(
        select(RolePermissionOverride)
        .where(RolePermissionOverride.role_id == role_id)
        .where(RolePermissionOverride.permission == permission)
    )
    override = override_result.scalar_one_or_none()

    if not override:
        raise HTTPException(
            status_code=404,
            detail=f"Permission override '{permission}' not found for role {role_id}"
        )

    # Store old value for audit log
    old_value = override.allowed

    # Delete override
    await db.execute(
        delete(RolePermissionOverride)
        .where(RolePermissionOverride.id == override.id)
    )

    # Get base permission value
    base_permissions = get_role_permissions(custom_role.base_role)
    base_value = base_permissions.get(permission)

    # Create audit log entry
    audit_log = PermissionAuditLog(
        role_id=role_id,
        action="remove_permission_override",
        changed_by_id=superadmin.id,
        details={
            "permission": permission,
            "old_value": old_value,
            "reverted_to": base_value
        }
    )
    db.add(audit_log)
    await db.commit()

    return {
        "message": f"Permission override '{permission}' removed. Reverted to base role default.",
        "role_id": role_id,
        "permission": permission,
        "reverted_to": base_value
    }


@router.post("/custom-roles/{role_id}/assign/{user_id}")
async def assign_custom_role_to_user(
    role_id: int,
    user_id: int,
    superadmin: User = Depends(get_superadmin),
    db: AsyncSession = Depends(get_db)
):
    """
    Assign a custom role to a user.

    This creates a UserCustomRole relationship between the user and the custom role.

    **Only SUPERADMIN can access this endpoint.**
    """
    # Re-fetch superadmin to avoid detached instance issues
    superadmin_result = await db.execute(
        select(User).where(User.id == superadmin.id)
    )
    superadmin = superadmin_result.scalar_one_or_none()
    if not superadmin:
        raise HTTPException(status_code=401, detail="Superadmin not found")

    # Get custom role
    role_result = await db.execute(
        select(CustomRole).where(CustomRole.id == role_id)
    )
    custom_role = role_result.scalar_one_or_none()

    if not custom_role:
        raise HTTPException(
            status_code=404,
            detail=f"Custom role with id {role_id} not found"
        )

    if not custom_role.is_active:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot assign inactive custom role '{custom_role.name}'"
        )

    # Get user
    user_result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = user_result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=404,
            detail=f"User with id {user_id} not found"
        )

    # Check if already assigned
    existing_result = await db.execute(
        select(UserCustomRole)
        .where(UserCustomRole.user_id == user_id)
        .where(UserCustomRole.role_id == role_id)
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"User {user.name} already has custom role '{custom_role.name}' assigned"
        )

    # Create assignment
    assignment = UserCustomRole(
        user_id=user_id,
        role_id=role_id
    )
    db.add(assignment)

    # Create audit log entry
    audit_log = PermissionAuditLog(
        role_id=role_id,
        user_id=user_id,
        action="assign_custom_role",
        changed_by_id=superadmin.id,
        details={
            "user_name": user.name,
            "user_email": user.email,
            "role_name": custom_role.name
        }
    )
    db.add(audit_log)
    await db.commit()

    return {
        "message": f"Custom role '{custom_role.name}' assigned to user {user.name}",
        "role_id": role_id,
        "user_id": user_id,
        "user_name": user.name,
        "role_name": custom_role.name
    }


@router.delete("/custom-roles/{role_id}/assign/{user_id}")
async def remove_custom_role_from_user(
    role_id: int,
    user_id: int,
    superadmin: User = Depends(get_superadmin),
    db: AsyncSession = Depends(get_db)
):
    """
    Remove a custom role from a user.

    This deletes the UserCustomRole relationship between the user and the custom role.

    **Only SUPERADMIN can access this endpoint.**
    """
    # Re-fetch superadmin to avoid detached instance issues
    superadmin_result = await db.execute(
        select(User).where(User.id == superadmin.id)
    )
    superadmin = superadmin_result.scalar_one_or_none()
    if not superadmin:
        raise HTTPException(status_code=401, detail="Superadmin not found")

    # Get custom role
    role_result = await db.execute(
        select(CustomRole).where(CustomRole.id == role_id)
    )
    custom_role = role_result.scalar_one_or_none()

    if not custom_role:
        raise HTTPException(
            status_code=404,
            detail=f"Custom role with id {role_id} not found"
        )

    # Get user
    user_result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = user_result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=404,
            detail=f"User with id {user_id} not found"
        )

    # Get assignment
    assignment_result = await db.execute(
        select(UserCustomRole)
        .where(UserCustomRole.user_id == user_id)
        .where(UserCustomRole.role_id == role_id)
    )
    assignment = assignment_result.scalar_one_or_none()

    if not assignment:
        raise HTTPException(
            status_code=404,
            detail=f"User {user.name} does not have custom role '{custom_role.name}' assigned"
        )

    # Delete assignment
    await db.execute(
        delete(UserCustomRole).where(UserCustomRole.id == assignment.id)
    )

    # Create audit log entry
    audit_log = PermissionAuditLog(
        role_id=role_id,
        user_id=user_id,
        action="remove_custom_role",
        changed_by_id=superadmin.id,
        details={
            "user_name": user.name,
            "user_email": user.email,
            "role_name": custom_role.name
        }
    )
    db.add(audit_log)
    await db.commit()

    return {
        "message": f"Custom role '{custom_role.name}' removed from user {user.name}",
        "role_id": role_id,
        "user_id": user_id,
        "user_name": user.name,
        "role_name": custom_role.name
    }


@router.get("/permission-audit-logs", response_model=List[PermissionAuditLogResponse])
async def get_permission_audit_logs(
    role_id: Optional[int] = Query(None, description="Filter by custom role ID"),
    changed_by: Optional[int] = Query(None, description="Filter by user who made the change"),
    limit: int = Query(100, description="Maximum number of logs to return"),
    offset: int = Query(0, description="Number of logs to skip"),
    _: User = Depends(get_superadmin),
    db: AsyncSession = Depends(get_db)
):
    """
    Get audit trail for custom roles and permission changes.

    Returns a log of all changes made to custom roles, including:
    - Role creation/updates/deletions
    - Permission overrides added/removed
    - Role assignments to users

    **Query Parameters:**
    - `role_id` (optional): Filter by custom role ID
    - `changed_by` (optional): Filter by user ID who made the change
    - `limit`: Maximum number of logs to return (default: 100)
    - `offset`: Number of logs to skip (default: 0)

    **Only SUPERADMIN can access this endpoint.**
    """
    query = select(PermissionAuditLog)

    # Apply filters
    if role_id is not None:
        query = query.where(PermissionAuditLog.role_id == role_id)
    if changed_by is not None:
        query = query.where(PermissionAuditLog.changed_by_id == changed_by)

    # Order by most recent first
    query = query.order_by(PermissionAuditLog.created_at.desc())

    # Apply pagination
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    logs = result.scalars().all()

    # Build response with user information
    response = []
    for log in logs:
        # Get user who made the change
        user_result = await db.execute(
            select(User).where(User.id == log.changed_by_id)
        )
        user = user_result.scalar_one_or_none()

        response.append(PermissionAuditLogResponse(
            id=log.id,
            custom_role_id=log.role_id,
            user_id=log.user_id,
            action=log.action,
            changed_by_id=log.changed_by_id,
            changed_by_name=user.name if user else "Unknown",
            changed_by_email=user.email if user else "Unknown",
            details=log.details,
            created_at=log.created_at
        ))

    return response


@router.get("/me/permissions", response_model=EffectivePermissionsResponse)
async def get_my_permissions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get the current user's effective permissions.

    Returns the merged permissions from custom role (if assigned) or default role permissions.
    This endpoint is used by the frontend to dynamically show/hide UI elements.
    """
    # Check if user has custom role
    custom_role_query = await db.execute(
        select(UserCustomRole, CustomRole)
        .join(CustomRole, CustomRole.id == UserCustomRole.role_id)
        .where(
            UserCustomRole.user_id == current_user.id,
            CustomRole.is_active == True
        )
        .order_by(UserCustomRole.assigned_at.desc())
        .limit(1)
    )
    custom_role_result = custom_role_query.first()

    if custom_role_result:
        user_custom_role, custom_role = custom_role_result

        # Get base permissions from the custom role's base_role
        base_permissions = get_role_permissions(custom_role.base_role)

        # Get permission overrides
        overrides_query = await db.execute(
            select(RolePermissionOverride)
            .where(RolePermissionOverride.role_id == custom_role.id)
        )
        overrides = overrides_query.scalars().all()

        # Merge overrides into base permissions
        permissions = base_permissions.copy()
        for override in overrides:
            permissions[override.permission] = override.allowed

        return EffectivePermissionsResponse(
            permissions=permissions,
            source="custom_role",
            custom_role_id=custom_role.id,
            custom_role_name=custom_role.name,
            base_role=custom_role.base_role
        )

    # No custom role - use standard role permissions
    user_role = current_user.role.value if current_user.role else "member"
    effective_role = user_role
    source = "user_role"

    # For users with basic "member" role, check if they have elevated department role
    # Don't override superadmin/admin/sub_admin - they already have high permissions
    if user_role == "member":
        # Check if user is a department lead/sub_admin
        dept_member_query = await db.execute(
            select(DepartmentMember)
            .where(DepartmentMember.user_id == current_user.id)
            .order_by(
                # Proper priority: lead=1, sub_admin=2, member=3
                # Use enum values for proper PostgreSQL enum comparison
                case(
                    (DepartmentMember.role == DeptRole.lead, 1),
                    (DepartmentMember.role == DeptRole.sub_admin, 2),
                    else_=3
                )
            )
            .limit(1)
        )
        dept_member = dept_member_query.scalar_one_or_none()

        if dept_member and dept_member.role:
            dept_role = dept_member.role.value if hasattr(dept_member.role, 'value') else dept_member.role
            # Department roles (lead, sub_admin) can override member role
            if dept_role in ["lead", "sub_admin"]:
                effective_role = dept_role
                source = "dept_role"

    permissions = get_role_permissions(effective_role)

    return EffectivePermissionsResponse(
        permissions=permissions,
        source=source,
        custom_role_id=None,
        custom_role_name=None,
        base_role=effective_role
    )
