"""
Shared schemas, imports, and helper functions for project management.
"""
from fastapi import Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing import Optional, List
from datetime import datetime, timezone
from pydantic import BaseModel
import logging

logger = logging.getLogger("hr-analyzer.projects")

from ...database import get_db
from ...models.database import (
    Project, ProjectStatus, ProjectMember, ProjectRole,
    ProjectMilestone, ProjectTask, TaskStatus, TaskTimeLog,
    User, Organization, Department, UserRole,
    OrgMember, OrgRole, DepartmentMember, DeptRole,
    SharedAccess, ResourceType, AccessLevel,
)
from ...services.auth import get_current_user, get_user_org, has_full_database_access as auth_has_full_database_access


# === Pydantic Schemas ===

class ProjectCreate(BaseModel):
    name: str
    prefix: Optional[str] = None  # Short code like "PM", "HR". Auto-generated from name if not provided.
    description: Optional[str] = None
    department_id: Optional[int] = None
    status: Optional[str] = "planning"
    priority: Optional[int] = 1
    client_name: Optional[str] = None
    progress_mode: Optional[str] = "auto"
    start_date: Optional[datetime] = None
    target_date: Optional[datetime] = None
    tags: Optional[list] = []
    color: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    department_id: Optional[int] = None
    status: Optional[str] = None
    priority: Optional[int] = None
    client_name: Optional[str] = None
    progress_percent: Optional[int] = None
    progress_mode: Optional[str] = None
    start_date: Optional[datetime] = None
    target_date: Optional[datetime] = None
    predicted_date: Optional[datetime] = None
    tags: Optional[list] = None
    color: Optional[str] = None
    extra_data: Optional[dict] = None


class ProjectResponse(BaseModel):
    id: int
    org_id: int
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    name: str
    prefix: Optional[str] = None
    description: Optional[str] = None
    status: str
    priority: int
    client_name: Optional[str] = None
    progress_percent: int
    progress_mode: str
    start_date: Optional[datetime] = None
    target_date: Optional[datetime] = None
    predicted_date: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    tags: list = []
    color: Optional[str] = None
    created_by: Optional[int] = None
    creator_name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    member_count: int = 0
    task_counts: dict = {}
    current_user_role: Optional[str] = None  # user's role in this project (manager/developer/reviewer/observer/dept_lead/admin)

    class Config:
        from_attributes = True


class MemberCreate(BaseModel):
    user_id: int
    role: Optional[str] = "developer"
    allocation_percent: Optional[int] = 100


class MemberUpdate(BaseModel):
    role: Optional[str] = None
    allocation_percent: Optional[int] = None


class MemberResponse(BaseModel):
    id: int
    project_id: int
    user_id: int
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    role: str
    allocation_percent: int
    joined_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    milestone_id: Optional[int] = None
    status: Optional[str] = "backlog"
    priority: Optional[int] = 1
    assignee_id: Optional[int] = None
    estimated_hours: Optional[int] = None
    due_date: Optional[datetime] = None
    tags: Optional[list] = []
    parent_task_id: Optional[int] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    milestone_id: Optional[int] = None
    status: Optional[str] = None
    priority: Optional[int] = None
    assignee_id: Optional[int] = None
    estimated_hours: Optional[int] = None
    due_date: Optional[datetime] = None
    tags: Optional[list] = None
    sort_order: Optional[int] = None


class TaskResponse(BaseModel):
    id: int
    project_id: int
    task_number: Optional[int] = None
    task_key: Optional[str] = None  # e.g. "PM-42"
    milestone_id: Optional[int] = None
    title: str
    description: Optional[str] = None
    status: str
    priority: int
    assignee_id: Optional[int] = None
    assignee_name: Optional[str] = None
    estimated_hours: Optional[int] = None
    due_date: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    sort_order: int = 0
    tags: list = []
    total_hours_logged: int = 0
    parent_task_id: Optional[int] = None
    blocker_id: Optional[int] = None
    subtask_count: int = 0
    subtasks_done: int = 0
    comment_count: int = 0
    attachment_count: int = 0
    created_by: Optional[int] = None
    creator_name: Optional[str] = None
    # Задачу завёл бот из сообщения в чате (по кнопке «Создать»): показываем
    # это в списке, чтобы «наработки бота» было видно и можно было отобрать.
    created_by_bot: bool = False
    source_message: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class MilestoneCreate(BaseModel):
    name: str
    description: Optional[str] = None
    target_date: Optional[datetime] = None
    sort_order: Optional[int] = 0


class MilestoneUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    target_date: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    sort_order: Optional[int] = None


class MilestoneResponse(BaseModel):
    id: int
    project_id: int
    name: str
    description: Optional[str] = None
    target_date: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    sort_order: int
    created_at: Optional[datetime] = None
    task_count: int = 0

    class Config:
        from_attributes = True


class TimeLogCreate(BaseModel):
    hours: int
    date: datetime
    note: Optional[str] = None


class TimeLogResponse(BaseModel):
    id: int
    task_id: int
    user_id: int
    user_name: Optional[str] = None
    hours: int
    date: datetime
    note: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TaskKanbanColumn(BaseModel):
    status: str
    title: str
    tasks: List[TaskResponse] = []
    count: int = 0


class TaskKanbanBoard(BaseModel):
    project_id: int
    columns: List[TaskKanbanColumn] = []
    total_count: int = 0


# === Access Control Helpers ===

async def has_full_access(user: User, org: Organization, db: AsyncSession) -> bool:
    """Superadmin or org owner has full access."""
    return await auth_has_full_database_access(user, org.id, db)


async def get_user_department_ids(user_id: int, org_id: int, db: AsyncSession) -> List[int]:
    """Get all department IDs user belongs to."""
    result = await db.execute(
        select(DepartmentMember.department_id)
        .join(Department, Department.id == DepartmentMember.department_id)
        .where(
            Department.org_id == org_id,
            DepartmentMember.user_id == user_id,
        )
    )
    return [row[0] for row in result.all()]


async def is_project_member(project_id: int, user_id: int, db: AsyncSession) -> bool:
    """Check if user is a member of the project."""
    result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )
    return result.scalar_one_or_none() is not None


async def is_project_manager(project_id: int, user_id: int, db: AsyncSession) -> bool:
    """Check if user is manager of the project."""
    result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
            ProjectMember.role == ProjectRole.manager,
        )
    )
    return result.scalar_one_or_none() is not None


async def is_dept_lead(user_id: int, department_id: int, db: AsyncSession) -> bool:
    """Check if user is lead or sub_admin of a department."""
    if not department_id:
        return False
    result = await db.execute(
        select(DepartmentMember).where(
            DepartmentMember.department_id == department_id,
            DepartmentMember.user_id == user_id,
            DepartmentMember.role.in_([DeptRole.lead, DeptRole.sub_admin]),
        )
    )
    return result.scalar_one_or_none() is not None


async def can_access_project(project: Project, user: User, org: Organization, db: AsyncSession) -> bool:
    """Check if user can view a project.

    Access hierarchy:
    - Superadmin / Org owner/admin → sees everything
    - Dept lead → sees all projects in their department
    - Project member → sees their project
    - Creator → sees their project
    - Otherwise → no access
    """
    # Superadmin / org owner
    if await has_full_access(user, org, db):
        return True
    # Department lead sees all projects in their dept
    if project.department_id:
        if await is_dept_lead(user.id, project.department_id, db):
            return True
        # Regular dept member sees project if they're a project member
        dept_ids = await get_user_department_ids(user.id, org.id, db)
        if project.department_id in dept_ids and await is_project_member(project.id, user.id, db):
            return True
    # Direct project member
    if await is_project_member(project.id, user.id, db):
        return True
    # Creator
    if project.created_by == user.id:
        return True
    return False


async def can_edit_project(project: Project, user: User, org: Organization, db: AsyncSession) -> bool:
    """Check if user can edit a project.

    Edit access:
    - Superadmin / Org owner → can edit anything
    - Dept lead → can edit projects in their department
    - Project manager → can edit their project
    - Creator → can edit their project
    - Regular member → cannot edit (only tasks assigned to them)
    """
    if await has_full_access(user, org, db):
        return True
    if project.created_by == user.id:
        return True
    if await is_project_manager(project.id, user.id, db):
        return True
    # Dept lead can edit projects in their department
    if project.department_id and await is_dept_lead(user.id, project.department_id, db):
        return True
    return False


async def can_manage_tasks(project: Project, user: User, org: Organization, db: AsyncSession) -> bool:
    """Check if user can create/assign/move tasks (not just edit own).

    - Superadmin / Org owner → yes
    - Dept lead → yes for dept projects
    - Project manager → yes
    - Developer/reviewer → can edit only tasks assigned to them
    """
    if await has_full_access(user, org, db):
        return True
    if await is_project_manager(project.id, user.id, db):
        return True
    if project.department_id and await is_dept_lead(user.id, project.department_id, db):
        return True
    return False


async def get_user_project_role(project_id: int, user_id: int, db: AsyncSession) -> str | None:
    """Get user's role within a project. Returns None if not a member."""
    result = await db.execute(
        select(ProjectMember.role).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    return row if isinstance(row, str) else row.value


def serialize_project(project: Project, members=None, tasks=None, current_user_role: str | None = None) -> dict:
    """Convert project to response dict with computed fields."""
    dept_name = project.department.name if project.department else None
    creator_name = project.creator.name if project.creator else None

    task_counts = {}
    if tasks:
        for t in tasks:
            s = t.status if isinstance(t.status, str) else t.status.value
            task_counts[s] = task_counts.get(s, 0) + 1

    return ProjectResponse(
        id=project.id,
        org_id=project.org_id,
        department_id=project.department_id,
        department_name=dept_name,
        name=project.name,
        prefix=project.prefix,
        description=project.description,
        status=project.status if isinstance(project.status, str) else project.status.value,
        priority=project.priority,
        client_name=project.client_name,
        progress_percent=project.progress_percent,
        progress_mode=project.progress_mode,
        start_date=project.start_date,
        target_date=project.target_date,
        predicted_date=project.predicted_date,
        completed_at=project.completed_at,
        tags=project.tags or [],
        color=project.color,
        created_by=project.created_by,
        creator_name=creator_name,
        created_at=project.created_at,
        updated_at=project.updated_at,
        member_count=len(members) if members else len(project.members) if hasattr(project, 'members') and project.members else 0,
        task_counts=task_counts,
        current_user_role=current_user_role,
    ).model_dump()
