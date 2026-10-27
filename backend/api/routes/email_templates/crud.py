"""
Email Templates CRUD Operations

Provides endpoints for creating, reading, updating, and deleting email templates.
"""

from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from pydantic import BaseModel, EmailStr

from ...database import get_db
from ...models.database import User, UserRole
from ...models.email_templates import EmailTemplate, EmailTemplateType
from ...services.auth import get_current_user, get_user_org
from ...utils.logging import get_logger

logger = get_logger("email-templates")

router = APIRouter()


# Schemas
class EmailTemplateCreate(BaseModel):
    name: str
    description: Optional[str] = None
    template_type: EmailTemplateType = EmailTemplateType.custom
    subject: str
    body_html: str
    body_text: Optional[str] = None
    is_active: bool = True
    is_default: bool = False
    variables: List[str] = []
    tags: List[str] = []


class EmailTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    template_type: Optional[EmailTemplateType] = None
    subject: Optional[str] = None
    body_html: Optional[str] = None
    body_text: Optional[str] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None
    variables: Optional[List[str]] = None
    tags: Optional[List[str]] = None


class EmailTemplateResponse(BaseModel):
    id: int
    org_id: int
    name: str
    description: Optional[str]
    template_type: str
    subject: str
    body_html: str
    body_text: Optional[str]
    is_active: bool
    is_default: bool
    variables: List[str]
    tags: List[str]
    created_by: Optional[int]
    updated_by: Optional[int]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Variable extraction helper
def extract_variables(text: str) -> List[str]:
    """Extract variable placeholders from text (e.g., {{candidate_name}})."""
    import re
    pattern = r'\{\{(\w+)\}\}'
    return list(set(re.findall(pattern, text)))


@router.get("", response_model=List[EmailTemplateResponse])
async def list_templates(
    template_type: Optional[EmailTemplateType] = None,
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List email templates for the current organization."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    stmt = select(EmailTemplate).where(EmailTemplate.org_id == org.id)

    if template_type:
        stmt = stmt.where(EmailTemplate.template_type == template_type)

    if is_active is not None:
        stmt = stmt.where(EmailTemplate.is_active == is_active)

    if search:
        stmt = stmt.where(
            EmailTemplate.name.ilike(f"%{search}%") |
            EmailTemplate.description.ilike(f"%{search}%")
        )

    stmt = stmt.order_by(EmailTemplate.name).offset(skip).limit(limit)

    result = await db.execute(stmt)
    templates = result.scalars().all()

    return [EmailTemplateResponse.model_validate(t) for t in templates]


@router.post("", response_model=EmailTemplateResponse, status_code=201)
async def create_template(
    data: EmailTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new email template."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Check for duplicate name
    existing = await db.execute(
        select(EmailTemplate).where(
            EmailTemplate.org_id == org.id,
            EmailTemplate.name == data.name
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Template with this name already exists")

    # Auto-extract variables if not provided
    variables = data.variables
    if not variables:
        variables = extract_variables(data.subject + " " + data.body_html)

    # If setting as default, unset other defaults of same type
    if data.is_default:
        await db.execute(
            select(EmailTemplate)
            .where(
                EmailTemplate.org_id == org.id,
                EmailTemplate.template_type == data.template_type,
                EmailTemplate.is_default == True
            )
        )
        existing_defaults = await db.execute(
            select(EmailTemplate).where(
                EmailTemplate.org_id == org.id,
                EmailTemplate.template_type == data.template_type,
                EmailTemplate.is_default == True
            )
        )
        for tpl in existing_defaults.scalars():
            tpl.is_default = False

    template = EmailTemplate(
        org_id=org.id,
        name=data.name,
        description=data.description,
        template_type=data.template_type,
        subject=data.subject,
        body_html=data.body_html,
        body_text=data.body_text,
        is_active=data.is_active,
        is_default=data.is_default,
        variables=variables,
        tags=data.tags,
        created_by=current_user.id,
        updated_by=current_user.id,
    )

    db.add(template)
    await db.commit()
    await db.refresh(template)

    logger.info(f"Created email template: {template.name} (id={template.id}) by user {current_user.id}")

    return EmailTemplateResponse.model_validate(template)


@router.get("/types/list", response_model=List[dict])
async def list_template_types(
    current_user: User = Depends(get_current_user),
):
    """List available template types with labels."""
    types = [
        {"value": "interview_invite", "label": "Приглашение на собеседование"},
        {"value": "interview_reminder", "label": "Напоминание о собеседовании"},
        {"value": "offer", "label": "Оффер"},
        {"value": "rejection", "label": "Отказ"},
        {"value": "screening_request", "label": "Запрос на скрининг"},
        {"value": "test_assignment", "label": "Тестовое задание"},
        {"value": "welcome", "label": "Приветственное письмо"},
        {"value": "follow_up", "label": "Фоллоу-ап"},
        {"value": "custom", "label": "Пользовательский"},
    ]
    return types


@router.get("/variables/list", response_model=List[dict])
async def list_available_variables(
    current_user: User = Depends(get_current_user),
):
    """List available template variables with descriptions."""
    variables = [
        {"name": "candidate_name", "description": "Имя кандидата", "example": "Имя кандидата"},
        {"name": "candidate_email", "description": "Email кандидата", "example": "candidate@example.com"},
        {"name": "vacancy_title", "description": "Название вакансии", "example": "Senior Python Developer"},
        {"name": "company_name", "description": "Название компании", "example": "ООО Компания"},
        {"name": "interview_date", "description": "Дата собеседования", "example": "15 января 2026"},
        {"name": "interview_time", "description": "Время собеседования", "example": "14:00"},
        {"name": "interview_link", "description": "Ссылка на собеседование", "example": "https://meet.google.com/xxx"},
        {"name": "hr_name", "description": "Имя HR менеджера", "example": "Имя HR менеджера"},
        {"name": "hr_email", "description": "Email HR менеджера", "example": "hr@company.com"},
        {"name": "salary_offer", "description": "Предложенная зарплата", "example": "150 000 ₽"},
        {"name": "start_date", "description": "Дата начала работы", "example": "1 февраля 2026"},
        {"name": "rejection_reason", "description": "Причина отказа", "example": "Недостаточный опыт"},
    ]
    return variables


@router.get("/{template_id}", response_model=EmailTemplateResponse)
async def get_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific email template."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    result = await db.execute(
        select(EmailTemplate).where(
            EmailTemplate.id == template_id,
            EmailTemplate.org_id == org.id
        )
    )
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    return EmailTemplateResponse.model_validate(template)


@router.put("/{template_id}", response_model=EmailTemplateResponse)
async def update_template(
    template_id: int,
    data: EmailTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update an email template."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    result = await db.execute(
        select(EmailTemplate).where(
            EmailTemplate.id == template_id,
            EmailTemplate.org_id == org.id
        )
    )
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Check for duplicate name if changing
    if data.name and data.name != template.name:
        existing = await db.execute(
            select(EmailTemplate).where(
                EmailTemplate.org_id == org.id,
                EmailTemplate.name == data.name,
                EmailTemplate.id != template_id
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Template with this name already exists")

    # If setting as default, unset other defaults
    if data.is_default:
        tpl_type = data.template_type or template.template_type
        existing_defaults = await db.execute(
            select(EmailTemplate).where(
                EmailTemplate.org_id == org.id,
                EmailTemplate.template_type == tpl_type,
                EmailTemplate.is_default == True,
                EmailTemplate.id != template_id
            )
        )
        for tpl in existing_defaults.scalars():
            tpl.is_default = False

    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(template, key, value)

    # Re-extract variables if content changed
    if data.subject or data.body_html:
        template.variables = extract_variables(
            (data.subject or template.subject) + " " + (data.body_html or template.body_html)
        )

    template.updated_by = current_user.id

    await db.commit()
    await db.refresh(template)

    logger.info(f"Updated email template: {template.name} (id={template.id}) by user {current_user.id}")

    return EmailTemplateResponse.model_validate(template)


@router.delete("/{template_id}", status_code=204)
async def delete_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete an email template."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    result = await db.execute(
        select(EmailTemplate).where(
            EmailTemplate.id == template_id,
            EmailTemplate.org_id == org.id
        )
    )
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    await db.delete(template)
    await db.commit()

    logger.info(f"Deleted email template: {template.name} (id={template_id}) by user {current_user.id}")


@router.post("/{template_id}/duplicate", response_model=EmailTemplateResponse, status_code=201)
async def duplicate_template(
    template_id: int,
    new_name: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Duplicate an email template."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    result = await db.execute(
        select(EmailTemplate).where(
            EmailTemplate.id == template_id,
            EmailTemplate.org_id == org.id
        )
    )
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Generate unique name
    if not new_name:
        base_name = f"{template.name} (копия)"
        new_name = base_name
        counter = 1
        while True:
            existing = await db.execute(
                select(EmailTemplate).where(
                    EmailTemplate.org_id == org.id,
                    EmailTemplate.name == new_name
                )
            )
            if not existing.scalar_one_or_none():
                break
            counter += 1
            new_name = f"{base_name} {counter}"

    new_template = EmailTemplate(
        org_id=org.id,
        name=new_name,
        description=template.description,
        template_type=template.template_type,
        subject=template.subject,
        body_html=template.body_html,
        body_text=template.body_text,
        is_active=template.is_active,
        is_default=False,  # Never duplicate as default
        variables=template.variables,
        tags=template.tags,
        created_by=current_user.id,
        updated_by=current_user.id,
    )

    db.add(new_template)
    await db.commit()
    await db.refresh(new_template)

    logger.info(f"Duplicated email template: {template.name} → {new_name} (id={new_template.id}) by user {current_user.id}")

    return EmailTemplateResponse.model_validate(new_template)
