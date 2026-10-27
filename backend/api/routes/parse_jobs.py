"""
API routes for background parsing jobs.
Allows users to start resume parsing without waiting for completion.
"""
import logging
import os
import uuid
import asyncio
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel

from ..services.auth import get_current_user, get_user_org
from ..database import get_db, AsyncSessionLocal
from ..models.database import (
    User, Entity, EntityType, EntityStatus, EntityFile, EntityFileType,
    ParseJob, ParseJobStatus
)
from ..services.parser import parse_resume_from_file, ParsedResume
from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Permanent storage for entity files (same as in files.py)
ENTITY_FILES_DIR = Path(__file__).parent.parent.parent / "uploads" / "entity_files"

router = APIRouter()


async def generate_ai_profile_for_entity(entity_id: int, org_id: int):
    """Generate AI profile for newly created entity from resume."""
    from ..services.entity_profile import entity_profile_service
    from ..models.database import Chat, CallRecording

    async with AsyncSessionLocal() as db:
        try:
            # Load entity with files
            result = await db.execute(
                select(Entity).where(Entity.id == entity_id)
            )
            entity = result.scalar_one_or_none()
            if not entity:
                return

            # Load files
            files_result = await db.execute(
                select(EntityFile).where(EntityFile.entity_id == entity_id)
            )
            files = list(files_result.scalars().all())

            # Load chats (probably empty for new entity)
            chats_result = await db.execute(
                select(Chat).where(Chat.entity_id == entity_id)
            )
            chats = list(chats_result.scalars().all())

            # Load calls (probably empty for new entity)
            calls_result = await db.execute(
                select(CallRecording).where(CallRecording.entity_id == entity_id)
            )
            calls = list(calls_result.scalars().all())

            # Generate profile
            profile = await entity_profile_service.generate_profile(
                entity=entity,
                chats=chats,
                calls=calls,
                files=files
            )

            # Store in entity.extra_data
            if not entity.extra_data:
                entity.extra_data = {}
            entity.extra_data['ai_profile'] = profile

            await db.commit()
            logger.info(f"Generated AI profile for entity {entity_id}")

        except Exception as e:
            logger.error(f"Error generating AI profile for entity {entity_id}: {e}")


# Pydantic models for responses
class ParseJobResponse(BaseModel):
    id: int
    status: str
    file_name: str
    progress: int
    progress_stage: Optional[str]
    entity_id: Optional[int]
    entity_name: Optional[str]
    error_message: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


class ParseJobCreateResponse(BaseModel):
    job_id: int
    message: str


class ParseJobsListResponse(BaseModel):
    jobs: List[ParseJobResponse]
    total: int
    pending_count: int
    processing_count: int


# Background processing function
async def process_parse_job(job_id: int):
    """Background task to process a parsing job."""
    async with AsyncSessionLocal() as db:
        try:
            # Get the job
            result = await db.execute(
                select(ParseJob).where(ParseJob.id == job_id)
            )
            job = result.scalar_one_or_none()
            if not job:
                logger.error(f"ParseJob {job_id} not found")
                return

            # Update status to processing
            job.status = ParseJobStatus.processing
            job.started_at = datetime.utcnow()
            job.progress = 10
            job.progress_stage = "Чтение файла"
            await db.commit()

            # Read file content
            if not os.path.exists(job.file_path):
                raise FileNotFoundError(f"File not found: {job.file_path}")

            with open(job.file_path, 'rb') as f:
                file_content = f.read()

            # Update progress
            job.progress = 30
            job.progress_stage = "Извлечение текста"
            await db.commit()

            # Parse the resume
            job.progress = 50
            job.progress_stage = "AI анализ резюме"
            await db.commit()

            resume = await parse_resume_from_file(file_content, job.file_name)

            # Update progress
            job.progress = 80
            job.progress_stage = "Создание контакта"
            await db.commit()

            # Create entity
            entity_name = resume.name or f"Кандидат из {job.file_name}"

            # Build extra_data from parsed resume
            extra_data = {}
            if resume.skills:
                extra_data["skills"] = resume.skills
            if resume.experience:
                extra_data["experience"] = [
                    {
                        "company": exp.company if hasattr(exp, 'company') else exp.get('company'),
                        "position": exp.position if hasattr(exp, 'position') else exp.get('position'),
                        "start_date": exp.start_date if hasattr(exp, 'start_date') else exp.get('start_date'),
                        "end_date": exp.end_date if hasattr(exp, 'end_date') else exp.get('end_date'),
                        "description": exp.description if hasattr(exp, 'description') else exp.get('description'),
                    }
                    for exp in resume.experience
                ]
            if resume.education:
                extra_data["education"] = [
                    {
                        "institution": edu.institution if hasattr(edu, 'institution') else edu.get('institution'),
                        "degree": edu.degree if hasattr(edu, 'degree') else edu.get('degree'),
                        "field": edu.field if hasattr(edu, 'field') else edu.get('field'),
                        "year": edu.year if hasattr(edu, 'year') else edu.get('year'),
                    }
                    for edu in resume.education
                ]
            if resume.languages:
                extra_data["languages"] = resume.languages
            if resume.summary:
                extra_data["summary"] = resume.summary
            if resume.location:
                extra_data["location"] = resume.location
            if resume.experience_years:
                extra_data["experience_years"] = resume.experience_years

            entity = Entity(
                name=entity_name,
                type=EntityType.candidate,
                status=EntityStatus.new,
                email=resume.email,
                phone=resume.phone,
                company=resume.experience[0].company if resume.experience and hasattr(resume.experience[0], 'company') else (
                    resume.experience[0].get('company') if resume.experience else None
                ),
                position=resume.position or (
                    resume.experience[0].position if resume.experience and hasattr(resume.experience[0], 'position') else (
                        resume.experience[0].get('position') if resume.experience else None
                    )
                ),
                tags=resume.skills[:10] if resume.skills else [],
                extra_data=extra_data,
                org_id=job.org_id,
                created_by=job.user_id,
                expected_salary_min=resume.salary_min,
                expected_salary_max=resume.salary_max,
                expected_salary_currency=resume.salary_currency or 'RUB',
                is_archived=True,  # bulk-парсер (async job) → теневая база (архив)
            )

            # Handle telegram
            if resume.telegram:
                tg = resume.telegram.lstrip('@').lower()
                entity.telegram_usernames = [tg]

            db.add(entity)
            await db.flush()

            # Move file from temp to permanent storage
            entity_files_dir = ENTITY_FILES_DIR / str(entity.id)
            entity_files_dir.mkdir(parents=True, exist_ok=True)

            # Generate unique filename
            file_extension = Path(job.file_name.lower()).suffix or '.pdf'
            unique_filename = f"{uuid.uuid4().hex}{file_extension}"
            permanent_path = entity_files_dir / unique_filename

            # Copy file to permanent location (keep original for now)
            shutil.copy2(job.file_path, permanent_path)
            logger.info(f"Copied resume file to permanent storage: {permanent_path}")

            # Содержимое также в БД (bytea): прод-диск эфемерный, иначе резюме
            # теряется при редеплое (download → 410 file_content_lost).
            try:
                resume_bytes = permanent_path.read_bytes()
            except Exception:
                resume_bytes = None

            # Determine MIME type based on file extension
            mime_types = {
                '.pdf': 'application/pdf',
                '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                '.doc': 'application/msword',
                '.txt': 'text/plain',
                '.rtf': 'application/rtf',
            }
            mime_type = mime_types.get(file_extension, 'application/octet-stream')

            # Attach file to entity with permanent path
            entity_file = EntityFile(
                entity_id=entity.id,
                org_id=job.org_id,
                file_type=EntityFileType.resume,
                file_name=job.file_name,
                file_path=str(permanent_path),
                file_data=resume_bytes,
                file_size=job.file_size,
                mime_type=mime_type,
                uploaded_by=job.user_id,
            )
            db.add(entity_file)

            # Update job as completed
            job.status = ParseJobStatus.completed
            job.completed_at = datetime.utcnow()
            job.progress = 100
            job.progress_stage = "Завершено"
            job.entity_id = entity.id

            await db.commit()
            logger.info(f"ParseJob {job_id} completed, created entity {entity.id}")

            # Generate AI profile in background (non-blocking)
            try:
                await generate_ai_profile_for_entity(entity.id, job.org_id)
            except Exception as profile_error:
                logger.warning(f"Failed to generate AI profile for entity {entity.id}: {profile_error}")

            # Clean up temp file after successful commit
            try:
                if os.path.exists(job.file_path):
                    os.remove(job.file_path)
                    logger.debug(f"Removed temp file: {job.file_path}")
            except Exception as cleanup_error:
                logger.warning(f"Failed to remove temp file {job.file_path}: {cleanup_error}")

        except Exception as e:
            logger.error(f"ParseJob {job_id} failed: {e}")
            # Update job as failed
            try:
                async with AsyncSessionLocal() as error_db:
                    await error_db.execute(
                        update(ParseJob)
                        .where(ParseJob.id == job_id)
                        .values(
                            status=ParseJobStatus.failed,
                            error_message=str(e)[:500],
                            completed_at=datetime.utcnow(),
                            progress_stage="Ошибка"
                        )
                    )
                    await error_db.commit()
            except Exception as update_error:
                logger.error(f"Failed to update job status: {update_error}")


@router.post("/start", response_model=ParseJobCreateResponse)
async def start_parse_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Start a background parsing job for a resume file.

    Returns immediately with job_id. Use /jobs/{job_id} to check status.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="File is required")

    # Check file type
    allowed_extensions = {'pdf', 'docx', 'doc', 'txt', 'rtf'}
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format: {ext}. Allowed: {', '.join(sorted(allowed_extensions))}"
        )

    # Read file content
    file_content = await file.read()
    if not file_content:
        raise HTTPException(status_code=400, detail="File is empty")

    # Check file size (max 20MB)
    max_size = 20 * 1024 * 1024
    if len(file_content) > max_size:
        raise HTTPException(
            status_code=400,
            detail=f"File too large: {len(file_content) / 1024 / 1024:.1f}MB (max 20MB)"
        )

    # Get user's organization
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=403, detail="No organization access")

    # Save file temporarily
    upload_dir = settings.upload_dir if hasattr(settings, 'upload_dir') else '/tmp/hr_uploads'
    os.makedirs(upload_dir, exist_ok=True)
    temp_filename = f"{uuid.uuid4()}_{file.filename}"
    temp_path = os.path.join(upload_dir, temp_filename)

    with open(temp_path, 'wb') as f:
        f.write(file_content)

    # Create job record
    job = ParseJob(
        org_id=org.id,
        user_id=current_user.id,
        status=ParseJobStatus.pending,
        file_name=file.filename,
        file_path=temp_path,
        file_size=len(file_content),
        progress=0,
        progress_stage="В очереди"
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Start background processing
    background_tasks.add_task(process_parse_job, job.id)

    logger.info(f"ParseJob {job.id} created for user {current_user.id}, file: {file.filename}")

    return ParseJobCreateResponse(
        job_id=job.id,
        message="Парсинг запущен"
    )


@router.get("", response_model=ParseJobsListResponse)
async def get_parse_jobs(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get list of parsing jobs for current user.
    """
    # Build query
    query = select(ParseJob).where(ParseJob.user_id == current_user.id)

    if status:
        try:
            status_enum = ParseJobStatus(status)
            query = query.where(ParseJob.status == status_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    # Get total count
    count_query = select(ParseJob).where(ParseJob.user_id == current_user.id)
    result = await db.execute(count_query)
    total = len(result.all())

    # Get pending/processing counts
    pending_result = await db.execute(
        select(ParseJob).where(
            ParseJob.user_id == current_user.id,
            ParseJob.status == ParseJobStatus.pending
        )
    )
    pending_count = len(pending_result.all())

    processing_result = await db.execute(
        select(ParseJob).where(
            ParseJob.user_id == current_user.id,
            ParseJob.status == ParseJobStatus.processing
        )
    )
    processing_count = len(processing_result.all())

    # Get jobs with pagination
    query = query.order_by(ParseJob.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    jobs = result.scalars().all()

    # Build response with entity names
    job_responses = []
    for job in jobs:
        entity_name = None
        if job.entity_id:
            entity_result = await db.execute(
                select(Entity.name).where(Entity.id == job.entity_id)
            )
            entity_name = entity_result.scalar_one_or_none()

        job_responses.append(ParseJobResponse(
            id=job.id,
            status=job.status.value,
            file_name=job.file_name,
            progress=job.progress or 0,
            progress_stage=job.progress_stage,
            entity_id=job.entity_id,
            entity_name=entity_name,
            error_message=job.error_message,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
        ))

    return ParseJobsListResponse(
        jobs=job_responses,
        total=total,
        pending_count=pending_count,
        processing_count=processing_count,
    )


@router.get("/{job_id}", response_model=ParseJobResponse)
async def get_parse_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get status of a specific parsing job.
    """
    result = await db.execute(
        select(ParseJob).where(
            ParseJob.id == job_id,
            ParseJob.user_id == current_user.id
        )
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Get entity name if completed
    entity_name = None
    if job.entity_id:
        entity_result = await db.execute(
            select(Entity.name).where(Entity.id == job.entity_id)
        )
        entity_name = entity_result.scalar_one_or_none()

    return ParseJobResponse(
        id=job.id,
        status=job.status.value,
        file_name=job.file_name,
        progress=job.progress or 0,
        progress_stage=job.progress_stage,
        entity_id=job.entity_id,
        entity_name=entity_name,
        error_message=job.error_message,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


@router.delete("/{job_id}")
async def cancel_parse_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Cancel a pending parsing job.
    Only pending jobs can be cancelled.
    """
    result = await db.execute(
        select(ParseJob).where(
            ParseJob.id == job_id,
            ParseJob.user_id == current_user.id
        )
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != ParseJobStatus.pending:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel job with status: {job.status.value}"
        )

    # Delete temp file
    if job.file_path and os.path.exists(job.file_path):
        try:
            os.remove(job.file_path)
        except Exception as e:
            logger.warning(f"Failed to delete temp file: {e}")

    # Delete job
    await db.delete(job)
    await db.commit()

    return {"success": True, "message": "Job cancelled"}
