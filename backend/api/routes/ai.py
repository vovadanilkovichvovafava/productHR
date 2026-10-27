from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Response, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified
import json

from ..database import get_db
from ..models.database import User, Chat, Message, ChatCriteria, AIConversation, AnalysisHistory
from ..models.schemas import (
    AIMessageRequest, AIConversationResponse, AnalysisResponse,
    AnalyzeRequest, ReportRequest
)
from ..services.auth import get_current_user
from ..services.ai import ai_service
from ..services.reports import generate_pdf_report, generate_docx_report
from ..services.permissions import PermissionService
from ..limiter import limiter, user_or_ip

router = APIRouter()


def _get_rate_limit_key(request: Request) -> str:
    """Лимит на пользователя (номер из токена), без входа — на адрес; см. limiter.user_or_ip."""
    return user_or_ip(request)


async def get_chat_context(db: AsyncSession, chat_id: int):
    """Get chat with messages and criteria, including owner and entity for participant identification."""
    result = await db.execute(
        select(Chat)
        .options(selectinload(Chat.owner), selectinload(Chat.entity))
        .where(Chat.id == chat_id)
    )
    chat = result.scalar_one_or_none()
    if not chat:
        return None, [], []

    result = await db.execute(
        select(Message).where(Message.chat_id == chat_id).order_by(Message.timestamp)
    )
    messages = result.scalars().all()

    result = await db.execute(select(ChatCriteria).where(ChatCriteria.chat_id == chat_id))
    criteria_obj = result.scalar_one_or_none()
    criteria = criteria_obj.criteria if criteria_obj else []

    return chat, list(messages), criteria


@router.post("/{chat_id}/ai/message")
@limiter.limit("30/minute", key_func=_get_rate_limit_key)
async def ai_message(
    chat_id: int,
    body: AIMessageRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Store user for rate limiter
    request.state._rate_limit_user = user

    user = await db.merge(user)
    chat, messages, criteria = await get_chat_context(db, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    permissions = PermissionService(db)
    if not await permissions.can_access_resource(user, chat, "read"):
        raise HTTPException(status_code=403, detail="Access denied")

    # Validate that at least one of message or quick_action is provided
    if not body.message and not body.quick_action:
        raise HTTPException(status_code=400, detail="Требуется message или quick_action")

    # Get or create conversation
    result = await db.execute(
        select(AIConversation).where(
            AIConversation.chat_id == chat_id,
            AIConversation.user_id == user.id
        )
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        conversation = AIConversation(
            chat_id=chat_id,
            user_id=user.id,
            messages=[]
        )
        db.add(conversation)

    history = conversation.messages or []

    # Get chat type info
    chat_type = chat.chat_type.value if chat.chat_type else "hr"
    custom_description = chat.custom_type_description

    # Handle quick actions
    if body.quick_action:
        async def generate():
            full_response = ""
            try:
                async for chunk in ai_service.quick_action(
                    body.quick_action, chat.title, messages, criteria,
                    chat_type, custom_description, chat
                ):
                    full_response += chunk
                    yield f"data: {json.dumps({'content': chunk})}\n\n"
            except Exception as e:
                error_msg = f"Ошибка AI: {str(e)}"
                yield f"data: {json.dumps({'content': error_msg, 'error': True})}\n\n"
                yield "data: [DONE]\n\n"
                return

            # Save to conversation
            new_messages = list(history)  # Create new list to ensure change detection
            new_messages.append({
                "role": "user",
                "content": f"[Быстрое действие: {body.quick_action}]",
                "timestamp": datetime.utcnow().isoformat()
            })
            new_messages.append({
                "role": "assistant",
                "content": full_response,
                "timestamp": datetime.utcnow().isoformat()
            })
            conversation.messages = new_messages
            flag_modified(conversation, "messages")
            await db.commit()

            yield "data: [DONE]\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")

    # Regular message
    async def generate():
        full_response = ""
        try:
            async for chunk in ai_service.chat_stream(
                body.message, chat.title, messages, criteria, history,
                chat_type, custom_description, chat
            ):
                full_response += chunk
                yield f"data: {json.dumps({'content': chunk})}\n\n"
        except Exception as e:
            error_msg = f"Ошибка AI: {str(e)}"
            yield f"data: {json.dumps({'content': error_msg, 'error': True})}\n\n"
            yield "data: [DONE]\n\n"
            return

        # Save to conversation
        new_messages = list(history)  # Create new list to ensure change detection
        new_messages.append({
            "role": "user",
            "content": body.message,
            "timestamp": datetime.utcnow().isoformat()
        })
        new_messages.append({
            "role": "assistant",
            "content": full_response,
            "timestamp": datetime.utcnow().isoformat()
        })
        conversation.messages = new_messages
        flag_modified(conversation, "messages")
        await db.commit()

        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/{chat_id}/ai/history", response_model=AIConversationResponse)
async def get_ai_history(
    chat_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    user = await db.merge(user)
    result = await db.execute(select(Chat).where(Chat.id == chat_id))
    chat = result.scalar_one_or_none()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    permissions = PermissionService(db)
    if not await permissions.can_access_resource(user, chat, "read"):
        raise HTTPException(status_code=403, detail="Access denied")

    result = await db.execute(
        select(AIConversation).where(
            AIConversation.chat_id == chat_id,
            AIConversation.user_id == user.id
        )
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        return AIConversationResponse(
            id=0, chat_id=chat_id, messages=[],
            created_at=datetime.utcnow(), updated_at=datetime.utcnow()
        )

    return AIConversationResponse(
        id=conversation.id,
        chat_id=conversation.chat_id,
        messages=conversation.messages or [],
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


@router.delete("/{chat_id}/ai/history", status_code=204)
async def clear_ai_history(
    chat_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    user = await db.merge(user)

    # Check chat exists and user has access
    result = await db.execute(select(Chat).where(Chat.id == chat_id))
    chat = result.scalar_one_or_none()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    permissions = PermissionService(db)
    if not await permissions.can_access_resource(user, chat, "read"):
        raise HTTPException(status_code=403, detail="Access denied")

    # Delete conversation for this user and chat
    result = await db.execute(
        select(AIConversation).where(
            AIConversation.chat_id == chat_id,
            AIConversation.user_id == user.id
        )
    )
    conversation = result.scalar_one_or_none()

    if conversation:
        await db.delete(conversation)
        await db.commit()


@router.post("/{chat_id}/analyze", response_model=AnalysisResponse)
@limiter.limit("10/minute", key_func=_get_rate_limit_key)
async def analyze_chat(
    chat_id: int,
    body: AnalyzeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    request.state._rate_limit_user = user
    user = await db.merge(user)
    chat, messages, criteria = await get_chat_context(db, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    permissions = PermissionService(db)
    if not await permissions.can_access_resource(user, chat, "read"):
        raise HTTPException(status_code=403, detail="Access denied")

    chat_type = chat.chat_type.value if chat.chat_type else "hr"
    result = await ai_service.generate_report(
        chat.title, messages, criteria, body.report_type, body.include_quotes,
        chat_type, chat.custom_type_description, chat.id, True, chat
    )

    analysis = AnalysisHistory(
        chat_id=chat_id,
        user_id=user.id,
        result=result,
        report_type=body.report_type,
        criteria_used=criteria,
    )
    db.add(analysis)
    await db.commit()
    await db.refresh(analysis)

    return AnalysisResponse(
        id=analysis.id,
        chat_id=analysis.chat_id,
        result=analysis.result,
        report_type=analysis.report_type,
        created_at=analysis.created_at,
    )


@router.get("/{chat_id}/analysis-history", response_model=List[AnalysisResponse])
async def get_analysis_history(
    chat_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    user = await db.merge(user)
    result = await db.execute(select(Chat).where(Chat.id == chat_id))
    chat = result.scalar_one_or_none()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    permissions = PermissionService(db)
    if not await permissions.can_access_resource(user, chat, "read"):
        raise HTTPException(status_code=403, detail="Access denied")

    result = await db.execute(
        select(AnalysisHistory)
        .where(AnalysisHistory.chat_id == chat_id)
        .order_by(AnalysisHistory.created_at.desc())
        .limit(20)
    )
    history = result.scalars().all()

    return [
        AnalysisResponse(
            id=h.id, chat_id=h.chat_id, result=h.result,
            report_type=h.report_type, created_at=h.created_at
        ) for h in history
    ]


@router.post("/{chat_id}/report")
async def generate_report_file(
    chat_id: int,
    request: ReportRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    user = await db.merge(user)
    chat, messages, criteria = await get_chat_context(db, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    permissions = PermissionService(db)
    if not await permissions.can_access_resource(user, chat, "read"):
        raise HTTPException(status_code=403, detail="Access denied")

    chat_type = chat.chat_type.value if chat.chat_type else "hr"
    # Generate report content
    content = await ai_service.generate_report(
        chat.title, messages, criteria, request.report_type, True,
        chat_type, chat.custom_type_description, chat.id, True, chat
    )

    # Save to history
    analysis = AnalysisHistory(
        chat_id=chat_id,
        user_id=user.id,
        result=content,
        report_type=request.report_type,
        report_format=request.format,
        criteria_used=criteria,
    )
    db.add(analysis)
    await db.commit()

    # Generate file
    title = chat.custom_name or chat.title

    if request.format == "pdf":
        file_bytes = generate_pdf_report(title, content, chat.title)
        return Response(
            content=file_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="report_{chat_id}.pdf"'}
        )
    elif request.format == "docx":
        file_bytes = generate_docx_report(title, content, chat.title)
        return Response(
            content=file_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="report_{chat_id}.docx"'}
        )
    else:
        return Response(
            content=content,
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="report_{chat_id}.md"'}
        )
