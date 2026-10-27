"""
Invitation Management Routes.

Provides:
- POST /invitations - Create invitation link (admin/owner only)
- GET /invitations - List organization invitations
- GET /invitations/validate/{token} - Validate invitation (public)
- POST /invitations/accept/{token} - Accept invitation and register (public)
- DELETE /invitations/{id} - Revoke invitation
"""
import secrets
from typing import List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from pydantic import BaseModel, EmailStr

from ..database import get_db
from ..limiter import PUBLIC_TOKEN_LIMIT, limiter
from ..models.database import (
    User, UserRole, Organization, OrgMember, OrgRole,
    Department, DepartmentMember, DeptRole, Invitation, Employee
)
from ..services.auth import get_current_user, hash_password, verify_password, create_access_token
from .organizations import get_current_org, require_org_admin
from ..config import settings

router = APIRouter()


async def require_invitation_access(
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db)
) -> tuple:
    """Require user to be org admin/owner OR department lead.

    Returns: (user, org, org_role, is_dept_lead, user_dept_ids)
    """
    user = await db.merge(user)

    # Superadmin bypasses all checks
    if user.role == UserRole.superadmin:
        return user, org, OrgRole.owner, True, set()

    # Get user's org role
    from ..services.auth import get_user_org_role
    org_role = await get_user_org_role(user, org.id, db)

    # Get user's department memberships with roles — только отделы ЭТОЙ
    # организации: лид отдела в другой организации раньше получал право
    # приглашать сюда (до 27.10.2026).
    result = await db.execute(
        select(DepartmentMember)
        .join(Department, Department.id == DepartmentMember.department_id)
        .where(DepartmentMember.user_id == user.id, Department.org_id == org.id)
    )
    dept_memberships = result.scalars().all()
    user_dept_ids = {dm.department_id for dm in dept_memberships}

    # Check if user is lead/sub_admin in any department
    # Use enum comparison since dm.role comes from DB as DeptRole enum
    is_dept_lead = any(dm.role in (DeptRole.lead, DeptRole.sub_admin) for dm in dept_memberships)

    # Allow org owner, org admin, OR department lead/sub_admin
    if org_role in ("owner", "admin"):
        return user, org, org_role, is_dept_lead, user_dept_ids

    if is_dept_lead:
        return user, org, org_role, is_dept_lead, user_dept_ids

    raise HTTPException(status_code=403, detail="Admin or department lead access required")


# Schemas
class InvitationCreate(BaseModel):
    email: Optional[EmailStr] = None
    name: Optional[str] = None
    org_role: str = "member"  # owner, admin, member
    department_ids: Optional[List[dict]] = None  # [{"id": 1, "role": "member"}]
    expires_in_days: int = 7  # 0 = never expires


class InvitationResponse(BaseModel):
    id: int
    token: str
    email: Optional[str]
    name: Optional[str]
    org_role: str
    department_ids: List[dict]
    invited_by_name: Optional[str] = None
    expires_at: Optional[datetime]
    used_at: Optional[datetime]
    used_by_name: Optional[str] = None
    created_at: datetime
    invitation_url: str

    class Config:
        from_attributes = True


class InvitationValidateResponse(BaseModel):
    valid: bool
    expired: bool = False
    used: bool = False
    email: Optional[str] = None
    name: Optional[str] = None
    org_name: Optional[str] = None
    org_role: str = "member"


class AcceptInvitationRequest(BaseModel):
    email: EmailStr
    name: str
    password: str


class AcceptInvitationResponse(BaseModel):
    success: bool
    access_token: str
    user_id: int
    telegram_bind_url: Optional[str] = None


def generate_token() -> str:
    """Generate a secure random token."""
    return secrets.token_urlsafe(32)


@router.post("", response_model=InvitationResponse)
async def create_invitation(
    data: InvitationCreate,
    db: AsyncSession = Depends(get_db),
    auth: tuple = Depends(require_invitation_access)
):
    """Create an invitation link for a new user.

    Permissions:
    - Org owner: can invite to any department with any org role
    - Org admin: can invite to their departments with member org role
    - Department lead/sub_admin: can invite to their departments with member org role
    """
    user, org, role, is_dept_lead, user_dept_ids = auth

    # Validate org role for invitation
    try:
        invite_org_role = OrgRole(data.org_role)
    except ValueError:
        invite_org_role = OrgRole.member

    # Only owner can create owner/admin invites
    if invite_org_role in ("owner", "admin") and role != "owner":
        raise HTTPException(status_code=403, detail="Only owner can create owner/admin invitations")
    # Роль рекрутёра (доступ к кандидатам и воронкам) выдают только owner/admin.
    # Лид отдела с ролью «сотрудник» раньше приглашал с org_role=hr и сам
    # принимал приглашение на второй адрес — получал HR-доступ (до 27.10.2026).
    if invite_org_role == OrgRole.hr and role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Роль рекрутёра выдаёт только администратор")

    # Роль в отделе — не выше своей: лид выдаёт саб-админа и сотрудника,
    # саб-админ — только сотрудника; owner/admin — любую.
    if role not in ("owner", "admin") and data.department_ids:
        my_dept_roles = {
            dm.department_id: dm.role for dm in (await db.execute(
                select(DepartmentMember).where(DepartmentMember.user_id == user.id)
            )).scalars().all()
        }
        rank = {DeptRole.member: 0, DeptRole.sub_admin: 1, DeptRole.lead: 2}
        for dept_info in data.department_ids:
            try:
                wanted = DeptRole(dept_info.get("role", "member"))
            except ValueError:
                wanted = DeptRole.member
            mine = my_dept_roles.get(dept_info.get("id"))
            if mine is None or rank[wanted] >= rank.get(mine, 0):
                raise HTTPException(status_code=403, detail="Нельзя выдать в отделе роль не ниже своей")

    # Срок: бессрочное приглашение — только владельцу; иначе 1–90 дней
    # (огромное число давало OverflowError → 500, отрицательное — бессрочное).
    if data.expires_in_days < 0 or data.expires_in_days > 90:
        raise HTTPException(status_code=400, detail="Срок приглашения — от 1 до 90 дней")
    if data.expires_in_days == 0 and role != "owner":
        raise HTTPException(status_code=403, detail="Бессрочное приглашение может создать только владелец")

    # Check if email is already a member of the organization
    if data.email:
        result = await db.execute(select(User).where(User.email == data.email))
        existing_user = result.scalar_one_or_none()
        if existing_user:
            result = await db.execute(
                select(OrgMember).where(
                    OrgMember.org_id == org.id,
                    OrgMember.user_id == existing_user.id
                )
            )
            if result.scalar_one_or_none():
                raise HTTPException(status_code=400, detail="User is already a member of this organization")

    # Non-owners can only invite to their own departments
    if role != "owner" and data.department_ids:
        for dept_info in data.department_ids:
            dept_id = dept_info.get("id")
            if dept_id and dept_id not in user_dept_ids:
                raise HTTPException(
                    status_code=403,
                    detail=f"You can only invite to departments you belong to"
                )

    # Department leads (not org admins) MUST specify at least one department
    if role not in ("owner", "admin") and is_dept_lead:
        if not data.department_ids:
            raise HTTPException(
                status_code=400,
                detail="Department leads must specify at least one department for the invitation"
            )

    # Generate token
    token = generate_token()

    # Calculate expiration
    expires_at = None
    if data.expires_in_days > 0:
        expires_at = datetime.utcnow() + timedelta(days=data.expires_in_days)

    # Create invitation
    invitation = Invitation(
        token=token,
        org_id=org.id,
        email=data.email,
        name=data.name,
        org_role=invite_org_role,
        department_ids=data.department_ids or [],
        invited_by_id=user.id,
        expires_at=expires_at
    )
    db.add(invitation)
    await db.commit()
    await db.refresh(invitation)

    # Build invitation URL (frontend will handle this)
    invitation_url = f"/invite/{token}"

    return InvitationResponse(
        id=invitation.id,
        token=invitation.token,
        email=invitation.email,
        name=invitation.name,
        org_role=invitation.org_role.value,
        department_ids=invitation.department_ids or [],
        invited_by_name=user.name,
        expires_at=invitation.expires_at,
        used_at=invitation.used_at,
        created_at=invitation.created_at,
        invitation_url=invitation_url
    )


@router.get("", response_model=List[InvitationResponse])
async def list_invitations(
    include_used: bool = False,
    db: AsyncSession = Depends(get_db),
    auth: tuple = Depends(require_invitation_access)
):
    """List invitations for current organization.

    Owner sees all, admin/lead sees only their own invitations.
    """
    user, org, role, is_dept_lead, user_dept_ids = auth

    query = select(Invitation).where(Invitation.org_id == org.id)

    # Non-owners can only see invitations they created
    if role != "owner":
        query = query.where(Invitation.invited_by_id == user.id)

    if not include_used:
        query = query.where(Invitation.used_at.is_(None))

    query = query.order_by(Invitation.created_at.desc())

    result = await db.execute(query)
    invitations = result.scalars().all()

    # Pre-fetch invited_by and used_by names
    user_ids = set()
    for inv in invitations:
        if inv.invited_by_id:
            user_ids.add(inv.invited_by_id)
        if inv.used_by_id:
            user_ids.add(inv.used_by_id)

    user_names = {}
    if user_ids:
        users_result = await db.execute(select(User).where(User.id.in_(user_ids)))
        for u in users_result.scalars().all():
            user_names[u.id] = u.name

    return [
        InvitationResponse(
            id=inv.id,
            token=inv.token,
            email=inv.email,
            name=inv.name,
            org_role=inv.org_role.value,
            department_ids=inv.department_ids or [],
            invited_by_name=user_names.get(inv.invited_by_id),
            expires_at=inv.expires_at,
            used_at=inv.used_at,
            used_by_name=user_names.get(inv.used_by_id),
            created_at=inv.created_at,
            invitation_url=f"/invite/{inv.token}"
        )
        for inv in invitations
    ]


@router.get("/validate/{token}", response_model=InvitationValidateResponse)
@limiter.limit(PUBLIC_TOKEN_LIMIT)
async def validate_invitation(
    request: Request,
    token: str,
    db: AsyncSession = Depends(get_db)
):
    """Validate an invitation token (public endpoint)."""
    result = await db.execute(
        select(Invitation)
        .options(selectinload(Invitation.organization))
        .where(Invitation.token == token)
    )
    invitation = result.scalar_one_or_none()

    if not invitation:
        return InvitationValidateResponse(valid=False)

    # Check if already used
    if invitation.used_at:
        return InvitationValidateResponse(
            valid=False,
            used=True,
            org_name=invitation.organization.name if invitation.organization else None
        )

    # Check if expired
    if invitation.expires_at and datetime.utcnow() > invitation.expires_at:
        return InvitationValidateResponse(
            valid=False,
            expired=True,
            org_name=invitation.organization.name if invitation.organization else None
        )

    return InvitationValidateResponse(
        valid=True,
        email=invitation.email,
        name=invitation.name,
        org_name=invitation.organization.name if invitation.organization else None,
        org_role=invitation.org_role.value
    )


@router.post("/accept/{token}", response_model=AcceptInvitationResponse)
@limiter.limit(PUBLIC_TOKEN_LIMIT)
async def accept_invitation(
    request: Request,
    token: str,
    data: AcceptInvitationRequest,
    db: AsyncSession = Depends(get_db)
):
    """Accept an invitation and create user account (public endpoint)."""
    # Wrap in explicit transaction with optimistic locking to prevent race conditions
    async with db.begin_nested():
        # Get invitation with row lock to prevent concurrent accepts
        result = await db.execute(
            select(Invitation)
            .options(selectinload(Invitation.organization))
            .where(Invitation.token == token)
            .with_for_update()  # Lock the row to prevent concurrent access
        )
        invitation = result.scalar_one_or_none()

        if not invitation:
            raise HTTPException(status_code=404, detail="Invitation not found")

        # Check if already used
        if invitation.used_at:
            raise HTTPException(status_code=400, detail="Invitation already used")

        # Check if expired
        if invitation.expires_at and datetime.utcnow() > invitation.expires_at:
            raise HTTPException(status_code=400, detail="Invitation expired")

        # Приглашение на конкретный адрес принимается только этим адресом. Раньше
        # email из формы не сверялся: по любой ссылке можно было «принять» её на
        # чужой адрес.
        if invitation.email and invitation.email.strip().lower() != data.email.strip().lower():
            raise HTTPException(
                status_code=400,
                detail="Приглашение выписано на другой email",
            )

        # Check if email already exists
        result = await db.execute(select(User).where(User.email == data.email))
        existing_user = result.scalar_one_or_none()

        if existing_user:
            # Существующий аккаунт — только с его паролем. Без этой проверки ответ
            # отдавал токен входа и ссылку привязки Telegram от ЧУЖОГО аккаунта
            # любому, у кого есть ссылка приглашения (захват аккаунта).
            if not existing_user.password_hash or not verify_password(
                data.password, existing_user.password_hash
            ):
                raise HTTPException(
                    status_code=401,
                    detail="Этот email уже зарегистрирован — введите пароль от своего аккаунта",
                )
            # Check if already a member of this org
            result = await db.execute(
                select(OrgMember).where(
                    OrgMember.org_id == invitation.org_id,
                    OrgMember.user_id == existing_user.id
                )
            )
            if result.scalar_one_or_none():
                raise HTTPException(status_code=400, detail="You are already a member of this organization")

            # Add existing user to org
            new_user = existing_user
        else:
            if len(data.password or "") < 8:
                raise HTTPException(status_code=400, detail="Пароль должен быть не короче 8 символов")
            if not (data.name or "").strip() or len(data.name) > 255:
                raise HTTPException(status_code=400, detail="Укажите имя (до 255 символов)")
            # Create new user with member role (access determined by OrgRole and DeptRole)
            new_user = User(
                email=data.email,
                password_hash=hash_password(data.password),
                name=data.name,
                role=UserRole.member  # Regular user - access via OrgMember/DeptMember
            )
            db.add(new_user)
            await db.flush()

        # Create organization membership
        membership = OrgMember(
            org_id=invitation.org_id,
            user_id=new_user.id,
            role=invitation.org_role,
            invited_by=invitation.invited_by_id
        )
        db.add(membership)

        # Add to departments if specified
        if invitation.department_ids:
            for dept_info in invitation.department_ids:
                dept_id = dept_info.get("id")
                dept_role_str = dept_info.get("role", "member")

                try:
                    dept_role = DeptRole(dept_role_str)
                except ValueError:
                    dept_role = DeptRole.member

                # Verify department belongs to org
                result = await db.execute(
                    select(Department).where(
                        Department.id == dept_id,
                        Department.org_id == invitation.org_id
                    )
                )
                dept = result.scalar_one_or_none()
                if dept:
                    dept_membership = DepartmentMember(
                        department_id=dept_id,
                        user_id=new_user.id,
                        role=dept_role
                    )
                    db.add(dept_membership)

        # Create Employee (HR card) for the new user — required by the Factorial module
        existing_emp = await db.execute(select(Employee).where(Employee.user_id == new_user.id))
        if existing_emp.scalar_one_or_none() is None:
            db.add(Employee(user_id=new_user.id, org_id=invitation.org_id))

        # Mark invitation as used
        invitation.used_at = datetime.utcnow()
        invitation.used_by_id = new_user.id
        await db.flush()

    # Одноразовый токен привязки Telegram. Раньше ссылка была вида
    # `?start=bind_<user_id>` — сырой идентификатор без всякой проверки, так что
    # любой человек мог написать боту «/start bind_1» и забрать чужой аккаунт.
    # Момент принятия приглашения — законный повод выдать токен: человек только
    # что доказал, что владеет инвайтом.
    import secrets as _secrets
    _bind_token = _secrets.token_urlsafe(32)
    new_user.telegram_bind_token = _bind_token
    # Сутки, а не 15 минут: приглашение принимают с компьютера, а к боту идут
    # потом с телефона — короткий срок ломал бы обычный сценарий найма.
    new_user.telegram_bind_expires = datetime.utcnow() + timedelta(hours=24)

    await db.commit()

    # Generate JWT token
    # token_version в токене — иначе смена пароля не отзывала бы этот токен.
    access_token = create_access_token({
        "sub": str(new_user.id),
        "token_version": new_user.token_version or 0,
    })

    # Deep link с одноразовым токеном (см. handle_bind_token в bot.py)
    telegram_bot_username = (settings.telegram_bot_username or "enceladus_mst_bot").lstrip("@")
    telegram_bind_url = f"https://t.me/{telegram_bot_username}?start={_bind_token}"

    return AcceptInvitationResponse(
        success=True,
        access_token=access_token,
        user_id=new_user.id,
        telegram_bind_url=telegram_bind_url
    )


@router.delete("/{invitation_id}")
async def revoke_invitation(
    invitation_id: int,
    db: AsyncSession = Depends(get_db),
    auth: tuple = Depends(require_invitation_access)
):
    """Revoke/delete an invitation.

    Owner can revoke any, admin/lead can only revoke their own invitations.
    """
    user, org, role, is_dept_lead, user_dept_ids = auth

    result = await db.execute(
        select(Invitation).where(
            Invitation.id == invitation_id,
            Invitation.org_id == org.id
        )
    )
    invitation = result.scalar_one_or_none()

    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found")

    # Admin can only revoke their own invitations
    if role != "owner" and invitation.invited_by_id != user.id:
        raise HTTPException(status_code=403, detail="You can only revoke your own invitations")

    await db.delete(invitation)
    await db.commit()

    return {"success": True}
