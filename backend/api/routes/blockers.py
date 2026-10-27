"""Blocker board endpoints."""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from ..models.database import Blocker, User, OrgMember, OrgRole, DepartmentMember, DeptRole, UserRole
from ..database import get_db
from ..services.auth import get_current_user


async def _scoped_user_ids(user: User, org_id: int, db: AsyncSession) -> list[int] | None:
    """Какие user_id видны в этом org для текущего юзера.

    None  — без фильтра (платформ-админ / owner / org-admin).
    list  — конкретные id (лид → коллеги отделов; остальные → только self).
    """
    if user.role == UserRole.superadmin:
        return None
    om = await db.execute(
        select(OrgMember.role).where(
            OrgMember.user_id == user.id, OrgMember.org_id == org_id
        )
    )
    org_role = om.scalar_one_or_none()
    if org_role in (OrgRole.owner, OrgRole.admin):
        return None

    dept_ids_res = await db.execute(
        select(DepartmentMember.department_id).where(
            DepartmentMember.user_id == user.id,
            DepartmentMember.role.in_([DeptRole.lead, DeptRole.sub_admin]),
        )
    )
    admin_dept_ids = [r for r in dept_ids_res.scalars().all()]
    if not admin_dept_ids:
        return [user.id]

    members_res = await db.execute(
        select(DepartmentMember.user_id).where(
            DepartmentMember.department_id.in_(admin_dept_ids)
        )
    )
    ids = {uid for uid in members_res.scalars().all()}
    ids.add(user.id)
    return list(ids)

router = APIRouter()


class BlockerOut(BaseModel):
    id: int
    user_id: int
    user_name: str | None = None
    project_id: int | None = None
    description: str
    status: str
    resolved_by: int | None = None
    resolver_name: str | None = None
    resolved_at: datetime | None = None
    resolve_comment: str | None = None
    created_at: datetime | None = None

    class Config:
        from_attributes = True


@router.get("")
async def list_blockers(
    status: str | None = "open",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List blockers for the org."""
    org_result = await db.execute(
        select(OrgMember.org_id).where(OrgMember.user_id == current_user.id).limit(1)
    )
    org_id = org_result.scalar_one_or_none()
    if not org_id:
        raise HTTPException(404, "No organization")

    query = select(Blocker).where(Blocker.org_id == org_id).order_by(Blocker.created_at.desc())
    if status:
        query = query.where(Blocker.status == status)
    allowed = await _scoped_user_ids(current_user, org_id, db)
    if allowed is not None:
        query = query.where(Blocker.user_id.in_(allowed))

    result = await db.execute(query)
    blockers = result.scalars().all()

    user_ids = set()
    for b in blockers:
        user_ids.add(b.user_id)
        if b.resolved_by:
            user_ids.add(b.resolved_by)

    users_result = await db.execute(select(User).where(User.id.in_(user_ids)))
    users_map = {u.id: u.name for u in users_result.scalars().all()}

    return [
        BlockerOut(
            id=b.id,
            user_id=b.user_id,
            user_name=users_map.get(b.user_id),
            project_id=b.project_id,
            description=b.description,
            status=b.status if isinstance(b.status, str) else b.status.value,
            resolved_by=b.resolved_by,
            resolver_name=users_map.get(b.resolved_by) if b.resolved_by else None,
            resolved_at=b.resolved_at,
            resolve_comment=b.resolve_comment,
            created_at=b.created_at,
        )
        for b in blockers
    ]


@router.post("/{blocker_id}/resolve")
async def resolve_blocker(
    blocker_id: int,
    comment: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Resolve a blocker."""
    blocker = await db.get(Blocker, blocker_id)
    if not blocker:
        raise HTTPException(404, "Blocker not found")

    blocker.status = "resolved"
    blocker.resolved_by = current_user.id
    blocker.resolved_at = datetime.utcnow()
    blocker.resolve_comment = comment
    await db.commit()

    # Send Telegram notification
    try:
        from ..bot import send_telegram_notification
        comment_text = f"\n\U0001f4ac {comment}" if comment else ""
        await send_telegram_notification(
            blocker.user_id,
            f"\u2705 <b>\u0411\u043b\u043e\u043a\u0435\u0440 \u0441\u043d\u044f\u0442!</b>\n\n"
            f"\U0001f4dd {blocker.description}\n"
            f"\u0420\u0435\u0448\u0438\u043b: {current_user.name}{comment_text}",
        )
    except Exception:
        pass

    return {"status": "resolved"}
