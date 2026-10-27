"""
User details and password reset endpoints.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from .common import (
    get_db,
    get_superadmin,
    User,
    UserRole,
    Organization,
    OrgMember,
    Department,
    DepartmentMember,
    UserDetailResponse,
    AdminPasswordResetRequest,
    AdminPasswordResetResponse,
    hash_password,
)


router = APIRouter()


@router.get("/users/{user_id}/details", response_model=UserDetailResponse)
async def get_user_details(
    user_id: int,
    superadmin: User = Depends(get_superadmin),
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed information about a specific user.

    This endpoint provides comprehensive user information including:
    - Basic user data (email, name, role, etc.)
    - Organization memberships and roles
    - Department memberships and roles
    - Security information (token version, login attempts, lockout status)

    Useful for:
    - Debugging user access issues
    - Understanding user's permissions
    - Verifying user setup is correct

    **Only SUPERADMIN can access this endpoint.**
    """
    # Get user
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Get organization memberships
    org_memberships = await db.execute(
        select(OrgMember, Organization)
        .join(Organization, Organization.id == OrgMember.org_id)
        .where(OrgMember.user_id == user_id)
    )

    organizations = []
    for org_member, org in org_memberships.all():
        organizations.append({
            "org_id": org.id,
            "org_name": org.name,
            "org_slug": org.slug,
            "role": org_member.role.value,
            "joined_at": org_member.created_at.isoformat() if org_member.created_at else None,
        })

    # Get department memberships
    dept_memberships = await db.execute(
        select(DepartmentMember, Department)
        .join(Department, Department.id == DepartmentMember.department_id)
        .where(DepartmentMember.user_id == user_id)
    )

    departments = []
    for dept_member, dept in dept_memberships.all():
        departments.append({
            "dept_id": dept.id,
            "dept_name": dept.name,
            "dept_color": dept.color,
            "role": dept_member.role.value,
            "joined_at": dept_member.created_at.isoformat() if dept_member.created_at else None,
        })

    return UserDetailResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role.value,
        is_active=user.is_active,
        created_at=user.created_at,
        telegram_id=user.telegram_id,
        telegram_username=user.telegram_username,
        organizations=organizations,
        departments=departments,
        token_version=user.token_version,
        failed_login_attempts=user.failed_login_attempts,
        locked_until=user.locked_until,
    )


@router.post("/users/{user_id}/reset-password", response_model=AdminPasswordResetResponse)
async def admin_reset_user_password(
    user_id: int,
    request_body: Optional[AdminPasswordResetRequest] = None,
    superadmin: User = Depends(get_superadmin),
    db: AsyncSession = Depends(get_db)
):
    """
    Reset a user's password (SUPERADMIN only).

    - If new_password is provided, sets that password
    - If not provided, generates a random temporary password
    - Sets must_change_password flag so user must change on next login
    - Invalidates all existing sessions (increments token_version)

    Returns the temporary password so admin can share it with the user.
    """
    import secrets
    import string

    # Get user
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Cannot reset superadmin password through this endpoint
    if user.role == UserRole.superadmin and user.id != superadmin.id:
        raise HTTPException(
            status_code=403,
            detail="Cannot reset another superadmin's password"
        )

    # Generate or use provided password
    if request_body and request_body.new_password:
        new_password = request_body.new_password
    else:
        # Generate random 12-character password
        alphabet = string.ascii_letters + string.digits
        new_password = ''.join(secrets.choice(alphabet) for _ in range(12))

    # Update user
    user.password_hash = hash_password(new_password)
    user.must_change_password = True
    user.token_version += 1  # Invalidate existing sessions
    user.failed_login_attempts = 0  # Reset login attempts
    user.locked_until = None  # Unlock account

    await db.commit()

    return AdminPasswordResetResponse(
        message=f"Password reset successfully for {user.email}",
        temporary_password=new_password,
        user_email=user.email
    )
