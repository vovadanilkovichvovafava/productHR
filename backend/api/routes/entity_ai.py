"""
Entity AI Routes - API endpoints for Entity AI assistant.

Provides:
- GET /entities/{id}/ai/actions - Get available quick actions
- POST /entities/{id}/ai/message - Send message (streaming)
- GET /entities/{id}/ai/history - Get conversation history
- DELETE /entities/{id}/ai/history - Clear conversation history
"""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified
from pydantic import BaseModel
import json
import logging

from ..database import get_db
from ..models.database import (
    User, UserRole, Entity, Chat, Message, CallRecording,
    EntityAIConversation, EntityCriteria, AnalysisHistory, EntityFile,
    OrgRole, DepartmentMember, DeptRole
)
from ..services.entity_memory import entity_memory_service
from ..services.cache import format_messages_optimized
from ..services.auth import get_current_user, get_user_org, get_user_org_role
from ..services.entity_ai import entity_ai_service
from ..services.reports import generate_pdf_report, generate_docx_report
from ..services.permissions import PermissionService
from ..limiter import limiter, user_or_ip

logger = logging.getLogger("hr-analyzer.entity-ai-routes")

router = APIRouter()


def _get_rate_limit_key(request: Request) -> str:
    """Лимит на пользователя (номер из токена), без входа — на адрес; см. limiter.user_or_ip."""
    return user_or_ip(request)


class EntityAIMessageRequest(BaseModel):
    message: Optional[str] = None
    quick_action: Optional[str] = None


class EntityReportRequest(BaseModel):
    report_type: str = "full_analysis"
    format: str = "pdf"  # pdf, docx, markdown


async def get_entity_with_data(db: AsyncSession, entity_id: int):
    """Get entity with all related chats (with messages), calls, and files"""
    # Get entity
    result = await db.execute(
        select(Entity).where(Entity.id == entity_id)
    )
    entity = result.scalar_one_or_none()
    if not entity:
        return None, [], [], []

    # Get chats with messages, owner, and entity for participant identification
    result = await db.execute(
        select(Chat)
        .options(
            selectinload(Chat.messages),
            selectinload(Chat.owner),
            selectinload(Chat.entity)
        )
        .where(Chat.entity_id == entity_id, Chat.deleted_at.is_(None))
        .order_by(Chat.created_at)
    )
    chats = list(result.scalars().all())

    # Get calls
    result = await db.execute(
        select(CallRecording)
        .where(CallRecording.entity_id == entity_id)
        .order_by(CallRecording.created_at)
    )
    calls = list(result.scalars().all())

    # Get entity files (resumes, test assignments, portfolios, etc.)
    result = await db.execute(
        select(EntityFile)
        .where(EntityFile.entity_id == entity_id)
        .order_by(EntityFile.created_at)
    )
    files = list(result.scalars().all())

    return entity, chats, calls, files


@router.get("/entities/{entity_id}/ai/actions")
async def get_available_actions(
    entity_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Get available quick actions for entity AI"""
    user = await db.merge(user)

    # Check entity exists
    result = await db.execute(
        select(Entity).where(Entity.id == entity_id)
    )
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    permissions = PermissionService(db)
    if not await permissions.can_access_resource(user, entity, "read"):
        raise HTTPException(status_code=403, detail="Access denied")

    return {
        "actions": entity_ai_service.get_available_actions()
    }


@router.post("/entities/{entity_id}/ai/message")
@limiter.limit("30/minute", key_func=_get_rate_limit_key)
async def entity_ai_message(
    entity_id: int,
    body: EntityAIMessageRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """AI assistant message with streaming response"""
    request.state._rate_limit_user = user
    user = await db.merge(user)

    # Get entity with all data
    entity, chats, calls, files = await get_entity_with_data(db, entity_id)

    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    permissions = PermissionService(db)
    if not await permissions.can_access_resource(user, entity, "read"):
        raise HTTPException(status_code=403, detail="Access denied")

    # Validate request
    if not body.message and not body.quick_action:
        raise HTTPException(status_code=400, detail="message or quick_action required")

    # Get or create conversation
    result = await db.execute(
        select(EntityAIConversation).where(
            EntityAIConversation.entity_id == entity_id,
            EntityAIConversation.user_id == user.id
        )
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        conversation = EntityAIConversation(
            entity_id=entity_id,
            user_id=user.id,
            messages=[]
        )
        db.add(conversation)
        await db.flush()

    history = conversation.messages or []

    async def generate():
        full_response = ""
        try:
            if body.quick_action:
                # Quick action
                async for chunk in entity_ai_service.quick_action(
                    body.quick_action, entity, chats, calls, files
                ):
                    full_response += chunk
                    yield f"data: {json.dumps({'content': chunk})}\n\n"
            else:
                # Regular chat
                async for chunk in entity_ai_service.chat_stream(
                    body.message, entity, chats, calls, history, files
                ):
                    full_response += chunk
                    yield f"data: {json.dumps({'content': chunk})}\n\n"

        except Exception as e:
            logger.exception(f"Entity AI error: {e}")
            yield f"data: {json.dumps({'content': f'Ошибка: {str(e)}', 'error': True})}\n\n"
            yield "data: [DONE]\n\n"
            return

        # Save to conversation history
        try:
            # Re-fetch conversation to avoid stale data
            result = await db.execute(
                select(EntityAIConversation).where(
                    EntityAIConversation.entity_id == entity_id,
                    EntityAIConversation.user_id == user.id
                )
            )
            conv = result.scalar_one_or_none()
            if conv:
                new_messages = list(conv.messages or [])

                # Add user message
                user_content = f"[{body.quick_action}]" if body.quick_action else body.message
                new_messages.append({
                    "role": "user",
                    "content": user_content,
                    "timestamp": datetime.utcnow().isoformat()
                })

                # Add assistant response
                new_messages.append({
                    "role": "assistant",
                    "content": full_response,
                    "timestamp": datetime.utcnow().isoformat()
                })

                conv.messages = new_messages
                flag_modified(conv, "messages")
                await db.commit()
        except Exception as e:
            logger.error(f"Failed to save conversation: {e}")

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("/entities/{entity_id}/ai/history")
async def get_entity_ai_history(
    entity_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Get AI conversation history for entity"""
    user = await db.merge(user)

    # Check entity exists and access
    result = await db.execute(
        select(Entity).where(Entity.id == entity_id)
    )
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    permissions = PermissionService(db)
    if not await permissions.can_access_resource(user, entity, "read"):
        raise HTTPException(status_code=403, detail="Access denied")

    # Get conversation
    result = await db.execute(
        select(EntityAIConversation).where(
            EntityAIConversation.entity_id == entity_id,
            EntityAIConversation.user_id == user.id
        )
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        return {"messages": []}

    return {"messages": conversation.messages or []}


@router.delete("/entities/{entity_id}/ai/history")
async def clear_entity_ai_history(
    entity_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Clear AI conversation history for entity"""
    user = await db.merge(user)

    # Check entity exists and access
    result = await db.execute(
        select(Entity).where(Entity.id == entity_id)
    )
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    permissions = PermissionService(db)
    if not await permissions.can_access_resource(user, entity, "read"):
        raise HTTPException(status_code=403, detail="Access denied")

    # Delete conversation
    result = await db.execute(
        select(EntityAIConversation).where(
            EntityAIConversation.entity_id == entity_id,
            EntityAIConversation.user_id == user.id
        )
    )
    conversation = result.scalar_one_or_none()

    if conversation:
        await db.delete(conversation)
        await db.commit()

    return {"success": True}


@router.post("/entities/{entity_id}/ai/update-summary")
@limiter.limit("5/minute", key_func=_get_rate_limit_key)
async def update_entity_ai_summary(
    entity_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Manually trigger AI summary update for entity.

    This creates/updates the ai_summary field based on all chats and calls.
    Useful for rebuilding context after significant interactions.
    """
    request.state._rate_limit_user = user
    user = await db.merge(user)

    # Get entity with all data
    entity, chats, calls, files = await get_entity_with_data(db, entity_id)

    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    permissions = PermissionService(db)
    if not await permissions.can_access_resource(user, entity, "read"):
        raise HTTPException(status_code=403, detail="Access denied")

    # Build content for summarization
    content_parts = []

    # Add chat messages
    for chat in chats:
        if hasattr(chat, 'messages') and chat.messages:
            messages = sorted(chat.messages, key=lambda m: m.timestamp)[-50:]
            content_parts.append(f"Чат {chat.title}:\n{format_messages_optimized(messages, max_per_message=300)}")

    # Add call summaries
    for call in calls:
        if call.summary:
            content_parts.append(f"Звонок {call.title}: {call.summary}")

    # Add files with parsed content (like in chat_stream)
    for file in files:
        file_header = f"Файл ({file.file_type.value}): {file.file_name}"
        if file.description:
            file_header += f"\nОписание: {file.description}"

        # Parse file content using entity_ai_service
        file_content = await entity_ai_service._parse_entity_file(file)
        if file_content:
            # Limit file content to prevent token overflow
            max_file_chars = 5000
            if len(file_content) > max_file_chars:
                file_content = file_content[:max_file_chars] + "\n... (содержимое сокращено)"
            content_parts.append(f"{file_header}\nСодержимое:\n{file_content}")
        else:
            content_parts.append(f"{file_header}\n(не удалось извлечь содержимое файла)")

    content = "\n\n".join(content_parts)

    if not content:
        return {"success": False, "error": "No content to summarize"}

    # Update summary
    new_summary = await entity_memory_service.update_summary(entity, content, db)

    # Extract key events
    new_events = await entity_memory_service.extract_key_events(entity, content, db)

    return {
        "success": True,
        "summary": new_summary,
        "new_events_count": len(new_events),
        "total_events": len(entity.key_events or [])
    }


@router.get("/entities/{entity_id}/ai/memory")
async def get_entity_ai_memory(
    entity_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Get entity AI memory (summary + key events)."""
    user = await db.merge(user)

    result = await db.execute(
        select(Entity).where(Entity.id == entity_id)
    )
    entity = result.scalar_one_or_none()

    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    permissions = PermissionService(db)
    if not await permissions.can_access_resource(user, entity, "read"):
        raise HTTPException(status_code=403, detail="Access denied")

    return {
        "summary": entity.ai_summary,
        "summary_updated_at": entity.ai_summary_updated_at.isoformat() if entity.ai_summary_updated_at else None,
        "key_events": entity.key_events or []
    }


@router.post("/entities/ai/batch-update-summaries")
@limiter.limit("2/minute", key_func=_get_rate_limit_key)
async def batch_update_entity_summaries(
    request: Request,
    limit: int = 10,
    only_empty: bool = True,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Batch update AI summaries for multiple entities.

    Args:
        limit: Max entities to process (default 10, max 50)
        only_empty: Only process entities without summaries (default True)

    This is useful for:
    - Initial setup: generate summaries for existing entities
    - Periodic refresh: update old summaries
    """
    request.state._rate_limit_user = user
    user = await db.merge(user)

    # Check if user has admin-level access (org admin, dept lead, or superadmin)
    is_admin = False
    if user.role == UserRole.superadmin:
        is_admin = True
    else:
        # Check org role
        org = await get_user_org(user, db)
        if org:
            org_role = await get_user_org_role(user, org.id, db)
            if org_role in ("owner", "admin"):
                is_admin = True

        # Check department role
        if not is_admin:
            result = await db.execute(
                select(DepartmentMember).where(
                    DepartmentMember.user_id == user.id,
                    DepartmentMember.role.in_([DeptRole.lead, DeptRole.sub_admin])
                )
            )
            if result.scalar_one_or_none():
                is_admin = True

    if not is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    limit = min(limit, 50)  # Cap at 50

    # Get entities to update
    query = select(Entity).where(Entity.created_by == user.id)

    if only_empty:
        query = query.where(Entity.ai_summary.is_(None))

    query = query.limit(limit)

    result = await db.execute(query)
    entities = list(result.scalars().all())

    updated = []
    errors = []

    for entity in entities:
        try:
            # Get entity data
            entity_obj, chats, calls, files = await get_entity_with_data(db, entity.id)

            # Build content
            content_parts = []
            for chat in chats:
                if hasattr(chat, 'messages') and chat.messages:
                    messages = sorted(chat.messages, key=lambda m: m.timestamp)[-50:]
                    content_parts.append(f"Чат {chat.title}:\n{format_messages_optimized(messages, max_per_message=300)}")

            for call in calls:
                if call.summary:
                    content_parts.append(f"Звонок {call.title}: {call.summary}")

            for file in files:
                content_parts.append(f"Файл ({file.file_type.value}): {file.file_name}")

            content = "\n\n".join(content_parts)

            if content:
                await entity_memory_service.update_summary(entity_obj, content, db)
                await entity_memory_service.extract_key_events(entity_obj, content, db)
                updated.append({"id": entity.id, "name": entity.name})
            else:
                errors.append({"id": entity.id, "name": entity.name, "error": "No content"})

        except Exception as e:
            logger.error(f"Failed to update entity {entity.id}: {e}")
            errors.append({"id": entity.id, "name": entity.name, "error": str(e)})

    return {
        "updated_count": len(updated),
        "error_count": len(errors),
        "updated": updated,
        "errors": errors
    }


@router.post("/entities/{entity_id}/report")
async def generate_entity_report(
    entity_id: int,
    request: EntityReportRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Generate downloadable report for entity.

    Generates a comprehensive report analyzing all chats and calls
    associated with this entity.
    """
    user = await db.merge(user)

    # Get entity with all data
    entity, chats, calls, files = await get_entity_with_data(db, entity_id)

    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    permissions = PermissionService(db)
    if not await permissions.can_access_resource(user, entity, "read"):
        raise HTTPException(status_code=403, detail="Access denied")

    # Get criteria if exists
    result = await db.execute(
        select(EntityCriteria).where(EntityCriteria.entity_id == entity_id)
    )
    criteria_obj = result.scalar_one_or_none()
    criteria = criteria_obj.criteria if criteria_obj else []

    # Build content for analysis
    content_parts = []

    # Add entity info
    content_parts.append(f"# Контакт: {entity.name}")
    if entity.company:
        content_parts.append(f"Компания: {entity.company}")
    if entity.position:
        content_parts.append(f"Должность: {entity.position}")
    if entity.ai_summary:
        content_parts.append(f"\n## Общее резюме\n{entity.ai_summary}")

    # Add files info
    for file in files:
        content_parts.append(f"\n## Файл ({file.file_type.value}): {file.file_name}")
        if file.description:
            content_parts.append(f"Описание: {file.description}")

    # Add chat messages
    for chat in chats:
        if hasattr(chat, 'messages') and chat.messages:
            messages = sorted(chat.messages, key=lambda m: m.timestamp)[-100:]
            content_parts.append(f"\n## Чат: {chat.title}\n{format_messages_optimized(messages, max_per_message=500)}")

    # Add call summaries
    for call in calls:
        call_info = f"\n## Звонок: {call.title or 'Без названия'}"
        if call.summary:
            call_info += f"\n{call.summary}"
        content_parts.append(call_info)

    content = "\n\n".join(content_parts)

    if not content:
        raise HTTPException(status_code=400, detail="No data to generate report")

    # Generate report using AI (with files for content analysis)
    report_content = await entity_ai_service.generate_entity_report(
        entity, chats, calls, criteria, request.report_type, files
    )

    # Save to analysis history
    analysis = AnalysisHistory(
        entity_id=entity_id,
        user_id=user.id,
        result=report_content,
        report_type=request.report_type,
        report_format=request.format,
        criteria_used=criteria,
    )
    db.add(analysis)
    await db.commit()

    # Generate file
    title = entity.name

    if request.format == "pdf":
        file_bytes = generate_pdf_report(title, report_content, entity.name)
        return Response(
            content=file_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="report_{entity_id}.pdf"'}
        )
    elif request.format == "docx":
        file_bytes = generate_docx_report(title, report_content, entity.name)
        return Response(
            content=file_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="report_{entity_id}.docx"'}
        )
    else:
        return Response(
            content=report_content,
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="report_{entity_id}.md"'}
        )
