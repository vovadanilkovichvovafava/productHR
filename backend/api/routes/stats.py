from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, distinct, and_

from ..database import get_db
from ..models.database import User, UserRole, Chat, Message, AnalysisHistory
from ..models.schemas import StatsResponse
from ..services.auth import get_current_user

router = APIRouter()


@router.get("", response_model=StatsResponse)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Merge detached user into current session to avoid lazy loading issues
    user = await db.merge(user)
    is_super = user.role == UserRole.superadmin
    now = datetime.utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = now - timedelta(days=7)

    # Base filter
    def chat_filter(query, chat_col):
        if is_super:
            return query
        return query.where(chat_col == user.id)

    # Total chats
    q = select(func.count(Chat.id))
    if not is_super:
        q = q.where(Chat.owner_id == user.id)
    total_chats = (await db.execute(q)).scalar() or 0

    # Active chats (messages in last 7 days)
    if is_super:
        active_q = select(func.count(distinct(Message.chat_id))).where(Message.timestamp >= week_ago)
    else:
        active_q = (
            select(func.count(distinct(Message.chat_id)))
            .select_from(Message)
            .join(Chat, Chat.id == Message.chat_id)
            .where(and_(Message.timestamp >= week_ago, Chat.owner_id == user.id))
        )
    active_chats = (await db.execute(active_q)).scalar() or 0

    # Total messages
    if is_super:
        msg_q = select(func.count(Message.id))
    else:
        msg_q = (
            select(func.count(Message.id))
            .select_from(Message)
            .join(Chat, Chat.id == Message.chat_id)
            .where(Chat.owner_id == user.id)
        )
    total_messages = (await db.execute(msg_q)).scalar() or 0

    # Total participants
    if is_super:
        part_q = select(func.count(distinct(Message.telegram_user_id)))
    else:
        part_q = (
            select(func.count(distinct(Message.telegram_user_id)))
            .select_from(Message)
            .join(Chat, Chat.id == Message.chat_id)
            .where(Chat.owner_id == user.id)
        )
    total_participants = (await db.execute(part_q)).scalar() or 0

    # Total analyses
    if is_super:
        anal_q = select(func.count(AnalysisHistory.id))
    else:
        anal_q = select(func.count(AnalysisHistory.id)).where(AnalysisHistory.user_id == user.id)
    total_analyses = (await db.execute(anal_q)).scalar() or 0

    # Messages today
    if is_super:
        today_q = select(func.count(Message.id)).where(Message.timestamp >= today)
    else:
        today_q = (
            select(func.count(Message.id))
            .select_from(Message)
            .join(Chat, Chat.id == Message.chat_id)
            .where(and_(Message.timestamp >= today, Chat.owner_id == user.id))
        )
    messages_today = (await db.execute(today_q)).scalar() or 0

    # Messages this week
    if is_super:
        week_q = select(func.count(Message.id)).where(Message.timestamp >= week_ago)
    else:
        week_q = (
            select(func.count(Message.id))
            .select_from(Message)
            .join(Chat, Chat.id == Message.chat_id)
            .where(and_(Message.timestamp >= week_ago, Chat.owner_id == user.id))
        )
    messages_this_week = (await db.execute(week_q)).scalar() or 0

    # Activity by day (last 7 days)
    activity_by_day = []
    for i in range(7):
        day = today - timedelta(days=6-i)
        next_day = day + timedelta(days=1)

        if is_super:
            day_q = select(func.count(Message.id)).where(
                and_(Message.timestamp >= day, Message.timestamp < next_day)
            )
        else:
            day_q = (
                select(func.count(Message.id))
                .select_from(Message)
                .join(Chat, Chat.id == Message.chat_id)
                .where(and_(
                    Message.timestamp >= day,
                    Message.timestamp < next_day,
                    Chat.owner_id == user.id
                ))
            )
        count = (await db.execute(day_q)).scalar() or 0
        activity_by_day.append({
            "date": day.strftime("%Y-%m-%d"),
            "day": day.strftime("%a"),
            "count": count
        })

    # Messages by type
    if is_super:
        type_q = select(Message.content_type, func.count(Message.id)).group_by(Message.content_type)
    else:
        type_q = (
            select(Message.content_type, func.count(Message.id))
            .select_from(Message)
            .join(Chat, Chat.id == Message.chat_id)
            .where(Chat.owner_id == user.id)
            .group_by(Message.content_type)
        )
    type_result = await db.execute(type_q)
    messages_by_type = {r[0]: r[1] for r in type_result.all()}

    # Top chats
    if is_super:
        top_q = (
            select(Chat.id, Chat.title, Chat.custom_name, func.count(Message.id).label("cnt"))
            .join(Message, Message.chat_id == Chat.id)
            .group_by(Chat.id, Chat.title, Chat.custom_name)
            .order_by(func.count(Message.id).desc())
            .limit(5)
        )
    else:
        top_q = (
            select(Chat.id, Chat.title, Chat.custom_name, func.count(Message.id).label("cnt"))
            .join(Message, Message.chat_id == Chat.id)
            .where(Chat.owner_id == user.id)
            .group_by(Chat.id, Chat.title, Chat.custom_name)
            .order_by(func.count(Message.id).desc())
            .limit(5)
        )
    top_result = await db.execute(top_q)
    top_chats = [{"id": r[0], "title": r[1], "custom_name": r[2], "messages": r[3]} for r in top_result.all()]

    return StatsResponse(
        total_chats=total_chats,
        total_messages=total_messages,
        total_participants=total_participants,
        total_analyses=total_analyses,
        active_chats=active_chats,
        messages_today=messages_today,
        messages_this_week=messages_this_week,
        activity_by_day=activity_by_day,
        messages_by_type=messages_by_type,
        top_chats=top_chats,
    )
