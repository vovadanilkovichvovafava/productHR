"""
Email History Operations

Provides endpoints for:
- Viewing email sending history
- Email analytics
"""

from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from pydantic import BaseModel

from ...database import get_db
from ...models.database import User
from ...models.email_templates import EmailLog, EmailStatus, EmailTemplateType
from ...services.auth import get_current_user, get_user_org
from ...utils.logging import get_logger

logger = get_logger("email-history")

router = APIRouter()


# Schemas
class EmailLogResponse(BaseModel):
    id: int
    org_id: int
    template_id: Optional[int]
    template_name: Optional[str]
    template_type: Optional[str]
    entity_id: Optional[int]
    recipient_email: str
    recipient_name: Optional[str]
    vacancy_id: Optional[int]
    application_id: Optional[int]
    subject: str
    status: str
    sent_at: Optional[datetime]
    delivered_at: Optional[datetime]
    opened_at: Optional[datetime]
    clicked_at: Optional[datetime]
    error_message: Optional[str]
    sent_by: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


class EmailLogDetailResponse(EmailLogResponse):
    body_html: Optional[str]
    variables_used: dict


class EmailStatsResponse(BaseModel):
    total_sent: int
    delivered: int
    opened: int
    clicked: int
    bounced: int
    failed: int
    delivery_rate: float
    open_rate: float
    click_rate: float


class EmailStatsByTypeResponse(BaseModel):
    template_type: str
    count: int
    delivered: int
    opened: int


class EmailStatsByTemplateResponse(BaseModel):
    template_id: int
    template_name: str
    count: int
    delivered: int
    opened: int
    open_rate: float


@router.get("", response_model=List[EmailLogResponse])
async def list_email_history(
    entity_id: Optional[int] = None,
    vacancy_id: Optional[int] = None,
    template_id: Optional[int] = None,
    template_type: Optional[EmailTemplateType] = None,
    status: Optional[EmailStatus] = None,
    sent_by: Optional[int] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List email sending history with filters."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    stmt = select(EmailLog).where(EmailLog.org_id == org.id)

    if entity_id:
        stmt = stmt.where(EmailLog.entity_id == entity_id)
    if vacancy_id:
        stmt = stmt.where(EmailLog.vacancy_id == vacancy_id)
    if template_id:
        stmt = stmt.where(EmailLog.template_id == template_id)
    if template_type:
        stmt = stmt.where(EmailLog.template_type == template_type)
    if status:
        stmt = stmt.where(EmailLog.status == status)
    if sent_by:
        stmt = stmt.where(EmailLog.sent_by == sent_by)
    if date_from:
        stmt = stmt.where(EmailLog.created_at >= date_from)
    if date_to:
        stmt = stmt.where(EmailLog.created_at <= date_to)

    stmt = stmt.order_by(EmailLog.created_at.desc()).offset(skip).limit(limit)

    result = await db.execute(stmt)
    logs = result.scalars().all()

    return [EmailLogResponse.model_validate(log) for log in logs]


@router.get("/{log_id}", response_model=EmailLogDetailResponse)
async def get_email_log(
    log_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get detailed email log entry."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    result = await db.execute(
        select(EmailLog).where(
            EmailLog.id == log_id,
            EmailLog.org_id == org.id
        )
    )
    log = result.scalar_one_or_none()

    if not log:
        raise HTTPException(status_code=404, detail="Email log not found")

    return EmailLogDetailResponse.model_validate(log)


@router.get("/stats/overview", response_model=EmailStatsResponse)
async def get_email_stats(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get email sending statistics for the period."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    date_from = datetime.utcnow() - timedelta(days=days)

    # Get counts by status
    result = await db.execute(
        select(
            EmailLog.status,
            func.count(EmailLog.id).label("count")
        ).where(
            EmailLog.org_id == org.id,
            EmailLog.created_at >= date_from
        ).group_by(EmailLog.status)
    )

    status_counts = {row.status: row.count for row in result}

    total = sum(status_counts.values())
    sent = status_counts.get(EmailStatus.sent, 0)
    delivered = status_counts.get(EmailStatus.delivered, 0)
    opened = status_counts.get(EmailStatus.opened, 0)
    clicked = status_counts.get(EmailStatus.clicked, 0)
    bounced = status_counts.get(EmailStatus.bounced, 0)
    failed = status_counts.get(EmailStatus.failed, 0)

    # For now, treat 'sent' as 'delivered' since we're not tracking actual delivery
    total_delivered = sent + delivered + opened + clicked

    return EmailStatsResponse(
        total_sent=total,
        delivered=total_delivered,
        opened=opened + clicked,  # Clicked implies opened
        clicked=clicked,
        bounced=bounced,
        failed=failed,
        delivery_rate=round(total_delivered / total * 100, 1) if total > 0 else 0,
        open_rate=round((opened + clicked) / total_delivered * 100, 1) if total_delivered > 0 else 0,
        click_rate=round(clicked / (opened + clicked) * 100, 1) if (opened + clicked) > 0 else 0,
    )


@router.get("/stats/by-type", response_model=List[EmailStatsByTypeResponse])
async def get_email_stats_by_type(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get email statistics grouped by template type."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    date_from = datetime.utcnow() - timedelta(days=days)

    result = await db.execute(
        select(
            EmailLog.template_type,
            func.count(EmailLog.id).label("count"),
            func.sum(
                func.cast(
                    EmailLog.status.in_([EmailStatus.sent, EmailStatus.delivered, EmailStatus.opened, EmailStatus.clicked]),
                    Integer
                )
            ).label("delivered"),
            func.sum(
                func.cast(
                    EmailLog.status.in_([EmailStatus.opened, EmailStatus.clicked]),
                    Integer
                )
            ).label("opened"),
        ).where(
            EmailLog.org_id == org.id,
            EmailLog.created_at >= date_from,
            EmailLog.template_type.isnot(None)
        ).group_by(EmailLog.template_type)
    )

    from sqlalchemy import Integer

    stats = []
    for row in result:
        stats.append(EmailStatsByTypeResponse(
            template_type=row.template_type.value if row.template_type else "unknown",
            count=row.count or 0,
            delivered=row.delivered or 0,
            opened=row.opened or 0,
        ))

    return stats


@router.get("/stats/by-template", response_model=List[EmailStatsByTemplateResponse])
async def get_email_stats_by_template(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get email statistics grouped by template."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    date_from = datetime.utcnow() - timedelta(days=days)

    result = await db.execute(
        select(
            EmailLog.template_id,
            EmailLog.template_name,
            func.count(EmailLog.id).label("count"),
            func.sum(
                func.cast(
                    EmailLog.status.in_([EmailStatus.sent, EmailStatus.delivered, EmailStatus.opened, EmailStatus.clicked]),
                    Integer
                )
            ).label("delivered"),
            func.sum(
                func.cast(
                    EmailLog.status.in_([EmailStatus.opened, EmailStatus.clicked]),
                    Integer
                )
            ).label("opened"),
        ).where(
            EmailLog.org_id == org.id,
            EmailLog.created_at >= date_from,
            EmailLog.template_id.isnot(None)
        ).group_by(EmailLog.template_id, EmailLog.template_name)
    )

    from sqlalchemy import Integer

    stats = []
    for row in result:
        count = row.count or 0
        delivered = row.delivered or 0
        opened = row.opened or 0

        stats.append(EmailStatsByTemplateResponse(
            template_id=row.template_id,
            template_name=row.template_name or "Unknown",
            count=count,
            delivered=delivered,
            opened=opened,
            open_rate=round(opened / delivered * 100, 1) if delivered > 0 else 0,
        ))

    return sorted(stats, key=lambda x: x.count, reverse=True)


@router.get("/entity/{entity_id}", response_model=List[EmailLogResponse])
async def get_entity_email_history(
    entity_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get email history for a specific candidate."""
    # Скоуп по воронкам: переписка с чужим кандидатом не читается.
    from ...services.vacancy_scope import ensure_entity_visible
    await ensure_entity_visible(entity_id, current_user, db)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    result = await db.execute(
        select(EmailLog).where(
            EmailLog.org_id == org.id,
            EmailLog.entity_id == entity_id
        ).order_by(EmailLog.created_at.desc()).offset(skip).limit(limit)
    )
    logs = result.scalars().all()

    return [EmailLogResponse.model_validate(log) for log in logs]


@router.get("/vacancy/{vacancy_id}", response_model=List[EmailLogResponse])
async def get_vacancy_email_history(
    vacancy_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get email history for a specific vacancy."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    result = await db.execute(
        select(EmailLog).where(
            EmailLog.org_id == org.id,
            EmailLog.vacancy_id == vacancy_id
        ).order_by(EmailLog.created_at.desc()).offset(skip).limit(limit)
    )
    logs = result.scalars().all()

    return [EmailLogResponse.model_validate(log) for log in logs]
