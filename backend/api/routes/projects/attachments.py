"""
Task file attachment endpoints.
Upload, list, download, delete files on project tasks.
"""
from fastapi import Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from datetime import datetime
from pydantic import BaseModel
import os
import uuid
import aiofiles
import logging

logger = logging.getLogger("hr-analyzer.projects.attachments")

from .common import (
    Project, ProjectTask, User,
    can_access_project, can_edit_project, has_full_access,
    get_db, get_current_user, get_user_org,
    Organization,
)
from ...models.database import TaskAttachment

UPLOAD_BASE = "/tmp/hr_uploads/task_attachments"
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


class AttachmentResponse(BaseModel):
    id: int
    task_id: int
    user_id: int
    user_name: str | None = None
    filename: str
    original_filename: str
    file_size: int
    content_type: str | None = None
    created_at: datetime | None = None

    class Config:
        from_attributes = True


def _serialize_attachment(att: TaskAttachment) -> dict:
    return AttachmentResponse(
        id=att.id,
        task_id=att.task_id,
        user_id=att.user_id,
        user_name=att.user.name if att.user else None,
        filename=att.filename,
        original_filename=att.original_filename,
        file_size=att.file_size,
        content_type=att.content_type,
        created_at=att.created_at,
    ).model_dump()


async def _get_task_or_404(project_id: int, task_id: int, db: AsyncSession) -> ProjectTask:
    result = await db.execute(
        select(ProjectTask).where(
            ProjectTask.id == task_id,
            ProjectTask.project_id == project_id,
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


async def list_attachments(
    project_id: int,
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list:
    """List all attachments for a task."""
    org = await get_user_org(current_user, db)
    project = await db.get(Project, project_id)
    if not project or project.org_id != org.id:
        raise HTTPException(status_code=404, detail="Project not found")
    if not await can_access_project(project, current_user, org, db):
        raise HTTPException(status_code=403, detail="Access denied")

    await _get_task_or_404(project_id, task_id, db)

    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(TaskAttachment)
        .where(TaskAttachment.task_id == task_id)
        .options(selectinload(TaskAttachment.user))
        .order_by(TaskAttachment.created_at)
    )
    attachments = list(result.scalars().all())
    return [_serialize_attachment(a) for a in attachments]


async def upload_attachment(
    project_id: int,
    task_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Upload a file attachment to a task.

    Доступ: любой, кто видит проект (включая обычных участников) — чтобы
    можно было прикладывать картинки/файлы к комментариям.
    """
    org = await get_user_org(current_user, db)
    project = await db.get(Project, project_id)
    if not project or project.org_id != org.id:
        raise HTTPException(status_code=404, detail="Project not found")
    if not await can_access_project(project, current_user, org, db):
        raise HTTPException(status_code=403, detail="Access denied")

    await _get_task_or_404(project_id, task_id, db)

    # Read and validate file size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)}MB")

    original_filename = file.filename or "unnamed"
    unique_filename = f"{uuid.uuid4()}_{original_filename}"

    # Содержимое храним в БД (file_data), а не на диске: Railway /tmp
    # эфемерный — при каждом редеплое файлы исчезали и скрины в
    # комментариях ломались («битая картинка»).
    attachment = TaskAttachment(
        task_id=task_id,
        user_id=current_user.id,
        filename=unique_filename,
        original_filename=original_filename,
        file_size=len(content),
        content_type=file.content_type,
        storage_path=None,
        file_data=content,
    )
    db.add(attachment)
    await db.commit()
    await db.refresh(attachment)

    # Load user relationship for response
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(TaskAttachment)
        .where(TaskAttachment.id == attachment.id)
        .options(selectinload(TaskAttachment.user))
    )
    attachment = result.scalar_one()
    return _serialize_attachment(attachment)


async def download_attachment(
    project_id: int,
    task_id: int,
    attachment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    """Download a file attachment."""
    org = await get_user_org(current_user, db)
    project = await db.get(Project, project_id)
    if not project or project.org_id != org.id:
        raise HTTPException(status_code=404, detail="Project not found")
    if not await can_access_project(project, current_user, org, db):
        raise HTTPException(status_code=403, detail="Access denied")

    result = await db.execute(
        select(TaskAttachment).where(
            TaskAttachment.id == attachment_id,
            TaskAttachment.task_id == task_id,
        )
    )
    attachment = result.scalar_one_or_none()
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")

    media_type = attachment.content_type or "application/octet-stream"

    # Новые вложения — из БД (file_data). inline-disposition чтобы
    # картинки рендерились в <img>, а не качались.
    if attachment.file_data:
        from fastapi.responses import Response
        return Response(
            content=attachment.file_data,
            media_type=media_type,
            headers={
                "Content-Disposition": f'inline; filename="{attachment.original_filename}"',
                "Cache-Control": "private, max-age=86400",
            },
        )

    # Legacy: старые вложения на диске (могут быть стёрты редеплоем Railway).
    if attachment.storage_path and os.path.exists(attachment.storage_path):
        return FileResponse(
            path=attachment.storage_path,
            filename=attachment.original_filename,
            media_type=media_type,
        )

    raise HTTPException(
        status_code=404,
        detail="Файл недоступен — был загружен до обновления и не сохранился. Загрузите заново.",
    )


async def delete_attachment(
    project_id: int,
    task_id: int,
    attachment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a file attachment.

    Доступ: автор вложения, superadmin/owner или редактор проекта.
    """
    org = await get_user_org(current_user, db)
    project = await db.get(Project, project_id)
    if not project or project.org_id != org.id:
        raise HTTPException(status_code=404, detail="Project not found")
    if not await can_access_project(project, current_user, org, db):
        raise HTTPException(status_code=403, detail="Access denied")

    result = await db.execute(
        select(TaskAttachment).where(
            TaskAttachment.id == attachment_id,
            TaskAttachment.task_id == task_id,
        )
    )
    attachment = result.scalar_one_or_none()
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")

    is_author = attachment.user_id == current_user.id
    is_privileged = (
        await has_full_access(current_user, org, db)
        or await can_edit_project(project, current_user, org, db)
    )
    if not is_author and not is_privileged:
        raise HTTPException(status_code=403, detail="Can only delete your own attachments")

    # Remove file from disk
    if os.path.exists(attachment.storage_path):
        try:
            os.remove(attachment.storage_path)
        except OSError:
            logger.warning(f"Failed to remove file: {attachment.storage_path}")

    await db.delete(attachment)
    await db.commit()
