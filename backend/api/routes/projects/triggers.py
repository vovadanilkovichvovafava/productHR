"""
Task trigger endpoints for testing auto-task creation from chat messages.
"""
from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional
import logging

from .common import (
    logger, Project,
    has_full_access, can_access_project,
    get_db, get_current_user, get_user_org,
    User, Organization,
)
from ...services.task_trigger import create_tasks_from_message, should_trigger


class TriggerTestRequest(BaseModel):
    text: str
    user_name: Optional[str] = None


class TriggerTestResponse(BaseModel):
    triggered: bool
    tasks_created: list


async def test_trigger(
    project_id: int,
    data: TriggerTestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Test the task trigger with a message.
    Useful for debugging trigger detection and AI parsing without Telegram."""

    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(400, "User not in an organization")

    project = await db.get(Project, project_id)
    if not project or project.org_id != org.id:
        raise HTTPException(404, "Project not found")

    if not await can_access_project(project, current_user, org, db):
        raise HTTPException(403, "Access denied")

    user_name = data.user_name or current_user.name

    result = await create_tasks_from_message(
        db=db,
        message_text=data.text,
        user_name=user_name,
        telegram_user_id=None,
        chat_id=None,
    )

    return {
        "triggered": len(result) > 0,
        "would_trigger": should_trigger(data.text),
        "tasks_created": result,
    }
