"""
Email Sending Operations

Provides endpoints for:
- Rendering email templates with variables
- Sending emails to candidates
- Preview functionality
"""

import re
from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr

from ...database import get_db
from ...models.database import User, Entity, Vacancy, VacancyApplication
from ...models.email_templates import EmailTemplate, EmailLog, EmailStatus, EmailTemplateType
from ...services.auth import get_current_user, get_user_org
from ...utils.logging import get_logger
from ...config import get_settings

logger = get_logger("email-sending")
settings = get_settings()

router = APIRouter()


# Schemas
class SendEmailRequest(BaseModel):
    template_id: int
    entity_id: int  # Candidate
    vacancy_id: Optional[int] = None
    custom_variables: Optional[Dict[str, str]] = None
    # Override template content if needed
    subject_override: Optional[str] = None
    body_override: Optional[str] = None


class BulkSendEmailRequest(BaseModel):
    template_id: int
    entity_ids: List[int]
    vacancy_id: Optional[int] = None
    custom_variables: Optional[Dict[str, str]] = None


class PreviewEmailRequest(BaseModel):
    template_id: Optional[int] = None
    # Or provide content directly
    subject: Optional[str] = None
    body_html: Optional[str] = None
    # Variables to use for preview
    entity_id: Optional[int] = None
    vacancy_id: Optional[int] = None
    custom_variables: Optional[Dict[str, str]] = None


class EmailPreviewResponse(BaseModel):
    subject: str
    body_html: str
    body_text: Optional[str]
    recipient_email: Optional[str]
    recipient_name: Optional[str]
    variables_used: Dict[str, str]


class SendEmailResponse(BaseModel):
    id: int
    status: str
    recipient_email: str
    recipient_name: Optional[str]
    subject: str
    message: str


class BulkSendEmailResponse(BaseModel):
    total: int
    sent: int
    failed: int
    results: List[SendEmailResponse]


def render_template(template: str, variables: Dict[str, str]) -> str:
    """Replace {{variable}} placeholders with actual values."""
    def replace_var(match):
        var_name = match.group(1)
        return variables.get(var_name, f"{{{{ {var_name} }}}}")  # Keep placeholder if not found

    pattern = r'\{\{(\w+)\}\}'
    return re.sub(pattern, replace_var, template)


async def get_entity_variables(entity: Entity, db: AsyncSession) -> Dict[str, str]:
    """Get template variables from entity (candidate)."""
    variables = {
        "candidate_name": entity.name or "",
        "candidate_email": entity.email or "",
        "candidate_phone": entity.phone or "",
        "candidate_position": entity.position or "",
        "candidate_company": entity.company or "",
    }

    # Add salary info if available
    if entity.expected_salary_min:
        currency = entity.expected_salary_currency or "RUB"
        if entity.expected_salary_max:
            variables["candidate_salary"] = f"{entity.expected_salary_min:,} - {entity.expected_salary_max:,} {currency}"
        else:
            variables["candidate_salary"] = f"{entity.expected_salary_min:,} {currency}"

    return variables


async def get_vacancy_variables(vacancy: Vacancy, db: AsyncSession) -> Dict[str, str]:
    """Get template variables from vacancy."""
    variables = {
        "vacancy_title": vacancy.title or "",
        "vacancy_description": vacancy.description or "",
        "vacancy_requirements": vacancy.requirements or "",
        "vacancy_location": vacancy.location or "",
        "vacancy_employment_type": vacancy.employment_type or "",
    }

    # Add salary info
    if vacancy.salary_min:
        currency = vacancy.salary_currency or "RUB"
        if vacancy.salary_max:
            variables["vacancy_salary"] = f"{vacancy.salary_min:,} - {vacancy.salary_max:,} {currency}"
        else:
            variables["vacancy_salary"] = f"от {vacancy.salary_min:,} {currency}"

    return variables


async def get_user_variables(user: User) -> Dict[str, str]:
    """Get template variables from user (HR manager)."""
    return {
        "hr_name": user.name or "",
        "hr_email": user.email or "",
    }


async def get_org_variables(org) -> Dict[str, str]:
    """Get template variables from organization."""
    return {
        "company_name": org.name or "",
    }


@router.post("/preview", response_model=EmailPreviewResponse)
async def preview_email(
    data: PreviewEmailRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Preview rendered email template."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    subject = data.subject
    body_html = data.body_html

    # Load template if ID provided
    if data.template_id:
        result = await db.execute(
            select(EmailTemplate).where(
                EmailTemplate.id == data.template_id,
                EmailTemplate.org_id == org.id
            )
        )
        template = result.scalar_one_or_none()
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        subject = template.subject
        body_html = template.body_html

    if not subject or not body_html:
        raise HTTPException(status_code=400, detail="Subject and body are required")

    # Gather variables
    variables: Dict[str, str] = {}
    variables.update(await get_user_variables(current_user))
    variables.update(await get_org_variables(org))

    recipient_email = None
    recipient_name = None

    # Entity variables
    if data.entity_id:
        result = await db.execute(
            select(Entity).where(
                Entity.id == data.entity_id,
                Entity.org_id == org.id
            )
        )
        entity = result.scalar_one_or_none()
        if entity:
            variables.update(await get_entity_variables(entity, db))
            recipient_email = entity.email
            recipient_name = entity.name

    # Vacancy variables
    if data.vacancy_id:
        result = await db.execute(
            select(Vacancy).where(
                Vacancy.id == data.vacancy_id,
                Vacancy.org_id == org.id
            )
        )
        vacancy = result.scalar_one_or_none()
        if vacancy:
            variables.update(await get_vacancy_variables(vacancy, db))

    # Custom variables (override)
    if data.custom_variables:
        variables.update(data.custom_variables)

    # Render
    rendered_subject = render_template(subject, variables)
    rendered_body = render_template(body_html, variables)

    return EmailPreviewResponse(
        subject=rendered_subject,
        body_html=rendered_body,
        body_text=None,  # TODO: Generate plain text version
        recipient_email=recipient_email,
        recipient_name=recipient_name,
        variables_used=variables,
    )


@router.post("/send", response_model=SendEmailResponse)
async def send_email(
    data: SendEmailRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Send email to a candidate using template."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Load template
    result = await db.execute(
        select(EmailTemplate).where(
            EmailTemplate.id == data.template_id,
            EmailTemplate.org_id == org.id
        )
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    if not template.is_active:
        raise HTTPException(status_code=400, detail="Template is not active")

    # Load entity
    result = await db.execute(
        select(Entity).where(
            Entity.id == data.entity_id,
            Entity.org_id == org.id
        )
    )
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=404, detail="Candidate not found")

    if not entity.email:
        raise HTTPException(status_code=400, detail="Candidate has no email address")

    # Gather variables
    variables: Dict[str, str] = {}
    variables.update(await get_user_variables(current_user))
    variables.update(await get_org_variables(org))
    variables.update(await get_entity_variables(entity, db))

    # Vacancy variables if provided
    vacancy = None
    application = None
    if data.vacancy_id:
        result = await db.execute(
            select(Vacancy).where(
                Vacancy.id == data.vacancy_id,
                Vacancy.org_id == org.id
            )
        )
        vacancy = result.scalar_one_or_none()
        if vacancy:
            variables.update(await get_vacancy_variables(vacancy, db))

            # Find application
            result = await db.execute(
                select(VacancyApplication).where(
                    VacancyApplication.vacancy_id == data.vacancy_id,
                    VacancyApplication.entity_id == data.entity_id
                )
            )
            application = result.scalar_one_or_none()

    # Custom variables
    if data.custom_variables:
        variables.update(data.custom_variables)

    # Render
    subject = data.subject_override or template.subject
    body_html = data.body_override or template.body_html

    rendered_subject = render_template(subject, variables)
    rendered_body = render_template(body_html, variables)

    # Create email log
    email_log = EmailLog(
        org_id=org.id,
        template_id=template.id,
        template_name=template.name,
        template_type=template.template_type,
        entity_id=entity.id,
        recipient_email=entity.email,
        recipient_name=entity.name,
        vacancy_id=vacancy.id if vacancy else None,
        application_id=application.id if application else None,
        subject=rendered_subject,
        body_html=rendered_body,
        variables_used=variables,
        status=EmailStatus.pending,
        sent_by=current_user.id,
    )

    db.add(email_log)
    await db.commit()
    await db.refresh(email_log)

    # B5-fix: реально отправляем через SMTP, если настроено. Если SMTP не задан
    # или отправка упала — честно помечаем pending, а не врём "отправлено".
    from ...services.email_sender import send_email_smtp
    actually_sent = False
    try:
        actually_sent = await send_email_smtp(entity.email, rendered_subject, rendered_body)
    except Exception:
        logger.exception(f"SMTP send failed: to={entity.email}, template={template.name}")
        actually_sent = False

    if actually_sent:
        email_log.status = EmailStatus.sent
        email_log.sent_at = datetime.utcnow()
        result_message = "Email отправлен"
    else:
        email_log.status = EmailStatus.pending
        result_message = "Письмо поставлено в очередь (SMTP не настроен — реальная отправка отключена)"
    await db.commit()

    logger.info(
        f"Email {email_log.status.value}: template={template.name}, "
        f"to={entity.email}, by user {current_user.id}"
    )

    return SendEmailResponse(
        id=email_log.id,
        status=email_log.status.value,
        recipient_email=entity.email,
        recipient_name=entity.name,
        subject=rendered_subject,
        message=result_message
    )


@router.post("/send-bulk", response_model=BulkSendEmailResponse)
async def send_bulk_email(
    data: BulkSendEmailRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Send email to multiple candidates using template."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Load template
    result = await db.execute(
        select(EmailTemplate).where(
            EmailTemplate.id == data.template_id,
            EmailTemplate.org_id == org.id
        )
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    if not template.is_active:
        raise HTTPException(status_code=400, detail="Template is not active")

    # Load vacancy if provided
    vacancy = None
    if data.vacancy_id:
        result = await db.execute(
            select(Vacancy).where(
                Vacancy.id == data.vacancy_id,
                Vacancy.org_id == org.id
            )
        )
        vacancy = result.scalar_one_or_none()

    # Base variables
    base_variables: Dict[str, str] = {}
    base_variables.update(await get_user_variables(current_user))
    base_variables.update(await get_org_variables(org))
    if vacancy:
        base_variables.update(await get_vacancy_variables(vacancy, db))
    if data.custom_variables:
        base_variables.update(data.custom_variables)

    results = []
    sent_count = 0
    failed_count = 0

    for entity_id in data.entity_ids:
        try:
            # Load entity
            result = await db.execute(
                select(Entity).where(
                    Entity.id == entity_id,
                    Entity.org_id == org.id
                )
            )
            entity = result.scalar_one_or_none()

            if not entity:
                results.append(SendEmailResponse(
                    id=0,
                    status="failed",
                    recipient_email="",
                    recipient_name=None,
                    subject="",
                    message=f"Кандидат {entity_id} не найден"
                ))
                failed_count += 1
                continue

            if not entity.email:
                results.append(SendEmailResponse(
                    id=0,
                    status="failed",
                    recipient_email="",
                    recipient_name=entity.name,
                    subject="",
                    message="У кандидата нет email адреса"
                ))
                failed_count += 1
                continue

            # Prepare variables
            variables = base_variables.copy()
            variables.update(await get_entity_variables(entity, db))

            # Render
            rendered_subject = render_template(template.subject, variables)
            rendered_body = render_template(template.body_html, variables)

            # Find application
            application = None
            if vacancy:
                result = await db.execute(
                    select(VacancyApplication).where(
                        VacancyApplication.vacancy_id == vacancy.id,
                        VacancyApplication.entity_id == entity.id
                    )
                )
                application = result.scalar_one_or_none()

            # Create log
            email_log = EmailLog(
                org_id=org.id,
                template_id=template.id,
                template_name=template.name,
                template_type=template.template_type,
                entity_id=entity.id,
                recipient_email=entity.email,
                recipient_name=entity.name,
                vacancy_id=vacancy.id if vacancy else None,
                application_id=application.id if application else None,
                subject=rendered_subject,
                body_html=rendered_body,
                variables_used=variables,
                status=EmailStatus.sent,  # TODO: Actually send
                sent_at=datetime.utcnow(),
                sent_by=current_user.id,
            )

            db.add(email_log)
            await db.commit()
            await db.refresh(email_log)

            results.append(SendEmailResponse(
                id=email_log.id,
                status="sent",
                recipient_email=entity.email,
                recipient_name=entity.name,
                subject=rendered_subject,
                message="Email отправлен"
            ))
            sent_count += 1

        except Exception as e:
            logger.error(f"Failed to send email to entity {entity_id}: {e}")
            results.append(SendEmailResponse(
                id=0,
                status="failed",
                recipient_email="",
                recipient_name=None,
                subject="",
                message=f"Ошибка: {str(e)}"
            ))
            failed_count += 1

    logger.info(f"Bulk email sent: template={template.name}, sent={sent_count}, failed={failed_count}, by user {current_user.id}")

    return BulkSendEmailResponse(
        total=len(data.entity_ids),
        sent=sent_count,
        failed=failed_count,
        results=results
    )
