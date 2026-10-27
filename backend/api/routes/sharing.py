"""API routes for sharing resources between users"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_, or_, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing import Optional, List
from datetime import datetime

from ..database import get_db
from ..models.database import (
    User, UserRole, SharedAccess, ResourceType, AccessLevel,
    Chat, Entity, CallRecording, OrgMember, Organization,
    Department, DepartmentMember, Vacancy
)
from ..models.sharing import (
    GenericShareRequest as ShareRequest,
    ShareResponse,
    UpdateShareRequest,
    UserSimple
)
from ..services.auth import get_current_user, get_user_org
from ..services.permissions import PermissionService
from .realtime import broadcast_share_created, broadcast_share_revoked

router = APIRouter()


# === Helper functions ===

async def resource_exists(resource_type: ResourceType, resource_id: int, db: AsyncSession) -> bool:
    """Check if a resource exists"""
    if resource_type == ResourceType.chat:
        result = await db.execute(select(Chat).where(Chat.id == resource_id))
        return result.scalar_one_or_none() is not None
    elif resource_type == ResourceType.entity:
        result = await db.execute(select(Entity).where(Entity.id == resource_id))
        return result.scalar_one_or_none() is not None
    elif resource_type == ResourceType.call:
        result = await db.execute(select(CallRecording).where(CallRecording.id == resource_id))
        return result.scalar_one_or_none() is not None
    elif resource_type == ResourceType.vacancy:
        result = await db.execute(select(Vacancy).where(Vacancy.id == resource_id))
        return result.scalar_one_or_none() is not None
    return False


async def get_resource_name(resource_type: ResourceType, resource_id: int, db: AsyncSession) -> Optional[str]:
    """Get human-readable name for a resource"""
    if resource_type == ResourceType.chat:
        result = await db.execute(select(Chat).where(Chat.id == resource_id))
        resource = result.scalar_one_or_none()
        return resource.custom_name or resource.title if resource else None
    elif resource_type == ResourceType.entity:
        result = await db.execute(select(Entity).where(Entity.id == resource_id))
        resource = result.scalar_one_or_none()
        return resource.name if resource else None
    elif resource_type == ResourceType.call:
        result = await db.execute(select(CallRecording).where(CallRecording.id == resource_id))
        resource = result.scalar_one_or_none()
        return resource.title or f"Звонок #{resource_id}" if resource else None
    elif resource_type == ResourceType.vacancy:
        result = await db.execute(select(Vacancy).where(Vacancy.id == resource_id))
        resource = result.scalar_one_or_none()
        return resource.title if resource else None
    return None


async def batch_get_resource_names(shares: List[SharedAccess], db: AsyncSession) -> dict:
    """Batch load resource names for multiple shares"""
    resource_names = {}

    # Group shares by resource type
    chat_ids = []
    entity_ids = []
    call_ids = []
    vacancy_ids = []

    for share in shares:
        if share.resource_type == ResourceType.chat:
            chat_ids.append(share.resource_id)
        elif share.resource_type == ResourceType.entity:
            entity_ids.append(share.resource_id)
        elif share.resource_type == ResourceType.call:
            call_ids.append(share.resource_id)
        elif share.resource_type == ResourceType.vacancy:
            vacancy_ids.append(share.resource_id)

    # Batch load chats
    if chat_ids:
        result = await db.execute(select(Chat).where(Chat.id.in_(chat_ids)))
        for chat in result.scalars().all():
            key = (ResourceType.chat, chat.id)
            resource_names[key] = chat.custom_name or chat.title

    # Batch load entities
    if entity_ids:
        result = await db.execute(select(Entity).where(Entity.id.in_(entity_ids)))
        for entity in result.scalars().all():
            key = (ResourceType.entity, entity.id)
            resource_names[key] = entity.name

    # Batch load calls
    if call_ids:
        result = await db.execute(select(CallRecording).where(CallRecording.id.in_(call_ids)))
        for call in result.scalars().all():
            key = (ResourceType.call, call.id)
            resource_names[key] = call.title or f"Звонок #{call.id}"

    # Batch load vacancies
    if vacancy_ids:
        result = await db.execute(select(Vacancy).where(Vacancy.id.in_(vacancy_ids)))
        for vacancy in result.scalars().all():
            key = (ResourceType.vacancy, vacancy.id)
            resource_names[key] = vacancy.title

    return resource_names


# === Routes ===

@router.post("", response_model=ShareResponse)
async def share_resource(
    data: ShareRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Share a resource with another user"""
    current_user = await db.merge(current_user)

    # ШАРИНГ ВОРОНОК ОТКЛЮЧЁН (2026-09-07, решение юзера): просмотр воронок открыт
    # всему HR-сегменту (см. vacancies/common.py::has_hr_segment_access), так что
    # выдавать доступ поштучно больше незачем. Специализированные роуты
    # /vacancies/{id}/share* удалены вместе с ветками SharedAccess в предикатах
    # доступа к вакансии — этот общий эндпоинт был последним способом завести
    # такую строку, поэтому режем resource_type=vacancy явно. Остальные типы
    # (чат, кандидат, звонок, проект) не трогаем: ими шарятся из ShareModal.
    if data.resource_type == ResourceType.vacancy:
        raise HTTPException(
            status_code=400,
            detail="Шаринг воронок отключён: воронки видны всем, у кого есть HR-раздел",
        )

    # Check if resource exists first (before permission check)
    if not await resource_exists(data.resource_type, data.resource_id, db):
        raise HTTPException(status_code=404, detail="Resource not found")

    # Check if user can share this resource
    permissions = PermissionService(db)
    resource = await permissions._load_resource(data.resource_type.value, data.resource_id)
    if not resource or not await permissions.can_access_resource(current_user, resource, "share"):
        raise HTTPException(status_code=403, detail="You don't have permission to share this resource")

    # Check if target user exists
    result = await db.execute(select(User).where(User.id == data.shared_with_id))
    target_user = result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    # Get current user's organization
    current_user_org = await get_user_org(current_user, db)
    if not current_user_org and current_user.role != UserRole.superadmin:
        raise HTTPException(status_code=403, detail="Вы не состоите в организации")

    # CRITICAL SECURITY CHECK: Verify target user is in the same organization
    # This prevents cross-organization sharing attacks
    if current_user.role != UserRole.superadmin:
        target_user_org = await get_user_org(target_user, db)
        if not target_user_org or (current_user_org and target_user_org.id != current_user_org.id):
            raise HTTPException(
                status_code=403,
                detail="Невозможно предоставить доступ пользователю из другой организации"
            )

    # Verify sharing permissions (organization and department rules)
    # This checks:
    # - SUPERADMIN can share with anyone
    # - OWNER can share with anyone in their organization
    # - ADMIN can share with their department + other admins + owner
    # - MEMBER can only share within their department
    if not await permissions.can_share_to(current_user, target_user, current_user_org.id if current_user_org else 0):
        raise HTTPException(
            status_code=403,
            detail="Невозможно предоставить доступ этому пользователю (пользователь не находится в вашей организации или отделе)"
        )

    # Check if already shared
    result = await db.execute(
        select(SharedAccess).where(
            SharedAccess.resource_type == data.resource_type,
            SharedAccess.resource_id == data.resource_id,
            SharedAccess.shared_with_id == data.shared_with_id
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        # Update existing share
        existing.access_level = data.access_level
        existing.note = data.note
        existing.expires_at = data.expires_at
        await db.commit()
        await db.refresh(existing)
        share = existing
    else:
        # Create new share
        share = SharedAccess(
            resource_type=data.resource_type,
            resource_id=data.resource_id,
            entity_id=data.resource_id if data.resource_type == ResourceType.entity else None,
            chat_id=data.resource_id if data.resource_type == ResourceType.chat else None,
            call_id=data.resource_id if data.resource_type == ResourceType.call else None,
            vacancy_id=data.resource_id if data.resource_type == ResourceType.vacancy else None,
            shared_by_id=current_user.id,
            shared_with_id=data.shared_with_id,
            access_level=data.access_level,
            note=data.note,
            expires_at=data.expires_at
        )
        db.add(share)
        await db.commit()
        await db.refresh(share)

    resource_name = await get_resource_name(data.resource_type, data.resource_id, db)

    # Auto-share related chats and calls when sharing an entity
    shared_related = {"chats": 0, "calls": 0}
    if data.resource_type == ResourceType.entity and data.auto_share_related:
        # Get the entity's org_id for filtering
        entity_result = await db.execute(
            select(Entity).where(Entity.id == data.resource_id)
        )
        entity = entity_result.scalar_one_or_none()

        if entity:
            # Find all chats linked to this entity
            chats_result = await db.execute(
                select(Chat).where(Chat.entity_id == data.resource_id, Chat.org_id == entity.org_id)
            )
            linked_chats = chats_result.scalars().all()

            if linked_chats:
                # Batch query: Get all existing chat shares for this user (avoid N+1)
                chat_ids = [chat.id for chat in linked_chats]
                existing_chat_shares_result = await db.execute(
                    select(SharedAccess.resource_id).where(
                        SharedAccess.resource_type == ResourceType.chat,
                        SharedAccess.resource_id.in_(chat_ids),
                        SharedAccess.shared_with_id == data.shared_with_id
                    )
                )
                existing_chat_share_ids = {r for r in existing_chat_shares_result.scalars().all()}

                for chat in linked_chats:
                    if chat.id not in existing_chat_share_ids:
                        chat_share = SharedAccess(
                            resource_type=ResourceType.chat,
                            resource_id=chat.id,
                            chat_id=chat.id,
                            shared_by_id=current_user.id,
                            shared_with_id=data.shared_with_id,
                            access_level=data.access_level,
                            note=f"Автоматически расшарено вместе с контактом: {entity.name}",
                            expires_at=data.expires_at
                        )
                        db.add(chat_share)
                        shared_related["chats"] += 1

            # Find all calls linked to this entity
            calls_result = await db.execute(
                select(CallRecording).where(CallRecording.entity_id == data.resource_id, CallRecording.org_id == entity.org_id)
            )
            linked_calls = calls_result.scalars().all()

            if linked_calls:
                # Batch query: Get all existing call shares for this user (avoid N+1)
                call_ids = [call.id for call in linked_calls]
                existing_call_shares_result = await db.execute(
                    select(SharedAccess.resource_id).where(
                        SharedAccess.resource_type == ResourceType.call,
                        SharedAccess.resource_id.in_(call_ids),
                        SharedAccess.shared_with_id == data.shared_with_id
                    )
                )
                existing_call_share_ids = {r for r in existing_call_shares_result.scalars().all()}

                for call in linked_calls:
                    if call.id not in existing_call_share_ids:
                        call_share = SharedAccess(
                            resource_type=ResourceType.call,
                            resource_id=call.id,
                            call_id=call.id,
                            shared_by_id=current_user.id,
                            shared_with_id=data.shared_with_id,
                            access_level=data.access_level,
                            note=f"Автоматически расшарено вместе с контактом: {entity.name}",
                            expires_at=data.expires_at
                        )
                        db.add(call_share)
                        shared_related["calls"] += 1

            if shared_related["chats"] > 0 or shared_related["calls"] > 0:
                await db.commit()

    response_data = ShareResponse(
        id=share.id,
        resource_type=share.resource_type,
        resource_id=share.resource_id,
        resource_name=resource_name,
        shared_by_id=current_user.id,
        shared_by_name=current_user.name,
        shared_with_id=target_user.id,
        shared_with_name=target_user.name,
        access_level=share.access_level,
        note=share.note,
        expires_at=share.expires_at,
        created_at=share.created_at
    )

    # Broadcast share.created event to the user who received the share
    await broadcast_share_created(
        target_user.id,
        {
            "share_id": share.id,
            "resource_type": share.resource_type.value,
            "resource_id": share.resource_id,
            "resource_name": resource_name,
            "access_level": share.access_level.value,
            "shared_by": current_user.name,
            "created_at": share.created_at.isoformat() if share.created_at else None
        }
    )

    return response_data


@router.patch("/{share_id}", response_model=ShareResponse)
async def update_share(
    share_id: int,
    data: UpdateShareRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a share's access level and other properties"""
    current_user = await db.merge(current_user)

    result = await db.execute(select(SharedAccess).where(SharedAccess.id == share_id))
    share = result.scalar_one_or_none()

    if not share:
        raise HTTPException(status_code=404, detail="Share not found")

    # Only the person who shared or superadmin can update
    if share.shared_by_id != current_user.id and current_user.role != UserRole.superadmin:
        raise HTTPException(status_code=403, detail="You can only update shares you created")

    # Update the share
    share.access_level = data.access_level
    if data.note is not None:
        share.note = data.note
    if data.expires_at is not None:
        share.expires_at = data.expires_at

    await db.commit()
    await db.refresh(share)

    # Get user details for response
    by_result = await db.execute(select(User).where(User.id == share.shared_by_id))
    by_user = by_result.scalar_one_or_none()
    with_result = await db.execute(select(User).where(User.id == share.shared_with_id))
    with_user = with_result.scalar_one_or_none()

    resource_name = await get_resource_name(share.resource_type, share.resource_id, db)

    return ShareResponse(
        id=share.id,
        resource_type=share.resource_type,
        resource_id=share.resource_id,
        resource_name=resource_name,
        shared_by_id=share.shared_by_id,
        shared_by_name=by_user.name if by_user else "Unknown",
        shared_with_id=share.shared_with_id,
        shared_with_name=with_user.name if with_user else "Unknown",
        access_level=share.access_level,
        note=share.note,
        expires_at=share.expires_at,
        created_at=share.created_at
    )


@router.delete("/{share_id}")
async def revoke_share(
    share_id: int,
    cascade: bool = Query(True, description="Also revoke related chats/calls when revoking entity share"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Revoke a share. For entities, also revokes related chat/call shares by default."""
    current_user = await db.merge(current_user)

    result = await db.execute(select(SharedAccess).where(SharedAccess.id == share_id))
    share = result.scalar_one_or_none()

    if not share:
        raise HTTPException(status_code=404, detail="Share not found")

    # Only the person who shared or superadmin can revoke
    if share.shared_by_id != current_user.id and current_user.role != UserRole.superadmin:
        raise HTTPException(status_code=403, detail="You can only revoke shares you created")

    # Store share info before deletion
    shared_with_id = share.shared_with_id
    resource_type = share.resource_type
    resource_id = share.resource_id
    revoke_data = {
        "share_id": share.id,
        "resource_type": resource_type.value,
        "resource_id": resource_id
    }

    # CASCADE: If this is an entity share, also delete related chat/call shares
    related_deleted = {"chats": 0, "calls": 0}
    if resource_type == ResourceType.entity and cascade:
        # Get the entity to find its org_id
        entity_result = await db.execute(
            select(Entity).where(Entity.id == resource_id)
        )
        entity = entity_result.scalar_one_or_none()

        if entity:
            # Find all chats linked to this entity (only IDs needed)
            chats_result = await db.execute(
                select(Chat.id).where(Chat.entity_id == resource_id, Chat.org_id == entity.org_id)
            )
            linked_chat_ids = [r for r in chats_result.scalars().all()]

            # Batch delete shares for linked chats (avoid N+1)
            if linked_chat_ids:
                delete_result = await db.execute(
                    delete(SharedAccess).where(
                        SharedAccess.resource_type == ResourceType.chat,
                        SharedAccess.resource_id.in_(linked_chat_ids),
                        SharedAccess.shared_with_id == shared_with_id
                    )
                )
                related_deleted["chats"] = delete_result.rowcount

            # Find all calls linked to this entity (only IDs needed)
            calls_result = await db.execute(
                select(CallRecording.id).where(CallRecording.entity_id == resource_id, CallRecording.org_id == entity.org_id)
            )
            linked_call_ids = [r for r in calls_result.scalars().all()]

            # Batch delete shares for linked calls (avoid N+1)
            if linked_call_ids:
                delete_result = await db.execute(
                    delete(SharedAccess).where(
                        SharedAccess.resource_type == ResourceType.call,
                        SharedAccess.resource_id.in_(linked_call_ids),
                        SharedAccess.shared_with_id == shared_with_id
                    )
                )
                related_deleted["calls"] = delete_result.rowcount

    await db.delete(share)
    await db.commit()

    # Broadcast share.revoked event to the user who had access
    await broadcast_share_revoked(shared_with_id, revoke_data)

    return {
        "success": True,
        "related_revoked": related_deleted
    }


@router.get("/my-shares", response_model=List[ShareResponse])
async def get_my_shares(
    resource_type: Optional[ResourceType] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get resources I've shared with others"""
    current_user = await db.merge(current_user)

    query = select(SharedAccess).options(
        selectinload(SharedAccess.shared_by),
        selectinload(SharedAccess.shared_with)
    ).where(SharedAccess.shared_by_id == current_user.id)
    if resource_type:
        query = query.where(SharedAccess.resource_type == resource_type)
    query = query.order_by(SharedAccess.created_at.desc())

    result = await db.execute(query)
    shares = result.scalars().all()

    # Batch load resource names
    resource_names = await batch_get_resource_names(shares, db)

    # Build response using pre-fetched data
    response = []
    for share in shares:
        resource_name = resource_names.get((share.resource_type, share.resource_id))

        response.append(ShareResponse(
            id=share.id,
            resource_type=share.resource_type,
            resource_id=share.resource_id,
            resource_name=resource_name,
            shared_by_id=share.shared_by_id,
            shared_by_name=share.shared_by.name if share.shared_by else "Unknown",
            shared_with_id=share.shared_with_id,
            shared_with_name=share.shared_with.name if share.shared_with else "Unknown",
            access_level=share.access_level,
            note=share.note,
            expires_at=share.expires_at,
            created_at=share.created_at
        ))

    return response


@router.get("/shared-with-me", response_model=List[ShareResponse])
async def get_shared_with_me(
    resource_type: Optional[ResourceType] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get resources shared with me"""
    current_user = await db.merge(current_user)

    query = select(SharedAccess).options(
        selectinload(SharedAccess.shared_by),
        selectinload(SharedAccess.shared_with)
    ).where(
        SharedAccess.shared_with_id == current_user.id,
        or_(SharedAccess.expires_at.is_(None), SharedAccess.expires_at > datetime.utcnow())
    )
    if resource_type:
        query = query.where(SharedAccess.resource_type == resource_type)
    query = query.order_by(SharedAccess.created_at.desc())

    result = await db.execute(query)
    shares = result.scalars().all()

    # Batch load resource names
    resource_names = await batch_get_resource_names(shares, db)

    # Build response using pre-fetched data
    response = []
    for share in shares:
        resource_name = resource_names.get((share.resource_type, share.resource_id))

        response.append(ShareResponse(
            id=share.id,
            resource_type=share.resource_type,
            resource_id=share.resource_id,
            resource_name=resource_name,
            shared_by_id=share.shared_by_id,
            shared_by_name=share.shared_by.name if share.shared_by else "Unknown",
            shared_with_id=share.shared_with_id,
            shared_with_name=share.shared_with.name if share.shared_with else "Unknown",
            access_level=share.access_level,
            note=share.note,
            expires_at=share.expires_at,
            created_at=share.created_at
        ))

    return response


@router.get("/resource/{resource_type}/{resource_id}", response_model=List[ShareResponse])
async def get_resource_shares(
    resource_type: ResourceType,
    resource_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all shares for a specific resource"""
    current_user = await db.merge(current_user)

    # Check if user has access to this resource
    permissions = PermissionService(db)
    if not await permissions.can_access(current_user, resource_type.value, resource_id, "read"):
        raise HTTPException(status_code=403, detail="Access denied")

    query = select(SharedAccess).options(
        selectinload(SharedAccess.shared_by),
        selectinload(SharedAccess.shared_with)
    ).where(
        SharedAccess.resource_type == resource_type,
        SharedAccess.resource_id == resource_id
    ).order_by(SharedAccess.created_at.desc())

    result = await db.execute(query)
    shares = result.scalars().all()

    # Batch load resource names
    resource_names = await batch_get_resource_names(shares, db)

    # Build response using pre-fetched data
    response = []
    for share in shares:
        resource_name = resource_names.get((share.resource_type, share.resource_id))

        response.append(ShareResponse(
            id=share.id,
            resource_type=share.resource_type,
            resource_id=share.resource_id,
            resource_name=resource_name,
            shared_by_id=share.shared_by_id,
            shared_by_name=share.shared_by.name if share.shared_by else "Unknown",
            shared_with_id=share.shared_with_id,
            shared_with_name=share.shared_with.name if share.shared_with else "Unknown",
            access_level=share.access_level,
            note=share.note,
            expires_at=share.expires_at,
            created_at=share.created_at
        ))

    return response


import logging
logger = logging.getLogger("hr-analyzer.sharing")

@router.get("/users", response_model=List[UserSimple])
async def get_sharable_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get list of users that can be shared with (same organization)"""
    current_user = await db.merge(current_user)

    org = await get_user_org(current_user, db)
    logger.info(f"get_sharable_users: user={current_user.id}, role={current_user.role}, org={org.id if org else None}")

    # For superadmin without org membership, get the first organization
    if not org and current_user.role == UserRole.superadmin:
        org_result = await db.execute(
            select(Organization).order_by(Organization.id).limit(1)
        )
        org = org_result.scalar_one_or_none()

    if not org:
        return []

    # Get all users in the same organization with their roles and departments
    # Note: Shadow users are excluded from sharing list - they are completely hidden
    result = await db.execute(
        select(User, OrgMember)
        .join(OrgMember, OrgMember.user_id == User.id)
        .where(
            OrgMember.org_id == org.id,
            User.id != current_user.id,
            User.is_active == True,
            User.is_shadow == False  # Hide shadow users from sharing
        )
        .order_by(User.name)
    )
    rows = result.all()

    if not rows:
        logger.info(f"get_sharable_users: no rows found for org_id={org.id}")
        return []

    logger.info(f"get_sharable_users: found {len(rows)} users")
    # Batch load departments for all users
    user_ids = [user.id for user, _ in rows]
    dept_memberships_result = await db.execute(
        select(DepartmentMember, Department)
        .join(Department, Department.id == DepartmentMember.department_id)
        .where(DepartmentMember.user_id.in_(user_ids))
    )

    # Build a map of user_id -> (department, department_member) for first department only
    user_dept_map = {}
    for dept_member, dept in dept_memberships_result.all():
        if dept_member.user_id not in user_dept_map:
            user_dept_map[dept_member.user_id] = (dept, dept_member)

    # Build response with role information
    response = []
    for user, org_member in rows:
        dept_id = None
        dept_name = None
        dept_role = None

        # Get department info from pre-fetched map
        if user.id in user_dept_map:
            dept, dept_member = user_dept_map[user.id]
            dept_id = dept.id
            dept_name = dept.name
            dept_role = dept_member.role.value if dept_member.role else None

        response.append(UserSimple(
            id=user.id,
            name=user.name,
            email=user.email,
            org_role=org_member.role.value if org_member.role else None,
            department_id=dept_id,
            department_name=dept_name,
            department_role=dept_role
        ))

    return response


@router.delete("/cleanup/orphaned")
async def cleanup_orphaned_shares(
    user_id: Optional[int] = Query(None, description="Clean up for specific user only"),
    dry_run: bool = Query(True, description="If true, only count without deleting"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Clean up orphaned chat/call shares that don't have a parent entity share.

    This happens when an entity share was deleted but the cascade delete failed
    or was added before cascade delete was implemented.

    Only superadmin can run this endpoint.
    """
    if current_user.role != UserRole.superadmin:
        raise HTTPException(status_code=403, detail="Only superadmin can clean up orphaned shares")

    # Find all entity shares
    entity_shares_query = select(SharedAccess).where(
        SharedAccess.resource_type == ResourceType.entity
    )
    if user_id:
        entity_shares_query = entity_shares_query.where(SharedAccess.shared_with_id == user_id)

    entity_shares_result = await db.execute(entity_shares_query)
    entity_shares = entity_shares_result.scalars().all()

    # Build a set of (entity_id, shared_with_id) tuples that have valid shares
    valid_entity_user_pairs = set()
    for es in entity_shares:
        valid_entity_user_pairs.add((es.resource_id, es.shared_with_id))

    # Find orphaned chat shares
    chat_shares_query = select(SharedAccess).where(
        SharedAccess.resource_type == ResourceType.chat
    )
    if user_id:
        chat_shares_query = chat_shares_query.where(SharedAccess.shared_with_id == user_id)

    chat_shares_result = await db.execute(chat_shares_query)
    chat_shares = chat_shares_result.scalars().all()

    # Batch load all chats for chat shares (avoid N+1)
    chat_ids = [cs.resource_id for cs in chat_shares]
    chats_map = {}
    if chat_ids:
        chats_result = await db.execute(
            select(Chat.id, Chat.entity_id).where(Chat.id.in_(chat_ids))
        )
        for chat_id, entity_id in chats_result.all():
            chats_map[chat_id] = entity_id

    orphaned_chats = []
    for cs in chat_shares:
        entity_id = chats_map.get(cs.resource_id)
        if entity_id:
            # Check if there's a valid entity share for this user
            if (entity_id, cs.shared_with_id) not in valid_entity_user_pairs:
                orphaned_chats.append(cs)

    # Find orphaned call shares
    call_shares_query = select(SharedAccess).where(
        SharedAccess.resource_type == ResourceType.call
    )
    if user_id:
        call_shares_query = call_shares_query.where(SharedAccess.shared_with_id == user_id)

    call_shares_result = await db.execute(call_shares_query)
    call_shares = call_shares_result.scalars().all()

    # Batch load all calls for call shares (avoid N+1)
    call_ids = [cs.resource_id for cs in call_shares]
    calls_map = {}
    if call_ids:
        calls_result = await db.execute(
            select(CallRecording.id, CallRecording.entity_id).where(CallRecording.id.in_(call_ids))
        )
        for call_id, entity_id in calls_result.all():
            calls_map[call_id] = entity_id

    orphaned_calls = []
    for cs in call_shares:
        entity_id = calls_map.get(cs.resource_id)
        if entity_id:
            # Check if there's a valid entity share for this user
            if (entity_id, cs.shared_with_id) not in valid_entity_user_pairs:
                orphaned_calls.append(cs)

    # Delete if not dry run - use batch delete for efficiency
    deleted_count = {"chats": 0, "calls": 0}
    if not dry_run:
        if orphaned_chats:
            orphaned_chat_ids = [share.id for share in orphaned_chats]
            await db.execute(
                delete(SharedAccess).where(SharedAccess.id.in_(orphaned_chat_ids))
            )
            deleted_count["chats"] = len(orphaned_chat_ids)

        if orphaned_calls:
            orphaned_call_ids = [share.id for share in orphaned_calls]
            await db.execute(
                delete(SharedAccess).where(SharedAccess.id.in_(orphaned_call_ids))
            )
            deleted_count["calls"] = len(orphaned_call_ids)

        await db.commit()

    return {
        "dry_run": dry_run,
        "orphaned_chat_shares": len(orphaned_chats),
        "orphaned_call_shares": len(orphaned_calls),
        "deleted": deleted_count if not dry_run else None
    }
