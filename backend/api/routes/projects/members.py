"""
Project member management endpoints.
"""
from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .common import (
    logger, MemberCreate, MemberUpdate, MemberResponse,
    Project, ProjectMember, ProjectRole, User,
    has_full_access, can_edit_project, is_project_member,
    get_db, get_current_user, get_user_org,
)


def serialize_member(m: ProjectMember) -> dict:
    return MemberResponse(
        id=m.id,
        project_id=m.project_id,
        user_id=m.user_id,
        user_name=m.user.name if m.user else None,
        user_email=m.user.email if m.user else None,
        role=m.role if isinstance(m.role, str) else m.role.value,
        allocation_percent=m.allocation_percent,
        joined_at=m.joined_at,
    ).model_dump()


async def list_members(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all members of a project."""
    org = await get_user_org(current_user, db)
    result = await db.execute(
        select(ProjectMember)
        .where(ProjectMember.project_id == project_id)
        .options(selectinload(ProjectMember.user))
    )
    members = list(result.scalars().all())
    return [serialize_member(m) for m in members]


async def add_member(
    project_id: int,
    data: MemberCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add a member to a project."""
    org = await get_user_org(current_user, db)
    project = await db.get(Project, project_id)
    if not project or project.org_id != org.id:
        raise HTTPException(status_code=404, detail="Project not found")
    if not await can_edit_project(project, current_user, org, db):
        raise HTTPException(status_code=403, detail="Access denied")

    # Check if already a member
    existing = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == data.user_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="User is already a member")

    member = ProjectMember(
        project_id=project_id,
        user_id=data.user_id,
        role=data.role or ProjectRole.developer,
        allocation_percent=data.allocation_percent or 100,
    )
    db.add(member)
    await db.commit()

    result = await db.execute(
        select(ProjectMember)
        .where(ProjectMember.id == member.id)
        .options(selectinload(ProjectMember.user))
    )
    member = result.scalar_one()
    logger.info(f"Member added to project {project_id}: user {data.user_id}")
    return serialize_member(member)


async def update_member(
    project_id: int,
    user_id: int,
    data: MemberUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a project member's role or allocation."""
    org = await get_user_org(current_user, db)
    project = await db.get(Project, project_id)
    if not project or project.org_id != org.id:
        raise HTTPException(status_code=404, detail="Project not found")
    if not await can_edit_project(project, current_user, org, db):
        raise HTTPException(status_code=403, detail="Access denied")

    result = await db.execute(
        select(ProjectMember)
        .where(ProjectMember.project_id == project_id, ProjectMember.user_id == user_id)
        .options(selectinload(ProjectMember.user))
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    if data.role is not None:
        member.role = data.role
    if data.allocation_percent is not None:
        member.allocation_percent = data.allocation_percent

    await db.commit()
    await db.refresh(member)
    return serialize_member(member)


async def remove_member(
    project_id: int,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove a member from a project."""
    org = await get_user_org(current_user, db)
    project = await db.get(Project, project_id)
    if not project or project.org_id != org.id:
        raise HTTPException(status_code=404, detail="Project not found")
    if not await can_edit_project(project, current_user, org, db):
        raise HTTPException(status_code=403, detail="Access denied")

    result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    await db.delete(member)
    await db.commit()
    logger.info(f"Member removed from project {project_id}: user {user_id}")
