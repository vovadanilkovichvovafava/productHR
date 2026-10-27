"""
Custom fields per project — like ClickUp's custom field feature.
Each project can define fields (text, number, currency, select, date, checkbox)
and set values on individual tasks.
"""
from fastapi import Depends, HTTPException
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from pydantic import BaseModel
import logging

logger = logging.getLogger("hr-analyzer.projects.custom_fields")

from ...database import get_db
from ...models.database import (
    Project, ProjectCustomField, TaskCustomFieldValue, ProjectTask,
    User, Organization,
)
from ...services.auth import get_current_user, get_user_org
from .common import can_access_project, can_edit_project


# ── Schemas ───────────────────────────────────────────────────

class CustomFieldCreate(BaseModel):
    name: str
    field_type: str  # text, number, currency, select, date, checkbox
    options: Optional[List[str]] = []
    currency: Optional[str] = None
    sort_order: Optional[int] = 0
    is_required: Optional[bool] = False


class CustomFieldUpdate(BaseModel):
    name: Optional[str] = None
    field_type: Optional[str] = None
    options: Optional[List[str]] = None
    currency: Optional[str] = None
    sort_order: Optional[int] = None
    is_required: Optional[bool] = None


class CustomFieldResponse(BaseModel):
    id: int
    project_id: int
    name: str
    field_type: str
    options: list = []
    currency: Optional[str] = None
    sort_order: int = 0
    is_required: bool = False

    class Config:
        from_attributes = True


class FieldValueSet(BaseModel):
    value: Optional[str] = None


class TaskFieldValue(BaseModel):
    field_id: int
    field_name: str
    field_type: str
    value: Optional[str] = None
    currency: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────

VALID_FIELD_TYPES = {"text", "number", "currency", "select", "date", "checkbox"}


async def _get_project_or_404(project_id: int, db: AsyncSession) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")
    return project


async def _get_field_or_404(field_id: int, project_id: int, db: AsyncSession) -> ProjectCustomField:
    result = await db.execute(
        select(ProjectCustomField).where(
            ProjectCustomField.id == field_id,
            ProjectCustomField.project_id == project_id,
        )
    )
    field = result.scalar_one_or_none()
    if not field:
        raise HTTPException(404, "Custom field not found")
    return field


async def _get_task_or_404(task_id: int, project_id: int, db: AsyncSession) -> ProjectTask:
    result = await db.execute(
        select(ProjectTask).where(
            ProjectTask.id == task_id,
            ProjectTask.project_id == project_id,
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")
    return task


# ── Field Definition CRUD ─────────────────────────────────────

async def list_custom_fields(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org = await get_user_org(current_user, db)
    project = await _get_project_or_404(project_id, db)
    if not await can_access_project(project, current_user, org, db):
        raise HTTPException(403, "No access to this project")

    result = await db.execute(
        select(ProjectCustomField)
        .where(ProjectCustomField.project_id == project_id)
        .order_by(ProjectCustomField.sort_order, ProjectCustomField.id)
    )
    fields = result.scalars().all()
    return [CustomFieldResponse.model_validate(f).model_dump() for f in fields]


async def create_custom_field(
    project_id: int,
    data: CustomFieldCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org = await get_user_org(current_user, db)
    project = await _get_project_or_404(project_id, db)
    if not await can_edit_project(project, current_user, org, db):
        raise HTTPException(403, "No permission to edit this project")

    if data.field_type not in VALID_FIELD_TYPES:
        raise HTTPException(400, f"Invalid field_type. Must be one of: {', '.join(VALID_FIELD_TYPES)}")

    field = ProjectCustomField(
        project_id=project_id,
        name=data.name,
        field_type=data.field_type,
        options=data.options or [],
        currency=data.currency,
        sort_order=data.sort_order or 0,
        is_required=data.is_required or False,
    )
    db.add(field)
    await db.commit()
    await db.refresh(field)
    return CustomFieldResponse.model_validate(field).model_dump()


async def update_custom_field(
    project_id: int,
    field_id: int,
    data: CustomFieldUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org = await get_user_org(current_user, db)
    project = await _get_project_or_404(project_id, db)
    if not await can_edit_project(project, current_user, org, db):
        raise HTTPException(403, "No permission to edit this project")

    field = await _get_field_or_404(field_id, project_id, db)

    updates = data.model_dump(exclude_unset=True)
    if "field_type" in updates and updates["field_type"] not in VALID_FIELD_TYPES:
        raise HTTPException(400, f"Invalid field_type. Must be one of: {', '.join(VALID_FIELD_TYPES)}")

    for key, value in updates.items():
        setattr(field, key, value)

    await db.commit()
    await db.refresh(field)
    return CustomFieldResponse.model_validate(field).model_dump()


async def delete_custom_field(
    project_id: int,
    field_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org = await get_user_org(current_user, db)
    project = await _get_project_or_404(project_id, db)
    if not await can_edit_project(project, current_user, org, db):
        raise HTTPException(403, "No permission to edit this project")

    field = await _get_field_or_404(field_id, project_id, db)

    # Delete associated values first
    await db.execute(
        delete(TaskCustomFieldValue).where(TaskCustomFieldValue.field_id == field_id)
    )
    await db.delete(field)
    await db.commit()


# ── Task Field Values ─────────────────────────────────────────

async def get_task_field_values(
    project_id: int,
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org = await get_user_org(current_user, db)
    project = await _get_project_or_404(project_id, db)
    if not await can_access_project(project, current_user, org, db):
        raise HTTPException(403, "No access to this project")

    await _get_task_or_404(task_id, project_id, db)

    # Get all fields for this project
    fields_result = await db.execute(
        select(ProjectCustomField)
        .where(ProjectCustomField.project_id == project_id)
        .order_by(ProjectCustomField.sort_order, ProjectCustomField.id)
    )
    fields = fields_result.scalars().all()

    # Get existing values for this task
    values_result = await db.execute(
        select(TaskCustomFieldValue)
        .where(TaskCustomFieldValue.task_id == task_id)
    )
    values = {v.field_id: v.value for v in values_result.scalars().all()}

    return [
        TaskFieldValue(
            field_id=f.id,
            field_name=f.name,
            field_type=f.field_type,
            value=values.get(f.id),
            currency=f.currency,
        ).model_dump()
        for f in fields
    ]


async def set_task_field_value(
    project_id: int,
    task_id: int,
    field_id: int,
    data: FieldValueSet,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org = await get_user_org(current_user, db)
    project = await _get_project_or_404(project_id, db)
    if not await can_edit_project(project, current_user, org, db):
        raise HTTPException(403, "No permission to edit this project")

    await _get_task_or_404(task_id, project_id, db)
    field = await _get_field_or_404(field_id, project_id, db)

    # Validate required
    if field.is_required and (data.value is None or data.value.strip() == ""):
        raise HTTPException(400, f"Field '{field.name}' is required")

    # Validate select options
    if field.field_type == "select" and data.value and field.options:
        if data.value not in field.options:
            raise HTTPException(400, f"Value must be one of: {', '.join(field.options)}")

    # Upsert value
    result = await db.execute(
        select(TaskCustomFieldValue).where(
            TaskCustomFieldValue.task_id == task_id,
            TaskCustomFieldValue.field_id == field_id,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.value = data.value
    else:
        db.add(TaskCustomFieldValue(
            task_id=task_id,
            field_id=field_id,
            value=data.value,
        ))

    await db.commit()
    return {"status": "ok", "field_id": field_id, "value": data.value}
