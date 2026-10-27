"""
Project analytics endpoints.
"""
from fastapi import Depends, HTTPException
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone, timedelta

from .common import (
    logger,
    Project, ProjectStatus, ProjectMember, ProjectRole,
    ProjectTask, TaskStatus, User,
    DepartmentMember, DeptRole,
    has_full_access,
    get_db, get_current_user, get_user_org,
)


async def get_projects_overview(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Overview analytics: total projects, by status, total effort."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=400, detail="User not in an organization")

    # Projects by status
    result = await db.execute(
        select(Project.status, func.count(Project.id))
        .where(Project.org_id == org.id)
        .group_by(Project.status)
    )
    status_counts = {row[0] if isinstance(row[0], str) else row[0].value: row[1] for row in result.all()}

    # Total tasks
    result = await db.execute(
        select(
            func.count(ProjectTask.id).label("total_tasks"),
            func.count(case((ProjectTask.status == TaskStatus.done, 1))).label("done_tasks"),
            func.count(case((ProjectTask.status == TaskStatus.in_progress, 1))).label("in_progress_tasks"),
        )
        .join(Project, Project.id == ProjectTask.project_id)
        .where(Project.org_id == org.id)
    )
    task_row = result.one()

    # Projects with upcoming deadlines (next 7 days)
    now = datetime.utcnow()
    week_from_now = now + timedelta(days=7)
    result = await db.execute(
        select(func.count(Project.id))
        .where(
            Project.org_id == org.id,
            Project.target_date.isnot(None),
            Project.target_date <= week_from_now,
            Project.status.in_([ProjectStatus.planning, ProjectStatus.active]),
        )
    )
    upcoming_deadlines = result.scalar() or 0

    return {
        "total_projects": sum(status_counts.values()),
        "status_counts": status_counts,
        "total_tasks": task_row.total_tasks,
        "done_tasks": task_row.done_tasks,
        "in_progress_tasks": task_row.in_progress_tasks,
        "upcoming_deadlines": upcoming_deadlines,
    }


async def get_resource_allocation(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Resource allocation: who's working on what, at what capacity."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=400, detail="User not in an organization")

    # Scope: платформ-админ видит всю org; лид видит участников своих отделов.
    # Обычный member на эту страницу попадать не должен (sidebar её прячет),
    # но на всякий случай — вернём пусто, чтобы не светить чужую команду.
    full_access = await has_full_access(current_user, org, db)
    allowed_user_ids: list[int] | None = None
    if not full_access:
        admin_dept_ids_result = await db.execute(
            select(DepartmentMember.department_id).where(
                DepartmentMember.user_id == current_user.id,
                DepartmentMember.role.in_([DeptRole.lead, DeptRole.sub_admin]),
            )
        )
        admin_dept_ids = [r for r in admin_dept_ids_result.scalars().all()]
        if not admin_dept_ids:
            return []
        member_ids_result = await db.execute(
            select(DepartmentMember.user_id).where(
                DepartmentMember.department_id.in_(admin_dept_ids)
            )
        )
        allowed_user_ids = list({uid for uid in member_ids_result.scalars().all()})
        # Лид сам тоже в выдаче
        allowed_user_ids.append(current_user.id)
        if not allowed_user_ids:
            return []

    query = (
        select(
            ProjectMember.user_id,
            User.name.label("user_name"),
            Project.id.label("project_id"),
            Project.name.label("project_name"),
            Project.status.label("project_status"),
            ProjectMember.role,
            ProjectMember.allocation_percent,
        )
        .join(Project, Project.id == ProjectMember.project_id)
        .join(User, User.id == ProjectMember.user_id)
        .where(
            Project.org_id == org.id,
            Project.status.in_([ProjectStatus.planning, ProjectStatus.active]),
        )
        .order_by(User.name, Project.name)
    )
    if allowed_user_ids is not None:
        query = query.where(ProjectMember.user_id.in_(allowed_user_ids))
    result = await db.execute(query)
    rows = result.all()

    # Group by user — calculate fair allocation if all are default 100%
    users = {}
    for row in rows:
        uid = row.user_id
        if uid not in users:
            users[uid] = {
                "user_id": uid,
                "user_name": row.user_name,
                "projects": [],
                "total_allocation": 0,
            }
        users[uid]["projects"].append({
            "project_id": row.project_id,
            "project_name": row.project_name,
            "project_status": row.project_status if isinstance(row.project_status, str) else row.project_status.value,
            "role": row.role if isinstance(row.role, str) else row.role.value,
            "allocation_percent": row.allocation_percent,
        })

    # Calculate total_allocation: if all allocations are default 100%, auto-split evenly
    for uid, user_data in users.items():
        projs = user_data["projects"]
        all_default = all(p["allocation_percent"] == 100 for p in projs)
        if all_default and len(projs) > 1:
            # Auto-split: 100% / N projects
            split = round(100 / len(projs))
            for p in projs:
                p["allocation_percent"] = split
            user_data["total_allocation"] = min(100, split * len(projs))
        else:
            user_data["total_allocation"] = sum(p["allocation_percent"] for p in projs)

    return list(users.values())


async def get_project_analytics(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Detailed analytics for a specific project: task breakdown, velocity, prediction."""
    org = await get_user_org(current_user, db)
    project = await db.get(Project, project_id)
    if not project or project.org_id != org.id:
        raise HTTPException(status_code=404, detail="Project not found")

    # Task counts by status
    result = await db.execute(
        select(ProjectTask.status, func.count(ProjectTask.id))
        .where(ProjectTask.project_id == project_id)
        .group_by(ProjectTask.status)
    )
    task_counts = {row[0] if isinstance(row[0], str) else row[0].value: row[1] for row in result.all()}

    # Velocity: completed tasks / elapsed days
    predicted_date = None
    velocity = None
    if project.start_date:
        elapsed_days = (datetime.utcnow() - project.start_date).days
        done = task_counts.get("done", 0)
        total = sum(v for k, v in task_counts.items() if k != "cancelled")
        remaining = total - done

        if elapsed_days >= 7 and done >= 3:
            velocity = round(done / elapsed_days, 2)
            if velocity > 0:
                days_remaining = round(remaining / velocity)
                predicted_date = (datetime.utcnow() + timedelta(days=days_remaining)).isoformat()

    # Effort per member
    result = await db.execute(
        select(
            User.name,
            func.sum(func.coalesce(ProjectMember.allocation_percent, 100)).label("allocation"),
            func.count(ProjectTask.id).filter(ProjectTask.assignee_id == ProjectMember.user_id).label("assigned_tasks"),
        )
        .join(ProjectMember, ProjectMember.project_id == project_id)
        .join(User, User.id == ProjectMember.user_id)
        .outerjoin(ProjectTask, (ProjectTask.project_id == project_id) & (ProjectTask.assignee_id == ProjectMember.user_id))
        .where(ProjectMember.project_id == project_id)
        .group_by(User.name, ProjectMember.allocation_percent)
    )

    return {
        "project_id": project_id,
        "task_counts": task_counts,
        "velocity_tasks_per_day": velocity,
        "predicted_date": predicted_date,
        "progress_percent": project.progress_percent,
    }
