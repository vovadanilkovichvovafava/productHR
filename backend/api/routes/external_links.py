"""
External Links API Routes.

Endpoints for processing external URLs:
- Fireflies.ai (transcripts)
- Google Docs (transcripts)
- Google Drive (media files)
- Direct media URLs
"""

from typing import Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, HttpUrl
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.database import User, CallRecording, CallSource, CallStatus
from ..services.auth import get_current_user, get_user_org
from ..services.external_links import external_link_processor, LinkType
import logging

logger = logging.getLogger("hr-analyzer.external_links_route")

router = APIRouter(prefix="/api/external", tags=["External Links"])


class ProcessURLRequest(BaseModel):
    """Request body for processing an external URL."""
    url: str
    title: Optional[str] = None
    department_id: Optional[int] = None
    entity_id: Optional[int] = None


class ProcessURLResponse(BaseModel):
    """Response for URL processing."""
    call_id: int
    status: str
    source_type: str
    title: Optional[str]
    message: str


class LinkTypeResponse(BaseModel):
    """Response for link type detection."""
    url: str
    link_type: str
    description: str
    can_process: bool = True
    message: Optional[str] = None


@router.post("/process-url", response_model=ProcessURLResponse)
async def process_external_url(
    request: ProcessURLRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Process an external URL containing a call recording or transcript.

    Supported URL types:
    - **Fireflies.ai**: Transcripts from Fireflies (processed in background)
    - **Google Docs**: Documents containing call transcripts (skips transcription, goes straight to AI analysis)
    - **Google Drive**: Audio/video files stored in Google Drive
    - **Direct media URLs**: Direct links to .mp3, .mp4, .wav, etc. files

    The processing happens in the background. Use the returned `id` to check status.
    """
    import logging
    logger = logging.getLogger("hr-analyzer.external_links")

    # Get user's organization
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=400, detail="User not associated with any organization")

    # Detect link type
    link_type = external_link_processor.detect_link_type(request.url)

    try:
        # Check for duplicate URL (same URL submitted in the last 5 minutes)
        from datetime import timedelta
        five_minutes_ago = datetime.utcnow() - timedelta(minutes=5)
        existing_result = await db.execute(
            select(CallRecording).where(
                CallRecording.source_url == request.url,
                CallRecording.org_id == org.id,
                CallRecording.created_at > five_minutes_ago
            )
        )
        existing_call = existing_result.scalar_one_or_none()

        if existing_call:
            logger.info(f"Duplicate URL detected, returning existing call {existing_call.id}")
            return ProcessURLResponse(
                call_id=existing_call.id,
                status=existing_call.status.value if existing_call.status else "pending",
                source_type=existing_call.source_type.value if existing_call.source_type else "unknown",
                title=existing_call.title,
                message="This URL is already being processed. Please wait."
            )

        # For Fireflies - use async processing (takes 1-2 minutes)
        # Create record immediately and process in background
        if link_type == LinkType.FIREFLIES:
            call = await external_link_processor.create_pending_call(
                url=request.url,
                organization_id=org.id,
                owner_id=current_user.id,
                source_type=CallSource.fireflies,
                entity_id=request.entity_id,
                title=request.title
            )

            # Process Fireflies in background - this takes 1-2 minutes
            background_tasks.add_task(
                external_link_processor.process_fireflies_async,
                call.id
            )

            return ProcessURLResponse(
                call_id=call.id,
                status="pending",
                source_type="fireflies",
                title=call.title,
                message="Fireflies transcript is being processed. This may take 1-2 minutes."
            )

        # For other types - process synchronously (they're fast)
        call = await external_link_processor.process_url(
            url=request.url,
            organization_id=org.id,
            owner_id=current_user.id,
            department_id=request.department_id,
            entity_id=request.entity_id,
            title=request.title
        )

        # If the call has audio and needs processing, do it in background
        if call.audio_file_path and call.status == CallStatus.pending:
            background_tasks.add_task(
                external_link_processor.process_call_audio,
                call.id
            )
            message = "Audio file downloaded. Transcription started in background."
        elif call.status == CallStatus.done:
            message = "Document processed successfully."
        elif call.status == CallStatus.failed:
            message = f"Processing failed: {call.error_message}"
        else:
            message = f"Processing started. Current status: {call.status.value}"

        return ProcessURLResponse(
            call_id=call.id,
            status=call.status.value if call.status else "unknown",
            source_type=call.source_type.value if call.source_type else "unknown",
            title=call.title,
            message=message
        )

    except IntegrityError as e:
        # Duplicate URL - race condition caught by unique constraint
        # Return the existing call
        logger.info(f"Duplicate URL detected via unique constraint: {request.url}")
        await db.rollback()
        existing_result = await db.execute(
            select(CallRecording).where(
                CallRecording.source_url == request.url,
                CallRecording.org_id == org.id
            ).order_by(CallRecording.created_at.desc())
        )
        existing_call = existing_result.scalar_one_or_none()
        if existing_call:
            return ProcessURLResponse(
                call_id=existing_call.id,
                status=existing_call.status.value if existing_call.status else "pending",
                source_type=existing_call.source_type.value if existing_call.source_type else "unknown",
                title=existing_call.title,
                message="This URL has already been imported."
            )
        raise HTTPException(status_code=409, detail="Duplicate URL detected")

    except Exception as e:
        import traceback
        logger.error(f"Error in process_external_url: {type(e).__name__}: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error processing URL: {str(e)}")


@router.get("/detect-type", response_model=LinkTypeResponse)
async def detect_link_type(
    url: str,
    current_user: User = Depends(get_current_user)
):
    """
    Detect the type of an external URL without processing it.

    Returns the detected type and a description of how it will be handled.
    """
    link_type = external_link_processor.detect_link_type(url)

    descriptions = {
        LinkType.FIREFLIES: "Fireflies.ai transcript. Will be fetched and analyzed (no transcription needed).",
        LinkType.GOOGLE_DOC: "Google Docs document. Will be parsed as text and analyzed (no transcription needed).",
        LinkType.GOOGLE_SHEET: "Google Sheets spreadsheet. Will be exported as CSV and analyzed.",
        LinkType.GOOGLE_FORM: "Google Forms. Will be parsed and analyzed.",
        LinkType.GOOGLE_DRIVE: "Google Drive file. Will be downloaded and transcribed if it's audio/video.",
        LinkType.DIRECT_MEDIA: "Direct media file. Will be downloaded and transcribed.",
        LinkType.UNKNOWN: "Unknown type. Will attempt to download and detect content type."
    }

    return LinkTypeResponse(
        url=url,
        link_type=link_type,
        description=descriptions.get(link_type, "Unknown type")
    )


@router.get("/status/{call_id}")
async def get_processing_status(
    call_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get the processing status of an external URL submission.
    """
    result = await db.execute(
        select(CallRecording).where(CallRecording.id == call_id)
    )
    call = result.scalar_one_or_none()

    if not call:
        raise HTTPException(status_code=404, detail="Recording not found")

    # Check access
    if call.owner_id != current_user.id and current_user.role.value != "superadmin":
        # Check org membership
        org = await get_user_org(current_user, db)
        if not org or call.org_id != org.id:
            raise HTTPException(status_code=403, detail="Access denied")

    return {
        "id": call.id,
        "status": call.status.value,
        "progress": call.progress or 0,
        "progress_stage": call.progress_stage or "",
        "source_type": call.source_type.value,
        "source_url": call.source_url,
        "title": call.title,
        "transcript_length": len(call.transcript) if call.transcript else 0,
        "has_summary": bool(call.summary),
        "has_key_points": bool(call.key_points),
        "has_action_items": bool(call.action_items),
        "error_message": call.error_message,
        "created_at": call.created_at.isoformat() if call.created_at else None,
        "processed_at": call.processed_at.isoformat() if call.processed_at else None
    }


@router.get("/supported-types")
async def get_supported_types():
    """
    Get list of supported URL types and their handling.
    """
    return {
        "supported_types": [
            {
                "type": "fireflies",
                "name": "Fireflies.ai",
                "description": "Shared transcripts from Fireflies.ai",
                "example": "https://app.fireflies.ai/view/ABC123",
                "handling": "Transcript fetched and analyzed by AI (no transcription needed)",
                "requirements": "Link must be public/shared"
            },
            {
                "type": "google_doc",
                "name": "Google Docs",
                "description": "Documents containing call transcripts",
                "example": "https://docs.google.com/document/d/ABC123/edit",
                "handling": "Parsed as text, directly analyzed by AI (no transcription)",
                "requirements": "Document must be shared as 'Anyone with link can view'"
            },
            {
                "type": "google_sheet",
                "name": "Google Sheets",
                "description": "Spreadsheets with data to analyze",
                "example": "https://docs.google.com/spreadsheets/d/ABC123/edit",
                "handling": "Exported as CSV, directly analyzed by AI",
                "requirements": "Spreadsheet must be shared as 'Anyone with link can view'"
            },
            {
                "type": "google_form",
                "name": "Google Forms",
                "description": "Forms with questions/responses",
                "example": "https://docs.google.com/forms/d/ABC123/viewform",
                "handling": "Parsed for questions/content, analyzed by AI",
                "requirements": "Form must be accessible"
            },
            {
                "type": "google_drive",
                "name": "Google Drive",
                "description": "Audio/video files stored in Google Drive",
                "example": "https://drive.google.com/file/d/ABC123/view",
                "handling": "Downloaded, transcribed via Whisper, then analyzed",
                "requirements": "File must be shared as 'Anyone with link can view'"
            },
            {
                "type": "direct_media",
                "name": "Direct Media URL",
                "description": "Direct links to audio/video files",
                "example": "https://example.com/recording.mp3",
                "handling": "Downloaded, transcribed via Whisper, then analyzed",
                "supported_formats": [".mp3", ".mp4", ".wav", ".m4a", ".webm", ".ogg", ".aac", ".mov", ".mkv"]
            }
        ]
    }
