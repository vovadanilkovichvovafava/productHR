"""
Project custom task status management.
"""
import re
from fastapi import Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from pydantic import BaseModel

from .common import (
    logger, Project, User,
    has_full_access, can_access_project, can_edit_project,
    get_db, get_current_user, get_user_org,
)
from ...models.database import ProjectTaskStatus


# === Pydantic Schemas ===

class TaskStatusCreate(BaseModel):
    name: str
    color: Optional[str] = "#6366f1"
    sort_order: Optional[int] = None
    is_done: Optional[bool] = False
    is_default: Optional[bool] = False


class TaskStatusUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    sort_order: Optional[int] = None
    is_done: Optional[bool] = None
    is_default: Optional[bool] = None


class TaskStatusResponse(BaseModel):
    id: int
    project_id: int
    name: str
    slug: str
    color: str
    sort_order: int
    is_done: bool
    is_default: bool

    class Config:
        from_attributes = True


class ReorderItem(BaseModel):
    id: int
    sort_order: int


class ReorderRequest(BaseModel):
    statuses: List[ReorderItem]


# === Helpers ===

def generate_slug(name: str) -> str:
    """Generate a slug from a name: lowercase, replace spaces with underscores, strip special chars."""
    slug = name.lower().strip()
    slug = re.sub(r'[^a-z0-9а-яё\s_-]', '', slug)
    slug = re.sub(r'[\s-]+', '_', slug)
    slug = re.sub(r'_+', '_', slug)
    slug = slug.strip('_')
    return slug or 'status'


def serialize_status(s: ProjectTaskStatus) -> dict:
    return TaskStatusResponse(
        id=s.id,
        project_id=s.project_id,
        name=s.name,
        slug=s.slug,
        color=s.color or "#6366f1",
        sort_order=s.sort_order or 0,
        is_done=s.is_done or False,
        is_default=s.is_default or False,
    ).model_dump()


# === Endpoints ===

async def list_statuses(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all custom task statuses for a project, ordered by sort_order."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=400, detail="User not in an organization")

    project = await db.get(Project, project_id)
    if not project or project.org_id != org.id:
        raise HTTPException(status_code=404, detail="Project not found")

    if not await can_access_project(project, current_user, org, db):
        raise HTTPException(status_code=403, detail="Access denied")

    result = await db.execute(
        select(ProjectTaskStatus)
        .where(ProjectTaskStatus.project_id == project_id)
        .order_by(ProjectTaskStatus.sort_order, ProjectTaskStatus.id)
    )
    statuses = list(result.scalars().all())
    return [serialize_status(s) for s in statuses]


async def create_status(
    project_id: int,
    data: TaskStatusCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new custom task status for a project."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=400, detail="User not in an organization")

    project = await db.get(Project, project_id)
    if not project or project.org_id != org.id:
        raise HTTPException(status_code=404, detail="Project not found")

    if not await can_edit_project(project, current_user, org, db):
        raise HTTPException(status_code=403, detail="Access denied")

    slug = generate_slug(data.name)

    # Check uniqueness of slug within project
    existing = await db.execute(
        select(ProjectTaskStatus).where(
            ProjectTaskStatus.project_id == project_id,
            ProjectTaskStatus.slug == slug,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Status with slug '{slug}' already exists in this project")

    # Auto-assign sort_order if not provided
    sort_order = data.sort_order
    if sort_order is None:
        max_result = await db.execute(
            select(func.max(ProjectTaskStatus.sort_order))
            .where(ProjectTaskStatus.project_id == project_id)
        )
        max_order = max_result.scalar() or 0
        sort_order = max_order + 1

    # If this is set as default, unset other defaults
    if data.is_default:
        await _unset_defaults(project_id, db)

    status = ProjectTaskStatus(
        project_id=project_id,
        name=data.name,
        slug=slug,
        color=data.color or "#6366f1",
        sort_order=sort_order,
        is_done=data.is_done or False,
        is_default=data.is_default or False,
    )
    db.add(status)
    await db.commit()
    await db.refresh(status)

    logger.info(f"Task status created: '{status.name}' (slug={status.slug}) for project {project_id}")
    return serialize_status(status)


async def update_status(
    project_id: int,
    status_id: int,
    data: TaskStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a custom task status."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=400, detail="User not in an organization")

    project = await db.get(Project, project_id)
    if not project or project.org_id != org.id:
        raise HTTPException(status_code=404, detail="Project not found")

    if not await can_edit_project(project, current_user, org, db):
        raise HTTPException(status_code=403, detail="Access denied")

    result = await db.execute(
        select(ProjectTaskStatus).where(
            ProjectTaskStatus.id == status_id,
            ProjectTaskStatus.project_id == project_id,
        )
    )
    status = result.scalar_one_or_none()
    if not status:
        raise HTTPException(status_code=404, detail="Status not found")

    update_data = data.model_dump(exclude_unset=True)

    # If name is being updated, regenerate slug
    if 'name' in update_data:
        new_slug = generate_slug(update_data['name'])
        # Check uniqueness
        existing = await db.execute(
            select(ProjectTaskStatus).where(
                ProjectTaskStatus.project_id == project_id,
                ProjectTaskStatus.slug == new_slug,
                ProjectTaskStatus.id != status_id,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail=f"Status with slug '{new_slug}' already exists")
        status.slug = new_slug

    # If setting as default, unset others
    if update_data.get('is_default'):
        await _unset_defaults(project_id, db, exclude_id=status_id)

    for key, value in update_data.items():
        setattr(status, key, value)

    await db.commit()
    await db.refresh(status)

    logger.info(f"Task status updated: '{status.name}' (id={status_id}) for project {project_id}")
    return serialize_status(status)


async def delete_status(
    project_id: int,
    status_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a custom task status."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=400, detail="User not in an organization")

    project = await db.get(Project, project_id)
    if not project or project.org_id != org.id:
        raise HTTPException(status_code=404, detail="Project not found")

    if not await can_edit_project(project, current_user, org, db):
        raise HTTPException(status_code=403, detail="Access denied")

    result = await db.execute(
        select(ProjectTaskStatus).where(
            ProjectTaskStatus.id == status_id,
            ProjectTaskStatus.project_id == project_id,
        )
    )
    status = result.scalar_one_or_none()
    if not status:
        raise HTTPException(status_code=404, detail="Status not found")

    await db.delete(status)
    await db.commit()
    logger.info(f"Task status deleted: id={status_id} for project {project_id}")


async def reorder_statuses(
    project_id: int,
    data: ReorderRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Bulk reorder statuses for a project."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=400, detail="User not in an organization")

    project = await db.get(Project, project_id)
    if not project or project.org_id != org.id:
        raise HTTPException(status_code=404, detail="Project not found")

    if not await can_edit_project(project, current_user, org, db):
        raise HTTPException(status_code=403, detail="Access denied")

    for item in data.statuses:
        result = await db.execute(
            select(ProjectTaskStatus).where(
                ProjectTaskStatus.id == item.id,
                ProjectTaskStatus.project_id == project_id,
            )
        )
        status = result.scalar_one_or_none()
        if status:
            status.sort_order = item.sort_order

    await db.commit()

    # Return updated list
    result = await db.execute(
        select(ProjectTaskStatus)
        .where(ProjectTaskStatus.project_id == project_id)
        .order_by(ProjectTaskStatus.sort_order, ProjectTaskStatus.id)
    )
    statuses = list(result.scalars().all())
    return [serialize_status(s) for s in statuses]


async def _unset_defaults(project_id: int, db: AsyncSession, exclude_id: int = None):
    """Unset is_default on all statuses for a project, optionally excluding one."""
    query = select(ProjectTaskStatus).where(
        ProjectTaskStatus.project_id == project_id,
        ProjectTaskStatus.is_default == True,
    )
    if exclude_id:
        query = query.where(ProjectTaskStatus.id != exclude_id)
    result = await db.execute(query)
    for s in result.scalars().all():
        s.is_default = False
