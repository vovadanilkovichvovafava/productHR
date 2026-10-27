from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path
from pydantic import BaseModel
import json
import hashlib
import zipfile
import io
import re
import os
import shutil
import uuid
import asyncio
import logging
import threading
from html.parser import HTMLParser

logger = logging.getLogger("hr-analyzer.chats")

# Uploads directory for imported media
UPLOADS_DIR = Path(__file__).parent.parent.parent / "uploads"

# Import progress tracking (in-memory) with thread-safe access
_import_progress_lock = threading.Lock()
import_progress: Dict[str, Dict[str, Any]] = {}
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, distinct, delete, and_, or_
from sqlalchemy.orm import selectinload

from ..database import get_db
from ..models.database import User, UserRole, Chat, Message, ChatCriteria, AIConversation, AnalysisHistory, Entity, OrgRole, Department, DepartmentMember, DeptRole, SharedAccess, ResourceType, AccessLevel
from ..models.schemas import ChatResponse, ChatUpdate, ChatTypeConfig
from ..models.sharing import BaseShareRequest as ShareRequest
from ..services.auth import get_current_user, get_user_org, get_user_org_role, can_share_to
from ..services.permissions import PermissionService
from ..services.chat_types import (
    get_all_chat_types, get_chat_type_config, get_quick_actions,
    get_suggested_questions, get_default_criteria
)
from ..services.transcription import transcription_service
from ..services.documents import document_parser
from ..services.google_docs import google_docs_service
from ..services.shadow_filter import get_isolated_creator_ids
from .realtime import broadcast_chat_updated, broadcast_chat_deleted

router = APIRouter()


@router.get("/types", response_model=List[Dict[str, Any]])
async def get_chat_types():
    """Get all available chat types."""
    return get_all_chat_types()


@router.get("/types/{type_id}")
async def get_chat_type_details(type_id: str):
    """Get detailed configuration for a chat type."""
    config = get_chat_type_config(type_id)
    return {
        "type_info": {
            "id": type_id,
            "name": config["name"],
            "description": config["description"],
            "icon": config["icon"],
            "color": config["color"],
        },
        "quick_actions": get_quick_actions(type_id),
        "suggested_questions": get_suggested_questions(type_id),
        "default_criteria": get_default_criteria(type_id),
    }


@router.get("", response_model=List[ChatResponse])
async def get_chats(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    search: str = Query(None, max_length=255),
    chat_type: str = Query(None, description="Filter by chat type"),
    limit: int = Query(500, le=2000),  # Поиск в UI клиентский — нужно загружать весь список юзера, иначе чаты за пределами лимита невидимы
    offset: int = Query(0, ge=0, le=5000),  # Reduced offset limit
):
    # Merge detached user into current session
    user = await db.merge(user)

    # SUPERADMIN sees everything across all organizations (with shadow content isolation)
    if user.role == UserRole.superadmin:
        query = select(Chat).options(selectinload(Chat.owner), selectinload(Chat.entity)).where(
            Chat.deleted_at.is_(None)
        )
        # Apply shadow user content isolation
        isolated_ids = await get_isolated_creator_ids(user, db)
        if isolated_ids:
            query = query.where(~Chat.owner_id.in_(isolated_ids))
    else:
        # Get user's organization
        org = await get_user_org(user, db)
        if not org:
            return []

        # Filter by org_id
        query = select(Chat).options(selectinload(Chat.owner), selectinload(Chat.entity)).where(
            Chat.deleted_at.is_(None),
            Chat.org_id == org.id
        )

        # Salesforce-style access control:
        # - Org Owner: see all in organization
        # - Member депта 'Практика': видит ВСЕ чаты в org (вся команда практики
        #   работает с чатами кандидатов вместе)
        # - Dept Lead/Sub_admin: see dept members' records + entity-linked chats
        # - Others: own + shared
        user_role = await get_user_org_role(user, org.id, db)

        # Проверка: член депта 'Практика'?
        practice_check = await db.execute(
            select(DepartmentMember.id)
            .join(Department, Department.id == DepartmentMember.department_id)
            .where(
                DepartmentMember.user_id == user.id,
                Department.org_id == org.id,
                func.lower(func.trim(Department.name)) == 'практика',
            )
            .limit(1)
        )
        is_practice_member = practice_check.scalar_one_or_none() is not None

        if user_role != "owner" and not is_practice_member:
            # Get IDs of chats shared with current user
            shared_result = await db.execute(
                select(SharedAccess.resource_id).where(
                    SharedAccess.resource_type == ResourceType.chat,
                    SharedAccess.shared_with_id == user.id,
                    or_(SharedAccess.expires_at.is_(None), SharedAccess.expires_at > datetime.utcnow())
                )
            )
            shared_chat_ids = [r for r in shared_result.scalars().all()]

            # Get ALL departments where user is a member (any role)
            all_dept_result = await db.execute(
                select(DepartmentMember.department_id).where(
                    DepartmentMember.user_id == user.id
                )
            )
            user_dept_ids = [r for r in all_dept_result.scalars().all()]

            # DEBUG: Log user's department status
            logger.info(f"get_chats: user={user.id} ({user.email}), org_role={user_role}, user_dept_ids={user_dept_ids}")

            # Get user IDs in the same departments
            dept_member_ids = []
            if user_dept_ids:
                dept_members_result = await db.execute(
                    select(DepartmentMember.user_id).where(
                        DepartmentMember.department_id.in_(user_dept_ids)
                    )
                )
                dept_member_ids = [r for r in dept_members_result.scalars().all()]
                logger.info(f"get_chats: dept_member_ids={dept_member_ids}")

            # Get entity IDs that belong to user's departments (for entity-based access)
            # Include entities with department_id AND entities created by department members
            dept_entity_ids = []
            if user_dept_ids:
                # Entities explicitly assigned to department
                dept_entities_result = await db.execute(
                    select(Entity.id).where(
                        Entity.department_id.in_(user_dept_ids)
                    )
                )
                dept_entity_ids = [r for r in dept_entities_result.scalars().all()]

                # Also include entities created by department members (even without department_id)
                if dept_member_ids:
                    member_entities_result = await db.execute(
                        select(Entity.id).where(
                            Entity.created_by.in_(dept_member_ids)
                        )
                    )
                    member_entity_ids = [r for r in member_entities_result.scalars().all()]
                    dept_entity_ids = list(set(dept_entity_ids + member_entity_ids))

            # Build access conditions
            conditions = [Chat.owner_id == user.id]  # Own records

            if shared_chat_ids:
                conditions.append(Chat.id.in_(shared_chat_ids))  # Shared with me

            if dept_member_ids:
                conditions.append(Chat.owner_id.in_(dept_member_ids))  # Dept members' records

            # Also show chats linked to entities in user's departments
            if dept_entity_ids:
                conditions.append(Chat.entity_id.in_(dept_entity_ids))  # Chats linked to dept entities

            # DEBUG: Log access conditions
            logger.info(f"get_chats: shared_chat_ids={shared_chat_ids}, dept_entity_ids={dept_entity_ids}, conditions_count={len(conditions)}")

            query = query.where(or_(*conditions))
        # org owner sees all in org (no additional filter)

    if search:
        query = query.where(Chat.title.ilike(f"%{search}%"))
    if chat_type:
        query = query.where(Chat.chat_type == chat_type)
    query = query.order_by(Chat.last_activity.desc())
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    chats = result.scalars().all()

    # DEBUG: Log query results
    logger.info(f"get_chats RESULT: user={user.id}, found {len(chats)} chats, ids={[c.id for c in chats][:20]}")

    if not chats:
        return []

    # Get all chat IDs for batch queries
    chat_ids = [chat.id for chat in chats]

    # Batch query: Get message counts for all chats
    msg_counts_result = await db.execute(
        select(Message.chat_id, func.count(Message.id))
        .where(Message.chat_id.in_(chat_ids))
        .group_by(Message.chat_id)
    )
    msg_counts = {row[0]: row[1] for row in msg_counts_result.fetchall()}

    # Batch query: Get participant counts for all chats
    part_counts_result = await db.execute(
        select(Message.chat_id, func.count(distinct(Message.telegram_user_id)))
        .where(Message.chat_id.in_(chat_ids))
        .group_by(Message.chat_id)
    )
    part_counts = {row[0]: row[1] for row in part_counts_result.fetchall()}

    # Batch query: Get chats with criteria
    criteria_result = await db.execute(
        select(ChatCriteria.chat_id)
        .where(ChatCriteria.chat_id.in_(chat_ids))
        .distinct()
    )
    chats_with_criteria = {row[0] for row in criteria_result.fetchall()}

    # Batch query: Get shared access for current user
    shared_access_result = await db.execute(
        select(SharedAccess.resource_id, SharedAccess.access_level)
        .where(
            SharedAccess.resource_type == ResourceType.chat,
            SharedAccess.resource_id.in_(chat_ids),
            SharedAccess.shared_with_id == user.id,
            or_(SharedAccess.expires_at.is_(None), SharedAccess.expires_at > datetime.utcnow())
        )
    )
    shared_access_map = {row[0]: row[1].value for row in shared_access_result.fetchall()}

    # Build response using the pre-fetched data
    response = []
    for chat in chats:
        is_mine = chat.owner_id == user.id
        is_shared = chat.id in shared_access_map
        access_level = shared_access_map.get(chat.id) if is_shared else ('full' if is_mine else None)

        response.append(ChatResponse(
            id=chat.id,
            telegram_chat_id=chat.telegram_chat_id,
            title=chat.title,
            custom_name=chat.custom_name,
            chat_type=chat.chat_type.value if chat.chat_type else "hr",
            custom_type_name=chat.custom_type_name,
            custom_type_description=chat.custom_type_description,
            owner_id=chat.owner_id,
            owner_name=chat.owner.name if chat.owner else None,
            entity_id=chat.entity_id,
            entity_name=chat.entity.name if chat.entity else None,
            is_active=chat.is_active,
            messages_count=msg_counts.get(chat.id, 0),
            participants_count=part_counts.get(chat.id, 0),
            last_activity=chat.last_activity,
            created_at=chat.created_at,
            has_criteria=chat.id in chats_with_criteria,
            is_mine=is_mine,
            is_shared=is_shared,
            access_level=access_level,
        ))

    return response


@router.get("/{chat_id}", response_model=ChatResponse)
async def get_chat(
    chat_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    user = await db.merge(user)

    # Get user's organization
    org = await get_user_org(user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Chat not found")

    result = await db.execute(
        select(Chat).options(selectinload(Chat.owner), selectinload(Chat.entity)).where(
            Chat.id == chat_id,
            Chat.org_id == org.id,
            Chat.deleted_at.is_(None)
        )
    )
    chat = result.scalar_one_or_none()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    permissions = PermissionService(db)
    if not await permissions.can_access_resource(user, chat, "read"):
        raise HTTPException(status_code=403, detail="Access denied")

    msg_count = await db.execute(
        select(func.count(Message.id)).where(Message.chat_id == chat.id)
    )
    part_count = await db.execute(
        select(func.count(distinct(Message.telegram_user_id))).where(Message.chat_id == chat.id)
    )
    has_crit = await db.execute(
        select(ChatCriteria.id).where(ChatCriteria.chat_id == chat.id)
    )

    # Get shared access info for this user
    is_mine = chat.owner_id == user.id
    shared_access_result = await db.execute(
        select(SharedAccess.access_level)
        .where(
            SharedAccess.resource_type == ResourceType.chat,
            SharedAccess.resource_id == chat.id,
            SharedAccess.shared_with_id == user.id,
            or_(SharedAccess.expires_at.is_(None), SharedAccess.expires_at > datetime.utcnow())
        )
    )
    shared_access = shared_access_result.scalar_one_or_none()
    is_shared = shared_access is not None
    access_level = shared_access.value if shared_access else ('full' if is_mine else None)

    return ChatResponse(
        id=chat.id,
        telegram_chat_id=chat.telegram_chat_id,
        title=chat.title,
        custom_name=chat.custom_name,
        chat_type=chat.chat_type.value if chat.chat_type else "hr",
        custom_type_name=chat.custom_type_name,
        custom_type_description=chat.custom_type_description,
        owner_id=chat.owner_id,
        owner_name=chat.owner.name if chat.owner else None,
        entity_id=chat.entity_id,
        entity_name=chat.entity.name if chat.entity else None,
        is_active=chat.is_active,
        messages_count=msg_count.scalar() or 0,
        participants_count=part_count.scalar() or 0,
        last_activity=chat.last_activity,
        created_at=chat.created_at,
        has_criteria=has_crit.scalar() is not None,
        is_mine=is_mine,
        is_shared=is_shared,
        access_level=access_level,
    )


@router.patch("/{chat_id}", response_model=ChatResponse)
async def update_chat(
    chat_id: int,
    data: ChatUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from ..models.database import ChatType
    user = await db.merge(user)

    # Get user's organization
    org = await get_user_org(user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Chat not found")

    result = await db.execute(
        select(Chat).options(selectinload(Chat.owner), selectinload(Chat.entity)).where(
            Chat.id == chat_id,
            Chat.org_id == org.id
        )
    )
    chat = result.scalar_one_or_none()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    # Check if user has edit or full access
    permissions = PermissionService(db)
    if not await permissions.can_modify(user, chat, require_full=False):
        raise HTTPException(status_code=403, detail="Access denied")

    if data.custom_name is not None:
        chat.custom_name = data.custom_name
    if data.is_active is not None:
        chat.is_active = data.is_active
    if data.owner_id is not None and user.role == UserRole.superadmin:
        chat.owner_id = data.owner_id
    if data.chat_type is not None:
        try:
            chat.chat_type = ChatType(data.chat_type)
        except ValueError:
            chat.chat_type = ChatType.custom
    if data.custom_type_name is not None:
        chat.custom_type_name = data.custom_type_name
    if data.custom_type_description is not None:
        chat.custom_type_description = data.custom_type_description
    if data.entity_id is not None:
        # -1 means unlink
        chat.entity_id = None if data.entity_id == -1 else data.entity_id

    await db.commit()
    await db.refresh(chat)

    # Re-load entity relationship after update
    if chat.entity_id:
        entity_result = await db.execute(select(Entity).where(Entity.id == chat.entity_id))
        entity = entity_result.scalar_one_or_none()
        entity_name = entity.name if entity else None
    else:
        entity_name = None

    response = ChatResponse(
        id=chat.id,
        telegram_chat_id=chat.telegram_chat_id,
        title=chat.title,
        custom_name=chat.custom_name,
        chat_type=chat.chat_type.value if chat.chat_type else "hr",
        custom_type_name=chat.custom_type_name,
        custom_type_description=chat.custom_type_description,
        owner_id=chat.owner_id,
        owner_name=chat.owner.name if chat.owner else None,
        entity_id=chat.entity_id,
        entity_name=entity_name,
        is_active=chat.is_active,
        messages_count=0,
        participants_count=0,
        last_activity=chat.last_activity,
        created_at=chat.created_at,
        has_criteria=False,
    )

    # Broadcast update to users with access only. mode="json": в ответе есть
    # datetime (created_at, last_activity), а realtime делает json.dumps — без
    # этого правка чата сохранялась, но ручка отвечала 500.
    await broadcast_chat_updated(org.id, response.model_dump(mode="json"), db=db)

    return response


@router.delete("/{chat_id}/messages", status_code=204)
async def clear_messages(
    chat_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    user = await db.merge(user)

    # Get user's organization
    org = await get_user_org(user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Chat not found")

    result = await db.execute(select(Chat).where(Chat.id == chat_id, Chat.org_id == org.id))
    chat = result.scalar_one_or_none()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    # Check if user has full access (destructive operation)
    permissions = PermissionService(db)
    if not await permissions.can_modify(user, chat, require_full=True):
        raise HTTPException(status_code=403, detail="Access denied")

    await db.execute(Message.__table__.delete().where(Message.chat_id == chat_id))
    await db.commit()


@router.delete("/{chat_id}", status_code=204)
async def delete_chat(
    chat_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Soft delete a chat (moves to trash for 30 days)."""
    user = await db.merge(user)

    # Get user's organization
    org = await get_user_org(user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Chat not found")

    result = await db.execute(select(Chat).where(
        Chat.id == chat_id,
        Chat.org_id == org.id,
        Chat.deleted_at.is_(None)
    ))
    chat = result.scalar_one_or_none()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    permissions = PermissionService(db)
    if not await permissions.can_access_resource(user, chat, "read"):
        raise HTTPException(status_code=403, detail="Access denied")

    # Check delete permissions (require ownership or full access)
    can_delete = False
    if user.role == UserRole.superadmin:
        can_delete = True
    else:
        user_role = await get_user_org_role(user, org.id, db)
        if user_role == "owner":
            can_delete = True
        elif chat.owner_id == user.id:
            can_delete = True  # Owner of chat
        else:
            # Check if shared with full access
            shared_result = await db.execute(
                select(SharedAccess).where(
                    SharedAccess.resource_type == ResourceType.chat,
                    SharedAccess.resource_id == chat_id,
                    SharedAccess.shared_with_id == user.id,
                    SharedAccess.access_level == AccessLevel.full,
                    or_(SharedAccess.expires_at.is_(None), SharedAccess.expires_at > datetime.utcnow())
                )
            )
            if shared_result.scalar_one_or_none():
                can_delete = True

    if not can_delete:
        raise HTTPException(status_code=403, detail="No delete permission for this chat")

    # Save owner_id and entity_id before commit for broadcast
    owner_id = chat.owner_id
    entity_id = chat.entity_id

    # Soft delete - just set deleted_at timestamp
    chat.deleted_at = datetime.utcnow()
    await db.commit()

    # Broadcast delete to users with access only
    await broadcast_chat_deleted(org.id, chat_id, owner_id=owner_id, entity_id=entity_id, db=db)


@router.get("/deleted/list", response_model=List[ChatResponse])
async def get_deleted_chats(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get list of deleted chats (trash)."""
    user = await db.merge(user)

    # Get user's organization
    org = await get_user_org(user, db)
    if not org:
        return []

    query = select(Chat).options(selectinload(Chat.owner)).where(
        Chat.deleted_at.isnot(None),
        Chat.org_id == org.id
    )
    if user.role != UserRole.superadmin:
        query = query.where(Chat.owner_id == user.id)
    query = query.order_by(Chat.deleted_at.desc())

    result = await db.execute(query)
    chats = result.scalars().all()

    if not chats:
        return []

    # Get all chat IDs for batch queries
    chat_ids = [chat.id for chat in chats]

    # Batch query: Get message counts for all deleted chats
    msg_counts_result = await db.execute(
        select(Message.chat_id, func.count(Message.id))
        .where(Message.chat_id.in_(chat_ids))
        .group_by(Message.chat_id)
    )
    msg_counts = {row[0]: row[1] for row in msg_counts_result.fetchall()}

    # Build response using the pre-fetched data
    response = []
    for chat in chats:
        days_left = 30 - (datetime.utcnow() - chat.deleted_at).days if chat.deleted_at else 30

        response.append(ChatResponse(
            id=chat.id,
            telegram_chat_id=chat.telegram_chat_id,
            title=chat.title,
            custom_name=chat.custom_name,
            chat_type=chat.chat_type.value if chat.chat_type else "hr",
            custom_type_name=chat.custom_type_name,
            custom_type_description=chat.custom_type_description,
            owner_id=chat.owner_id,
            owner_name=chat.owner.name if chat.owner else None,
            is_active=chat.is_active,
            messages_count=msg_counts.get(chat.id, 0),
            participants_count=0,
            last_activity=chat.last_activity,
            created_at=chat.created_at,
            has_criteria=False,
            deleted_at=chat.deleted_at,
            days_until_permanent_delete=max(0, days_left),
        ))

    return response


@router.post("/{chat_id}/restore", status_code=200)
async def restore_chat(
    chat_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Restore a deleted chat from trash."""
    user = await db.merge(user)

    # Get user's organization
    org = await get_user_org(user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Deleted chat not found")

    result = await db.execute(select(Chat).where(
        Chat.id == chat_id,
        Chat.org_id == org.id,
        Chat.deleted_at.isnot(None)
    ))
    chat = result.scalar_one_or_none()
    if not chat:
        raise HTTPException(status_code=404, detail="Deleted chat not found")
    # Check if user has edit or full access
    permissions = PermissionService(db)
    if not await permissions.can_modify(user, chat, require_full=False):
        raise HTTPException(status_code=403, detail="Access denied")

    chat.deleted_at = None
    await db.commit()
    return {"message": "Chat restored successfully"}


@router.delete("/{chat_id}/permanent", status_code=204)
async def permanent_delete_chat(
    chat_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Permanently delete a chat (no recovery)."""
    user = await db.merge(user)

    # Get user's organization
    org = await get_user_org(user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Chat not found")

    result = await db.execute(select(Chat).where(Chat.id == chat_id, Chat.org_id == org.id))
    chat = result.scalar_one_or_none()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    # Check if user has full access (destructive operation)
    permissions = PermissionService(db)
    if not await permissions.can_modify(user, chat, require_full=True):
        raise HTTPException(status_code=403, detail="Access denied")

    # Delete all related data
    await db.execute(delete(Message).where(Message.chat_id == chat_id))
    await db.execute(delete(ChatCriteria).where(ChatCriteria.chat_id == chat_id))
    await db.execute(delete(AIConversation).where(AIConversation.chat_id == chat_id))
    await db.execute(delete(AnalysisHistory).where(AnalysisHistory.chat_id == chat_id))
    await db.delete(chat)
    await db.commit()


async def cleanup_old_deleted_chats(db: AsyncSession):
    """Delete chats that have been in trash for more than 30 days."""
    cutoff = datetime.utcnow() - timedelta(days=30)

    # Find old deleted chats
    result = await db.execute(
        select(Chat.id).where(Chat.deleted_at < cutoff)
    )
    old_chat_ids = [row[0] for row in result.fetchall()]

    for chat_id in old_chat_ids:
        await db.execute(delete(Message).where(Message.chat_id == chat_id))
        await db.execute(delete(ChatCriteria).where(ChatCriteria.chat_id == chat_id))
        await db.execute(delete(AIConversation).where(AIConversation.chat_id == chat_id))
        await db.execute(delete(AnalysisHistory).where(AnalysisHistory.chat_id == chat_id))
        await db.execute(delete(Chat).where(Chat.id == chat_id))

    await db.commit()
    return len(old_chat_ids)


def parse_telegram_date(date_str: str) -> datetime:
    """Parse Telegram export date format."""
    if not date_str:
        return datetime.now()

    # Strip timezone suffix like " UTC+03:00"
    if ' UTC' in date_str:
        date_str = date_str.split(' UTC')[0]

    # Try ISO format first: 2024-12-10T14:30:00
    try:
        return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    except ValueError:
        pass

    # Try Russian format: DD.MM.YYYY HH:MM:SS
    try:
        if '.' in date_str and len(date_str.split('.')[0]) <= 2:
            return datetime.strptime(date_str, '%d.%m.%Y %H:%M:%S')
    except ValueError:
        pass

    # Try other common formats
    formats = [
        '%Y-%m-%d %H:%M:%S',
        '%d/%m/%Y %H:%M:%S',
        '%Y-%m-%dT%H:%M:%S',
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue

    # Fallback - return now (shouldn't happen often)
    return datetime.now()


def detect_content_type(msg: dict) -> str:
    """Detect message content type from Telegram export."""
    if msg.get('media_type') == 'voice_message':
        return 'voice'
    if msg.get('media_type') == 'video_message':
        return 'video_note'
    if msg.get('media_type') == 'sticker':
        return 'sticker'
    if 'photo' in msg:
        return 'photo'
    if 'file' in msg and msg.get('mime_type', '').startswith('video'):
        return 'video'
    if 'file' in msg:
        return 'document'
    return 'text'


def extract_text_content(msg: dict) -> str:
    """Extract text content from Telegram message."""
    text = msg.get('text', '')

    # Handle complex text (with formatting entities)
    if isinstance(text, list):
        parts = []
        for part in text:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                parts.append(part.get('text', ''))
        text = ''.join(parts)

    # Add media type indicator if no text
    if not text:
        content_type = detect_content_type(msg)
        type_labels = {
            'voice': '[Голосовое сообщение]',
            'video_note': '[Видеосообщение]',
            'photo': '[Фото]',
            'video': '[Видео]',
            'sticker': '[Стикер]',
            'document': f'[Файл: {msg.get("file_name", "документ")}]',
        }
        text = type_labels.get(content_type, '[Медиа]')

    return text


def get_content_hash(content: str, timestamp: datetime, media_file: str = None) -> str:
    """Generate hash for deduplication when message_id is not available.

    For media messages, use media_file instead of content to avoid
    duplicates when content changes (e.g., transcription replaces placeholder).
    """
    if media_file:
        # Use media file path - stable across auto-processing runs
        data = f"media:{media_file}:{timestamp.isoformat()}"
    else:
        data = f"{content}:{timestamp.isoformat()}"
    return hashlib.md5(data.encode()).hexdigest()


class TelegramHTMLParser(HTMLParser):
    """
    Parser for Telegram Desktop HTML export format.

    HTML structure:
    - Message container: div.message.default (or div.message.default.joined for continuation)
    - Sender name: div.from_name (only in first message of a sequence)
    - Message body: div.body > div.text
    - Date: div.date (datetime in title attribute, format: "DD.MM.YYYY HH:MM:SS")
    - Media: div.media_wrap (photos, videos, etc.)

    Messages with class "joined" don't have from_name - they continue from previous sender.
    """

    def __init__(self):
        super().__init__()
        self.messages = []
        self.current_message = None
        self.last_sender = None  # Track last sender for "joined" messages
        self.in_from_name = False
        self.in_text = False
        self.in_media = False
        self.text_buffer = ""
        self.from_buffer = ""
        self.div_depth = 0  # Track div nesting to know when message ends
        self.message_div_depth = 0  # Depth where message div started
        self.is_joined = False
        self.media_type = None  # photo, video, sticker, video_note, voice
        self.skipped_service = 0  # Track skipped service messages

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        class_name = attrs_dict.get('class', '')
        classes = class_name.split() if class_name else []

        if tag == 'div':
            self.div_depth += 1

            # Check for message container: div.message.default or div.message.service
            if 'message' in classes:
                # Skip service messages (like "User joined the group")
                if 'service' in classes:
                    self.skipped_service += 1
                    return  # Skip service messages

                # Only process default messages
                if 'default' in classes:
                    self.message_div_depth = self.div_depth
                    self.is_joined = 'joined' in classes
                    self.current_message = {
                        'id': None,
                        'from': self.last_sender if self.is_joined else None,
                        'date': '',
                        'text': '',
                        'has_media': False,
                        'media_file': None,  # Path to media file in export
                        'media_type': None,  # photo, video, sticker, video_note, voice
                        'type': 'message'
                    }
                    # Get message ID from id attribute (format: "message123")
                    msg_id = attrs_dict.get('id', '')
                    if msg_id.startswith('message'):
                        try:
                            self.current_message['id'] = int(msg_id[7:])
                        except ValueError:
                            pass

            elif self.current_message:
                # Check for from_name
                if 'from_name' in classes:
                    self.in_from_name = True
                    self.from_buffer = ""

                # Check for text content
                elif 'text' in classes:
                    # IMPORTANT: Close from_name when text starts
                    # This prevents message text from being added to sender name
                    self.in_from_name = False
                    self.in_text = True
                    self.text_buffer = ""

                # Check for media
                elif 'media_wrap' in classes or 'media' in classes:
                    # Also close from_name when media starts
                    self.in_from_name = False
                    self.in_media = True
                    self.current_message['has_media'] = True
                    # Detect media type from classes
                    if 'photo' in classes:
                        self.current_message['media_type'] = 'photo'
                    elif 'video' in classes:
                        self.current_message['media_type'] = 'video'
                    elif 'sticker' in classes:
                        self.current_message['media_type'] = 'sticker'
                    elif 'document' in classes:
                        self.current_message['media_type'] = 'document'
                    elif 'audio_file' in classes:
                        self.current_message['media_type'] = 'voice'

                # Check for document wrapper (separate from media_wrap)
                elif 'document_wrap' in classes or 'document' in classes:
                    self.in_from_name = False  # Close from_name
                    self.in_media = True
                    self.current_message['has_media'] = True
                    self.current_message['media_type'] = 'document'

                # Check for date (datetime in title attribute)
                elif 'date' in classes:
                    title = attrs_dict.get('title', '')
                    if title:
                        self.current_message['date'] = title

        # Capture media file paths from a, img, video tags inside media div
        elif self.in_media and self.current_message:
            if tag == 'a':
                href = attrs_dict.get('href', '')
                # Skip external links and anchors
                if href and not href.startswith('#') and not href.startswith('http'):
                    # For photos, prefer full-size over thumbnail
                    # For stickers, accept thumbs (they only have thumb versions)
                    is_thumb = '_thumb' in href
                    is_sticker = 'sticker' in href.lower()

                    # Accept if: not a thumb, OR is a sticker thumb, OR we don't have a file yet
                    if not is_thumb or is_sticker or not self.current_message.get('media_file'):
                        # Don't overwrite full-size with thumb for photos
                        if is_thumb and self.current_message.get('media_file') and not is_sticker:
                            pass  # Keep existing full-size file
                        else:
                            self.current_message['media_file'] = href
                            # Detect type from file path
                            if 'photos/' in href or href.endswith(('.jpg', '.jpeg', '.png')):
                                self.current_message['media_type'] = 'photo'
                            elif 'round_video' in href or 'video_messages/' in href:
                                # Video notes (circles) are in round_video_messages/ folder
                                self.current_message['media_type'] = 'video_note'
                            elif 'video_files/' in href or 'videos/' in href or href.endswith(('.mp4', '.webm')):
                                # Regular videos in video_files/ or videos/ folder
                                self.current_message['media_type'] = 'video'
                            elif 'stickers/' in href or is_sticker:
                                self.current_message['media_type'] = 'sticker'
                            elif 'voice_messages/' in href or href.endswith(('.ogg', '.mp3', '.wav', '.m4a', '.opus')):
                                self.current_message['media_type'] = 'voice'
                            elif 'files/' in href and not href.endswith(('.ogg', '.mp3', '.wav', '.m4a', '.opus', '.mp4', '.webm', '.mov')):
                                self.current_message['media_type'] = 'document'
                            elif href.endswith(('.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.zip', '.rar', '.7z', '.csv', '.json')):
                                self.current_message['media_type'] = 'document'
                            elif href.endswith('.webp'):
                                # .webp can be sticker or photo
                                if 'sticker' in href.lower():
                                    self.current_message['media_type'] = 'sticker'
                                else:
                                    self.current_message['media_type'] = 'photo'
            elif tag == 'img':
                src = attrs_dict.get('src', '')
                # Only use img src if we don't have a file from <a> tag yet
                if src and not src.startswith('http') and not self.current_message.get('media_file'):
                    self.current_message['media_file'] = src
                    if 'sticker' in src.lower():
                        self.current_message['media_type'] = 'sticker'
                    else:
                        self.current_message['media_type'] = 'photo'
            elif tag == 'video':
                src = attrs_dict.get('src', '')
                if src and not self.current_message.get('media_file'):
                    self.current_message['media_file'] = src
                    if 'round' in src.lower():
                        self.current_message['media_type'] = 'video_note'
                    else:
                        self.current_message['media_type'] = 'video'
            elif tag == 'audio':
                src = attrs_dict.get('src', '')
                if src and not self.current_message.get('media_file'):
                    self.current_message['media_file'] = src
                    self.current_message['media_type'] = 'voice'
            elif tag == 'source':
                src = attrs_dict.get('src', '')
                if src and not self.current_message.get('media_file'):
                    self.current_message['media_file'] = src
                    # Detect type from source src
                    if 'voice' in src.lower() or src.endswith('.ogg'):
                        self.current_message['media_type'] = 'voice'
                    elif 'round' in src.lower():
                        self.current_message['media_type'] = 'video_note'

        # Handle links in text - might be document links
        elif tag == 'a' and self.in_text and self.current_message:
            href = attrs_dict.get('href', '')
            # Check if it's a file link (not external)
            if href and not href.startswith('#') and not href.startswith('http'):
                # Check if it's a document/file by extension
                doc_extensions = ('.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
                                  '.txt', '.zip', '.rar', '.7z', '.csv', '.json')
                if href.endswith(doc_extensions) or 'files/' in href:
                    if not self.current_message.get('media_file'):
                        self.current_message['media_file'] = href
                        self.current_message['media_type'] = 'document'
                        self.current_message['has_media'] = True

        elif tag == 'br' and self.in_text:
            self.text_buffer += '\n'

    def handle_endtag(self, tag):
        if tag == 'div':
            # Check if we're closing the message div
            if self.current_message and self.div_depth == self.message_div_depth:
                # Finalize the message
                if self.from_buffer.strip():
                    self.current_message['from'] = self.from_buffer.strip()
                    self.last_sender = self.from_buffer.strip()

                if self.text_buffer.strip():
                    self.current_message['text'] = self.text_buffer.strip()

                # Save message (use last sender or "Unknown" if no sender)
                if not self.current_message.get('from'):
                    self.current_message['from'] = self.last_sender or 'Unknown'
                self.messages.append(self.current_message)

                # Reset state
                self.current_message = None
                self.in_from_name = False
                self.in_text = False
                self.in_media = False
                self.text_buffer = ""
                self.from_buffer = ""
                self.is_joined = False

            self.div_depth -= 1

        # Reset from_name flag when its span/div closes
        elif tag in ('span', 'div') and self.in_from_name:
            self.in_from_name = False

    def handle_data(self, data):
        if self.in_from_name:
            self.from_buffer += data
        elif self.in_text:
            self.text_buffer += data


def parse_html_export(html_content: str) -> List[dict]:
    """Parse Telegram HTML export and return messages list."""
    import logging
    logger = logging.getLogger("hr-analyzer")

    parser = TelegramHTMLParser()
    try:
        parser.feed(html_content)
    except (ValueError, AssertionError, MemoryError) as e:
        logger.error(f"HTML parse error: {e}")
        return []

    logger.info(f"HTML parser found {len(parser.messages)} raw messages")

    messages = []
    skipped_no_sender = 0
    skipped_empty = 0

    for msg in parser.messages:
        # Log media detection
        if msg.get('has_media') or msg.get('media_file'):
            logger.info(f"Media message: type={msg.get('media_type')}, file={msg.get('media_file')}, has_media={msg.get('has_media')}")

        # Skip if no sender (shouldn't happen now)
        if not msg.get('from'):
            skipped_no_sender += 1
            continue

        # Parse date (format: "DD.MM.YYYY HH:MM:SS" or "DD.MM.YYYY HH:MM:SS UTC+03:00")
        date_str = msg.get('date', '')

        # Strip timezone suffix like " UTC+03:00"
        if ' UTC' in date_str:
            date_str = date_str.split(' UTC')[0]

        logger.info(f"HTML Parser - cleaned date string: '{date_str}'")

        try:
            if '.' in date_str and len(date_str.split('.')[0]) <= 2:
                # Russian format: DD.MM.YYYY HH:MM:SS
                parsed_date = datetime.strptime(date_str, '%d.%m.%Y %H:%M:%S')
                logger.info(f"HTML Parser - parsed as DD.MM.YYYY: {parsed_date}")
            elif 'T' in date_str:
                # ISO format
                parsed_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                logger.info(f"HTML Parser - parsed as ISO: {parsed_date}")
            else:
                parsed_date = datetime.now()
                logger.warning(f"HTML Parser - using datetime.now() for unknown format: '{date_str}'")
        except (ValueError, AttributeError) as e:
            parsed_date = datetime.now()
            logger.error(f"HTML Parser - date parse error for '{date_str}': {e}")

        # Determine text content and media type
        text = msg.get('text', '').strip()
        media_file = msg.get('media_file')
        media_type = msg.get('media_type')

        # Handle messages with media
        if msg.get('has_media') or media_file:
            if not media_type:
                # Try to detect type from file path
                if media_file:
                    if 'photo' in media_file or media_file.endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp')):
                        media_type = 'photo'
                    elif 'sticker' in media_file:
                        media_type = 'sticker'
                    elif 'round' in media_file or 'video_note' in media_file:
                        media_type = 'video_note'
                    elif 'video' in media_file or media_file.endswith(('.mp4', '.webm', '.mov')):
                        media_type = 'video'
                    elif 'voice' in media_file or media_file.endswith(('.ogg', '.opus', '.mp3', '.wav', '.m4a')):
                        media_type = 'voice'
                    elif ('files/' in media_file and not media_file.endswith(('.ogg', '.opus', '.mp3', '.wav', '.m4a', '.mp4', '.webm', '.mov'))) or media_file.endswith(('.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.zip', '.rar', '.7z', '.csv', '.json')):
                        media_type = 'document'

            if not text:
                # Set appropriate placeholder based on media type
                if media_type == 'photo':
                    text = '[Фото]'
                elif media_type == 'video_note':
                    text = '[Видео-кружок]'
                elif media_type == 'video':
                    text = '[Видео]'
                elif media_type == 'sticker':
                    text = '[Стикер]'
                elif media_type == 'voice':
                    text = '[Голосовое сообщение]'
                elif media_type == 'document':
                    text = '[Файл]'
                else:
                    text = '[Медиа]'
        elif not text:
            skipped_empty += 1
            continue  # Skip empty messages without media

        messages.append({
            'id': msg.get('id'),
            'type': 'message',
            'date': parsed_date.isoformat(),
            'from': msg.get('from'),
            'from_id': '',
            'text': text,
            'media_file': media_file,  # Path to media file in export
            'media_type': media_type   # photo, video, sticker, video_note, voice
        })

    logger.info(f"HTML parse result: {len(messages)} messages, skipped {skipped_no_sender} (no sender), {skipped_empty} (empty), {parser.skipped_service} (service)")
    return messages


@router.post("/{chat_id}/import")
async def import_telegram_history(
    chat_id: int,
    file: UploadFile = File(...),
    auto_process: bool = Query(True, description="Auto-transcribe voice/video and parse documents"),
    import_id: str = Query(None, description="Optional import ID for progress tracking"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Import chat history from Telegram Desktop export (JSON, HTML or ZIP format).

    Expected format: result.json, messages.html or ZIP archive containing them

    Set auto_process=true to automatically transcribe voice/video and parse documents.
    This is slow but provides immediate content. Otherwise use manual transcription buttons.

    Pass import_id to enable progress tracking via GET /{chat_id}/import/progress/{import_id}
    """
    import logging
    logger = logging.getLogger("hr-analyzer")

    # Initialize progress tracking
    if import_id:
        with _import_progress_lock:
            import_progress[import_id] = {
                "status": "starting",
                "phase": "reading_file",
                "current": 0,
                "total": 0,
                "imported": 0,
                "skipped": 0,
                "current_file": None
            }

    user = await db.merge(user)

    # Get user's organization
    org = await get_user_org(user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Chat not found")

    # Check chat exists and user has access
    result = await db.execute(select(Chat).where(
        Chat.id == chat_id,
        Chat.org_id == org.id,
        Chat.deleted_at.is_(None)
    ))
    chat = result.scalar_one_or_none()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    permissions = PermissionService(db)
    if not await permissions.can_access_resource(user, chat, "read"):
        raise HTTPException(status_code=403, detail="Access denied")

    # Read file content
    messages_data = None
    is_html_source = False  # Track if data came from HTML parser
    filename = file.filename.lower() if file.filename else ""

    logger.info(f"Import started for chat {chat_id}, file: {filename}")

    try:
        content = await file.read()
        logger.info(f"File size: {len(content)} bytes")

        # Variables for ZIP file handling
        zip_file = None
        zip_bytes = None

        # Check if it's a ZIP file
        if filename.endswith('.zip'):
            try:
                zip_bytes = io.BytesIO(content)
                zip_file = zipfile.ZipFile(zip_bytes)

                # First try to find JSON file
                target_file = None
                is_html = False

                file_list = zip_file.namelist()
                logger.info(f"ZIP contents: {file_list}")

                for name in file_list:
                    if name.endswith('result.json') or name == 'result.json':
                        target_file = name
                        break

                if not target_file:
                    for name in file_list:
                        if name.endswith('.json'):
                            target_file = name
                            break

                # If no JSON, try HTML
                if not target_file:
                    for name in file_list:
                        if name.endswith('.html') or name.endswith('.htm'):
                            target_file = name
                            is_html = True
                            break

                if not target_file:
                    zip_file.close()
                    raise HTTPException(status_code=400, detail="ZIP-архив не содержит JSON или HTML файл")

                logger.info(f"Using file from ZIP: {target_file}, is_html: {is_html}")
                file_content = zip_file.read(target_file).decode('utf-8')

                if is_html:
                    messages_data = parse_html_export(file_content)
                    is_html_source = True
                    logger.info(f"HTML parsed, got {len(messages_data)} messages")
                else:
                    data = json.loads(file_content)
                    messages_data = data.get('messages', [])
                    logger.info(f"JSON parsed, got {len(messages_data)} messages")

            except zipfile.BadZipFile:
                raise HTTPException(status_code=400, detail="Повреждённый ZIP-архив")

        # Check if it's an HTML file
        elif filename.endswith('.html') or filename.endswith('.htm'):
            html_content = content.decode('utf-8')
            messages_data = parse_html_export(html_content)
            is_html_source = True
            logger.info(f"HTML file parsed, got {len(messages_data)} messages")

        # Regular JSON file
        else:
            data = json.loads(content.decode('utf-8'))
            messages_data = data.get('messages', [])
            logger.info(f"JSON file parsed, got {len(messages_data)} messages")

    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
        raise HTTPException(status_code=400, detail=f"Неверный формат JSON: {str(e)}")
    except HTTPException:
        raise
    except (UnicodeDecodeError, OSError, KeyError, ValueError) as e:
        logger.error(f"File read error: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Ошибка чтения файла: {str(e)}")

    # Validate structure
    if not messages_data:
        if import_id:
            with _import_progress_lock:
                import_progress[import_id] = {"status": "error", "error": "Файл не содержит сообщений"}
        raise HTTPException(status_code=400, detail="Файл не содержит сообщений")

    # Update progress - parsing complete
    if import_id:
        with _import_progress_lock:
            import_progress[import_id].update({
                "status": "processing",
                "phase": "importing",
                "total": len(messages_data),
                "current": 0
            })

    # Get existing message IDs and hashes for deduplication
    existing_result = await db.execute(
        select(Message.telegram_message_id, Message.content, Message.timestamp, Message.file_path)
        .where(Message.chat_id == chat_id)
    )
    existing_messages = existing_result.fetchall()

    existing_msg_ids = {row[0] for row in existing_messages if row[0] is not None}
    existing_hashes = {get_content_hash(row[1], row[2], row[3]) for row in existing_messages}

    imported_count = 0
    skipped_count = 0
    errors = []

    for msg_idx, msg in enumerate(messages_data):
        try:
            # Update progress every 10 messages
            if import_id and msg_idx % 10 == 0:
                with _import_progress_lock:
                    import_progress[import_id].update({
                        "current": msg_idx,
                        "imported": imported_count,
                        "skipped": skipped_count
                    })

            # Skip service messages
            if msg.get('type') != 'message':
                continue

            telegram_msg_id = msg.get('id')

            # Check for duplicates by message_id
            if telegram_msg_id and telegram_msg_id in existing_msg_ids:
                skipped_count += 1
                continue

            # Handle differently based on source
            file_path = None  # For imported media files
            document_metadata = None
            parse_status = None
            parse_error = None

            if is_html_source:
                # HTML parser already extracted text in 'text' field
                content = msg.get('text', '')
                content_type = msg.get('media_type') or 'text'
                timestamp = parse_telegram_date(msg.get('date', ''))
                from_name = msg.get('from', 'Unknown')
                from_id = msg.get('from_id', '')

                # Extract media file from ZIP if available
                media_file = msg.get('media_file')
                if media_file and zip_file:
                    try:
                        # Create uploads directory for this chat
                        chat_uploads_dir = UPLOADS_DIR / str(chat_id)
                        chat_uploads_dir.mkdir(parents=True, exist_ok=True)

                        # Try to find the file in ZIP (might have different path prefix)
                        file_found = False

                        # For video_note, if we have a thumb file, find the actual video
                        search_file = media_file
                        if content_type == 'video_note' and '_thumb.jpg' in media_file:
                            # Strip _thumb.jpg to get actual video filename
                            search_file = media_file.replace('_thumb.jpg', '')
                            logger.info(f"Video note: looking for {search_file} instead of thumb {media_file}")

                        # Get just the filename for more flexible matching
                        search_filename = os.path.basename(search_file)

                        for zip_path in zip_file.namelist():
                            zip_filename = os.path.basename(zip_path)

                            # Match by filename or full path
                            if zip_filename == search_filename or zip_path.endswith(search_file) or search_file in zip_path:
                                # Make sure it's the actual file, not another thumb
                                if '_thumb' in zip_path and '_thumb' not in search_file:
                                    logger.debug(f"Skipping thumb file: {zip_path}")
                                    continue
                                # Extract and save the file
                                file_data = zip_file.read(zip_path)
                                # Create a unique filename
                                safe_name = os.path.basename(search_file)
                                if telegram_msg_id:
                                    safe_name = f"{telegram_msg_id}_{safe_name}"
                                dest_path = chat_uploads_dir / safe_name
                                dest_path.write_bytes(file_data)
                                file_path = f"uploads/{chat_id}/{safe_name}"
                                file_found = True
                                logger.info(f"Extracted media: {zip_path} -> {file_path}")
                                break

                        if not file_found:
                            logger.warning(f"Media file not found in ZIP: {media_file} (searching for: {search_filename})")
                            # List available files in ZIP for debugging video_note issues
                            if content_type == 'video_note':
                                round_videos = [z for z in zip_file.namelist() if 'round_video' in z.lower()]
                                logger.warning(f"Available round_video files in ZIP: {round_videos[:5]}")
                        elif auto_process and file_data:
                            # Update progress with current file
                            if import_id:
                                with _import_progress_lock:
                                    import_progress[import_id].update({
                                        "current_file": os.path.basename(media_file),
                                        "phase": "processing_media"
                                    })

                            # Auto-transcribe voice and video files (only if auto_process=True)
                            if content_type in ('voice', 'video_note', 'video'):
                                try:
                                    logger.info(f"Auto-transcribing {content_type}: {file_path}")
                                    if content_type == 'voice':
                                        transcription = await transcription_service.transcribe_audio(file_data)
                                    else:
                                        transcription = await transcription_service.transcribe_video(file_data, media_file)

                                    # Only use transcription if successful (not an error message)
                                    if transcription and not transcription.startswith("["):
                                        content = transcription
                                        logger.info(f"Transcription success: {transcription[:50]}...")
                                    else:
                                        logger.warning(f"Transcription returned: {transcription}")
                                except Exception as e:
                                    logger.error(f"Auto-transcription error: {e}")

                            # Auto-parse documents and photos (OCR)
                            elif content_type in ('document', 'photo'):
                                try:
                                    file_name_for_parse = os.path.basename(media_file)
                                    logger.info(f"Auto-parsing {content_type}: {file_name_for_parse}")
                                    result = await document_parser.parse(file_data, file_name_for_parse)
                                    if result.content and result.status in ('parsed', 'partial'):
                                        content = result.content
                                        document_metadata = result.metadata
                                        parse_status = result.status
                                        logger.info(f"Parse success: {content[:50]}...")
                                    else:
                                        parse_status = result.status
                                        parse_error = result.error
                                        logger.warning(f"Parse returned: {result.error}")
                                except Exception as e:
                                    logger.error(f"Auto-parse error: {e}")
                                    parse_status = "failed"
                                    parse_error = str(e)
                    except (KeyError, OSError, RuntimeError, zipfile.BadZipFile) as e:
                        logger.error(f"Error extracting media {media_file}: {e}")
            else:
                # JSON format - use original extract functions
                timestamp = parse_telegram_date(msg.get('date', ''))
                content = extract_text_content(msg)
                content_type = detect_content_type(msg)
                from_name = msg.get('from', 'Unknown')
                from_id = msg.get('from_id', '')

            # Auto-parse Google Docs links in text messages
            if auto_process and content_type == 'text' and content:
                # Check for Google Docs links in the message
                google_docs_urls = re.findall(
                    r'https?://docs\.google\.com/document/d/[a-zA-Z0-9_-]+[^\s]*',
                    content
                )
                if google_docs_urls:
                    for gdoc_url in google_docs_urls[:3]:  # Limit to 3 links per message
                        try:
                            logger.info(f"Auto-parsing Google Doc: {gdoc_url}")
                            result = await google_docs_service.parse_from_url(gdoc_url)
                            if result.content and result.status in ('parsed', 'partial'):
                                # Append parsed content to message
                                content += f"\n\n--- Содержимое документа ---\n{result.content[:5000]}"
                                if not document_metadata:
                                    document_metadata = {}
                                document_metadata['google_doc_url'] = gdoc_url
                                document_metadata['google_doc_parsed'] = True
                                parse_status = result.status
                                logger.info(f"Google Doc parsed: {result.content[:100]}...")
                            else:
                                logger.warning(f"Google Doc parse failed: {result.error}")
                        except Exception as e:
                            logger.error(f"Google Doc auto-parse error: {e}")

            # Check for duplicates by content hash (when no message_id)
            # For media messages, use media_file for stable hash
            media_file_for_hash = msg.get('media_file') if is_html_source else None
            content_hash = get_content_hash(content, timestamp, media_file_for_hash)
            if content_hash in existing_hashes:
                skipped_count += 1
                continue

            # Parse telegram user ID from string like "user123456"
            # For HTML imports without user IDs, generate consistent ID from name
            telegram_user_id = 0
            if isinstance(from_id, str) and from_id.startswith('user'):
                try:
                    telegram_user_id = int(from_id[4:])
                except ValueError:
                    pass
            elif isinstance(from_id, int):
                telegram_user_id = from_id

            # If no user ID, generate one from the sender name (for HTML imports)
            if telegram_user_id == 0 and from_name:
                # Normalize name for consistent hashing (lowercase, strip spaces, remove extra whitespace)
                normalized_name = ' '.join(from_name.lower().split())
                # Generate consistent ID from name hash (negative to avoid collision with real IDs)
                name_hash = hashlib.md5(normalized_name.encode()).hexdigest()[:8]
                telegram_user_id = -abs(int(name_hash, 16) % 1000000000)

            # Split name into first/last name
            name_parts = from_name.split(' ', 1) if from_name else ['Unknown']
            first_name = (name_parts[0] if name_parts else 'Unknown')[:255]  # Truncate to 255
            last_name = (name_parts[1] if len(name_parts) > 1 else None)
            if last_name:
                last_name = last_name[:255]  # Truncate to 255

            # Get file_name from msg or extract from media_file path
            file_name = msg.get('file_name')
            if not file_name and file_path:
                # Extract filename from path like "uploads/3/123_document.pdf"
                file_name = os.path.basename(file_path)
                # Remove message ID prefix if present (e.g., "123_document.pdf" -> "document.pdf")
                if '_' in file_name and file_name.split('_')[0].isdigit():
                    file_name = '_'.join(file_name.split('_')[1:])
            if file_name:
                file_name = file_name[:255]

            # Create message
            new_message = Message(
                chat_id=chat_id,
                telegram_message_id=telegram_msg_id,
                telegram_user_id=telegram_user_id,
                username=None,  # Not available in export
                first_name=first_name,
                last_name=last_name,
                content=content,
                content_type=content_type[:50] if content_type else 'text',  # Truncate to 50
                file_id=None,  # Telegram Bot API file_id (not available in export)
                file_path=file_path,  # Local file path for imported media
                file_name=file_name,
                document_metadata=document_metadata,
                parse_status=parse_status,
                parse_error=parse_error,
                is_imported=True,  # Mark as imported from file
                timestamp=timestamp,
            )

            db.add(new_message)
            existing_msg_ids.add(telegram_msg_id)
            existing_hashes.add(content_hash)
            imported_count += 1

        except Exception as e:
            logger.error(f"Error importing message {msg.get('id', '?')}: {e}")
            errors.append(f"Message {msg.get('id', '?')}: {str(e)}")
            continue

    # Close ZIP file if open
    if zip_file:
        try:
            zip_file.close()
        except (OSError, RuntimeError):
            pass  # Ignore errors when closing ZIP file

    # Update chat's last_activity if we imported newer messages
    if imported_count > 0:
        await db.commit()
        logger.info(f"Imported {imported_count} messages, skipped {skipped_count}")

        # Get the latest message timestamp
        latest_result = await db.execute(
            select(func.max(Message.timestamp)).where(Message.chat_id == chat_id)
        )
        latest_timestamp = latest_result.scalar()
        if latest_timestamp and (not chat.last_activity or latest_timestamp > chat.last_activity):
            chat.last_activity = latest_timestamp
            await db.commit()

    # Update final progress
    if import_id:
        with _import_progress_lock:
            import_progress[import_id] = {
                "status": "completed",
                "phase": "done",
                "current": len(messages_data),
                "total": len(messages_data),
                "imported": imported_count,
                "skipped": skipped_count,
                "current_file": None
            }
        # Schedule cleanup after 60 seconds (thread-safe pop)
        def _cleanup_progress():
            with _import_progress_lock:
                import_progress.pop(import_id, None)
        asyncio.get_event_loop().call_later(60, _cleanup_progress)

    return {
        "success": True,
        "imported": imported_count,
        "skipped": skipped_count,
        "errors": errors[:10] if errors else [],  # Return first 10 errors
        "total_errors": len(errors),
        "import_id": import_id,
    }


@router.get("/{chat_id}/import/progress/{import_id}")
async def get_import_progress(
    chat_id: int,
    import_id: str,
    user: User = Depends(get_current_user),
):
    """Get import progress by import_id."""
    with _import_progress_lock:
        progress = import_progress.get(import_id)
        if not progress:
            return {"status": "not_found"}
        # Return a copy to avoid race conditions
        return dict(progress)


@router.post("/{chat_id}/repair-video-notes")
async def repair_video_notes(
    chat_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Repair video_note files from ZIP without re-importing messages.

    Finds all video_note messages in the chat and re-extracts
    the actual video files from the ZIP (not thumbnails).
    """
    import logging
    logger = logging.getLogger("hr-analyzer")

    user = await db.merge(user)

    # Get user's organization
    org = await get_user_org(user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Chat not found")

    result = await db.execute(select(Chat).where(
        Chat.id == chat_id,
        Chat.org_id == org.id,
        Chat.deleted_at.is_(None)
    ))
    chat = result.scalar_one_or_none()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    permissions = PermissionService(db)
    if not await permissions.can_access_resource(user, chat, "read"):
        raise HTTPException(status_code=403, detail="Access denied")

    # Read the ZIP file
    content = await file.read()

    try:
        zip_file = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid ZIP file")

    # Find all video_note messages
    result = await db.execute(
        select(Message).where(
            Message.chat_id == chat_id,
            Message.content_type == 'video_note',
            Message.file_path.isnot(None)
        )
    )
    video_notes = result.scalars().all()

    if not video_notes:
        return {"repaired": 0, "message": "No video_note messages found"}

    # List all .mp4 files in ZIP (not thumbs)
    mp4_files = [z for z in zip_file.namelist()
                 if z.endswith('.mp4') and '_thumb' not in z and 'round_video' in z.lower()]

    logger.info(f"Found {len(video_notes)} video_notes and {len(mp4_files)} mp4 files in ZIP")
    logger.info(f"MP4 files: {mp4_files}")

    repaired = 0
    chat_uploads_dir = UPLOADS_DIR / str(chat_id)
    chat_uploads_dir.mkdir(parents=True, exist_ok=True)

    for msg in video_notes:
        # Extract filename from current file_path
        if not msg.file_path:
            continue

        current_filename = os.path.basename(msg.file_path)
        # Remove message ID prefix if present
        base_filename = current_filename
        if '_' in current_filename:
            parts = current_filename.split('_', 1)
            if parts[0].isdigit():
                base_filename = parts[1]

        # Remove _thumb.jpg if present in base filename
        if '_thumb.jpg' in base_filename:
            base_filename = base_filename.replace('_thumb.jpg', '')

        logger.info(f"Looking for video matching: {base_filename}")

        # Find matching file in ZIP
        for zip_path in mp4_files:
            zip_filename = os.path.basename(zip_path)
            if zip_filename == base_filename or base_filename in zip_filename:
                # Found it! Extract and replace
                file_data = zip_file.read(zip_path)

                # Keep the same filename in uploads
                dest_path = chat_uploads_dir / current_filename
                dest_path.write_bytes(file_data)

                logger.info(f"Repaired: {zip_path} -> {dest_path}")
                repaired += 1
                break

    zip_file.close()
    return {"repaired": repaired, "total": len(video_notes)}


@router.delete("/{chat_id}/import/cleanup")
async def cleanup_bad_import(
    chat_id: int,
    mode: str = Query("bad", description="Cleanup mode: 'bad' for Unknown/[Медиа], 'today' for messages with today's date, 'all_imported' for all without telegram_message_id"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Delete badly imported messages.

    Modes:
    - bad: Delete messages with Unknown sender and [Медиа] content
    - today: Delete messages with today's timestamp (wrong date import)
    - all_imported: Delete all messages without telegram_message_id (imported from file)
    """
    user = await db.merge(user)

    # Get user's organization
    org = await get_user_org(user, db)
    if not org:
        raise HTTPException(status_code=404, detail="Chat not found")

    result = await db.execute(select(Chat).where(
        Chat.id == chat_id,
        Chat.org_id == org.id,
        Chat.deleted_at.is_(None)
    ))
    chat = result.scalar_one_or_none()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    permissions = PermissionService(db)
    if not await permissions.can_access_resource(user, chat, "read"):
        raise HTTPException(status_code=403, detail="Access denied")

    deleted_count = 0

    if mode == "bad":
        # Delete messages with Unknown sender and [Медиа] content
        delete_result = await db.execute(
            delete(Message).where(
                Message.chat_id == chat_id,
                Message.first_name == 'Unknown',
                Message.content == '[Медиа]'
            )
        )
        deleted_count = delete_result.rowcount

    elif mode == "today":
        # Delete messages with today's timestamp (likely wrong date import)
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        delete_result = await db.execute(
            delete(Message).where(
                Message.chat_id == chat_id,
                Message.timestamp >= today_start
            )
        )
        deleted_count = delete_result.rowcount

    elif mode == "all_imported":
        # Delete all imported messages (is_imported=True flag)
        delete_result = await db.execute(
            delete(Message).where(
                Message.chat_id == chat_id,
                Message.is_imported == True
            )
        )
        deleted_count = delete_result.rowcount

    elif mode == "all":
        # Delete all imported messages (is_imported=True)
        delete_result = await db.execute(
            delete(Message).where(
                Message.chat_id == chat_id,
                Message.is_imported == True
            )
        )
        deleted_count = delete_result.rowcount

    elif mode == "clear_all":
        # Delete ALL messages in the chat (nuclear option)
        delete_result = await db.execute(
            delete(Message).where(Message.chat_id == chat_id)
        )
        deleted_count = delete_result.rowcount

    elif mode == "duplicates":
        # Find and remove duplicate messages (same timestamp and content/file_path)
        # Keep the first (lowest id) message, delete others
        from sqlalchemy import and_, or_

        # Get all messages in the chat
        result = await db.execute(
            select(Message)
            .where(Message.chat_id == chat_id)
            .order_by(Message.id)
        )
        all_messages = result.scalars().all()

        # Find duplicates - group by timestamp + (content or file_path)
        seen = {}  # key -> first message id
        duplicates_to_delete = []

        for msg in all_messages:
            # Create a key for deduplication
            if msg.file_path:
                key = f"{msg.timestamp.isoformat()}:file:{msg.file_path}"
            else:
                key = f"{msg.timestamp.isoformat()}:text:{msg.content[:100] if msg.content else ''}"

            if key in seen:
                # This is a duplicate, mark for deletion
                duplicates_to_delete.append(msg.id)
            else:
                seen[key] = msg.id

        # Delete duplicates
        if duplicates_to_delete:
            delete_result = await db.execute(
                delete(Message).where(Message.id.in_(duplicates_to_delete))
            )
            deleted_count = delete_result.rowcount

    await db.commit()

    return {
        "success": True,
        "deleted": deleted_count,
        "mode": mode,
    }


@router.post("/{chat_id}/share")
async def share_chat(
    chat_id: int,
    data: ShareRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Share a chat with another user.

    Permissions:
    - MEMBER → only within their department
    - ADMIN → their department + admins of other departments + OWNER/SUPERADMIN
    - OWNER → anyone in organization
    - SUPERADMIN → anyone
    """
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    # Get chat
    result = await db.execute(
        select(Chat).where(
            Chat.id == chat_id,
            Chat.org_id == org.id,
            Chat.deleted_at.is_(None)
        )
    )
    chat = result.scalar_one_or_none()

    if not chat:
        raise HTTPException(404, "Chat not found")

    # Check if user has permission to share this chat (requires full access or ownership)
    can_share = False
    if current_user.role == UserRole.superadmin:
        can_share = True
    else:
        user_role = await get_user_org_role(current_user, org.id, db)
        if user_role == "owner":
            can_share = True
        elif chat.owner_id == current_user.id:
            can_share = True  # Owner of chat
        else:
            # Check if shared with full access
            shared_result = await db.execute(
                select(SharedAccess).where(
                    SharedAccess.resource_type == ResourceType.chat,
                    SharedAccess.resource_id == chat_id,
                    SharedAccess.shared_with_id == current_user.id,
                    SharedAccess.access_level == AccessLevel.full,
                    or_(SharedAccess.expires_at.is_(None), SharedAccess.expires_at > datetime.utcnow())
                )
            )
            if shared_result.scalar_one_or_none():
                can_share = True

    if not can_share:
        raise HTTPException(403, "No permission to share this chat")

    # Get target user
    to_user_result = await db.execute(
        select(User).where(User.id == data.shared_with_id)
    )
    to_user = to_user_result.scalar_one_or_none()

    if not to_user:
        raise HTTPException(404, "Target user not found")

    # Check if current_user can share with to_user
    if not await can_share_to(current_user, to_user, org.id, db):
        raise HTTPException(403, "You cannot share with this user based on your role and department")

    # Check if already shared
    existing_result = await db.execute(
        select(SharedAccess).where(
            SharedAccess.resource_type == ResourceType.chat,
            SharedAccess.resource_id == chat_id,
            SharedAccess.shared_with_id == data.shared_with_id
        )
    )
    existing_share = existing_result.scalar_one_or_none()

    if existing_share:
        # Update existing share
        existing_share.access_level = data.access_level
        existing_share.note = data.note
        existing_share.expires_at = data.expires_at
        existing_share.shared_by_id = current_user.id
    else:
        # Create new share
        share = SharedAccess(
            resource_type=ResourceType.chat,
            resource_id=chat_id,
            chat_id=chat_id,  # FK for cascade delete
            shared_by_id=current_user.id,
            shared_with_id=data.shared_with_id,
            access_level=data.access_level,
            note=data.note,
            expires_at=data.expires_at
        )
        db.add(share)

    await db.commit()

    return {
        "success": True,
        "chat_id": chat_id,
        "shared_with_id": data.shared_with_id,
        "access_level": data.access_level.value
    }
