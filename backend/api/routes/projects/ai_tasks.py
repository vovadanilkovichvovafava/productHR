"""
AI-powered task creation from free-text plans.
Uses Claude API to parse text into structured tasks and detect duplicates.
"""
from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
from typing import Optional, List
import logging
import json

logger = logging.getLogger("hr-analyzer.projects.ai_tasks")

from ...database import get_db
from ...models.database import Project, ProjectTask, ProjectMember, User
from ...services.auth import get_current_user, get_user_org
from .common import can_access_project

# Try to import anthropic
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


class AIParsePlanRequest(BaseModel):
    text: str  # The raw plan text to parse
    default_status: Optional[str] = "todo"


class ParsedTaskItem(BaseModel):
    action: str  # "create", "update", "skip"
    title: str
    description: Optional[str] = None
    priority: int = 1  # 0-3
    estimated_hours: Optional[int] = None
    assignee_hint: Optional[str] = None  # name mentioned in text
    existing_task_id: Optional[int] = None  # if action=update, which task to update
    existing_task_title: Optional[str] = None  # for display
    reason: Optional[str] = None  # why this action


class AIParsePlanResponse(BaseModel):
    items: List[ParsedTaskItem]
    raw_ai_response: Optional[str] = None


class AICreateTasksRequest(BaseModel):
    items: List[ParsedTaskItem]
    default_status: Optional[str] = "todo"


async def ai_parse_plan(
    project_id: int,
    data: AIParsePlanRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Parse free-text plan into structured tasks using Claude AI.
    Compares with existing tasks to detect duplicates."""

    import os
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or not ANTHROPIC_AVAILABLE:
        raise HTTPException(400, "Anthropic API key not configured or anthropic package not installed")

    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(400, "User not in an organization")

    project = await db.get(Project, project_id)
    if not project or project.org_id != org.id:
        raise HTTPException(404, "Project not found")

    # Get existing tasks for duplicate detection
    result = await db.execute(
        select(ProjectTask)
        .where(ProjectTask.project_id == project_id)
        .options(selectinload(ProjectTask.assignee))
    )
    existing_tasks = list(result.scalars().all())
    existing_tasks_text = "\n".join([
        f"- ID:{t.id} | \"{t.title}\" | Статус: {t.status} | Приоритет: {t.priority} | Исполнитель: {t.assignee.name if t.assignee else 'нет'}"
        for t in existing_tasks
    ]) or "Нет существующих задач"

    # Get project members for assignee matching
    members_result = await db.execute(
        select(ProjectMember)
        .where(ProjectMember.project_id == project_id)
        .options(selectinload(ProjectMember.user))
    )
    members = list(members_result.scalars().all())
    members_text = "\n".join([
        f"- ID:{m.user_id} | {m.user.name if m.user else 'Unknown'} | Роль: {m.role}"
        for m in members
    ]) or "Нет участников"

    # Call Claude API
    client = anthropic.Anthropic(api_key=api_key)

    prompt = f"""Ты помощник по управлению проектами. Разбери текст плана на отдельные задачи.

ТЕКСТ ПЛАНА:
{data.text}

СУЩЕСТВУЮЩИЕ ЗАДАЧИ В ПРОЕКТЕ:
{existing_tasks_text}

УЧАСТНИКИ ПРОЕКТА:
{members_text}

Для каждого пункта плана определи:
1. Это НОВАЯ задача (action: "create") — если ничего похожего нет
2. Это ОБНОВЛЕНИЕ существующей (action: "update") — если есть похожая задача, которую нужно дополнить или изменить статус
3. Это ДУБЛИКАТ (action: "skip") — если точно такая задача уже есть

Верни JSON массив объектов. Каждый объект:
{{
  "action": "create" | "update" | "skip",
  "title": "Название задачи (чистое, без номеров)",
  "description": "Описание если есть детали" или null,
  "priority": 0-3 (0=низкий, 1=нормальный, 2=высокий, 3=критический),
  "estimated_hours": число часов или null,
  "assignee_hint": "имя человека если упоминается" или null,
  "existing_task_id": ID существующей задачи если action=update/skip или null,
  "existing_task_title": "название существующей задачи" или null,
  "reason": "почему это действие выбрано"
}}

Верни ТОЛЬКО JSON массив, без markdown, без комментариев."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )

        ai_text = response.content[0].text.strip()

        # Parse JSON from response (handle possible markdown wrapping)
        if ai_text.startswith("```"):
            ai_text = ai_text.split("```")[1]
            if ai_text.startswith("json"):
                ai_text = ai_text[4:]
            ai_text = ai_text.strip()

        items = json.loads(ai_text)
        parsed_items = [ParsedTaskItem(**item) for item in items]

        return AIParsePlanResponse(items=parsed_items, raw_ai_response=ai_text).model_dump()

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse AI response as JSON: {e}")
        raise HTTPException(500, f"AI returned invalid JSON: {str(e)}")
    except Exception as e:
        logger.error(f"Claude API error: {e}")
        raise HTTPException(500, f"AI service error: {str(e)}")


async def ai_create_tasks(
    project_id: int,
    data: AICreateTasksRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create/update tasks from AI-parsed plan items."""

    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(400, "User not in an organization")

    project = await db.get(Project, project_id)
    if not project or project.org_id != org.id:
        raise HTTPException(404, "Project not found")

    # Get members for assignee matching
    members_result = await db.execute(
        select(ProjectMember)
        .where(ProjectMember.project_id == project_id)
        .options(selectinload(ProjectMember.user))
    )
    members = list(members_result.scalars().all())
    member_map = {}
    for m in members:
        if m.user and m.user.name:
            member_map[m.user.name.lower()] = m.user_id

    created = 0
    updated = 0
    skipped = 0

    for item in data.items:
        if item.action == "skip":
            skipped += 1
            continue

        # Try to match assignee by name hint
        assignee_id = None
        if item.assignee_hint:
            hint = item.assignee_hint.lower()
            for name, uid in member_map.items():
                if hint in name or name in hint:
                    assignee_id = uid
                    break

        if item.action == "create":
            # Increment task counter
            project.task_counter = (project.task_counter or 0) + 1

            task = ProjectTask(
                project_id=project_id,
                task_number=project.task_counter,
                title=item.title,
                description=item.description,
                status=data.default_status or "todo",
                priority=item.priority,
                assignee_id=assignee_id,
                estimated_hours=item.estimated_hours,
                created_by=current_user.id,
            )
            db.add(task)
            created += 1

        elif item.action == "update" and item.existing_task_id:
            result = await db.execute(
                select(ProjectTask).where(
                    ProjectTask.id == item.existing_task_id,
                    ProjectTask.project_id == project_id,
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                # Update description if provided
                if item.description:
                    existing.description = (existing.description or "") + "\n\n" + item.description
                # Update priority if higher
                if item.priority > existing.priority:
                    existing.priority = item.priority
                # Update estimated hours if provided
                if item.estimated_hours:
                    existing.estimated_hours = item.estimated_hours
                # Set assignee if not set
                if assignee_id and not existing.assignee_id:
                    existing.assignee_id = assignee_id
                updated += 1

    await db.commit()

    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "total": len(data.items),
    }
