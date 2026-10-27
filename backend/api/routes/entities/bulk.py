"""
Bulk operations for entities - resume parsing, bulk profile generation.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, File, Form, UploadFile, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel
from pathlib import Path
import uuid
import mimetypes
import re

import aiofiles

from .common import (
    logger, get_db, Entity, EntityType, EntityStatus, Chat, CallRecording, User,
    Department, EntityFile, EntityFileType,
    get_current_user, get_user_org,
    normalize_and_validate_identifiers, broadcast_entity_created,
    limiter, _get_rate_limit_key
)
from .files import ENTITY_FILES_DIR, MAX_FILE_SIZE

router = APIRouter()


# === Resume Parsing API ===

class ParsedResumeResponse(BaseModel):
    """Response with parsed resume data."""
    # Basic data
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    telegram: Optional[str] = None

    # Professional data
    position: Optional[str] = None
    company: Optional[str] = None
    experience_years: Optional[int] = None

    # Salary expectations
    expected_salary_min: Optional[int] = None
    expected_salary_max: Optional[int] = None
    expected_salary_currency: str = "RUB"

    # Skills and education
    skills: List[str] = []
    education: List[dict] = []
    experience: List[dict] = []
    languages: List[dict] = []

    # Additional data
    location: Optional[str] = None
    about: Optional[str] = None
    links: List[str] = []

    # Parsing metadata
    parse_confidence: float = 0.0
    parse_warnings: List[str] = []

    class Config:
        from_attributes = True


class EntityFromResumeResponse(BaseModel):
    """Response when creating Entity from resume."""
    entity: dict  # Created candidate card
    parsed_data: ParsedResumeResponse  # Parsed resume data
    file_id: Optional[int] = None  # ID of attached file


@router.post("/parse-resume", response_model=ParsedResumeResponse)
async def parse_resume(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Parse resume and extract structured data.

    Accepts resume file (PDF, DOC, DOCX) and returns JSON
    with extracted data: name, contacts, skills, experience, etc.

    This endpoint only parses the resume, but does not create a candidate card.
    For creating a card use POST /api/entities/from-resume.
    """
    from ...services.resume_parser import resume_parser_service

    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    # Check file size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            413,
            f"File too large. Maximum size: {MAX_FILE_SIZE // (1024 * 1024)} MB"
        )

    filename = file.filename or "resume"

    # Check file extension
    ext = filename.lower().split('.')[-1] if '.' in filename else ''
    allowed_extensions = {'pdf', 'doc', 'docx', 'txt', 'rtf', 'odt'}
    if ext not in allowed_extensions:
        raise HTTPException(
            400,
            f"Unsupported file format: .{ext}. "
            f"Supported: {', '.join(allowed_extensions)}"
        )

    try:
        # Parse resume
        parsed = await resume_parser_service.parse_resume(content, filename)

        logger.info(
            f"RESUME_PARSE: success | filename='{filename}' | "
            f"name='{parsed.name}' | confidence={parsed.parse_confidence} | "
            f"user_id={current_user.id} | org_id={org.id}"
        )

        return ParsedResumeResponse(
            name=parsed.name,
            phone=parsed.phone,
            email=parsed.email,
            telegram=parsed.telegram,
            position=parsed.position,
            company=parsed.company,
            experience_years=parsed.experience_years,
            expected_salary_min=parsed.expected_salary_min,
            expected_salary_max=parsed.expected_salary_max,
            expected_salary_currency=parsed.expected_salary_currency,
            skills=parsed.skills or [],
            education=parsed.education or [],
            experience=parsed.experience or [],
            languages=parsed.languages or [],
            location=parsed.location,
            about=parsed.about,
            links=parsed.links or [],
            parse_confidence=parsed.parse_confidence,
            parse_warnings=parsed.parse_warnings or []
        )

    except ValueError as e:
        logger.warning(
            f"RESUME_PARSE: failed | filename='{filename}' | "
            f"error='{str(e)}' | user_id={current_user.id}"
        )
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error(
            f"RESUME_PARSE: error | filename='{filename}' | "
            f"error='{str(e)}' | user_id={current_user.id}"
        )
        raise HTTPException(500, f"Resume parsing error: {str(e)}")


@router.post("/from-resume", response_model=EntityFromResumeResponse)
async def create_entity_from_resume(
    file: UploadFile = File(...),
    department_id: Optional[int] = Form(None),
    auto_attach_file: bool = Form(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Parse resume and automatically create candidate card.

    This endpoint:
    1. Parses resume (PDF, DOC, DOCX)
    2. Extracts structured data with AI
    3. Creates Entity of type 'candidate' with filled fields
    4. Optionally attaches original file to the card

    Args:
        file: Resume file
        department_id: Department ID (optional)
        auto_attach_file: Attach file to card (default True)

    Returns:
        Created candidate card and parsed data
    """
    from ...services.resume_parser import resume_parser_service

    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    # Check file size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            413,
            f"File too large. Maximum size: {MAX_FILE_SIZE // (1024 * 1024)} MB"
        )

    filename = file.filename or "resume"

    # Check file extension
    ext = filename.lower().split('.')[-1] if '.' in filename else ''
    allowed_extensions = {'pdf', 'doc', 'docx', 'txt', 'rtf', 'odt', 'html', 'htm', 'zip'}
    if ext not in allowed_extensions:
        raise HTTPException(
            400,
            f"Unsupported file format: .{ext}. "
            f"Supported: {', '.join(allowed_extensions)}"
        )

    # Validate department_id
    department_name = None
    if department_id:
        dept_result = await db.execute(
            select(Department).where(
                Department.id == department_id,
                Department.org_id == org.id
            )
        )
        dept = dept_result.scalar_one_or_none()
        if not dept:
            raise HTTPException(400, "Invalid department")
        department_name = dept.name

    try:
        # Step 1: Parse resume
        parsed = await resume_parser_service.parse_resume(content, filename)

        # Step 2: Convert to Entity data
        entity_data = parsed.to_entity_data()

        # Normalize identifiers
        normalized_usernames, validated_emails, filtered_phones = normalize_and_validate_identifiers(
            telegram_usernames=entity_data.get("telegram_usernames", []),
            emails=entity_data.get("emails", []),
            phones=entity_data.get("phones", [])
        )

        # Step 3: Create Entity
        entity = Entity(
            org_id=org.id,
            type=EntityType.candidate,
            name=entity_data["name"],
            status=EntityStatus.new,
            phone=entity_data.get("phone"),
            email=entity_data.get("email"),
            telegram_usernames=normalized_usernames,
            emails=validated_emails,
            phones=filtered_phones,
            company=entity_data.get("company"),
            position=entity_data.get("position"),
            tags=entity_data.get("tags", []),
            extra_data=entity_data.get("extra_data", {}),
            created_by=current_user.id,
            department_id=department_id,
            expected_salary_min=entity_data.get("expected_salary_min"),
            expected_salary_max=entity_data.get("expected_salary_max"),
            expected_salary_currency=entity_data.get("expected_salary_currency", "RUB")
        )
        db.add(entity)
        await db.flush()  # Get entity ID

        # Step 4: Attach file (if needed)
        file_id = None
        if auto_attach_file:
            # Create directory for files
            entity_dir = ENTITY_FILES_DIR / str(entity.id)
            entity_dir.mkdir(parents=True, exist_ok=True)

            # Generate unique filename
            safe_filename = re.sub(r'[^\w\-\.]', '_', filename)
            unique_name = f"{uuid.uuid4().hex[:8]}_{safe_filename}"
            file_path = entity_dir / unique_name

            # Save file
            async with aiofiles.open(file_path, 'wb') as f:
                await f.write(content)

            # Determine MIME type
            content_type = file.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"

            # Create EntityFile record
            entity_file = EntityFile(
                entity_id=entity.id,
                org_id=org.id,
                file_type=EntityFileType.resume,
                file_name=filename,
                file_path=str(file_path),
                file_size=len(content),
                mime_type=content_type,
                description="Resume (auto-uploaded during parsing)",
                uploaded_by=current_user.id
            )
            db.add(entity_file)
            await db.flush()
            file_id = entity_file.id

        # Теневая дедупликация: сверяем загруженного кандидата с архивом до коммита
        try:
            from ...services.similarity import detect_archived_duplicate
            _hidden_dup = await detect_archived_duplicate(db, entity)
            if _hidden_dup:
                _extra = dict(entity.extra_data or {})
                _extra["hidden_duplicate_id"] = _hidden_dup
                entity.extra_data = _extra
        except Exception:
            import logging
            logging.getLogger("hr-analyzer.bulk").warning(
                "shadow-dedup detect failed (non-critical)", exc_info=True
            )

        # Детектор «копипаст текста резюме» (Feature B) — независим от детектора
        # личности выше. Best-effort: ошибка не должна ломать создание кандидата.
        try:
            from ...services.resume_text_twin import detect_resume_text_twin
            _twin_id, _sim = await detect_resume_text_twin(db, entity)
        except Exception:
            import logging
            logging.getLogger("hr-analyzer.bulk").warning(
                "resume-text-twin detect failed (non-critical)", exc_info=True
            )

        await db.commit()
        await db.refresh(entity)

        # Build response
        entity_response = {
            "id": entity.id,
            "type": entity.type.value if hasattr(entity.type, 'value') else entity.type,
            "name": entity.name,
            "status": entity.status.value if hasattr(entity.status, 'value') else entity.status,
            "phone": entity.phone,
            "email": entity.email,
            "telegram_usernames": entity.telegram_usernames or [],
            "emails": entity.emails or [],
            "phones": entity.phones or [],
            "company": entity.company,
            "position": entity.position,
            "tags": entity.tags or [],
            "extra_data": entity.extra_data or {},
            "created_by": entity.created_by,
            "department_id": entity.department_id,
            "department_name": department_name,
            "created_at": entity.created_at.isoformat() if entity.created_at else None,
            "updated_at": entity.updated_at.isoformat() if entity.updated_at else None,
            "chats_count": 0,
            "calls_count": 0,
            "expected_salary_min": entity.expected_salary_min,
            "expected_salary_max": entity.expected_salary_max,
            "expected_salary_currency": entity.expected_salary_currency or 'RUB',
            "has_hidden_duplicate": bool((entity.extra_data or {}).get("hidden_duplicate_id")),
            "hidden_duplicate_id": (entity.extra_data or {}).get("hidden_duplicate_id"),
        }

        parsed_response = ParsedResumeResponse(
            name=parsed.name,
            phone=parsed.phone,
            email=parsed.email,
            telegram=parsed.telegram,
            position=parsed.position,
            company=parsed.company,
            experience_years=parsed.experience_years,
            expected_salary_min=parsed.expected_salary_min,
            expected_salary_max=parsed.expected_salary_max,
            expected_salary_currency=parsed.expected_salary_currency,
            skills=parsed.skills or [],
            education=parsed.education or [],
            experience=parsed.experience or [],
            languages=parsed.languages or [],
            location=parsed.location,
            about=parsed.about,
            links=parsed.links or [],
            parse_confidence=parsed.parse_confidence,
            parse_warnings=parsed.parse_warnings or []
        )

        logger.info(
            f"ENTITY_FROM_RESUME: success | entity_id={entity.id} | "
            f"name='{entity.name}' | confidence={parsed.parse_confidence} | "
            f"file_attached={file_id is not None} | user_id={current_user.id} | org_id={org.id}"
        )

        # Broadcast entity.created event
        await broadcast_entity_created(org.id, entity_response)

        # Generate AI profile in background (non-blocking)
        try:
            from ...services.entity_profile import entity_profile_service
            # Simple profile from parsed data (no AI call needed)
            simple_profile = {
                "skills": parsed.skills or entity.tags or [],
                "experience_years": parsed.experience_years,
                "level": "unknown",
                "specialization": parsed.position or entity.position or "",
                "salary_min": entity.expected_salary_min,
                "salary_max": entity.expected_salary_max,
                "salary_currency": entity.expected_salary_currency or "RUB",
                "location": parsed.location,
                "work_format": "unknown",
                "languages": parsed.languages or [],
                "education": parsed.education[0] if parsed.education else None,
                "summary": f"{entity.name} - {parsed.position or 'specialist'}",
                "strengths": [],
                "weaknesses": [],
                "red_flags": [],
                "communication_style": "",
                "generated_at": datetime.utcnow().isoformat(),
                "auto_generated": True
            }
            # Реассайн (не in-place) — иначе на уже закоммиченном entity мутация
            # JSON не детектится и профиль не сохраняется.
            entity.extra_data = {**(entity.extra_data or {}), 'ai_profile': simple_profile}
            await db.commit()
        except Exception as profile_err:
            logger.warning(f"Failed to auto-generate profile: {profile_err}")

        return EntityFromResumeResponse(
            entity=entity_response,
            parsed_data=parsed_response,
            file_id=file_id
        )

    except ValueError as e:
        logger.warning(
            f"ENTITY_FROM_RESUME: failed | filename='{filename}' | "
            f"error='{str(e)}' | user_id={current_user.id}"
        )
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error(
            f"ENTITY_FROM_RESUME: error | filename='{filename}' | "
            f"error='{str(e)}' | user_id={current_user.id}"
        )
        await db.rollback()
        raise HTTPException(500, f"Error creating card from resume: {str(e)}")


# === Bulk Profile Generation ===

class BulkProfileResponse(BaseModel):
    """Bulk profile generation response"""
    total_candidates: int
    profiles_generated: int
    profiles_skipped: int
    errors: int


@router.post("/profiles/generate-all", response_model=BulkProfileResponse)
@limiter.limit("1/minute", key_func=_get_rate_limit_key)
async def generate_all_profiles(
    request: Request,
    force_regenerate: bool = Query(default=False, description="Regenerate even if profile exists"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Generate AI profiles for all candidates in the organization.

    This is useful for initial setup or bulk update.
    By default, skips candidates that already have profiles.
    Set force_regenerate=true to regenerate all profiles.

    Note: This uses simple profile generation (from existing data, no AI calls)
    to keep it fast and cheap. For full AI profiles, use the individual endpoint.
    """
    from ...services.entity_profile import entity_profile_service

    request.state._rate_limit_user = current_user
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    # Get all candidates
    candidates_result = await db.execute(
        select(Entity)
        .options(selectinload(Entity.files))
        .where(
            Entity.org_id == org.id,
            Entity.type == EntityType.candidate
        )
    )
    candidates = list(candidates_result.scalars().all())

    total = len(candidates)
    generated = 0
    skipped = 0
    errors = 0

    for candidate in candidates:
        try:
            # Skip if already has profile and not forcing regenerate
            if not force_regenerate and (candidate.extra_data or {}).get('ai_profile'):
                skipped += 1
                continue

            # Load chats for this candidate
            chats_result = await db.execute(
                select(Chat)
                .options(selectinload(Chat.messages))
                .where(Chat.entity_id == candidate.id, Chat.org_id == org.id)
            )
            chats = list(chats_result.scalars().all())

            # Load calls
            calls_result = await db.execute(
                select(CallRecording)
                .where(CallRecording.entity_id == candidate.id, CallRecording.org_id == org.id)
            )
            calls = list(calls_result.scalars().all())

            # Generate full AI profile
            profile = await entity_profile_service.generate_profile(
                entity=candidate,
                chats=chats,
                calls=calls,
                files=candidate.files
            )

            # Store profile. РЕАССАЙН словаря, а не in-place: extra_data — обычный
            # Column(JSON), SQLAlchemy не детектит in-place мутацию → commit молча
            # ничего не сохранял, хотя репортил generated=N.
            candidate.extra_data = {**(candidate.extra_data or {}), 'ai_profile': profile}
            generated += 1

        except Exception as e:
            logger.error(f"Failed to generate profile for entity {candidate.id}: {e}")
            errors += 1

    await db.commit()

    logger.info(f"Bulk profile generation: total={total}, generated={generated}, skipped={skipped}, errors={errors}")

    return BulkProfileResponse(
        total_candidates=total,
        profiles_generated=generated,
        profiles_skipped=skipped,
        errors=errors
    )
