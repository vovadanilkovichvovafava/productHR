"""
Task comments — CRUD for comment threads on project tasks.
"""
import os
import re
from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing import List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel

from .common import (
    logger,
    Project, ProjectTask, User,
    has_full_access, can_access_project,
    get_db, get_current_user, get_user_org,
    Organization,
)
from ...models.database import TaskComment, Notification, OrgMember

MENTION_PATTERN = re.compile(r'@\[([^\]\n]+)\]')


async def _notify_mentions(
    db: AsyncSession,
    content: str,
    author: User,
    project: Project,
    task: ProjectTask,
    org: Organization,
    already_notified_ids: Optional[set[int]] = None,
    comment_id: Optional[int] = None,
) -> set[int]:
    """Парсим @[Name] в тексте и шлём в ЛС и в in-app каждому упомянутому.

    Возвращает множество user_id кого реально нашли — чтобы при update не слать повторно.
    """
    names = MENTION_PATTERN.findall(content)
    if not names:
        return set()

    notified: set[int] = set(already_notified_ids or set())
    newly_notified: set[int] = set()
    frontend_url = os.getenv("FRONTEND_URL", "https://enceladus.site")

    for raw_name in names:
        name = raw_name.strip()
        if not name:
            continue
        # exact match сперва, потом substring
        result = await db.execute(
            select(User)
            .join(OrgMember, OrgMember.user_id == User.id)
            .where(OrgMember.org_id == org.id)
            .where(User.name == name)
            .limit(1)
        )
        mentioned = result.scalar_one_or_none()
        if not mentioned:
            result = await db.execute(
                select(User)
                .join(OrgMember, OrgMember.user_id == User.id)
                .where(OrgMember.org_id == org.id)
                .where(User.name.ilike(f"%{name}%"))
                .limit(1)
            )
            mentioned = result.scalar_one_or_none()
        if not mentioned or mentioned.id == author.id or mentioned.id in notified:
            continue
        notified.add(mentioned.id)
        newly_notified.add(mentioned.id)

        # in-app уведомление с deep-link на конкретную задачу + коммент,
        # чтобы клик в панели уведомлений сразу открывал нужное место,
        # а не страницу проекта с поиском вручную.
        try:
            link = f"/projects/{project.id}/tasks/{task.id}"
            if comment_id:
                link += f"?comment={comment_id}"
            db.add(Notification(
                user_id=mentioned.id,
                type="comment_mention",
                title=f"Вас упомянули в задаче: {task.title}",
                message=(content[:280] + '…') if len(content) > 280 else content,
                link=link,
            ))
        except Exception as e:
            logger.warning(f"Failed to create in-app notification for mention: {e}")

        # Telegram DM
        try:
            from ...bot import send_telegram_notification
            snippet = content[:400].replace('<', '&lt;').replace('>', '&gt;')
            # Deep-link на саму задачу + якорь на конкретный коммент
            # (фронт умеет ?comment=, скроллит и подсвечивает).
            link_path = f"/projects/{project.id}/tasks/{task.id}"
            if comment_id:
                link_path += f"?comment={comment_id}"
            text = (
                f"\U0001f4ac <b>Вас упомянули в комментарии</b>\n\n"
                f"\U0001f464 {author.name}\n"
                f"\U0001f4dd Задача: {task.title}\n"
                f"\U0001f4c2 Проект: {project.name}\n\n"
                f"{snippet}\n\n"
                f'\U0001f517 <a href="{frontend_url}{link_path}">Открыть</a>'
            )
            await send_telegram_notification(mentioned.id, text)
        except Exception as e:
            logger.warning(f"Failed to send mention DM to {mentioned.name}: {e}")

    if newly_notified:
        logger.info(f"Mention notifications sent to {len(newly_notified)} user(s) for task {task.id}")
    return notified


# === Schemas ===

class CommentCreate(BaseModel):
    content: str


class CommentUpdate(BaseModel):
    content: str


class CommentResponse(BaseModel):
    id: int
    task_id: int
    user_id: int
    user_name: Optional[str] = None
    content: str
    edited_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# === Helpers ===

def serialize_comment(c: TaskComment) -> dict:
    return CommentResponse(
        id=c.id,
        task_id=c.task_id,
        user_id=c.user_id,
        user_name=c.user.name if c.user else None,
        content=c.content,
        edited_at=c.edited_at,
        created_at=c.created_at,
    ).model_dump()


async def _get_project_and_task(
    project_id: int,
    task_id: int,
    org: Organization,
    db: AsyncSession,
) -> tuple:
    """Fetch and validate project + task, raise 404 if not found."""
    project = await db.get(Project, project_id)
    if not project or project.org_id != org.id:
        raise HTTPException(status_code=404, detail="Project not found")

    result = await db.execute(
        select(ProjectTask).where(
            ProjectTask.id == task_id,
            ProjectTask.project_id == project_id,
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return project, task


# === Endpoints ===

async def list_comments(
    project_id: int,
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[dict]:
    """List all comments for a task, ordered by created_at."""
    org = await get_user_org(current_user, db)
    project, task = await _get_project_and_task(project_id, task_id, org, db)

    result = await db.execute(
        select(TaskComment)
        .where(TaskComment.task_id == task_id)
        .options(selectinload(TaskComment.user))
        .order_by(TaskComment.created_at)
    )
    comments = list(result.scalars().all())
    return [serialize_comment(c) for c in comments]


async def create_comment(
    project_id: int,
    task_id: int,
    data: CommentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Create a comment on a task. Any project member can comment."""
    org = await get_user_org(current_user, db)
    project, task = await _get_project_and_task(project_id, task_id, org, db)

    if not data.content or not data.content.strip():
        raise HTTPException(status_code=400, detail="Comment content cannot be empty")

    content = data.content.strip()
    comment = TaskComment(
        task_id=task_id,
        user_id=current_user.id,
        content=content,
    )
    db.add(comment)
    await db.flush()

    # Пинг упомянутых через @[Name] — передаём comment.id для deep-link
    try:
        await _notify_mentions(db, content, current_user, project, task, org, comment_id=comment.id)
    except Exception as e:
        logger.warning(f"notify_mentions failed on create: {e}")

    await db.commit()
    await db.refresh(comment)

    # Пинг в рабочий чат, откуда родилась задача: утром человек написал план,
    # бот завёл задачи, а обсуждение идёт там же (владелец, 28.09.2026).
    source_chat_id = getattr(task, "source_chat_id", None)
    if source_chat_id:
        try:
            from ...bot import notify_comment_to_chat

            task_key = (
                f"{project.prefix}-{task.task_number}"
                if project.prefix and task.task_number else f"#{task.id}"
            )
            await notify_comment_to_chat(
                chat_id=source_chat_id,
                author=current_user.name or "—",
                project_name=project.name,
                task_key=task_key,
                task_title=task.title,
                content=content,
                project_id=project.id,
                task_id=task.id,
            )
        except Exception as e:
            logger.warning(f"Пинг о комментарии не ушёл в чат {source_chat_id}: {e}")

    # Reload with user relationship
    result = await db.execute(
        select(TaskComment)
        .where(TaskComment.id == comment.id)
        .options(selectinload(TaskComment.user))
    )
    comment = result.scalar_one()
    return serialize_comment(comment)


async def update_comment(
    project_id: int,
    task_id: int,
    comment_id: int,
    data: CommentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Edit a comment. Only the author or admin can edit."""
    org = await get_user_org(current_user, db)
    project, task = await _get_project_and_task(project_id, task_id, org, db)

    result = await db.execute(
        select(TaskComment)
        .where(TaskComment.id == comment_id, TaskComment.task_id == task_id)
        .options(selectinload(TaskComment.user))
    )
    comment = result.scalar_one_or_none()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    # Only author or admin can edit
    is_admin = await has_full_access(current_user, org, db)
    if comment.user_id != current_user.id and not is_admin:
        raise HTTPException(status_code=403, detail="Can only edit your own comments")

    if not data.content or not data.content.strip():
        raise HTTPException(status_code=400, detail="Comment content cannot be empty")

    # Вычисляем кого уже упоминали в ПРОШЛОЙ версии, чтобы не слать DM повторно
    previously_mentioned_names = set(MENTION_PATTERN.findall(comment.content or ""))
    previously_notified_ids: set[int] = set()
    if previously_mentioned_names:
        for name in previously_mentioned_names:
            res = await db.execute(
                select(User.id)
                .join(OrgMember, OrgMember.user_id == User.id)
                .where(OrgMember.org_id == org.id)
                .where(User.name == name)
                .limit(1)
            )
            uid = res.scalar_one_or_none()
            if uid:
                previously_notified_ids.add(uid)

    new_content = data.content.strip()
    comment.content = new_content
    comment.edited_at = datetime.utcnow()

    # Пинг только НОВЫМ упомянутым
    try:
        await _notify_mentions(
            db, new_content, current_user, project, task, org,
            already_notified_ids=previously_notified_ids,
            comment_id=comment.id,
        )
    except Exception as e:
        logger.warning(f"notify_mentions failed on update: {e}")

    await db.commit()
    await db.refresh(comment)

    return serialize_comment(comment)


async def delete_comment(
    project_id: int,
    task_id: int,
    comment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a comment. Only the author or admin can delete."""
    org = await get_user_org(current_user, db)
    project, task = await _get_project_and_task(project_id, task_id, org, db)

    result = await db.execute(
        select(TaskComment).where(TaskComment.id == comment_id, TaskComment.task_id == task_id)
    )
    comment = result.scalar_one_or_none()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    # Only author or admin can delete
    is_admin = await has_full_access(current_user, org, db)
    if comment.user_id != current_user.id and not is_admin:
        raise HTTPException(status_code=403, detail="Can only delete your own comments")

    await db.delete(comment)
    await db.commit()
