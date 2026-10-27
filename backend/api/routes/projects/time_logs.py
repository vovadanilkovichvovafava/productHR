"""
Task time logging endpoints.
"""
from fastapi import Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .common import (
    logger, TimeLogCreate, TimeLogResponse,
    Project, ProjectTask, TaskTimeLog, User,
    get_db, get_current_user, get_user_org,
)


def serialize_time_log(tl: TaskTimeLog) -> dict:
    return TimeLogResponse(
        id=tl.id,
        task_id=tl.task_id,
        user_id=tl.user_id,
        user_name=tl.user.name if tl.user else None,
        hours=tl.hours,
        date=tl.date,
        note=tl.note,
        created_at=tl.created_at,
    ).model_dump()


async def create_time_log(
    project_id: int,
    task_id: int,
    data: TimeLogCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Log time spent on a task."""
    result = await db.execute(
        select(ProjectTask).where(
            ProjectTask.id == task_id,
            ProjectTask.project_id == project_id,
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    time_log = TaskTimeLog(
        task_id=task_id,
        user_id=current_user.id,
        hours=data.hours,
        date=data.date,
        note=data.note,
    )
    db.add(time_log)
    await db.commit()

    result = await db.execute(
        select(TaskTimeLog)
        .where(TaskTimeLog.id == time_log.id)
        .options(selectinload(TaskTimeLog.user))
    )
    time_log = result.scalar_one()
    return serialize_time_log(time_log)


async def list_task_time_logs(
    project_id: int,
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List time logs for a task."""
    result = await db.execute(
        select(TaskTimeLog)
        .where(TaskTimeLog.task_id == task_id)
        .options(selectinload(TaskTimeLog.user))
        .order_by(TaskTimeLog.date.desc())
    )
    logs = list(result.scalars().all())
    return [serialize_time_log(tl) for tl in logs]


async def delete_time_log(
    project_id: int,
    task_id: int,
    log_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a time log entry (only own entries unless admin)."""
    result = await db.execute(
        select(TaskTimeLog).where(TaskTimeLog.id == log_id, TaskTimeLog.task_id == task_id)
    )
    time_log = result.scalar_one_or_none()
    if not time_log:
        raise HTTPException(status_code=404, detail="Time log not found")

    if time_log.user_id != current_user.id and current_user.role.value != "superadmin":
        raise HTTPException(status_code=403, detail="Can only delete own time logs")

    await db.delete(time_log)
    await db.commit()


async def get_project_effort(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get effort summary per member for the entire project."""
    result = await db.execute(
        select(
            TaskTimeLog.user_id,
            User.name.label("user_name"),
            func.sum(TaskTimeLog.hours).label("total_hours"),
            func.count(TaskTimeLog.id).label("entries"),
        )
        .join(ProjectTask, ProjectTask.id == TaskTimeLog.task_id)
        .join(User, User.id == TaskTimeLog.user_id)
        .where(ProjectTask.project_id == project_id)
        .group_by(TaskTimeLog.user_id, User.name)
        .order_by(func.sum(TaskTimeLog.hours).desc())
    )
    rows = result.all()
    return [
        {
            "user_id": row.user_id,
            "user_name": row.user_name,
            "total_hours": row.total_hours,
            "entries": row.entries,
        }
        for row in rows
    ]
