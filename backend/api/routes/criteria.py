from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_

from ..database import get_db
from ..models.database import User, UserRole, Chat, CriteriaPreset, ChatCriteria, Entity, EntityCriteria
from ..models.schemas import (
    CriteriaPresetCreate, CriteriaPresetResponse,
    ChatCriteriaUpdate, ChatCriteriaResponse,
    EntityCriteriaUpdate, EntityCriteriaResponse,
    ChatTypeDefaultCriteriaUpdate, EntityTypeDefaultCriteriaUpdate
)
from ..services.auth import get_current_user
from ..services.permissions import PermissionService
from ..services.chat_types import (
    get_default_criteria as get_hardcoded_defaults,
    get_universal_presets,
    get_entity_default_criteria as get_hardcoded_entity_defaults
)

router = APIRouter()


# ============ PRESETS ============

@router.get("/presets", response_model=List[CriteriaPresetResponse])
async def get_presets(
    chat_type: Optional[str] = Query(None, description="Filter by chat type"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    user = await db.merge(user)
    # Global presets + user's own presets
    conditions = [
        or_(
            CriteriaPreset.is_global == True,
            CriteriaPreset.created_by == user.id
        )
    ]

    # Add chat_type filter if provided
    if chat_type:
        conditions.append(
            or_(
                CriteriaPreset.chat_type == chat_type,
                CriteriaPreset.chat_type.is_(None)  # Also include non-type-specific presets
            )
        )

    query = select(CriteriaPreset).where(
        and_(*conditions)
    ).order_by(CriteriaPreset.category, CriteriaPreset.name)

    result = await db.execute(query)
    presets = result.scalars().all()

    return [
        CriteriaPresetResponse(
            id=p.id,
            name=p.name,
            description=p.description,
            criteria=p.criteria,
            category=p.category,
            is_global=p.is_global,
            chat_type=p.chat_type,
            is_default=p.is_default,
            created_by=p.created_by,
            created_at=p.created_at,
        ) for p in presets
    ]


@router.post("/presets", response_model=CriteriaPresetResponse, status_code=201)
async def create_preset(
    data: CriteriaPresetCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    user = await db.merge(user)
    # Only superadmin can create global presets or set defaults
    is_global = data.is_global and user.role == UserRole.superadmin
    is_default = data.is_default and user.role == UserRole.superadmin

    # If setting as default, clear any existing defaults for this chat type
    if is_default and data.chat_type:
        await db.execute(
            select(CriteriaPreset).where(
                and_(
                    CriteriaPreset.chat_type == data.chat_type,
                    CriteriaPreset.is_default == True
                )
            )
        )
        # Update any existing defaults to non-default
        from sqlalchemy import update
        await db.execute(
            update(CriteriaPreset)
            .where(
                and_(
                    CriteriaPreset.chat_type == data.chat_type,
                    CriteriaPreset.is_default == True
                )
            )
            .values(is_default=False)
        )

    preset = CriteriaPreset(
        name=data.name,
        description=data.description,
        criteria=[c.model_dump() for c in data.criteria],
        category=data.category,
        is_global=is_global,
        chat_type=data.chat_type,
        is_default=is_default,
        created_by=user.id,
    )
    db.add(preset)
    await db.commit()
    await db.refresh(preset)

    return CriteriaPresetResponse(
        id=preset.id,
        name=preset.name,
        description=preset.description,
        criteria=preset.criteria,
        category=preset.category,
        is_global=preset.is_global,
        chat_type=preset.chat_type,
        is_default=preset.is_default,
        created_by=preset.created_by,
        created_at=preset.created_at,
    )


@router.put("/presets/{preset_id}", response_model=CriteriaPresetResponse)
async def update_preset(
    preset_id: int,
    data: CriteriaPresetCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    user = await db.merge(user)
    result = await db.execute(select(CriteriaPreset).where(CriteriaPreset.id == preset_id))
    preset = result.scalar_one_or_none()

    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")

    # Only owner or superadmin can update
    if preset.created_by != user.id and user.role != UserRole.superadmin:
        raise HTTPException(status_code=403, detail="Access denied")

    preset.name = data.name
    preset.description = data.description
    preset.criteria = [c.model_dump() for c in data.criteria]
    preset.category = data.category

    # Only superadmin can toggle global flag
    if user.role == UserRole.superadmin:
        preset.is_global = data.is_global

    await db.commit()
    await db.refresh(preset)

    return CriteriaPresetResponse(
        id=preset.id,
        name=preset.name,
        description=preset.description,
        criteria=preset.criteria,
        category=preset.category,
        is_global=preset.is_global,
        chat_type=preset.chat_type,
        is_default=preset.is_default,
        created_by=preset.created_by,
        created_at=preset.created_at,
    )


@router.delete("/presets/{preset_id}", status_code=204)
async def delete_preset(
    preset_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    user = await db.merge(user)
    result = await db.execute(select(CriteriaPreset).where(CriteriaPreset.id == preset_id))
    preset = result.scalar_one_or_none()

    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")

    # Only owner or superadmin can delete
    if preset.created_by != user.id and user.role != UserRole.superadmin:
        raise HTTPException(status_code=403, detail="Access denied")

    await db.delete(preset)
    await db.commit()


@router.get("/presets/universal")
async def get_universal_preset_templates(
    user: User = Depends(get_current_user),
):
    """Get universal preset templates that work for all chat types."""
    presets = get_universal_presets()
    return [
        {
            "id": f"universal_{i}",
            "name": p["name"],
            "description": p["description"],
            "criteria": p["criteria"],
            "is_universal": True,
        }
        for i, p in enumerate(presets)
    ]


@router.post("/presets/seed-universal", status_code=201)
async def seed_universal_presets(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Seed universal presets to database as global presets. Superadmin only."""
    user = await db.merge(user)

    if user.role != UserRole.superadmin:
        raise HTTPException(status_code=403, detail="Only superadmins can seed presets")

    presets = get_universal_presets()
    created = []

    for preset_data in presets:
        # Check if preset with this name already exists
        result = await db.execute(
            select(CriteriaPreset).where(
                and_(
                    CriteriaPreset.name == preset_data["name"],
                    CriteriaPreset.is_global == True
                )
            )
        )
        existing = result.scalar_one_or_none()

        if not existing:
            preset = CriteriaPreset(
                name=preset_data["name"],
                description=preset_data["description"],
                criteria=preset_data["criteria"],
                category="basic",
                is_global=True,
                chat_type=None,  # Universal - works for all types
                is_default=False,
                created_by=user.id,
            )
            db.add(preset)
            created.append(preset_data["name"])

    await db.commit()

    return {
        "message": f"Created {len(created)} universal presets",
        "created": created,
    }


# ============ DEFAULT CRITERIA BY CHAT TYPE ============

@router.get("/defaults/{chat_type}")
async def get_default_criteria_for_type(
    chat_type: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get default criteria for a chat type. First checks DB for custom defaults, then falls back to hardcoded."""
    # First check for a custom default preset in the database
    result = await db.execute(
        select(CriteriaPreset).where(
            and_(
                CriteriaPreset.chat_type == chat_type,
                CriteriaPreset.is_default == True
            )
        )
    )
    custom_default = result.scalar_one_or_none()

    if custom_default:
        return {
            "chat_type": chat_type,
            "criteria": custom_default.criteria,
            "is_custom": True,
            "preset_id": custom_default.id,
        }

    # Fall back to hardcoded defaults
    hardcoded = get_hardcoded_defaults(chat_type)
    return {
        "chat_type": chat_type,
        "criteria": hardcoded,
        "is_custom": False,
        "preset_id": None,
    }


@router.put("/defaults/{chat_type}")
async def set_default_criteria_for_type(
    chat_type: str,
    data: ChatTypeDefaultCriteriaUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Set custom default criteria for a chat type. Superadmin only."""
    user = await db.merge(user)

    if user.role != UserRole.superadmin:
        raise HTTPException(status_code=403, detail="Only superadmins can set default criteria")

    from sqlalchemy import update

    # First, clear any existing defaults for this chat type
    await db.execute(
        update(CriteriaPreset)
        .where(
            and_(
                CriteriaPreset.chat_type == chat_type,
                CriteriaPreset.is_default == True
            )
        )
        .values(is_default=False)
    )

    # Check if we already have a preset for this type (even if not default)
    result = await db.execute(
        select(CriteriaPreset).where(
            and_(
                CriteriaPreset.chat_type == chat_type,
                CriteriaPreset.is_global == True,
                CriteriaPreset.name == f"Default criteria for {chat_type}"
            )
        )
    )
    existing = result.scalar_one_or_none()

    criteria_data = [c.model_dump() for c in data.criteria]

    if existing:
        # Update existing preset
        existing.criteria = criteria_data
        existing.is_default = True
        preset = existing
    else:
        # Create new preset
        preset = CriteriaPreset(
            name=f"Default criteria for {chat_type}",
            description=f"Custom default criteria for {chat_type} chats",
            criteria=criteria_data,
            category="basic",
            is_global=True,
            chat_type=chat_type,
            is_default=True,
            created_by=user.id,
        )
        db.add(preset)

    await db.commit()
    await db.refresh(preset)

    return {
        "chat_type": chat_type,
        "criteria": preset.criteria,
        "is_custom": True,
        "preset_id": preset.id,
    }


@router.delete("/defaults/{chat_type}", status_code=204)
async def reset_default_criteria_for_type(
    chat_type: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Reset default criteria for a chat type back to hardcoded defaults. Superadmin only."""
    user = await db.merge(user)

    if user.role != UserRole.superadmin:
        raise HTTPException(status_code=403, detail="Only superadmins can reset default criteria")

    from sqlalchemy import update

    # Clear any custom defaults for this chat type
    await db.execute(
        update(CriteriaPreset)
        .where(
            and_(
                CriteriaPreset.chat_type == chat_type,
                CriteriaPreset.is_default == True
            )
        )
        .values(is_default=False)
    )

    await db.commit()


# ============ CHAT CRITERIA ============

@router.get("/chats/{chat_id}", response_model=ChatCriteriaResponse)
async def get_chat_criteria(
    chat_id: int,
    use_defaults: bool = Query(False, description="Return default criteria if none set"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    user = await db.merge(user)
    # Check access using PermissionService (consistent with messages routes)
    result = await db.execute(select(Chat).where(Chat.id == chat_id))
    chat = result.scalar_one_or_none()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    permission_service = PermissionService(db)
    if not await permission_service.can_access_resource(user, chat):
        raise HTTPException(status_code=403, detail="Access denied")

    result = await db.execute(select(ChatCriteria).where(ChatCriteria.chat_id == chat_id))
    criteria = result.scalar_one_or_none()

    if not criteria:
        # If use_defaults is True, try to get default criteria for this chat type
        if use_defaults and chat.chat_type:
            # First check for custom default in DB
            default_result = await db.execute(
                select(CriteriaPreset).where(
                    and_(
                        CriteriaPreset.chat_type == chat.chat_type.value if hasattr(chat.chat_type, 'value') else chat.chat_type,
                        CriteriaPreset.is_default == True
                    )
                )
            )
            custom_default = default_result.scalar_one_or_none()

            if custom_default:
                return ChatCriteriaResponse(
                    id=0,
                    chat_id=chat_id,
                    criteria=custom_default.criteria,
                    updated_at=chat.created_at,
                )

            # Fall back to hardcoded defaults
            chat_type_str = chat.chat_type.value if hasattr(chat.chat_type, 'value') else str(chat.chat_type)
            hardcoded = get_hardcoded_defaults(chat_type_str)
            if hardcoded:
                return ChatCriteriaResponse(
                    id=0,
                    chat_id=chat_id,
                    criteria=hardcoded,
                    updated_at=chat.created_at,
                )

        # Return empty criteria
        return ChatCriteriaResponse(
            id=0,
            chat_id=chat_id,
            criteria=[],
            updated_at=chat.created_at,
        )

    return ChatCriteriaResponse(
        id=criteria.id,
        chat_id=criteria.chat_id,
        criteria=criteria.criteria,
        updated_at=criteria.updated_at,
    )


@router.put("/chats/{chat_id}", response_model=ChatCriteriaResponse)
async def update_chat_criteria(
    chat_id: int,
    data: ChatCriteriaUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    user = await db.merge(user)
    # Check access using PermissionService (consistent with messages routes)
    result = await db.execute(select(Chat).where(Chat.id == chat_id))
    chat = result.scalar_one_or_none()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    permission_service = PermissionService(db)
    if not await permission_service.can_access_resource(user, chat, "read"):
        raise HTTPException(status_code=403, detail="Access denied")

    result = await db.execute(select(ChatCriteria).where(ChatCriteria.chat_id == chat_id))
    criteria = result.scalar_one_or_none()

    criteria_data = [c.model_dump() for c in data.criteria]

    if criteria:
        criteria.criteria = criteria_data
    else:
        criteria = ChatCriteria(chat_id=chat_id, criteria=criteria_data)
        db.add(criteria)

    await db.commit()
    await db.refresh(criteria)

    return ChatCriteriaResponse(
        id=criteria.id,
        chat_id=criteria.chat_id,
        criteria=criteria.criteria,
        updated_at=criteria.updated_at,
    )


# ============ DEFAULT CRITERIA BY ENTITY TYPE ============

@router.get("/defaults/entity/{entity_type}")
async def get_default_criteria_for_entity_type(
    entity_type: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get default criteria for an entity type. First checks DB for custom defaults, then falls back to hardcoded."""
    # First check for a custom default preset in the database
    result = await db.execute(
        select(CriteriaPreset).where(
            and_(
                CriteriaPreset.entity_type == entity_type,
                CriteriaPreset.is_default == True
            )
        )
    )
    custom_default = result.scalar_one_or_none()

    if custom_default:
        return {
            "entity_type": entity_type,
            "criteria": custom_default.criteria,
            "is_custom": True,
            "preset_id": custom_default.id,
        }

    # Fall back to hardcoded defaults
    hardcoded = get_hardcoded_entity_defaults(entity_type)
    return {
        "entity_type": entity_type,
        "criteria": hardcoded,
        "is_custom": False,
        "preset_id": None,
    }


@router.put("/defaults/entity/{entity_type}")
async def set_default_criteria_for_entity_type(
    entity_type: str,
    data: EntityTypeDefaultCriteriaUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Set custom default criteria for an entity type. Superadmin only."""
    user = await db.merge(user)

    if user.role != UserRole.superadmin:
        raise HTTPException(status_code=403, detail="Only superadmins can set default criteria")

    from sqlalchemy import update

    # First, clear any existing defaults for this entity type
    await db.execute(
        update(CriteriaPreset)
        .where(
            and_(
                CriteriaPreset.entity_type == entity_type,
                CriteriaPreset.is_default == True
            )
        )
        .values(is_default=False)
    )

    # Check if we already have a preset for this type (even if not default)
    result = await db.execute(
        select(CriteriaPreset).where(
            and_(
                CriteriaPreset.entity_type == entity_type,
                CriteriaPreset.is_global == True,
                CriteriaPreset.name == f"Default criteria for entity type {entity_type}"
            )
        )
    )
    existing = result.scalar_one_or_none()

    criteria_data = [c.model_dump() for c in data.criteria]

    if existing:
        # Update existing preset
        existing.criteria = criteria_data
        existing.is_default = True
        preset = existing
    else:
        # Create new preset
        preset = CriteriaPreset(
            name=f"Default criteria for entity type {entity_type}",
            description=f"Custom default criteria for {entity_type} entities",
            criteria=criteria_data,
            category="basic",
            is_global=True,
            entity_type=entity_type,
            is_default=True,
            created_by=user.id,
        )
        db.add(preset)

    await db.commit()
    await db.refresh(preset)

    return {
        "entity_type": entity_type,
        "criteria": preset.criteria,
        "is_custom": True,
        "preset_id": preset.id,
    }


@router.delete("/defaults/entity/{entity_type}", status_code=204)
async def reset_default_criteria_for_entity_type(
    entity_type: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Reset default criteria for an entity type back to hardcoded defaults. Superadmin only."""
    user = await db.merge(user)

    if user.role != UserRole.superadmin:
        raise HTTPException(status_code=403, detail="Only superadmins can reset default criteria")

    from sqlalchemy import update

    # Clear any custom defaults for this entity type
    await db.execute(
        update(CriteriaPreset)
        .where(
            and_(
                CriteriaPreset.entity_type == entity_type,
                CriteriaPreset.is_default == True
            )
        )
        .values(is_default=False)
    )

    await db.commit()


# ============ ENTITY CRITERIA ============

@router.get("/entities/{entity_id}", response_model=EntityCriteriaResponse)
async def get_entity_criteria(
    entity_id: int,
    use_defaults: bool = Query(False, description="Return default criteria if none set"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    user = await db.merge(user)
    # Check access using PermissionService (consistent with other endpoints)
    result = await db.execute(select(Entity).where(Entity.id == entity_id))
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    permission_service = PermissionService(db)
    if not await permission_service.can_access_resource(user, entity, "read"):
        raise HTTPException(status_code=403, detail="Access denied")

    result = await db.execute(select(EntityCriteria).where(EntityCriteria.entity_id == entity_id))
    criteria = result.scalar_one_or_none()

    if not criteria:
        # If use_defaults is True, try to get default criteria for this entity type
        if use_defaults and entity.type:
            # First check for custom default in DB
            entity_type_str = entity.type.value if hasattr(entity.type, 'value') else str(entity.type)
            default_result = await db.execute(
                select(CriteriaPreset).where(
                    and_(
                        CriteriaPreset.entity_type == entity_type_str,
                        CriteriaPreset.is_default == True
                    )
                )
            )
            custom_default = default_result.scalar_one_or_none()

            if custom_default:
                return EntityCriteriaResponse(
                    id=0,
                    entity_id=entity_id,
                    criteria=custom_default.criteria,
                    updated_at=entity.created_at,
                )

            # Fall back to hardcoded defaults
            hardcoded = get_hardcoded_entity_defaults(entity_type_str)
            if hardcoded:
                return EntityCriteriaResponse(
                    id=0,
                    entity_id=entity_id,
                    criteria=hardcoded,
                    updated_at=entity.created_at,
                )

        # Return empty criteria
        return EntityCriteriaResponse(
            id=0,
            entity_id=entity_id,
            criteria=[],
            updated_at=entity.created_at,
        )

    return EntityCriteriaResponse(
        id=criteria.id,
        entity_id=criteria.entity_id,
        criteria=criteria.criteria,
        updated_at=criteria.updated_at,
    )


@router.put("/entities/{entity_id}", response_model=EntityCriteriaResponse)
async def update_entity_criteria(
    entity_id: int,
    data: EntityCriteriaUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    user = await db.merge(user)
    # Check access using PermissionService (consistent with other endpoints)
    result = await db.execute(select(Entity).where(Entity.id == entity_id))
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    permission_service = PermissionService(db)
    if not await permission_service.can_access_resource(user, entity, "read"):
        raise HTTPException(status_code=403, detail="Access denied")

    result = await db.execute(select(EntityCriteria).where(EntityCriteria.entity_id == entity_id))
    criteria = result.scalar_one_or_none()

    criteria_data = [c.model_dump() for c in data.criteria]

    if criteria:
        criteria.criteria = criteria_data
    else:
        criteria = EntityCriteria(entity_id=entity_id, criteria=criteria_data)
        db.add(criteria)

    await db.commit()
    await db.refresh(criteria)

    return EntityCriteriaResponse(
        id=criteria.id,
        entity_id=criteria.entity_id,
        criteria=criteria.criteria,
        updated_at=criteria.updated_at,
    )
