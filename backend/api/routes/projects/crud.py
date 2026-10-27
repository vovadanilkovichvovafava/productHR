"""
Project CRUD operations.
"""
from fastapi import Depends, HTTPException, Query
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing import Optional, List
from datetime import datetime, timezone

from .common import (
    logger, ProjectCreate, ProjectUpdate, ProjectResponse,
    Project, ProjectStatus, ProjectMember, ProjectRole, ProjectTask,
    User, Organization, Department, UserRole, OrgMember, OrgRole,
    DepartmentMember, DeptRole,
    has_full_access, get_user_department_ids, can_access_project, can_edit_project,
    is_project_member, serialize_project,
    get_db, get_current_user, get_user_org,
)
from ...models.database import ProjectTaskStatus

DEFAULT_STATUSES = [
    {"name": "Бэклог", "slug": "backlog", "color": "#6b7280", "sort_order": 0},
    {"name": "К выполнению", "slug": "todo", "color": "#3b82f6", "sort_order": 1},
    {"name": "В работе", "slug": "in_progress", "color": "#f59e0b", "sort_order": 2},
    {"name": "Ревью", "slug": "review", "color": "#8b5cf6", "sort_order": 3},
    {"name": "Готово", "slug": "done", "color": "#10b981", "sort_order": 4, "is_done": True},
]


async def list_projects(
    status: Optional[str] = Query(None),
    department_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List projects accessible to the current user."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=400, detail="User not in an organization")

    query = (
        select(Project)
        .where(Project.org_id == org.id)
        .options(
            selectinload(Project.department),
            selectinload(Project.creator),
            selectinload(Project.members),
            selectinload(Project.tasks),
        )
    )

    if status:
        query = query.where(Project.status == status)
    if department_id:
        query = query.where(Project.department_id == department_id)
    if search:
        query = query.where(
            or_(
                Project.name.ilike(f"%{search}%"),
                Project.description.ilike(f"%{search}%"),
                Project.client_name.ilike(f"%{search}%"),
            )
        )

    query = query.order_by(Project.priority.desc(), Project.created_at.desc())

    result = await db.execute(query)
    projects = list(result.scalars().unique().all())

    # Filter by access if not superadmin/owner
    full_access = await has_full_access(current_user, org, db)
    if not full_access:
        accessible = []
        for p in projects:
            if await can_access_project(p, current_user, org, db):
                accessible.append(p)
        projects = accessible

    # Determine user's role for each project
    results = []
    for p in projects:
        role = None
        if current_user.role and current_user.role.value == 'superadmin':
            role = 'admin'
        elif full_access:
            role = 'admin'
        else:
            # Check project membership
            for m in (p.members or []):
                if m.user_id == current_user.id:
                    role = m.role if isinstance(m.role, str) else m.role.value
                    break
        results.append(serialize_project(p, p.members, p.tasks, current_user_role=role))
    return results


async def create_project(
    data: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new project. Auto-adds creator as manager."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=400, detail="User not in an organization")

    # Auto-generate prefix from name if not provided
    import re
    prefix = data.prefix
    if not prefix:
        # Take first letters of each word, uppercase, max 5 chars
        words = re.sub(r'[^a-zA-Zа-яА-ЯёЁ0-9\s]', '', data.name).split()
        if len(words) >= 2:
            prefix = ''.join(w[0] for w in words[:4]).upper()
        else:
            prefix = data.name[:4].upper().strip()
        # Transliterate Russian if needed
        translit_map = {'А':'A','Б':'B','В':'V','Г':'G','Д':'D','Е':'E','Ж':'Z','З':'Z','И':'I','К':'K','Л':'L','М':'M','Н':'N','О':'O','П':'P','Р':'R','С':'S','Т':'T','У':'U','Ф':'F','Х':'H','Ц':'C','Ч':'C','Ш':'S','Э':'E','Ю':'U','Я':'Y'}
        prefix = ''.join(translit_map.get(c, c) for c in prefix)
        prefix = re.sub(r'[^A-Z0-9]', '', prefix)[:5] or 'PRJ'

    project = Project(
        org_id=org.id,
        department_id=data.department_id,
        name=data.name,
        prefix=prefix,
        task_counter=0,
        description=data.description,
        status=data.status or ProjectStatus.planning,
        priority=data.priority or 1,
        client_name=data.client_name,
        progress_mode=data.progress_mode or "auto",
        start_date=data.start_date,
        target_date=data.target_date,
        tags=data.tags or [],
        color=data.color,
        created_by=current_user.id,
    )
    db.add(project)
    await db.flush()

    # Auto-add creator as manager
    member = ProjectMember(
        project_id=project.id,
        user_id=current_user.id,
        role=ProjectRole.manager,
    )
    db.add(member)

    # Auto-create default task statuses
    for s in DEFAULT_STATUSES:
        db.add(ProjectTaskStatus(project_id=project.id, **s))

    await db.commit()

    # Reload with relationships
    result = await db.execute(
        select(Project)
        .where(Project.id == project.id)
        .options(
            selectinload(Project.department),
            selectinload(Project.creator),
            selectinload(Project.members),
            selectinload(Project.tasks),
        )
    )
    project = result.scalar_one()

    logger.info(f"Project created: {project.name} (id={project.id}) by user {current_user.id}")
    return serialize_project(project, project.members, project.tasks)


async def get_project(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get project details."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=400, detail="User not in an organization")

    result = await db.execute(
        select(Project)
        .where(Project.id == project_id, Project.org_id == org.id)
        .options(
            selectinload(Project.department),
            selectinload(Project.creator),
            selectinload(Project.members).selectinload(ProjectMember.user),
            selectinload(Project.tasks),
            selectinload(Project.milestones),
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not await can_access_project(project, current_user, org, db):
        raise HTTPException(status_code=403, detail="Access denied")

    return serialize_project(project, project.members, project.tasks)


async def update_project(
    project_id: int,
    data: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a project."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=400, detail="User not in an organization")

    result = await db.execute(
        select(Project)
        .where(Project.id == project_id, Project.org_id == org.id)
        .options(
            selectinload(Project.department),
            selectinload(Project.creator),
            selectinload(Project.members),
            selectinload(Project.tasks),
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not await can_edit_project(project, current_user, org, db):
        raise HTTPException(status_code=403, detail="Access denied")

    update_data = data.model_dump(exclude_unset=True)

    # Validate status
    VALID_STATUSES = {'planning', 'active', 'on_hold', 'completed', 'cancelled'}
    if 'status' in update_data and update_data['status'] not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(VALID_STATUSES)}")

    for key, value in update_data.items():
        setattr(project, key, value)

    # If status changed to completed, set completed_at
    if data.status == "completed" and not project.completed_at:
        project.completed_at = datetime.utcnow()

    await db.commit()
    await db.refresh(project)

    logger.info(f"Project updated: {project.name} (id={project.id}) by user {current_user.id}")
    return serialize_project(project, project.members, project.tasks)


async def delete_project(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a project."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=400, detail="User not in an organization")

    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.org_id == org.id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not await can_edit_project(project, current_user, org, db):
        raise HTTPException(status_code=403, detail="Access denied")

    await db.delete(project)
    await db.commit()
    logger.info(f"Project deleted: id={project_id} by user {current_user.id}")
