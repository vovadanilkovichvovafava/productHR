from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks, Request, Query
from fastapi.responses import FileResponse, Response
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel
import aiofiles
import os
import uuid
import logging
import re

from ..database import get_db
from ..models.database import (
    CallRecording, CallSource, CallStatus, Entity, User, OrgRole, UserRole,
    DepartmentMember, DeptRole, SharedAccess, ResourceType, AccessLevel
)
from ..models.sharing import BaseShareRequest as ShareRequest
from ..services.auth import get_current_user, get_user_org, get_user_org_role, can_share_to
from ..services.permissions import PermissionService
from ..services.shadow_filter import get_isolated_creator_ids
from ..config import get_settings
from datetime import datetime as dt

router = APIRouter()
logger = logging.getLogger("hr-analyzer.calls")

# Лимит дублирования аудио в БД (bytea). Типовые HR-звонки помещаются; крупные
# остаются только на диске, чтобы не раздувать БД и не ловить OOM при чтении блоба.
AUDIO_DB_MAX_BYTES = 30 * 1024 * 1024

# Get settings
settings = get_settings()

# Only create directory if not in test environment (avoids permission errors in CI)
if not os.getenv("TESTING"):
    try:
        os.makedirs(settings.upload_dir, exist_ok=True)
    except PermissionError:
        logger.warning(f"Cannot create upload directory {settings.upload_dir} - permission denied")


# === Pydantic Schemas ===

class CallCreate(BaseModel):
    entity_id: Optional[int] = None
    source_url: Optional[str] = None
    bot_name: Optional[str] = None
    title: Optional[str] = None


class StartBotRequest(BaseModel):
    source_url: str
    bot_name: Optional[str] = None
    entity_id: Optional[int] = None
    title: Optional[str] = None
    max_duration: int = 90  # Max recording duration in minutes (15-120)


class CallUpdateRequest(BaseModel):
    title: Optional[str] = None
    entity_id: Optional[int] = None  # Use -1 to unlink


class CallResponse(BaseModel):
    id: int
    title: Optional[str] = None
    entity_id: Optional[int] = None
    owner_id: Optional[int] = None
    source_type: CallSource
    source_url: Optional[str] = None
    bot_name: str
    status: CallStatus
    duration_seconds: Optional[int] = None
    transcript: Optional[str] = None
    summary: Optional[str] = None
    action_items: Optional[List[str]] = None
    key_points: Optional[List[str]] = None
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None
    entity_name: Optional[str] = None

    class Config:
        from_attributes = True


# === Routes ===

@router.get("")
async def list_calls(
    entity_id: Optional[int] = None,
    status: Optional[CallStatus] = None,
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0, le=10000),  # Limit offset to prevent abuse
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List call recordings (filtered by organization and role)"""
    current_user = await db.merge(current_user)

    # SUPERADMIN sees everything across all organizations (with shadow content isolation)
    if current_user.role == UserRole.superadmin:
        query = select(CallRecording)
        # Apply shadow user content isolation
        isolated_ids = await get_isolated_creator_ids(current_user, db)
        if isolated_ids:
            query = query.where(~CallRecording.owner_id.in_(isolated_ids))
    else:
        org = await get_user_org(current_user, db)
        if not org:
            return []

        query = select(CallRecording).where(CallRecording.org_id == org.id)

        # Salesforce-style access control:
        # - Org Owner: see all in organization
        # - Others: own + shared + dept lead sees dept members' records
        user_role = await get_user_org_role(current_user, org.id, db)

        if user_role != "owner":
            # Get IDs of recordings shared with current user
            shared_result = await db.execute(
                select(SharedAccess.resource_id).where(
                    SharedAccess.resource_type == ResourceType.call,
                    SharedAccess.shared_with_id == current_user.id,
                    or_(SharedAccess.expires_at.is_(None), SharedAccess.expires_at > dt.utcnow())
                )
            )
            shared_call_ids = [r for r in shared_result.scalars().all()]

            # Get departments where user is lead or sub_admin
            # Use string values to avoid enum serialization issues
            lead_dept_result = await db.execute(
                select(DepartmentMember.department_id).where(
                    DepartmentMember.user_id == current_user.id,
                    DepartmentMember.role.in_([DeptRole.lead, DeptRole.sub_admin])
                )
            )
            lead_dept_ids = [r for r in lead_dept_result.scalars().all()]

            # Get user IDs in departments where current user is lead
            dept_member_ids = []
            if lead_dept_ids:
                dept_members_result = await db.execute(
                    select(DepartmentMember.user_id).where(
                        DepartmentMember.department_id.in_(lead_dept_ids)
                    )
                )
                dept_member_ids = [r for r in dept_members_result.scalars().all()]

            # Get entity IDs that belong to user's departments (for entity-based access)
            # Include entities with department_id AND entities created by department members
            dept_entity_ids = []
            if lead_dept_ids:
                # Entities explicitly assigned to department
                dept_entities_result = await db.execute(
                    select(Entity.id).where(
                        Entity.department_id.in_(lead_dept_ids)
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
            conditions = [CallRecording.owner_id == current_user.id]  # Own records

            if shared_call_ids:
                conditions.append(CallRecording.id.in_(shared_call_ids))  # Shared with me

            if dept_member_ids:
                conditions.append(CallRecording.owner_id.in_(dept_member_ids))  # Dept members' records

            # Also show calls linked to entities in user's departments
            if dept_entity_ids:
                conditions.append(CallRecording.entity_id.in_(dept_entity_ids))  # Calls linked to dept entities

            # DEBUG: Log access conditions
            logger.info(f"list_calls: user={current_user.id}, lead_dept_ids={lead_dept_ids}, dept_member_ids={dept_member_ids}, shared_call_ids={shared_call_ids}, dept_entity_ids={dept_entity_ids}")

            query = query.where(or_(*conditions))
        # org owner sees all in org (no additional filter)

    if entity_id:
        query = query.where(CallRecording.entity_id == entity_id)
    if status:
        query = query.where(CallRecording.status == status)

    query = query.order_by(CallRecording.created_at.desc())
    query = query.offset(offset).limit(limit)

    # Add eager loading for entity relationship
    from sqlalchemy.orm import joinedload
    query = query.options(joinedload(CallRecording.entity))

    result = await db.execute(query)
    calls = result.unique().scalars().all()

    # DEBUG: Log query results
    logger.info(f"list_calls RESULT: user={current_user.id}, found {len(calls)} calls, ids={[c.id for c in calls][:20]}")

    if not calls:
        return []

    # Get call IDs and owner IDs for batch queries
    call_ids = [call.id for call in calls]
    owner_ids = list(set(call.owner_id for call in calls if call.owner_id))

    # Batch query: Get owner names
    owner_names_map = {}
    if owner_ids:
        owner_result = await db.execute(
            select(User.id, User.name).where(User.id.in_(owner_ids))
        )
        owner_names_map = {row[0]: row[1] for row in owner_result.fetchall()}

    # Batch query: Get shared access for current user
    shared_access_result = await db.execute(
        select(SharedAccess.resource_id, SharedAccess.access_level)
        .where(
            SharedAccess.resource_type == ResourceType.call,
            SharedAccess.resource_id.in_(call_ids),
            SharedAccess.shared_with_id == current_user.id,
            or_(SharedAccess.expires_at.is_(None), SharedAccess.expires_at > dt.utcnow())
        )
    )
    shared_access_map = {row[0]: row[1].value for row in shared_access_result.fetchall()}

    response = []
    for call in calls:
        entity_name = call.entity.name if call.entity else None
        owner_name = owner_names_map.get(call.owner_id) if call.owner_id else None
        is_mine = call.owner_id == current_user.id
        is_shared = call.id in shared_access_map
        access_level = shared_access_map.get(call.id) if is_shared else ('full' if is_mine else None)

        response.append({
            "id": call.id,
            "title": call.title,
            "entity_id": call.entity_id,
            "owner_id": call.owner_id,
            "owner_name": owner_name,
            "source_type": call.source_type,
            "source_url": call.source_url,
            "bot_name": call.bot_name,
            "status": call.status,
            "duration_seconds": call.duration_seconds,
            "transcript": call.transcript[:500] if call.transcript else None,
            "summary": call.summary,
            "action_items": call.action_items,
            "key_points": call.key_points,
            "error_message": call.error_message,
            "created_at": call.created_at,
            "started_at": call.started_at,
            "ended_at": call.ended_at,
            "processed_at": call.processed_at,
            "entity_name": entity_name,
            "is_mine": is_mine,
            "is_shared": is_shared,
            "access_level": access_level,
        })

    return response


@router.post("/upload")
async def upload_call(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    entity_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Upload audio/video file for processing"""
    current_user = await db.merge(current_user)

    # Get user's organization
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    # Check format
    allowed_extensions = {'.mp3', '.mp4', '.wav', '.m4a', '.webm', '.ogg', '.mpeg'}
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed_extensions:
        raise HTTPException(400, f"Unsupported format. Allowed: {allowed_extensions}")

    # Save file
    file_id = str(uuid.uuid4())
    file_path = os.path.join(settings.upload_dir, f"{file_id}{ext}")

    async with aiofiles.open(file_path, 'wb') as f:
        content = await file.read()
        await f.write(content)

    # Create record. Дублируем аудио в БД, если помещается в лимит — переживёт
    # редеплой эфемерного диска; крупные остаются disk-only (download отдаст 410).
    call = CallRecording(
        org_id=org.id,
        entity_id=entity_id,
        owner_id=current_user.id,
        source_type=CallSource.upload,
        status=CallStatus.processing,
        audio_file_path=file_path,
        audio_data=content if len(content) <= AUDIO_DB_MAX_BYTES else None,
    )
    db.add(call)
    await db.commit()
    await db.refresh(call)

    # Start background processing
    from ..services.call_processor import process_call_background
    background_tasks.add_task(process_call_background, call.id)

    logger.info(f"Call {call.id} uploaded and queued for processing")

    return {"id": call.id, "status": call.status.value}


@router.post("/upload-text")
async def upload_text_call(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    entity_id: Optional[int] = None,
    title: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Upload a text file (transcript) for AI analysis - skips transcription."""
    current_user = await db.merge(current_user)

    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    # Allow text-based and document formats
    text_extensions = {'.txt', '.csv', '.md', '.rtf', '.log'}
    doc_extensions = {'.pdf', '.doc', '.docx', '.html', '.htm'}
    allowed_extensions = text_extensions | doc_extensions
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed_extensions:
        raise HTTPException(
            400,
            f"Unsupported format. Allowed: {', '.join(sorted(allowed_extensions))}"
        )

    content = await file.read()
    if not content:
        raise HTTPException(400, "File is empty")
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(400, "File too large (max 20MB)")

    # Extract text content based on file type
    transcript_text = None

    if ext in text_extensions:
        # Plain text files - read directly
        for encoding in ['utf-8', 'cp1251', 'latin-1']:
            try:
                transcript_text = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if not transcript_text:
            raise HTTPException(400, "Could not decode text file")
    elif ext in doc_extensions:
        # Document files - use document parser
        try:
            from ..services.documents import document_parser
            result = await document_parser.parse(content, file.filename or "document")
            if result.status == "failed":
                raise HTTPException(400, f"Could not parse document: {result.error}")
            transcript_text = result.content
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error parsing document: {e}")
            raise HTTPException(400, f"Could not parse document: {str(e)}")

    if not transcript_text or len(transcript_text.strip()) < 10:
        raise HTTPException(400, "File contains no meaningful text")

    # Create call record with transcript already set (skip transcription)
    call = CallRecording(
        org_id=org.id,
        entity_id=entity_id,
        owner_id=current_user.id,
        source_type=CallSource.upload,
        status=CallStatus.analyzing,
        title=title or f"Transcript - {file.filename}",
        transcript=transcript_text
    )
    db.add(call)
    await db.commit()
    await db.refresh(call)

    # Start AI analysis in background (skip transcription, go straight to analysis)
    async def analyze_text_call(call_id: int, text: str):
        from ..services.call_processor import call_processor
        call_processor._init_clients()
        await call_processor.analyze_transcript(call_id, text, [])

    background_tasks.add_task(analyze_text_call, call.id, transcript_text)

    logger.info(f"Text call {call.id} uploaded and queued for analysis")

    return {"id": call.id, "status": call.status.value}


@router.post("/start-bot")
async def start_bot(
    data: StartBotRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Start a bot to record a Meet/Zoom call"""
    current_user = await db.merge(current_user)

    # Get user's organization
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    # Determine source type by URL
    source_type = CallSource.meet
    url_lower = data.source_url.lower()
    if "zoom.us" in url_lower or "zoom.com" in url_lower:
        source_type = CallSource.zoom
    elif "teams.microsoft.com" in url_lower or "teams.live.com" in url_lower:
        source_type = CallSource.teams
    elif "meet.google.com" not in url_lower:
        raise HTTPException(400, "Unsupported meeting URL. Use Google Meet, Zoom, or Microsoft Teams.")

    # Use default bot name if not provided
    bot_name = data.bot_name or settings.default_bot_name

    # Create record
    call = CallRecording(
        org_id=org.id,
        entity_id=data.entity_id,
        owner_id=current_user.id,
        source_type=source_type,
        source_url=data.source_url,
        bot_name=bot_name,
        status=CallStatus.pending
    )
    db.add(call)
    await db.commit()
    await db.refresh(call)

    # Start the recording bot via Fireflies
    try:
        from ..services.call_recorder import call_recorder
        result = await call_recorder.start_recording(
            call.id,
            data.source_url,
            bot_name,
            duration=data.max_duration
        )

        if not result.get("success"):
            error_msg = result.get("message", "Fireflies API error")
            logger.error(f"Fireflies rejected call {call.id}: {error_msg}")
            call.status = CallStatus.failed
            call.error_message = error_msg
            await db.commit()
            raise HTTPException(500, f"Fireflies error: {error_msg}")

        # Update status to recording
        # Note: Fireflies bot joins within ~1 minute, and we have no webhook for "joined"
        # So we set to "recording" immediately - the bot IS recording once it joins
        call.status = CallStatus.recording
        call.started_at = datetime.utcnow()
        await db.commit()
        logger.info(f"Call {call.id} Fireflies bot dispatched for {data.source_url}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start bot for call {call.id}: {e}")
        call.status = CallStatus.failed
        call.error_message = str(e)
        await db.commit()
        raise HTTPException(500, f"Failed to start recording bot: {e}")

    return {"id": call.id, "status": call.status.value}


@router.get("/{call_id}")
async def get_call(
    call_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get call recording details"""
    current_user = await db.merge(current_user)

    # Get user's organization
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(404, "Call not found")

    result = await db.execute(
        select(CallRecording).where(
            CallRecording.id == call_id,
            CallRecording.org_id == org.id
        )
    )
    call = result.scalar_one_or_none()

    if not call:
        raise HTTPException(404, "Call not found")

    # Check if user has access to view this call
    permissions = PermissionService(db)
    if not await permissions.can_access_resource(current_user, call, "read"):
        raise HTTPException(403, "Access denied")

    entity_name = None
    if call.entity_id:
        entity_result = await db.execute(
            select(Entity.name).where(Entity.id == call.entity_id)
        )
        entity_name = entity_result.scalar()

    return {
        "id": call.id,
        "title": call.title,
        "entity_id": call.entity_id,
        "owner_id": call.owner_id,
        "source_type": call.source_type,
        "source_url": call.source_url,
        "bot_name": call.bot_name,
        "status": call.status,
        "progress": call.progress,
        "progress_stage": call.progress_stage,
        "duration_seconds": call.duration_seconds,
        "audio_file_path": call.audio_file_path,
        "transcript": call.transcript,
        "speakers": call.speakers,
        "speaker_stats": call.speaker_stats,
        "participant_roles": call.participant_roles,
        "summary": call.summary,
        "action_items": call.action_items,
        "key_points": call.key_points,
        "error_message": call.error_message,
        "created_at": call.created_at,
        "started_at": call.started_at,
        "ended_at": call.ended_at,
        "processed_at": call.processed_at,
        "entity_name": entity_name
    }


@router.get("/{call_id}/status")
async def get_call_status(
    call_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get call status (for polling)"""
    current_user = await db.merge(current_user)

    # Get user's organization
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(404, "Call not found")

    # Need to get the full call object to check access
    result = await db.execute(
        select(CallRecording).where(
            CallRecording.id == call_id,
            CallRecording.org_id == org.id
        )
    )
    call = result.scalar_one_or_none()

    if not call:
        raise HTTPException(404, "Call not found")

    # Check if user has access to view this call
    permissions = PermissionService(db)
    if not await permissions.can_access_resource(current_user, call, "read"):
        raise HTTPException(403, "Access denied")

    return {
        "status": call.status.value,
        "duration_seconds": call.duration_seconds,
        "error_message": call.error_message,
        "progress": call.progress or 0,
        "progress_stage": call.progress_stage or ""
    }


@router.get("/{call_id}/download/transcript")
async def download_transcript(
    call_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Download call transcript as a text file"""
    current_user = await db.merge(current_user)

    # Get user's organization
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(404, "Call not found")

    result = await db.execute(
        select(CallRecording).where(
            CallRecording.id == call_id,
            CallRecording.org_id == org.id
        )
    )
    call = result.scalar_one_or_none()

    if not call:
        raise HTTPException(404, "Call not found")

    # Check if user has access to view this call
    permissions = PermissionService(db)
    if not await permissions.can_access_resource(current_user, call, "read"):
        raise HTTPException(403, "Access denied")

    # Check if transcript exists
    if not call.transcript:
        raise HTTPException(404, "Transcript not available")

    # Generate filename
    title = call.title or f"Call_{call.id}"
    # Sanitize filename
    safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
    filename = f"{safe_title}_transcript.txt"

    # Return transcript as downloadable file
    return Response(
        content=call.transcript,
        media_type="text/plain",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


@router.get("/{call_id}/download/audio")
async def download_audio(
    call_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Download call audio file"""
    current_user = await db.merge(current_user)

    # Get user's organization
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(404, "Call not found")

    result = await db.execute(
        select(CallRecording).where(
            CallRecording.id == call_id,
            CallRecording.org_id == org.id
        )
    )
    call = result.scalar_one_or_none()

    if not call:
        raise HTTPException(404, "Call not found")

    # Check if user has access to view this call
    permissions = PermissionService(db)
    if not await permissions.can_access_resource(current_user, call, "read"):
        raise HTTPException(403, "Access denied")

    # Determine content type based on file extension (path хранит исходное расширение)
    ext = os.path.splitext(call.audio_file_path or "")[1].lower()
    content_type_map = {
        '.mp3': 'audio/mpeg',
        '.mp4': 'video/mp4',
        '.wav': 'audio/wav',
        '.m4a': 'audio/mp4',
        '.webm': 'video/webm',
        '.ogg': 'audio/ogg',
        '.mpeg': 'audio/mpeg',
    }
    content_type = content_type_map.get(ext, 'application/octet-stream')

    # Generate filename
    title = call.title or f"Call_{call.id}"
    safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
    filename = f"{safe_title}{ext}"
    disposition = {"Content-Disposition": f'attachment; filename="{filename}"'}

    # 1) Байты из БД (переживают редеплой) — приоритетно.
    if call.audio_data:
        return Response(content=call.audio_data, media_type=content_type, headers=disposition)

    # 2) Fallback на диск (legacy / крупные файлы).
    if call.audio_file_path and os.path.exists(call.audio_file_path):
        return FileResponse(call.audio_file_path, media_type=content_type, headers=disposition)

    # 3) Аудио потеряно (эфемерный диск + не дублировалось в БД). Честный 410 —
    # транскрипт и анализ звонка по-прежнему доступны; URL-звонок можно пере-загрузить.
    raise HTTPException(
        410,
        "Аудиофайл недоступен (потерян при обновлении сервера). "
        "Транскрипт и анализ звонка сохранены."
    )


@router.post("/{call_id}/recalculate-stats")
async def recalculate_call_stats(
    call_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Recalculate speaker stats for a call.

    Useful for calls that were processed before speaker stats were implemented,
    or when timestamps/speakers have been fixed.
    """
    current_user = await db.merge(current_user)

    # Get user's organization
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(404, "Call not found")

    result = await db.execute(
        select(CallRecording).where(
            CallRecording.id == call_id,
            CallRecording.org_id == org.id
        )
    )
    call = result.scalar_one_or_none()

    if not call:
        raise HTTPException(404, "Call not found")

    # Check if user has access to edit this call
    permissions = PermissionService(db)
    if not await permissions.can_access_resource(current_user, call, "read"):
        raise HTTPException(403, "Access denied")

    if not call.speakers:
        raise HTTPException(400, "Call has no speaker data to calculate stats from")

    # Calculate speaker stats
    from ..services.call_processor import calculate_speaker_stats
    call.speaker_stats = calculate_speaker_stats(call.speakers, call.duration_seconds)

    await db.commit()
    await db.refresh(call)

    return {
        "message": "Speaker stats recalculated successfully",
        "speaker_stats": call.speaker_stats
    }


@router.post("/{call_id}/stop")
async def stop_recording(
    call_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Stop a recording"""
    current_user = await db.merge(current_user)

    # Get user's organization
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(404, "Call not found")

    result = await db.execute(
        select(CallRecording).where(
            CallRecording.id == call_id,
            CallRecording.org_id == org.id
        )
    )
    call = result.scalar_one_or_none()

    if not call:
        raise HTTPException(404, "Call not found")

    # Check if user has full access (destructive operation)
    permissions = PermissionService(db)
    if not await permissions.can_modify(current_user, call, require_full=True):
        raise HTTPException(403, "No permission to stop this recording")

    if call.status != CallStatus.recording:
        raise HTTPException(400, "Call is not currently recording")

    # Send stop command
    try:
        from ..services.call_recorder import call_recorder
        await call_recorder.stop_recording(call_id)
        logger.info(f"Stop command sent for call {call_id}")
    except Exception as e:
        logger.error(f"Failed to stop call {call_id}: {e}")
        raise HTTPException(500, f"Failed to stop recording: {e}")

    return {"success": True}


@router.delete("/{call_id}")
async def delete_call(
    call_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a call recording"""
    current_user = await db.merge(current_user)

    # Get user's organization
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(404, "Call not found")

    result = await db.execute(
        select(CallRecording).where(
            CallRecording.id == call_id,
            CallRecording.org_id == org.id
        )
    )
    call = result.scalar_one_or_none()

    if not call:
        raise HTTPException(404, "Call not found")

    # Check if user has full access (destructive operation)
    permissions = PermissionService(db)
    if not await permissions.can_modify(current_user, call, require_full=True):
        raise HTTPException(403, "No delete permission for this call")

    # Delete the audio file if it exists
    if call.audio_file_path and os.path.exists(call.audio_file_path):
        try:
            os.remove(call.audio_file_path)
        except OSError as e:
            logger.warning(f"Failed to delete audio file: {e}")

    await db.delete(call)
    await db.commit()
    return {"success": True}


@router.post("/{call_id}/link-entity/{entity_id}")
async def link_call_to_entity(
    call_id: int,
    entity_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Link a call recording to an entity"""
    current_user = await db.merge(current_user)

    # Get user's organization
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(404, "Call not found")

    # Verify entity exists and belongs to same org
    entity_result = await db.execute(
        select(Entity).where(Entity.id == entity_id, Entity.org_id == org.id)
    )
    entity = entity_result.scalar_one_or_none()
    if not entity:
        raise HTTPException(404, "Entity not found")

    # Get and update call (must belong to same org)
    call_result = await db.execute(
        select(CallRecording).where(
            CallRecording.id == call_id,
            CallRecording.org_id == org.id
        )
    )
    call = call_result.scalar_one_or_none()

    if not call:
        raise HTTPException(404, "Call not found")

    # Check if user has edit or full access
    permissions = PermissionService(db)
    if not await permissions.can_modify(current_user, call, require_full=False):
        raise HTTPException(403, "No permission to link this call")

    call.entity_id = entity_id
    await db.commit()
    return {"success": True}


@router.post("/{call_id}/reprocess")
async def reprocess_call(
    call_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Re-process a call recording - works for both audio files and Fireflies transcripts"""
    current_user = await db.merge(current_user)

    # Get user's organization
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(404, "Call not found")

    result = await db.execute(
        select(CallRecording).where(
            CallRecording.id == call_id,
            CallRecording.org_id == org.id
        )
    )
    call = result.scalar_one_or_none()

    if not call:
        raise HTTPException(404, "Call not found")

    # Check if user has edit or full access
    permissions = PermissionService(db)
    if not await permissions.can_modify(current_user, call, require_full=False):
        raise HTTPException(403, "No permission to reprocess this call")

    # Check what we have to reprocess
    has_audio = bool(call.audio_file_path)
    has_transcript = bool(call.transcript)
    has_fireflies = bool(call.fireflies_transcript_id)

    if not has_audio and not has_transcript and not has_fireflies:
        raise HTTPException(400, "No data to process")

    # If we have fireflies_id but no transcript, we can't re-analyze
    # (fireflies_id alone is just a reference, we need actual transcript text)
    if has_fireflies and not has_transcript and not has_audio:
        raise HTTPException(400, "No data to process")

    # Reset status
    call.status = CallStatus.analyzing
    call.error_message = None
    await db.commit()

    if has_fireflies or has_transcript:
        # Re-analyze existing transcript with Claude
        from ..services.call_processor import call_processor

        # IMPORTANT: Save values to local variables BEFORE creating closure
        # to avoid issues with detached SQLAlchemy objects after session closes
        call_id_for_task = call.id
        transcript_for_task = call.transcript or ""
        speakers_for_task = call.speakers if call.speakers else []

        logger.info(f"Starting reanalysis for call {call_id_for_task}, "
                    f"transcript length: {len(transcript_for_task)}, "
                    f"speakers count: {len(speakers_for_task)}, "
                    f"has_fireflies: {has_fireflies}")

        async def reanalyze_transcript():
            try:
                if not transcript_for_task:
                    # No transcript to analyze - mark as failed
                    logger.warning(f"Call {call_id_for_task} has no transcript to re-analyze")
                    async with AsyncSessionLocal() as db2:
                        result2 = await db2.execute(
                            select(CallRecording).where(CallRecording.id == call_id_for_task)
                        )
                        call2 = result2.scalar_one_or_none()
                        if call2:
                            call2.status = CallStatus.failed
                            call2.error_message = "No transcript available for re-analysis"
                            await db2.commit()
                    return

                logger.info(f"Calling analyze_transcript for call {call_id_for_task}")
                await call_processor.analyze_transcript(
                    call_id=call_id_for_task,
                    transcript=transcript_for_task,
                    speakers=speakers_for_task
                )
                logger.info(f"Call {call_id_for_task} re-analyzed successfully")
            except Exception as e:
                logger.error(f"Failed to re-analyze call {call_id_for_task}: {e}", exc_info=True)
                # Mark as failed
                async with AsyncSessionLocal() as db2:
                    result2 = await db2.execute(
                        select(CallRecording).where(CallRecording.id == call_id_for_task)
                    )
                    call2 = result2.scalar_one_or_none()
                    if call2:
                        call2.status = CallStatus.failed
                        call2.error_message = str(e)
                        await db2.commit()

        background_tasks.add_task(reanalyze_transcript)
    elif has_audio:
        # Process audio file from scratch
        from ..services.call_processor import process_call_background
        call.status = CallStatus.processing
        await db.commit()
        background_tasks.add_task(process_call_background, call.id)

    return {"success": True, "status": call.status.value}


@router.patch("/{call_id}")
async def update_call(
    call_id: int,
    data: CallUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update call recording (title, entity link)"""
    current_user = await db.merge(current_user)

    # Get user's organization
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(404, "Call not found")

    result = await db.execute(
        select(CallRecording).where(
            CallRecording.id == call_id,
            CallRecording.org_id == org.id
        )
    )
    call = result.scalar_one_or_none()

    if not call:
        raise HTTPException(404, "Call not found")

    # Check if user has edit or full access
    permissions = PermissionService(db)
    if not await permissions.can_modify(current_user, call, require_full=False):
        raise HTTPException(403, "No edit permission for this call")

    # Update title if provided
    if data.title is not None:
        call.title = data.title if data.title else None

    # Update entity link
    if data.entity_id is not None:
        if data.entity_id == -1:
            # Unlink entity
            call.entity_id = None
        else:
            # Verify entity exists and belongs to same org
            entity_result = await db.execute(
                select(Entity).where(Entity.id == data.entity_id, Entity.org_id == org.id)
            )
            entity = entity_result.scalar_one_or_none()
            if not entity:
                raise HTTPException(404, "Entity not found")
            call.entity_id = data.entity_id

    await db.commit()
    await db.refresh(call)

    # Get entity name for response
    entity_name = None
    if call.entity_id:
        entity_result = await db.execute(
            select(Entity.name).where(Entity.id == call.entity_id)
        )
        entity_name = entity_result.scalar()

    return {
        "id": call.id,
        "title": call.title,
        "entity_id": call.entity_id,
        "entity_name": entity_name,
        "success": True
    }


# === Fireflies Webhook ===

@router.post("/fireflies-webhook")
async def fireflies_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Webhook endpoint for Fireflies.ai notifications.

    Fireflies sends this when transcription is completed:
    {
        "meetingId": "abc123",           # Fireflies transcript ID
        "eventType": "Transcription completed",
        "clientReferenceId": null        # Only for uploadAudio
    }

    We identify our call by parsing the title "HR Call #123"
    which Fireflies returns in the transcript.
    """
    try:
        data = await request.json()
        logger.info(f"Fireflies webhook received: {data}")

        meeting_id = data.get("meetingId")
        event_type = data.get("eventType", "")

        # Only process transcription completed events
        if "completed" not in event_type.lower():
            logger.info(f"Ignoring Fireflies event: {event_type}")
            return {"status": "ignored", "reason": f"event_type: {event_type}"}

        if not meeting_id:
            logger.warning("Fireflies webhook missing meetingId")
            return {"status": "error", "reason": "missing_meeting_id"}

        # Fetch transcript from Fireflies to get the title
        from ..services.fireflies_client import fireflies_client

        transcript = await fireflies_client.get_transcript(meeting_id)
        if not transcript:
            logger.error(f"Could not fetch transcript {meeting_id} from Fireflies")
            return {"status": "error", "reason": "transcript_not_found"}

        title = transcript.get("title", "")
        logger.info(f"Fireflies transcript title: {title}")

        # Extract call_id from title "HR Call #123"
        call_id = None
        match = re.search(r"HR Call #(\d+)", title)
        if match:
            call_id = int(match.group(1))
        else:
            # Try to find by meeting URL or just log
            logger.warning(f"Could not extract call_id from title: {title}")
            return {"status": "ignored", "reason": "unknown_meeting", "title": title}

        # Get call from database
        result = await db.execute(
            select(CallRecording).where(CallRecording.id == call_id)
        )
        call = result.scalar_one_or_none()

        if not call:
            logger.error(f"Call {call_id} not found in database")
            return {"status": "error", "reason": "call_not_found", "call_id": call_id}

        # Prevent duplicate processing
        if call.status in (CallStatus.done, CallStatus.processing, CallStatus.analyzing):
            logger.info(f"Call {call_id} already processed or in progress, skipping")
            return {"status": "ignored", "reason": "already_processed", "call_id": call_id}

        # Update call with Fireflies transcript ID
        call.fireflies_transcript_id = meeting_id
        call.status = CallStatus.processing
        await db.commit()

        logger.info(f"Processing Fireflies transcript for call {call_id}")

        # Process transcript in background
        background_tasks.add_task(
            process_fireflies_transcript,
            call_id,
            transcript
        )

        return {"status": "ok", "call_id": call_id, "transcript_id": meeting_id}

    except Exception as e:
        logger.exception(f"Error processing Fireflies webhook: {e}")
        return {"status": "error", "reason": str(e)}


@router.post("/{call_id}/share")
async def share_call(
    call_id: int,
    data: ShareRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Share a call recording with another user.

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

    # Get call
    result = await db.execute(
        select(CallRecording).where(
            CallRecording.id == call_id,
            CallRecording.org_id == org.id
        )
    )
    call = result.scalar_one_or_none()

    if not call:
        raise HTTPException(404, "Call not found")

    # Check if user has permission to share this call (requires full access or ownership)
    can_share = False
    if current_user.role == UserRole.superadmin:
        can_share = True
    else:
        user_role = await get_user_org_role(current_user, org.id, db)
        if user_role == OrgRole.owner:
            can_share = True
        elif call.owner_id == current_user.id:
            can_share = True  # Owner of call
        else:
            # Check if shared with full access
            shared_result = await db.execute(
                select(SharedAccess).where(
                    SharedAccess.resource_type == ResourceType.call,
                    SharedAccess.resource_id == call_id,
                    SharedAccess.shared_with_id == current_user.id,
                    SharedAccess.access_level == AccessLevel.full,
                    or_(SharedAccess.expires_at.is_(None), SharedAccess.expires_at > datetime.utcnow())
                )
            )
            if shared_result.scalar_one_or_none():
                can_share = True

    if not can_share:
        raise HTTPException(403, "No permission to share this call")

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
            SharedAccess.resource_type == ResourceType.call,
            SharedAccess.resource_id == call_id,
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
            resource_type=ResourceType.call,
            resource_id=call_id,
            call_id=call_id,  # FK for cascade delete
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
        "call_id": call_id,
        "shared_with_id": data.shared_with_id,
        "access_level": data.access_level.value
    }


async def process_fireflies_transcript(call_id: int, transcript: dict):
    """
    Process Fireflies transcript: format speakers, analyze with Claude, save results.
    """
    from ..database import AsyncSessionLocal
    from ..services.call_processor import call_processor

    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(CallRecording).where(CallRecording.id == call_id)
            )
            call = result.scalar_one_or_none()

            if not call:
                logger.error(f"Call {call_id} not found for processing")
                return

            # Format transcript with speaker labels
            sentences = transcript.get("sentences") or []
            duration = transcript.get("duration") or 0
            summary_data = transcript.get("summary") or {}

            # Build formatted transcript text
            formatted_lines = []
            speaker_segments = []

            # Find the first timestamp to normalize all times
            # This makes the transcript always start from 0:00
            first_timestamp = 0.0
            for sentence in sentences:
                text = sentence.get("text") or sentence.get("raw_text") or ""
                if text.strip():  # First non-empty sentence
                    first_timestamp = float(sentence.get("start_time") or 0)
                    break

            for sentence in sentences:
                speaker_name = sentence.get("speaker_name") or f"Speaker {sentence.get('speaker_id', '?')}"
                text = sentence.get("text") or sentence.get("raw_text") or ""
                raw_start_time = float(sentence.get("start_time") or 0)
                raw_end_time = float(sentence.get("end_time") or 0)

                # Normalize timestamps to start from 0
                start_time = max(0, raw_start_time - first_timestamp)
                end_time = max(0, raw_end_time - first_timestamp)

                # Skip empty sentences
                if not text.strip():
                    continue

                # Format timestamp
                start_min = int(start_time // 60)
                start_sec = int(start_time % 60)
                timestamp = f"[{start_min:02d}:{start_sec:02d}]"

                formatted_lines.append(f"{timestamp} {speaker_name}: {text}")

                # Store speaker segment for JSON
                speaker_segments.append({
                    "speaker": speaker_name,
                    "start": start_time,
                    "end": end_time,
                    "text": text
                })

            formatted_transcript = "\n".join(formatted_lines)

            # Update call with transcript data
            call.transcript = formatted_transcript
            call.speakers = speaker_segments
            call.duration_seconds = int(duration) if duration else None
            call.status = CallStatus.analyzing

            # Use Fireflies summary if available, otherwise analyze with Claude
            if summary_data.get("overview") or summary_data.get("short_summary"):
                # Build comprehensive summary from Fireflies data
                summary_parts = []

                # Main overview
                overview = summary_data.get("overview") or summary_data.get("short_summary", "")
                if overview:
                    summary_parts.append(overview)

                # Add bullet gist for more details
                bullet_gist = summary_data.get("bullet_gist") or []
                if bullet_gist and isinstance(bullet_gist, list):
                    summary_parts.append("\n\n**Основные пункты обсуждения:**")
                    for item in bullet_gist[:10]:  # Limit to 10 items
                        if isinstance(item, str):
                            summary_parts.append(f"• {item}")
                        elif isinstance(item, dict) and item.get("text"):
                            summary_parts.append(f"• {item.get('text')}")

                call.summary = "\n".join(summary_parts)

                # Get action items
                action_items = summary_data.get("action_items") or []
                if isinstance(action_items, list):
                    call.action_items = [
                        item.get("text") if isinstance(item, dict) else str(item)
                        for item in action_items if item
                    ][:15]  # Limit to 15 items
                else:
                    call.action_items = []

                # Get keywords/outline as key points
                key_points = []

                # Try outline first (more detailed)
                outline = summary_data.get("outline") or []
                if outline and isinstance(outline, list):
                    for item in outline[:10]:
                        if isinstance(item, str):
                            key_points.append(item)
                        elif isinstance(item, dict) and item.get("text"):
                            key_points.append(item.get("text"))

                # Fall back to keywords if no outline
                if not key_points:
                    keywords = summary_data.get("keywords") or []
                    if isinstance(keywords, list):
                        key_points = [str(k) for k in keywords[:15]]

                call.key_points = key_points
                call.status = CallStatus.done
                call.processed_at = datetime.utcnow()
                call.ended_at = datetime.utcnow()
                await db.commit()
                logger.info(f"Call {call_id} processed with Fireflies summary")
            else:
                # Analyze with Claude
                await db.commit()
                await call_processor.analyze_transcript(call_id, formatted_transcript, speaker_segments)

    except Exception as e:
        logger.exception(f"Error processing transcript for call {call_id}: {e}")

        # Mark as failed
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(CallRecording).where(CallRecording.id == call_id)
                )
                call = result.scalar_one_or_none()
                if call:
                    call.status = CallStatus.failed
                    call.error_message = str(e)
                    await db.commit()
        except Exception as db_error:
            logger.error(f"Failed to update call status: {db_error}")
