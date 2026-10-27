"""
User impersonation endpoints.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import jwt, JWTError

from .common import (
    get_db,
    get_superadmin,
    User,
    UserRole,
    ImpersonationLog,
    ImpersonateRequest,
    ImpersonationLogResponse,
    create_access_token,
    create_impersonation_token,
    settings,
)


router = APIRouter()
security = HTTPBearer()


@router.post("/impersonate")
async def impersonate_user(
    request_body: ImpersonateRequest,
    request: Request,
    superadmin: User = Depends(get_superadmin),
    db: AsyncSession = Depends(get_db)
):
    """
    Impersonate a user as SUPERADMIN.

    Creates a special JWT token with:
    - subject (sub): impersonated user's ID
    - original_user_id: superadmin's ID
    - is_impersonating: true
    - Token expires in 1 hour

    All impersonation sessions are logged for audit purposes.

    **Only SUPERADMIN can access this endpoint.**
    """
    # Re-fetch superadmin to avoid detached instance issues
    superadmin_result = await db.execute(
        select(User).where(User.id == superadmin.id)
    )
    superadmin = superadmin_result.scalar_one_or_none()
    if not superadmin:
        raise HTTPException(status_code=401, detail="Superadmin not found")

    # Get target user
    result = await db.execute(select(User).where(User.id == request_body.user_id))
    target_user = result.scalar_one_or_none()

    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Shadow users cannot impersonate anyone
    if getattr(superadmin, 'is_shadow', False):
        raise HTTPException(status_code=403, detail="Shadow users cannot impersonate")

    # Cannot impersonate yourself
    if target_user.id == superadmin.id:
        raise HTTPException(status_code=400, detail="Cannot impersonate yourself")

    # Cannot impersonate another superadmin (main or shadow)
    if target_user.role == UserRole.superadmin:
        raise HTTPException(status_code=403, detail="Cannot impersonate another superadmin")

    # Cannot impersonate inactive users
    if not target_user.is_active:
        raise HTTPException(status_code=400, detail="Cannot impersonate inactive user")

    # Create impersonation token (expires in 1 hour)
    token = create_impersonation_token(
        impersonated_user_id=target_user.id,
        original_user_id=superadmin.id,
        token_version=target_user.token_version
    )

    # Log impersonation session for audit
    impersonation_log = ImpersonationLog(
        superadmin_id=superadmin.id,
        impersonated_user_id=target_user.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent")
    )
    db.add(impersonation_log)
    await db.commit()

    return {
        "token": token,
        "impersonated_user": {
            "id": target_user.id,
            "email": target_user.email,
            "name": target_user.name,
            "role": target_user.role.value,
            "is_active": target_user.is_active,
            "created_at": target_user.created_at.isoformat()
        }
    }


@router.post("/exit-impersonation")
async def exit_impersonation(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
):
    """
    Exit impersonation and return to original SUPERADMIN account.

    This endpoint should be called when a SUPERADMIN wants to stop
    impersonating and return to their own account.

    **Returns a regular token for the SUPERADMIN.**
    """
    # Decode the impersonation token to get original user
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm]
        )
        is_impersonating = payload.get("is_impersonating", False)
        original_user_id = payload.get("original_user_id")

        if not is_impersonating or not original_user_id:
            raise HTTPException(
                status_code=400,
                detail="Not in impersonation mode"
            )
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Get the original superadmin user
    result = await db.execute(select(User).where(User.id == original_user_id))
    original_user = result.scalar_one_or_none()

    if not original_user:
        raise HTTPException(status_code=404, detail="Original user not found")

    # Verify original user is a SUPERADMIN
    if original_user.role != UserRole.superadmin:
        raise HTTPException(
            status_code=403,
            detail="Only superadmin can use impersonation"
        )

    # Create regular token for superadmin
    token = create_access_token({
        "sub": str(original_user.id),
        "token_version": original_user.token_version
    })

    return {
        "token": token,
        "message": "Exited impersonation mode"
    }


@router.get("/impersonation-logs", response_model=List[ImpersonationLogResponse])
async def get_impersonation_logs(
    limit: int = Query(100, description="Maximum number of logs to return"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_superadmin)
):
    """
    Get audit log of all impersonation sessions.

    Returns a list of all impersonation sessions, including:
    - Who impersonated whom
    - When the session started
    - IP address and user agent
    - Session duration

    **Only accessible by SUPERADMIN.**
    """
    result = await db.execute(
        select(ImpersonationLog)
        .order_by(ImpersonationLog.started_at.desc())
        .limit(limit)
    )
    logs = result.scalars().all()

    # Batch fetch all users involved (fix N+1 query)
    user_ids = set()
    for log in logs:
        user_ids.add(log.superadmin_id)
        user_ids.add(log.impersonated_user_id)

    users_result = await db.execute(
        select(User).where(User.id.in_(user_ids))
    )
    users_map = {user.id: user for user in users_result.scalars().all()}

    # Build responses using pre-fetched users
    log_responses = []
    for log in logs:
        superadmin = users_map.get(log.superadmin_id)
        impersonated = users_map.get(log.impersonated_user_id)

        log_responses.append(ImpersonationLogResponse(
            id=log.id,
            superadmin_id=log.superadmin_id,
            superadmin_name=superadmin.name if superadmin else "Unknown",
            superadmin_email=superadmin.email if superadmin else "Unknown",
            impersonated_user_id=log.impersonated_user_id,
            impersonated_user_name=impersonated.name if impersonated else "Unknown",
            impersonated_user_email=impersonated.email if impersonated else "Unknown",
            started_at=log.started_at,
            ended_at=log.ended_at,
            ip_address=log.ip_address,
            user_agent=log.user_agent,
        ))

    return log_responses
