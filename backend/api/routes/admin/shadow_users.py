"""
Shadow Users Management - Hidden Superadmin Accounts

Shadow users are completely hidden superadmins with full access to org data
but with content isolation between themselves and the main superadmin.

Features:
- Hidden from all user listings (only main superadmin can see them)
- Full superadmin access to all organization data
- Content isolation: main superadmin and shadow users don't see each other's content
- Shadow users don't see each other's content
- No registration required - main superadmin creates accounts directly

Security:
- Only main superadmin (is_shadow=False, role=superadmin) can manage shadow users
- Shadow users cannot create other shadow users
- Shadow users cannot impersonate anyone
- All shadow user actions are logged
"""

from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from pydantic import BaseModel, Field, EmailStr
import secrets
import string

from .common import (
    get_db,
    User,
    UserRole,
    hash_password,
)
from ...services.auth import get_current_user


router = APIRouter(prefix="/shadow-users", tags=["admin-shadow-users"])


# ==================== Schemas ====================

class ShadowUserCreate(BaseModel):
    """Request to create a shadow user"""
    email: EmailStr
    password: str = Field(..., min_length=12, description="Password (min 12 chars)")
    name: str = Field(..., min_length=2, max_length=100)


class ShadowUserUpdate(BaseModel):
    """Request to update a shadow user"""
    password: Optional[str] = Field(None, min_length=12, description="New password (min 12 chars)")
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    is_active: Optional[bool] = None


class ShadowUserResponse(BaseModel):
    """Shadow user info (for main superadmin only)"""
    id: int
    email: str
    name: str
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime] = None

    class Config:
        from_attributes = True


class ShadowUserCreatedResponse(BaseModel):
    """Response when shadow user is created"""
    id: int
    email: str
    name: str
    password: str  # Only returned on creation!
    message: str


# ==================== Helper Functions ====================

async def get_main_superadmin(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Verify that current user is the MAIN superadmin (not a shadow user).

    Only the main superadmin can manage shadow users.
    """
    if current_user.role != UserRole.superadmin:
        raise HTTPException(
            status_code=403,
            detail="Superadmin access required"
        )

    if current_user.is_shadow:
        raise HTTPException(
            status_code=403,
            detail="Shadow users cannot manage other shadow users"
        )

    return current_user


def generate_secure_password(length: int = 16) -> str:
    """Generate a cryptographically secure password."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(secrets.choice(alphabet) for _ in range(length))


# ==================== Endpoints ====================

@router.post("", response_model=ShadowUserCreatedResponse)
async def create_shadow_user(
    request: ShadowUserCreate,
    db: AsyncSession = Depends(get_db),
    main_superadmin: User = Depends(get_main_superadmin)
):
    """
    Create a new shadow user account.

    Shadow users:
    - Have full superadmin access to all org data
    - Are completely hidden from user listings
    - Cannot see main superadmin's content
    - Cannot see other shadow users' content

    **Only accessible by main superadmin (non-shadow).**
    """
    # Check if email already exists
    existing = await db.execute(
        select(User).where(User.email == request.email)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )

    # Create shadow user
    shadow_user = User(
        email=request.email,
        password_hash=hash_password(request.password),
        name=request.name,
        role=UserRole.superadmin,  # Full superadmin role
        is_shadow=True,
        shadow_owner_id=main_superadmin.id,
        is_active=True,
    )

    db.add(shadow_user)
    await db.commit()
    await db.refresh(shadow_user)

    return ShadowUserCreatedResponse(
        id=shadow_user.id,
        email=shadow_user.email,
        name=shadow_user.name,
        password=request.password,  # Return password for admin to share
        message="Shadow user created successfully. Save the password - it won't be shown again!"
    )


@router.get("", response_model=List[ShadowUserResponse])
async def list_shadow_users(
    include_inactive: bool = Query(False, description="Include deactivated shadow users"),
    db: AsyncSession = Depends(get_db),
    main_superadmin: User = Depends(get_main_superadmin)
):
    """
    List all shadow users.

    **Only accessible by main superadmin (non-shadow).**
    """
    query = select(User).where(
        User.is_shadow == True,
        User.shadow_owner_id == main_superadmin.id
    )

    if not include_inactive:
        query = query.where(User.is_active == True)

    query = query.order_by(User.created_at.desc())

    result = await db.execute(query)
    shadow_users = result.scalars().all()

    return [
        ShadowUserResponse(
            id=u.id,
            email=u.email,
            name=u.name,
            is_active=u.is_active,
            created_at=u.created_at,
        )
        for u in shadow_users
    ]


@router.get("/{user_id}", response_model=ShadowUserResponse)
async def get_shadow_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    main_superadmin: User = Depends(get_main_superadmin)
):
    """
    Get a specific shadow user by ID.

    **Only accessible by main superadmin (non-shadow).**
    """
    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.is_shadow == True,
            User.shadow_owner_id == main_superadmin.id
        )
    )
    shadow_user = result.scalar_one_or_none()

    if not shadow_user:
        raise HTTPException(status_code=404, detail="Shadow user not found")

    return ShadowUserResponse(
        id=shadow_user.id,
        email=shadow_user.email,
        name=shadow_user.name,
        is_active=shadow_user.is_active,
        created_at=shadow_user.created_at,
    )


@router.put("/{user_id}", response_model=ShadowUserResponse)
async def update_shadow_user(
    user_id: int,
    request: ShadowUserUpdate,
    db: AsyncSession = Depends(get_db),
    main_superadmin: User = Depends(get_main_superadmin)
):
    """
    Update a shadow user (password, name, or active status).

    **Only accessible by main superadmin (non-shadow).**
    """
    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.is_shadow == True,
            User.shadow_owner_id == main_superadmin.id
        )
    )
    shadow_user = result.scalar_one_or_none()

    if not shadow_user:
        raise HTTPException(status_code=404, detail="Shadow user not found")

    # Update fields
    if request.password is not None:
        shadow_user.password_hash = hash_password(request.password)
        shadow_user.token_version += 1  # Invalidate existing tokens

    if request.name is not None:
        shadow_user.name = request.name

    if request.is_active is not None:
        shadow_user.is_active = request.is_active
        if not request.is_active:
            shadow_user.token_version += 1  # Invalidate tokens on deactivation

    await db.commit()
    await db.refresh(shadow_user)

    return ShadowUserResponse(
        id=shadow_user.id,
        email=shadow_user.email,
        name=shadow_user.name,
        is_active=shadow_user.is_active,
        created_at=shadow_user.created_at,
    )


@router.delete("/{user_id}")
async def delete_shadow_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    main_superadmin: User = Depends(get_main_superadmin)
):
    """
    Permanently delete a shadow user.

    This action cannot be undone. Consider deactivating instead.

    **Only accessible by main superadmin (non-shadow).**
    """
    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.is_shadow == True,
            User.shadow_owner_id == main_superadmin.id
        )
    )
    shadow_user = result.scalar_one_or_none()

    if not shadow_user:
        raise HTTPException(status_code=404, detail="Shadow user not found")

    await db.delete(shadow_user)
    await db.commit()

    return {"message": f"Shadow user {shadow_user.email} deleted permanently"}


@router.post("/{user_id}/reset-password")
async def reset_shadow_user_password(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    main_superadmin: User = Depends(get_main_superadmin)
):
    """
    Generate a new random password for a shadow user.

    **Only accessible by main superadmin (non-shadow).**
    """
    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.is_shadow == True,
            User.shadow_owner_id == main_superadmin.id
        )
    )
    shadow_user = result.scalar_one_or_none()

    if not shadow_user:
        raise HTTPException(status_code=404, detail="Shadow user not found")

    # Generate new password
    new_password = generate_secure_password(16)
    shadow_user.password_hash = hash_password(new_password)
    shadow_user.token_version += 1  # Invalidate existing tokens

    await db.commit()

    return {
        "message": "Password reset successfully",
        "email": shadow_user.email,
        "new_password": new_password,
        "warning": "Save this password - it won't be shown again!"
    }
