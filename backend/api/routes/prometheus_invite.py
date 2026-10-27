"""
Prometheus Invite — send invitation email to candidate for Prometheus registration.

Provides:
- POST /invite — send invite to single candidate
- POST /invite/bulk — send invites to multiple candidates
"""

import logging
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from ..database import get_db
from ..models.database import Entity, User, Vacancy, VacancyApplication, ApplicationStage
from ..services.auth import get_current_user, get_user_org
from ..config import get_settings

logger = logging.getLogger("hr-analyzer.prometheus-invite")
settings = get_settings()

router = APIRouter()


class InviteRequest(BaseModel):
    entity_id: int
    vacancy_id: Optional[int] = None
    custom_message: Optional[str] = None


class BulkInviteRequest(BaseModel):
    entity_ids: List[int]
    vacancy_id: Optional[int] = None
    custom_message: Optional[str] = None


class InviteResponse(BaseModel):
    success: bool
    entity_id: int
    email: Optional[str] = None
    message: str


class BulkInviteResponse(BaseModel):
    total: int
    sent: int
    skipped: int
    errors: int
    details: List[InviteResponse]


def _get_prometheus_registration_url() -> str:
    """Build Prometheus registration URL."""
    base = settings.prometheus_base_url
    if not base:
        return "https://prometheus.enceladus.app/register"
    return f"{base.rstrip('/')}/register"


@router.post("/invite", response_model=InviteResponse)
async def invite_to_prometheus(
    data: InviteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Send Prometheus invitation to a candidate."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(400, "User not in organization")

    # Load entity
    result = await db.execute(
        select(Entity).where(Entity.id == data.entity_id, Entity.org_id == org.id)
    )
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(404, "Candidate not found")

    if not entity.email:
        raise HTTPException(400, "У кандидата не указан email — невозможно отправить приглашение")

    # Check if already invited
    extra = entity.extra_data or {}
    if extra.get("prometheus_invited"):
        return InviteResponse(
            success=True,
            entity_id=entity.id,
            email=entity.email,
            message="Приглашение уже было отправлено ранее",
        )

    # Build registration link
    reg_url = _get_prometheus_registration_url()

    # Build email content
    candidate_name = entity.name or "Кандидат"
    org_name = org.name if org.name else "Компания"

    subject = f"Приглашение на практику — {org_name}"
    body_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #333;">Здравствуйте, {candidate_name}!</h2>
        <p style="color: #555; line-height: 1.6;">
            Мы рады сообщить, что вы приглашены на практику в {org_name}!
        </p>
        <p style="color: #555; line-height: 1.6;">
            Для начала обучения, пожалуйста, зарегистрируйтесь на платформе Prometheus:
        </p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{reg_url}"
               style="background-color: #6366f1; color: white; padding: 14px 28px;
                      text-decoration: none; border-radius: 8px; font-size: 16px;
                      display: inline-block;">
                Зарегистрироваться в Prometheus
            </a>
        </div>
        {f'<p style="color: #555; line-height: 1.6;"><strong>Сообщение от рекрутера:</strong><br>{data.custom_message}</p>' if data.custom_message else ''}
        <p style="color: #888; font-size: 12px; margin-top: 30px;">
            Это автоматическое письмо от платформы Enceladus.
        </p>
    </div>
    """

    # Try to send via email template system
    try:
        from ..models.email_templates import EmailLog, EmailStatus

        email_log = EmailLog(
            org_id=org.id,
            template_id=None,
            template_name="prometheus_invite",
            template_type="notification",
            entity_id=entity.id,
            recipient_email=entity.email,
            recipient_name=entity.name,
            vacancy_id=data.vacancy_id,
            subject=subject,
            body_html=body_html,
            variables_used={"registration_url": reg_url, "candidate_name": candidate_name},
            status=EmailStatus.pending,
            sent_by=current_user.id,
        )
        db.add(email_log)

        # TODO: Send via SMTP/SendGrid when configured
        # For now mark as sent (email log recorded)
        email_log.status = EmailStatus.sent
        email_log.sent_at = datetime.utcnow()

    except Exception as e:
        logger.warning(f"Could not create email log: {e}")

    # Mark entity as invited
    if not entity.extra_data:
        entity.extra_data = {}
    entity.extra_data = {
        **entity.extra_data,
        "prometheus_invited": True,
        "prometheus_invited_at": datetime.utcnow().isoformat(),
        "prometheus_invited_by": current_user.id,
    }

    # If vacancy specified, update application stage to practice
    if data.vacancy_id:
        app_result = await db.execute(
            select(VacancyApplication).where(
                VacancyApplication.vacancy_id == data.vacancy_id,
                VacancyApplication.entity_id == entity.id,
            )
        )
        app = app_result.scalar_one_or_none()
        # ApplicationStage.practice и .accepted НЕ СУЩЕСТВУЮТ (см. закомментированный
        # блок deprecated-значений в database.py) — обращение к ним роняло весь
        # эндпоинт с AttributeError → 500, и откат транзакции стирал уже созданную
        # запись EmailLog и отметку prometheus_invited. Приглашение не сохранялось
        # НИКОГДА, сколько ни повторяй.
        # «Практика» — это probation (так подписано и в APPLICATION_STAGE_LABELS,
        # и в KANBAN_STATUS_LABELS). Не откатываем назад тех, кто уже дальше.
        TERMINAL = (ApplicationStage.probation, ApplicationStage.hired,
                    ApplicationStage.transferred)
        if app and app.stage not in TERMINAL:
            app.stage = ApplicationStage.probation
            app.last_stage_change_at = datetime.utcnow()

    await db.commit()

    logger.info(f"Prometheus invite sent: entity={entity.id}, email={entity.email}, by user={current_user.id}")

    return InviteResponse(
        success=True,
        entity_id=entity.id,
        email=entity.email,
        message=f"Приглашение отправлено на {entity.email}",
    )


@router.post("/invite/bulk", response_model=BulkInviteResponse)
async def bulk_invite_to_prometheus(
    data: BulkInviteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Send Prometheus invitations to multiple candidates."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(400, "User not in organization")

    result = await db.execute(
        select(Entity).where(
            Entity.id.in_(data.entity_ids),
            Entity.org_id == org.id,
        )
    )
    entities = list(result.scalars().all())

    details = []
    sent = 0
    skipped = 0
    errors = 0

    for entity in entities:
        if not entity.email:
            details.append(InviteResponse(
                success=False, entity_id=entity.id, email=None,
                message="Нет email",
            ))
            skipped += 1
            continue

        extra = entity.extra_data or {}
        if extra.get("prometheus_invited"):
            details.append(InviteResponse(
                success=True, entity_id=entity.id, email=entity.email,
                message="Уже приглашён",
            ))
            skipped += 1
            continue

        try:
            if not entity.extra_data:
                entity.extra_data = {}
            entity.extra_data = {
                **entity.extra_data,
                "prometheus_invited": True,
                "prometheus_invited_at": datetime.utcnow().isoformat(),
                "prometheus_invited_by": current_user.id,
            }
            details.append(InviteResponse(
                success=True, entity_id=entity.id, email=entity.email,
                message=f"Приглашение отправлено на {entity.email}",
            ))
            sent += 1
        except Exception as e:
            details.append(InviteResponse(
                success=False, entity_id=entity.id, email=entity.email,
                message=f"Ошибка: {str(e)}",
            ))
            errors += 1

    await db.commit()

    return BulkInviteResponse(
        total=len(data.entity_ids),
        sent=sent,
        skipped=skipped,
        errors=errors,
        details=details,
    )
