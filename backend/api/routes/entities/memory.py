"""
Entity memory/notes operations - AI profiles, sharing, linking chats/calls.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, Request
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel
import asyncio

from .common import (
    logger, get_db, Entity, EntityType, Chat, CallRecording, User, Message,
    SharedAccess, ResourceType, UserRole, AccessLevel, Department,
    DepartmentMember, DeptRole, Vacancy, VacancyApplication, VacancyStatus,
    ApplicationStage, STAGE_SYNC_MAP,
    get_current_user, get_user_org, get_user_org_role, can_share_to,
    has_full_database_access, ShareRequest, limiter, _get_rate_limit_key,
    check_entity_access, regenerate_entity_profile_background
)

router = APIRouter()


# === Chat/Call Linking ===

@router.post("/{entity_id}/link-chat/{chat_id}")
async def link_chat_to_entity(
    entity_id: int,
    chat_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Link a chat to a contact"""
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    # Verify entity exists and belongs to same org
    entity_result = await db.execute(
        select(Entity).where(Entity.id == entity_id, Entity.org_id == org.id)
    )
    entity = entity_result.scalar_one_or_none()
    if not entity:
        raise HTTPException(404, "Entity not found")

    # Check edit permissions - requires edit or full access
    has_access = await check_entity_access(entity, current_user, org.id, db, required_level=AccessLevel.edit)
    if not has_access:
        raise HTTPException(403, "No edit permission for this entity")

    # Get and update chat (must belong to same org)
    chat_result = await db.execute(
        select(Chat).where(Chat.id == chat_id, Chat.org_id == org.id)
    )
    chat = chat_result.scalar_one_or_none()

    if not chat:
        raise HTTPException(404, "Chat not found")

    chat.entity_id = entity_id
    await db.commit()

    # Generate/regenerate AI profile in background with new chat context
    # Always generate profile when new context is added (chat, call, file)
    background_tasks.add_task(
        asyncio.create_task,
        regenerate_entity_profile_background(entity_id, org.id)
    )

    return {"success": True}


@router.delete("/{entity_id}/unlink-chat/{chat_id}")
async def unlink_chat_from_entity(
    entity_id: int,
    chat_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Unlink a chat from a contact"""
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    # Verify entity exists and user has edit access
    entity_result = await db.execute(
        select(Entity).where(Entity.id == entity_id, Entity.org_id == org.id)
    )
    entity = entity_result.scalar_one_or_none()
    if not entity:
        raise HTTPException(404, "Entity not found")

    # Check edit permissions - requires edit or full access
    has_access = await check_entity_access(entity, current_user, org.id, db, required_level=AccessLevel.edit)
    if not has_access:
        raise HTTPException(403, "No edit permission for this entity")

    chat_result = await db.execute(
        select(Chat).where(
            Chat.id == chat_id,
            Chat.entity_id == entity_id,
            Chat.org_id == org.id
        )
    )
    chat = chat_result.scalar_one_or_none()

    if not chat:
        raise HTTPException(404, "Chat not found or not linked to this entity")

    chat.entity_id = None
    await db.commit()
    return {"success": True}


@router.post("/{entity_id}/link-call/{call_id}")
async def link_call_to_entity(
    entity_id: int,
    call_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Link a call recording to an entity (candidate/contact).
    """
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    # Verify entity exists and belongs to same org
    entity_result = await db.execute(
        select(Entity).where(Entity.id == entity_id, Entity.org_id == org.id)
    )
    entity = entity_result.scalar_one_or_none()
    if not entity:
        raise HTTPException(404, "Entity not found")

    # Check edit permissions - requires edit or full access
    has_access = await check_entity_access(entity, current_user, org.id, db, required_level=AccessLevel.edit)
    if not has_access:
        raise HTTPException(403, "No edit permission for this entity")

    # Get and update call (must belong to same org)
    call_result = await db.execute(
        select(CallRecording).where(CallRecording.id == call_id, CallRecording.org_id == org.id)
    )
    call = call_result.scalar_one_or_none()

    if not call:
        raise HTTPException(404, "Call not found")

    call.entity_id = entity_id
    await db.commit()

    # Generate/regenerate AI profile in background with new call context
    # Always generate profile when new context is added (chat, call, file)
    background_tasks.add_task(
        asyncio.create_task,
        regenerate_entity_profile_background(entity_id, org.id)
    )

    return {"success": True, "entity_id": entity_id, "call_id": call_id}


@router.delete("/{entity_id}/unlink-call/{call_id}")
async def unlink_call_from_entity(
    entity_id: int,
    call_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Unlink a call recording from an entity (candidate/contact).
    """
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    # Verify entity exists and user has edit access
    entity_result = await db.execute(
        select(Entity).where(Entity.id == entity_id, Entity.org_id == org.id)
    )
    entity = entity_result.scalar_one_or_none()
    if not entity:
        raise HTTPException(404, "Entity not found")

    # Check edit permissions - requires edit or full access
    has_access = await check_entity_access(entity, current_user, org.id, db, required_level=AccessLevel.edit)
    if not has_access:
        raise HTTPException(403, "No edit permission for this entity")

    call_result = await db.execute(
        select(CallRecording).where(
            CallRecording.id == call_id,
            CallRecording.entity_id == entity_id,
            CallRecording.org_id == org.id
        )
    )
    call = call_result.scalar_one_or_none()

    if not call:
        raise HTTPException(404, "Call not found or not linked to this entity")

    call.entity_id = None
    await db.commit()
    return {"success": True}


# === Sharing ===

@router.post("/{entity_id}/share")
async def share_entity(
    entity_id: int,
    data: ShareRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Share an entity (contact) with another user.

    If auto_share_related=True, automatically shares all related chats and calls
    with the same access level.
    """
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    # Get entity
    result = await db.execute(
        select(Entity).where(Entity.id == entity_id, Entity.org_id == org.id)
    )
    entity = result.scalar_one_or_none()

    if not entity:
        raise HTTPException(404, "Entity not found")

    # Check if user has permission to share this entity (requires full access or ownership)
    can_share = False
    if current_user.role == UserRole.superadmin:
        can_share = True
    else:
        # Full access (owner or member with has_full_access) can share all
        user_has_full_access = await has_full_database_access(current_user, org.id, db)
        if user_has_full_access:
            can_share = True
        elif entity.created_by == current_user.id:
            can_share = True  # Owner of entity
        else:
            # Check if shared with full access
            shared_result = await db.execute(
                select(SharedAccess).where(
                    SharedAccess.resource_type == ResourceType.entity,
                    SharedAccess.resource_id == entity_id,
                    SharedAccess.shared_with_id == current_user.id,
                    SharedAccess.access_level == AccessLevel.full,
                    or_(SharedAccess.expires_at.is_(None), SharedAccess.expires_at > datetime.utcnow())
                )
            )
            if shared_result.scalar_one_or_none():
                can_share = True

    if not can_share:
        raise HTTPException(403, "No permission to share this entity")

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
            SharedAccess.resource_type == ResourceType.entity,
            SharedAccess.resource_id == entity_id,
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
            resource_type=ResourceType.entity,
            resource_id=entity_id,
            entity_id=entity_id,  # FK for cascade delete
            shared_by_id=current_user.id,
            shared_with_id=data.shared_with_id,
            access_level=data.access_level,
            note=data.note,
            expires_at=data.expires_at
        )
        db.add(share)

    await db.commit()

    # Auto-share related chats and calls if requested
    shared_chats = 0
    shared_calls = 0

    if data.auto_share_related:
        # Find all chats and calls linked to this entity
        chats_result = await db.execute(
            select(Chat).where(Chat.entity_id == entity_id, Chat.org_id == org.id)
        )
        chats = chats_result.scalars().all()
        chat_ids = [c.id for c in chats]

        calls_result = await db.execute(
            select(CallRecording).where(CallRecording.entity_id == entity_id, CallRecording.org_id == org.id)
        )
        calls = calls_result.scalars().all()
        call_ids = [c.id for c in calls]

        # Batch fetch all existing shares for this user (avoid N+1 queries)
        existing_shares_result = await db.execute(
            select(SharedAccess).where(
                SharedAccess.shared_with_id == data.shared_with_id,
                ((SharedAccess.resource_type == ResourceType.chat) & (SharedAccess.resource_id.in_(chat_ids))) |
                ((SharedAccess.resource_type == ResourceType.call) & (SharedAccess.resource_id.in_(call_ids)))
            )
        ) if chat_ids or call_ids else None

        # Build lookup dict: (resource_type, resource_id) -> SharedAccess
        existing_shares_map = {}
        if existing_shares_result:
            for share in existing_shares_result.scalars().all():
                existing_shares_map[(share.resource_type, share.resource_id)] = share

        # Process chats
        for chat in chats:
            key = (ResourceType.chat, chat.id)
            if key in existing_shares_map:
                # Update existing
                existing_share = existing_shares_map[key]
                existing_share.access_level = data.access_level
                existing_share.expires_at = data.expires_at
                existing_share.shared_by_id = current_user.id
            else:
                # Create new share for chat
                chat_share = SharedAccess(
                    resource_type=ResourceType.chat,
                    resource_id=chat.id,
                    chat_id=chat.id,  # FK for cascade delete
                    shared_by_id=current_user.id,
                    shared_with_id=data.shared_with_id,
                    access_level=data.access_level,
                    expires_at=data.expires_at
                )
                db.add(chat_share)
                shared_chats += 1

        # Process calls
        for call in calls:
            key = (ResourceType.call, call.id)
            if key in existing_shares_map:
                # Update existing
                existing_share = existing_shares_map[key]
                existing_share.access_level = data.access_level
                existing_share.expires_at = data.expires_at
                existing_share.shared_by_id = current_user.id
            else:
                # Create new share for call
                call_share = SharedAccess(
                    resource_type=ResourceType.call,
                    resource_id=call.id,
                    call_id=call.id,  # FK for cascade delete
                    shared_by_id=current_user.id,
                    shared_with_id=data.shared_with_id,
                    access_level=data.access_level,
                    expires_at=data.expires_at
                )
                db.add(call_share)
                shared_calls += 1

        await db.commit()

    return {
        "success": True,
        "entity_id": entity_id,
        "shared_with_id": data.shared_with_id,
        "access_level": data.access_level.value,
        "auto_shared": {
            "chats": shared_chats,
            "calls": shared_calls
        } if data.auto_share_related else None
    }


# === Chat Participants ===

@router.get("/{entity_id}/chat-participants")
async def get_entity_chat_participants(
    entity_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all participants from chats linked to this Entity.
    Returns a list of participants with their roles and identifiers.
    """
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    # Get entity
    result = await db.execute(
        select(Entity).where(Entity.id == entity_id, Entity.org_id == org.id)
    )
    entity = result.scalar_one_or_none()

    if not entity:
        raise HTTPException(404, "Entity not found")

    # Check if user has access to view this entity
    has_access = await check_entity_access(entity, current_user, org.id, db, required_level=None)
    if not has_access:
        raise HTTPException(404, "Entity not found")

    # Get all chats linked to this entity
    chats_result = await db.execute(
        select(Chat).where(Chat.entity_id == entity_id)
    )
    chats = chats_result.scalars().all()

    if not chats:
        return []

    # Collect all participants from all chats
    participants_map = {}  # Key: telegram_user_id, Value: participant info

    for chat in chats:
        # Get messages from this chat to identify participants
        messages_result = await db.execute(
            select(Message.telegram_user_id, Message.username, Message.first_name, Message.last_name)
            .where(Message.chat_id == chat.id)
            .distinct(Message.telegram_user_id)
        )
        messages = messages_result.all()

        for msg in messages:
            telegram_user_id, username, first_name, last_name = msg

            if telegram_user_id and telegram_user_id not in participants_map:
                # Build participant name
                name_parts = []
                if first_name:
                    name_parts.append(first_name)
                if last_name:
                    name_parts.append(last_name)
                name = " ".join(name_parts) if name_parts else f"User {telegram_user_id}"

                participants_map[telegram_user_id] = {
                    "telegram_user_id": telegram_user_id,
                    "telegram_username": username,
                    "name": name,
                    "first_name": first_name,
                    "last_name": last_name,
                    "chat_ids": []
                }

            # Add chat to participant's chat list
            if telegram_user_id and chat.id not in participants_map[telegram_user_id]["chat_ids"]:
                participants_map[telegram_user_id]["chat_ids"].append(chat.id)

    # Convert to list and sort by name
    participants = list(participants_map.values())
    participants.sort(key=lambda p: p["name"])

    return participants


# === Entity Chats & Calls Lists ===

@router.get("/{entity_id}/chats")
async def get_entity_chats(
    entity_id: int,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0, le=10000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all chats linked to an entity (candidate/contact).
    """
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    # Get entity
    result = await db.execute(
        select(Entity).where(Entity.id == entity_id, Entity.org_id == org.id)
    )
    entity = result.scalar_one_or_none()

    if not entity:
        raise HTTPException(404, "Entity not found")

    # Check if user has access to view this entity
    has_access = await check_entity_access(entity, current_user, org.id, db, required_level=None)
    if not has_access:
        raise HTTPException(404, "Entity not found")

    # Get chats linked to this entity
    chats_query = (
        select(Chat)
        .options(selectinload(Chat.owner))
        .where(
            Chat.entity_id == entity_id,
            Chat.org_id == org.id,
            Chat.deleted_at.is_(None)
        )
        .order_by(Chat.last_activity.desc())
        .offset(offset)
        .limit(limit)
    )

    result = await db.execute(chats_query)
    chats = result.scalars().all()

    if not chats:
        return []

    # Get chat IDs for batch queries
    chat_ids = [chat.id for chat in chats]

    # Batch query: Get message counts
    msg_counts_result = await db.execute(
        select(Message.chat_id, func.count(Message.id))
        .where(Message.chat_id.in_(chat_ids))
        .group_by(Message.chat_id)
    )
    msg_counts = {row[0]: row[1] for row in msg_counts_result.fetchall()}

    # Build response
    response = []
    for chat in chats:
        is_mine = chat.owner_id == current_user.id

        response.append({
            "id": chat.id,
            "telegram_chat_id": chat.telegram_chat_id,
            "title": chat.title,
            "custom_name": chat.custom_name,
            "chat_type": chat.chat_type.value if chat.chat_type else "hr",
            "owner_id": chat.owner_id,
            "owner_name": chat.owner.name if chat.owner else None,
            "is_active": chat.is_active,
            "messages_count": msg_counts.get(chat.id, 0),
            "last_activity": chat.last_activity.isoformat() if chat.last_activity else None,
            "created_at": chat.created_at.isoformat() if chat.created_at else None,
            "is_mine": is_mine,
        })

    return response


@router.get("/{entity_id}/calls")
async def get_entity_calls(
    entity_id: int,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0, le=10000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all call recordings linked to an entity (candidate/contact).
    """
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    # Get entity
    result = await db.execute(
        select(Entity).where(Entity.id == entity_id, Entity.org_id == org.id)
    )
    entity = result.scalar_one_or_none()

    if not entity:
        raise HTTPException(404, "Entity not found")

    # Check if user has access to view this entity
    has_access = await check_entity_access(entity, current_user, org.id, db, required_level=None)
    if not has_access:
        raise HTTPException(404, "Entity not found")

    # Get calls linked to this entity
    calls_query = (
        select(CallRecording)
        .where(
            CallRecording.entity_id == entity_id,
            CallRecording.org_id == org.id
        )
        .order_by(CallRecording.created_at.desc())
        .offset(offset)
        .limit(limit)
    )

    result = await db.execute(calls_query)
    calls = result.scalars().all()

    if not calls:
        return []

    # Get owner IDs for batch query
    owner_ids = list(set(call.owner_id for call in calls if call.owner_id))

    # Batch query: Get owner names
    owner_names_map = {}
    if owner_ids:
        owner_result = await db.execute(
            select(User.id, User.name).where(User.id.in_(owner_ids))
        )
        owner_names_map = {row[0]: row[1] for row in owner_result.fetchall()}

    # Build response
    response = []
    for call in calls:
        is_mine = call.owner_id == current_user.id

        response.append({
            "id": call.id,
            "title": call.title,
            "source_type": call.source_type.value if call.source_type else None,
            "status": call.status.value if call.status else None,
            "duration_seconds": call.duration_seconds,
            "owner_id": call.owner_id,
            "owner_name": owner_names_map.get(call.owner_id) if call.owner_id else None,
            "summary": call.summary[:200] + "..." if call.summary and len(call.summary) > 200 else call.summary,
            "created_at": call.created_at.isoformat() if call.created_at else None,
            "processed_at": call.processed_at.isoformat() if call.processed_at else None,
            "is_mine": is_mine,
        })

    return response


# === AI Profile Endpoints ===

class ProfileResponse(BaseModel):
    """AI Profile response"""
    entity_id: int
    profile: dict
    generated_at: Optional[str] = None


class SimilarWithProfileResponse(BaseModel):
    """Similar candidate with profile-based matching"""
    entity_id: int
    entity_name: str
    entity_position: Optional[str] = None
    entity_status: str
    score: int  # 0-100
    matches: List[str] = []
    differences: List[str] = []
    summary: str
    profile_summary: Optional[str] = None
    profile_level: Optional[str] = None
    profile_specialization: Optional[str] = None


@router.post("/{entity_id}/profile/generate", response_model=ProfileResponse)
@limiter.limit("10/minute", key_func=_get_rate_limit_key)
async def generate_entity_profile(
    entity_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Generate AI profile for entity based on all available context.
    """
    from ...services.entity_profile import entity_profile_service
    from ...models.database import EntityFile

    request.state._rate_limit_user = current_user
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    # Load entity with all related data
    entity_result = await db.execute(
        select(Entity)
        .options(selectinload(Entity.files))
        .where(Entity.id == entity_id, Entity.org_id == org.id)
    )
    entity = entity_result.scalar_one_or_none()
    if not entity:
        raise HTTPException(404, "Entity not found")

    # Load chats
    chats_result = await db.execute(
        select(Chat)
        .options(selectinload(Chat.messages))
        .where(Chat.entity_id == entity_id, Chat.org_id == org.id)
    )
    chats = list(chats_result.scalars().all())

    # Load calls
    calls_result = await db.execute(
        select(CallRecording)
        .where(CallRecording.entity_id == entity_id, CallRecording.org_id == org.id)
    )
    calls = list(calls_result.scalars().all())

    # Generate profile
    profile = await entity_profile_service.generate_profile(
        entity=entity,
        chats=chats,
        calls=calls,
        files=entity.files
    )

    # Store profile in entity
    if not entity.extra_data:
        entity.extra_data = {}
    entity.extra_data['ai_profile'] = profile
    await db.commit()

    return ProfileResponse(
        entity_id=entity_id,
        profile=profile,
        generated_at=profile.get('generated_at')
    )


@router.get("/{entity_id}/profile", response_model=ProfileResponse)
async def get_entity_profile(
    entity_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get existing AI profile for entity.
    """
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    entity_result = await db.execute(
        select(Entity)
        .where(Entity.id == entity_id, Entity.org_id == org.id)
    )
    entity = entity_result.scalar_one_or_none()
    if not entity:
        raise HTTPException(404, "Entity not found")

    profile = (entity.extra_data or {}).get('ai_profile')
    if not profile:
        raise HTTPException(404, "Profile not generated. Call POST /profile/generate first.")

    return ProfileResponse(
        entity_id=entity_id,
        profile=profile,
        generated_at=profile.get('generated_at')
    )


@router.get("/{entity_id}/similar-profiles", response_model=List[SimilarWithProfileResponse])
async def get_similar_by_profile(
    entity_id: int,
    min_score: int = Query(default=30, ge=0, le=100),
    limit: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Find similar candidates using AI profile matching.
    """
    from ...services.entity_profile import entity_profile_service

    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    # Load target entity
    entity_result = await db.execute(
        select(Entity)
        .options(selectinload(Entity.files))
        .where(Entity.id == entity_id, Entity.org_id == org.id)
    )
    entity = entity_result.scalar_one_or_none()
    if not entity:
        raise HTTPException(404, "Entity not found")

    # Check user has access to this entity
    has_access = await check_entity_access(entity, current_user, org.id, db, required_level=None)
    if not has_access:
        raise HTTPException(403, "No access to this entity")

    # Get or generate target profile
    target_profile = (entity.extra_data or {}).get('ai_profile')

    if not target_profile:
        # Generate profile on-the-fly
        chats_result = await db.execute(
            select(Chat)
            .options(selectinload(Chat.messages))
            .where(Chat.entity_id == entity_id, Chat.org_id == org.id)
        )
        chats = list(chats_result.scalars().all())

        calls_result = await db.execute(
            select(CallRecording)
            .where(CallRecording.entity_id == entity_id, CallRecording.org_id == org.id)
        )
        calls = list(calls_result.scalars().all())

        target_profile = await entity_profile_service.generate_profile(
            entity=entity,
            chats=chats,
            calls=calls,
            files=entity.files
        )

        # Store it
        if not entity.extra_data:
            entity.extra_data = {}
        entity.extra_data['ai_profile'] = target_profile
        await db.commit()

    # Find all other candidates with profiles (filtered by user's access rights)
    # SECURITY: Get accessible entity IDs to prevent data leak
    from ...services.permissions import PermissionService
    permissions = PermissionService(db)
    accessible_ids = await permissions.get_accessible_ids(current_user, "entity", org.id)

    candidates_result = await db.execute(
        select(Entity)
        .where(
            Entity.org_id == org.id,
            Entity.id != entity_id,
            Entity.type == EntityType.candidate
        )
    )
    all_candidates = list(candidates_result.scalars().all())

    # Filter to accessible candidates only (SECURITY: prevent data leak)
    accessible_candidates = [c for c in all_candidates if c.id in accessible_ids]

    # Filter to those with profiles and build list
    candidates_with_profiles = []
    for candidate in accessible_candidates:
        profile = (candidate.extra_data or {}).get('ai_profile')
        if profile:
            candidates_with_profiles.append((candidate, profile))

    # Calculate similarities
    similar = entity_profile_service.find_similar(
        target_profile=target_profile,
        candidates=candidates_with_profiles,
        min_score=min_score,
        limit=limit
    )

    return [SimilarWithProfileResponse(**s) for s in similar]
