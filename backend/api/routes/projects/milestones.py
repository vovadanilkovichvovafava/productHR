"""
Project milestone management endpoints.
"""
from fastapi import Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from .common import (
    logger, MilestoneCreate, MilestoneUpdate, MilestoneResponse,
    Project, ProjectMilestone, ProjectTask, User,
    can_edit_project,
    get_db, get_current_user, get_user_org,
)


def serialize_milestone(m: ProjectMilestone, task_count: int = 0) -> dict:
    return MilestoneResponse(
        id=m.id,
        project_id=m.project_id,
        name=m.name,
        description=m.description,
        target_date=m.target_date,
        completed_at=m.completed_at,
        sort_order=m.sort_order,
        created_at=m.created_at,
        task_count=task_count,
    ).model_dump()


async def list_milestones(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List milestones for a project."""
    result = await db.execute(
        select(ProjectMilestone)
        .where(ProjectMilestone.project_id == project_id)
        .order_by(ProjectMilestone.sort_order, ProjectMilestone.created_at)
    )
    milestones = list(result.scalars().all())

    # Get task counts per milestone
    count_result = await db.execute(
        select(ProjectTask.milestone_id, func.count(ProjectTask.id))
        .where(ProjectTask.project_id == project_id, ProjectTask.milestone_id.isnot(None))
        .group_by(ProjectTask.milestone_id)
    )
    counts = dict(count_result.all())

    return [serialize_milestone(m, counts.get(m.id, 0)) for m in milestones]


async def create_milestone(
    project_id: int,
    data: MilestoneCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a milestone."""
    org = await get_user_org(current_user, db)
    project = await db.get(Project, project_id)
    if not project or project.org_id != org.id:
        raise HTTPException(status_code=404, detail="Project not found")
    if not await can_edit_project(project, current_user, org, db):
        raise HTTPException(status_code=403, detail="Access denied")

    milestone = ProjectMilestone(
        project_id=project_id,
        name=data.name,
        description=data.description,
        target_date=data.target_date,
        sort_order=data.sort_order or 0,
    )
    db.add(milestone)
    await db.commit()
    await db.refresh(milestone)
    return serialize_milestone(milestone)


async def update_milestone(
    project_id: int,
    milestone_id: int,
    data: MilestoneUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a milestone."""
    org = await get_user_org(current_user, db)
    project = await db.get(Project, project_id)
    if not project or project.org_id != org.id:
        raise HTTPException(status_code=404, detail="Project not found")
    if not await can_edit_project(project, current_user, org, db):
        raise HTTPException(status_code=403, detail="Access denied")

    result = await db.execute(
        select(ProjectMilestone).where(
            ProjectMilestone.id == milestone_id,
            ProjectMilestone.project_id == project_id,
        )
    )
    milestone = result.scalar_one_or_none()
    if not milestone:
        raise HTTPException(status_code=404, detail="Milestone not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(milestone, key, value)

    await db.commit()
    await db.refresh(milestone)
    return serialize_milestone(milestone)


async def delete_milestone(
    project_id: int,
    milestone_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a milestone. Tasks linked to it will have milestone_id set to NULL."""
    org = await get_user_org(current_user, db)
    project = await db.get(Project, project_id)
    if not project or project.org_id != org.id:
        raise HTTPException(status_code=404, detail="Project not found")
    if not await can_edit_project(project, current_user, org, db):
        raise HTTPException(status_code=403, detail="Access denied")

    result = await db.execute(
        select(ProjectMilestone).where(
            ProjectMilestone.id == milestone_id,
            ProjectMilestone.project_id == project_id,
        )
    )
    milestone = result.scalar_one_or_none()
    if not milestone:
        raise HTTPException(status_code=404, detail="Milestone not found")

    await db.delete(milestone)
    await db.commit()
