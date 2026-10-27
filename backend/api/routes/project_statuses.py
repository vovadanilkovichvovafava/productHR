"""
Organization-level custom project status definitions.

These define the kanban columns on the Projects board (per organization).
Not to be confused with project *task* statuses (per project).
"""
import re
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from pydantic import BaseModel

from ..database import get_db
from ..models.database import (
    ProjectStatusDef, Project, User, Organization,
    OrgMember, OrgRole, UserRole,
)
from ..services.auth import get_current_user, get_user_org

router = APIRouter()

# ============================================================
# Transliteration table RU -> EN for slug generation
# ============================================================
_TRANSLIT = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
}


def _transliterate(text: str) -> str:
    result = []
    for ch in text.lower():
        result.append(_TRANSLIT.get(ch, ch))
    return ''.join(result)


def generate_slug(name: str) -> str:
    """Generate a slug from a name: transliterate Russian, lowercase, spaces to underscores."""
    slug = _transliterate(name.strip())
    slug = re.sub(r'[^a-z0-9\s_-]', '', slug)
    slug = re.sub(r'[\s-]+', '_', slug)
    slug = re.sub(r'_+', '_', slug)
    slug = slug.strip('_')
    return slug or 'status'


# ============================================================
# Pydantic schemas
# ============================================================

class ProjectStatusCreate(BaseModel):
    name: str
    color: Optional[str] = "#6366f1"
    sort_order: Optional[int] = None
    is_done: Optional[bool] = False


class ProjectStatusUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    sort_order: Optional[int] = None
    is_done: Optional[bool] = None


class ProjectStatusResponse(BaseModel):
    id: int
    org_id: int
    name: str
    slug: str
    color: str
    sort_order: int
    is_done: bool

    class Config:
        from_attributes = True


class ReorderItem(BaseModel):
    id: int
    sort_order: int


class ReorderRequest(BaseModel):
    statuses: List[ReorderItem]


# ============================================================
# Helpers
# ============================================================

def serialize_status(s: ProjectStatusDef) -> dict:
    return ProjectStatusResponse(
        id=s.id,
        org_id=s.org_id,
        name=s.name,
        slug=s.slug,
        color=s.color or "#6366f1",
        sort_order=s.sort_order or 0,
        is_done=s.is_done or False,
    ).model_dump()


async def _is_org_admin(user: User, org: Organization, db: AsyncSession) -> bool:
    """Check if user is superadmin or org owner/admin."""
    if user.role == UserRole.superadmin:
        return True
    result = await db.execute(
        select(OrgMember).where(
            OrgMember.user_id == user.id,
            OrgMember.org_id == org.id,
            OrgMember.role.in_([OrgRole.owner, OrgRole.admin]),
        )
    )
    return result.scalar_one_or_none() is not None


# ============================================================
# Endpoints
# ============================================================

@router.get("")
async def list_project_statuses(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all project status definitions for the current user's org."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=400, detail="User not in an organization")

    result = await db.execute(
        select(ProjectStatusDef)
        .where(ProjectStatusDef.org_id == org.id)
        .order_by(ProjectStatusDef.sort_order, ProjectStatusDef.id)
    )
    statuses = list(result.scalars().all())
    return [serialize_status(s) for s in statuses]


@router.post("", status_code=201)
async def create_project_status(
    data: ProjectStatusCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new project status definition. Org admin/owner only."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=400, detail="User not in an organization")

    if not await _is_org_admin(current_user, org, db):
        raise HTTPException(status_code=403, detail="Only org admin/owner can manage project statuses")

    slug = generate_slug(data.name)

    # Check uniqueness within org
    existing = await db.execute(
        select(ProjectStatusDef).where(
            ProjectStatusDef.org_id == org.id,
            ProjectStatusDef.slug == slug,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Status with slug '{slug}' already exists")

    # Auto-assign sort_order
    sort_order = data.sort_order
    if sort_order is None:
        max_result = await db.execute(
            select(func.max(ProjectStatusDef.sort_order))
            .where(ProjectStatusDef.org_id == org.id)
        )
        max_order = max_result.scalar() or 0
        sort_order = max_order + 1

    status = ProjectStatusDef(
        org_id=org.id,
        name=data.name,
        slug=slug,
        color=data.color or "#6366f1",
        sort_order=sort_order,
        is_done=data.is_done or False,
    )
    db.add(status)
    await db.commit()
    await db.refresh(status)

    return serialize_status(status)


@router.put("/{status_id}")
async def update_project_status(
    status_id: int,
    data: ProjectStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a project status definition."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=400, detail="User not in an organization")

    if not await _is_org_admin(current_user, org, db):
        raise HTTPException(status_code=403, detail="Only org admin/owner can manage project statuses")

    result = await db.execute(
        select(ProjectStatusDef).where(
            ProjectStatusDef.id == status_id,
            ProjectStatusDef.org_id == org.id,
        )
    )
    status = result.scalar_one_or_none()
    if not status:
        raise HTTPException(status_code=404, detail="Project status not found")

    if data.name is not None:
        status.name = data.name
        new_slug = generate_slug(data.name)
        # Check uniqueness of new slug
        dup = await db.execute(
            select(ProjectStatusDef).where(
                ProjectStatusDef.org_id == org.id,
                ProjectStatusDef.slug == new_slug,
                ProjectStatusDef.id != status_id,
            )
        )
        if dup.scalar_one_or_none():
            raise HTTPException(status_code=409, detail=f"Status with slug '{new_slug}' already exists")
        status.slug = new_slug

    if data.color is not None:
        status.color = data.color
    if data.sort_order is not None:
        status.sort_order = data.sort_order
    if data.is_done is not None:
        status.is_done = data.is_done

    await db.commit()
    await db.refresh(status)
    return serialize_status(status)


@router.delete("/{status_id}", status_code=204)
async def delete_project_status(
    status_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a project status definition. Fails if projects use it."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=400, detail="User not in an organization")

    if not await _is_org_admin(current_user, org, db):
        raise HTTPException(status_code=403, detail="Only org admin/owner can manage project statuses")

    result = await db.execute(
        select(ProjectStatusDef).where(
            ProjectStatusDef.id == status_id,
            ProjectStatusDef.org_id == org.id,
        )
    )
    status = result.scalar_one_or_none()
    if not status:
        raise HTTPException(status_code=404, detail="Project status not found")

    # Check if any projects use this status slug
    count_result = await db.execute(
        select(func.count(Project.id)).where(
            Project.org_id == org.id,
            Project.status == status.slug,
        )
    )
    count = count_result.scalar() or 0
    if count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete status '{status.name}': {count} project(s) still use it",
        )

    await db.delete(status)
    await db.commit()


@router.put("/reorder")
async def reorder_project_statuses(
    data: ReorderRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Bulk reorder project status definitions."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=400, detail="User not in an organization")

    if not await _is_org_admin(current_user, org, db):
        raise HTTPException(status_code=403, detail="Only org admin/owner can manage project statuses")

    for item in data.statuses:
        result = await db.execute(
            select(ProjectStatusDef).where(
                ProjectStatusDef.id == item.id,
                ProjectStatusDef.org_id == org.id,
            )
        )
        status = result.scalar_one_or_none()
        if status:
            status.sort_order = item.sort_order

    await db.commit()

    # Return updated list
    result = await db.execute(
        select(ProjectStatusDef)
        .where(ProjectStatusDef.org_id == org.id)
        .order_by(ProjectStatusDef.sort_order, ProjectStatusDef.id)
    )
    return [serialize_status(s) for s in result.scalars().all()]
