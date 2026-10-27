"""
Notification routes for in-app notifications.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from pydantic import BaseModel
from datetime import datetime

from ..models.database import Notification, User
from ..database import get_db
from ..services.auth import get_current_user

router = APIRouter()


class NotificationResponse(BaseModel):
    id: int
    user_id: int
    type: str
    title: str
    message: str | None
    link: str | None
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UnreadCountResponse(BaseModel):
    count: int


# Канонические типы уведомлений и дефолты (True = включён по умолчанию).
# По умолчанию остаются только упоминания и ответы на анкеты — остальное шум.
NOTIFICATION_TYPE_DEFAULTS: dict[str, bool] = {
    "comment_mentioned": True,    # упоминание в комментарии к кандидату
    "comment_mention": True,      # упоминание в комментарии к задаче
    "form_submitted": True,       # ответ на анкету
    "new_request": True,          # новая заявка → HR-админам/owner'ам
    "request_assigned": True,     # заявка распределена рекрутёру
    "new_candidate": False,
    "stage_change": False,
    "interview_scheduled": False,
    "practice_started": False,
    "probation_ending": False,
    "task_assigned": False,
    "blocker_resolved": False,
}


def _effective_prefs(user: User) -> dict[str, bool]:
    """Эффективные настройки: дефолт по типу, перекрытый сохранённым выбором."""
    saved = dict(user.notification_prefs or {})
    return {t: bool(saved.get(t, d)) for t, d in NOTIFICATION_TYPE_DEFAULTS.items()}


def _disabled_types(user: User) -> list[str]:
    """Типы, ЯВНО выключенные пользователем (их прячем). Неизвестные/новые типы
    не фильтруем — показываем, чтобы случайно ничего не потерять."""
    return [t for t, on in _effective_prefs(user).items() if not on]


class PrefsUpdate(BaseModel):
    prefs: dict[str, bool]


@router.get("/notifications", response_model=List[NotificationResponse])
async def list_notifications(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List user's notifications, unread first, limit 50. Скрывает выключенные типы."""
    disabled = _disabled_types(current_user)
    stmt = (
        select(Notification)
        .where(Notification.user_id == current_user.id)
    )
    if disabled:
        stmt = stmt.where(Notification.type.notin_(disabled))
    stmt = stmt.order_by(Notification.is_read.asc(), Notification.created_at.desc()).limit(50)
    result = await db.execute(stmt)
    notifications = list(result.scalars().all())
    return notifications


@router.get("/notifications/unread-count", response_model=UnreadCountResponse)
async def unread_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get count of unread notifications. Не считает выключенные типы."""
    disabled = _disabled_types(current_user)
    stmt = (
        select(func.count(Notification.id))
        .where(Notification.user_id == current_user.id, Notification.is_read == False)
    )
    if disabled:
        stmt = stmt.where(Notification.type.notin_(disabled))
    result = await db.execute(stmt)
    count = result.scalar() or 0
    return {"count": count}


@router.put("/notifications/{notification_id}/read")
async def mark_read(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark a single notification as read."""
    result = await db.execute(
        select(Notification)
        .where(Notification.id == notification_id, Notification.user_id == current_user.id)
    )
    notification = result.scalar_one_or_none()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    notification.is_read = True
    await db.commit()
    return {"ok": True}


@router.put("/notifications/read-all")
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark all notifications as read."""
    await db.execute(
        update(Notification)
        .where(Notification.user_id == current_user.id, Notification.is_read == False)
        .values(is_read=True)
    )
    await db.commit()
    return {"ok": True}


@router.get("/notifications/prefs")
async def get_notification_prefs(
    current_user: User = Depends(get_current_user),
):
    """Эффективные настройки типов уведомлений (тип → вкл/выкл)."""
    return {"prefs": _effective_prefs(current_user)}


@router.put("/notifications/prefs")
async def update_notification_prefs(
    body: PrefsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Обновить вкл/выкл типов уведомлений (мерж по переданным ключам)."""
    user = (await db.execute(select(User).where(User.id == current_user.id))).scalar_one()
    saved = dict(user.notification_prefs or {})
    for t, on in body.prefs.items():
        if t in NOTIFICATION_TYPE_DEFAULTS:
            saved[t] = bool(on)
    user.notification_prefs = saved
    await db.commit()
    return {"prefs": _effective_prefs(user)}
