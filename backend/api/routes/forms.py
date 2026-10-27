"""
API routes for form constructor — create custom forms, public submission by candidates.
"""
import os
import re
import secrets
import uuid
import json
import mimetypes
import logging
from typing import Optional, List
from datetime import datetime
from pathlib import Path

from anthropic import AsyncAnthropic
import asyncio
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, File, Form, Request, Response, UploadFile
from sqlalchemy import select, func, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from ..config import get_settings
from ..database import get_db
from ..limiter import PUBLIC_PAGE_LIMIT, PUBLIC_REPORT_LIMIT, PUBLIC_SUBMIT_LIMIT, limiter
from ..models.database import (
    FormTemplate, FormSubmission, FormVacancy, FormDispatch,
    Entity, EntityFile, EntityFileType, AccessLevel,
    Vacancy, User, UserRole, Organization, OrgMember
)
from ..services.auth import get_current_user, get_current_user_optional, get_user_org
from ..services.form_answers import (
    AnswerError, answer_fields, clean_answers, field_labels, form_problem, required_problem,
)
from .entities.common import check_entity_access

# File upload settings for public forms
ENTITY_FILES_DIR = Path(__file__).parent.parent.parent / "uploads" / "entity_files"
PUBLIC_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB per file (документы/картинки)
PUBLIC_MAX_VIDEO_SIZE = 100 * 1024 * 1024  # 100MB для видео (MP4/MOV/AVI)
# ВНИМАНИЕ: файлы читаются целиком в память и хранятся в БД (bytea — диск на
# проде эфемерный, теряется при редеплое). Видео тяжёлые → лимит жёсткий,
# чтобы не ловить OOM и не раздувать БД. Для больших видео нужен S3 (отдельно).
PUBLIC_MAX_FILES = 5  # Max files per public form submission
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi"}
ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png", ".webp"} | VIDEO_EXTENSIONS
PDF_RENDER_DPI = 200

logger = logging.getLogger("hr-analyzer.forms")

router = APIRouter()


# ============================================================
# Pydantic schemas
# ============================================================

class FormFieldSchema(BaseModel):
    id: str
    type: str  # text, email, phone, textarea, select, multiselect, radio, file, url, scale, date
    label: str
    required: bool = False
    placeholder: Optional[str] = None
    options: Optional[List[str]] = None
    min: Optional[int] = None   # for scale type
    max: Optional[int] = None   # for scale type


class FormCreateSchema(BaseModel):
    title: str
    description: Optional[str] = None
    vacancy_id: Optional[int] = None
    vacancy_ids: Optional[List[int]] = None
    fields: List[FormFieldSchema] = []
    is_active: bool = True
    is_template: bool = False


class FormUpdateSchema(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    vacancy_id: Optional[int] = None
    vacancy_ids: Optional[List[int]] = None
    fields: Optional[List[FormFieldSchema]] = None
    is_active: Optional[bool] = None
    is_template: Optional[bool] = None


class PublicSubmitSchema(BaseModel):
    data: dict  # {field_id: value}


class DispatchCreateSchema(BaseModel):
    entity_id: int


class AIChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class AIChatSchema(BaseModel):
    entity_id: int
    messages: List[AIChatMessage]


# ============================================================
# Helpers
# ============================================================

# Transliteration map for Russian to Latin
_TRANSLIT = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
}


def generate_slug(title: str) -> str:
    """Generate URL-friendly slug from title (supports Russian)."""
    text = title.lower().strip()
    # Transliterate Russian characters
    result = []
    for char in text:
        if char in _TRANSLIT:
            result.append(_TRANSLIT[char])
        # Пробел сюда не входит — он становится дефисом ниже (до 20.10.2026 он
        # проходил этой веткой, и адрес выходил «novaya anketa-…» с пробелом).
        elif char.isascii() and (char.isalnum() or char in ('-', '_')):
            result.append(char)
        elif char == ' ':
            result.append('-')
        else:
            result.append('')
    slug = ''.join(result)
    # Collapse multiple hyphens
    slug = re.sub(r'-+', '-', slug).strip('-')
    # Add short unique suffix to avoid collisions
    suffix = uuid.uuid4().hex[:6]
    return f"{slug}-{suffix}" if slug else suffix


# ============================================================
# Authenticated routes — CRUD for form templates
# ============================================================

async def _own_vacancy_ids(db: AsyncSession, org_id: int, ids: List[int]) -> List[int]:
    """Воронки анкеты — только этого орга, без повторов, порядок как прислали.

    Несуществующий id раньше давал 500 (внешний ключ), чужой — молча
    привязывался (20.10.2026).
    """
    wanted = [int(v) for v in dict.fromkeys(ids or []) if v]
    if not wanted:
        return []
    own = set((await db.execute(
        select(Vacancy.id).where(Vacancy.id.in_(wanted), Vacancy.org_id == org_id)
    )).scalars().all())
    return [v for v in wanted if v in own]


@router.get("")
async def list_forms(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List forms created by current user (or all for superadmin)."""
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)

    query = select(FormTemplate)

    if current_user.role == UserRole.superadmin:
        # Superadmin sees all
        pass
    elif org:
        query = query.where(FormTemplate.org_id == org.id)
    else:
        query = query.where(FormTemplate.created_by == current_user.id)

    query = query.order_by(FormTemplate.created_at.desc())
    result = await db.execute(query)
    forms = result.scalars().all()

    # Get submission counts
    form_ids = [f.id for f in forms]
    counts = {}
    fv_map = {}  # form_id -> [vacancy_ids]
    if form_ids:
        count_result = await db.execute(
            select(FormSubmission.form_id, func.count(FormSubmission.id))
            .where(FormSubmission.form_id.in_(form_ids))
            .group_by(FormSubmission.form_id)
        )
        counts = dict(count_result.all())

        # Get vacancy_ids for each form via junction table
        fv_result = await db.execute(
            select(FormVacancy.form_id, FormVacancy.vacancy_id)
            .where(FormVacancy.form_id.in_(form_ids))
        )
        for fid, vid in fv_result.all():
            fv_map.setdefault(fid, []).append(vid)

    return [
        {
            "id": f.id,
            "title": f.title,
            "description": f.description,
            "slug": f.slug,
            "vacancy_id": f.vacancy_id,
            "vacancy_ids": fv_map.get(f.id, [f.vacancy_id] if f.vacancy_id else []),
            "is_active": f.is_active,
            "is_template": f.is_template,
            "fields": f.fields or [],
            "submissions_count": counts.get(f.id, 0),
            "created_at": f.created_at.isoformat() if f.created_at else None,
            "updated_at": f.updated_at.isoformat() if f.updated_at else None,
            "created_by": f.created_by,
        }
        for f in forms
    ]


@router.post("")
async def create_form(
    body: FormCreateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new form template."""
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=400, detail="User has no organization")

    slug = generate_slug(body.title)

    # Resolve vacancy_ids from both legacy and new fields
    vacancy_ids = await _own_vacancy_ids(db, org.id, body.vacancy_ids or ([body.vacancy_id] if body.vacancy_id else []))

    form = FormTemplate(
        org_id=org.id,
        vacancy_id=vacancy_ids[0] if vacancy_ids else None,  # legacy compat
        created_by=current_user.id,
        title=body.title,
        description=body.description,
        slug=slug,
        is_active=body.is_active,
        is_template=body.is_template,
        fields=[f.model_dump() for f in body.fields],
    )
    db.add(form)
    await db.flush()

    # Create many-to-many links
    for vid in vacancy_ids:
        db.add(FormVacancy(form_id=form.id, vacancy_id=vid))

    await db.commit()
    await db.refresh(form)

    return {
        "id": form.id,
        "title": form.title,
        "description": form.description,
        "slug": form.slug,
        "vacancy_id": form.vacancy_id,
        "vacancy_ids": vacancy_ids,
        "is_active": form.is_active,
        "is_template": form.is_template,
        "fields": form.fields or [],
        "submissions_count": 0,
        "created_at": form.created_at.isoformat() if form.created_at else None,
        "updated_at": form.updated_at.isoformat() if form.updated_at else None,
        "created_by": form.created_by,
    }


@router.get("/templates")
async def get_form_templates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return all org-scoped form templates (is_template=True)."""
    org = await get_user_org(current_user, db)
    if not org:
        return []
    result = await db.execute(
        select(FormTemplate)
        .where(FormTemplate.org_id == org.id)
        .where(FormTemplate.is_template == True)  # noqa: E712
        .order_by(FormTemplate.created_at.desc())
    )
    forms = result.scalars().all()
    form_ids = [f.id for f in forms]
    # Воронки шаблона (junction) — чтобы фронт показывал шаблон в нужной воронке.
    fv_map: dict[int, list[int]] = {}
    if form_ids:
        fv_rows = await db.execute(
            select(FormVacancy.form_id, FormVacancy.vacancy_id)
            .where(FormVacancy.form_id.in_(form_ids))
        )
        for fid, vid in fv_rows.all():
            fv_map.setdefault(fid, []).append(vid)
    # Кол-во ответов по шаблону: раз «Использовать» теперь шлёт FormDispatch
    # напрямую на шаблон (без клона), удаление шаблона каскадно стирает ВСЕ
    # ответы всех кандидатов, кто по нему отвечал — фронту нужно это число,
    # чтобы предупредить/заблокировать удаление шаблона с ответами.
    submissions_map: dict[int, int] = {}
    if form_ids:
        sub_rows = await db.execute(
            select(FormSubmission.form_id, func.count(FormSubmission.id))
            .where(FormSubmission.form_id.in_(form_ids))
            .group_by(FormSubmission.form_id)
        )
        submissions_map = {fid: count for fid, count in sub_rows.all()}
    return [
        {
            "id": f.id,
            "title": f.title,
            "description": f.description,
            "fields": f.fields or [],
            "is_template": True,
            "is_active": f.is_active is not False,
            "vacancy_ids": fv_map.get(f.id, [f.vacancy_id] if f.vacancy_id else []),
            "submissions_count": submissions_map.get(f.id, 0),
            "created_at": f.created_at.isoformat() if f.created_at else None,
        }
        for f in forms
    ]


@router.post("/ai-chat")
async def ai_form_chat(
    body: AIChatSchema,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Multi-turn AI dialogue for building a form questionnaire.
    Supports PDF (text extraction) and image resumes (Claude vision API).
    """
    import base64 as _b64
    import io as _io

    # Резюме кандидата уходит в Claude — только своего орга и в своём скоупе
    # (до 20.10.2026 проверки не было: по чужому entity_id резюме читалось).
    current_user = await db.merge(current_user)
    await _assert_entity_access(body.entity_id, current_user, db)

    cfg = get_settings()
    api_key = (
        os.environ.get("ANTHROPIC_API_KEY_FORMS")
        or cfg.anthropic_api_key_forms
        or os.environ.get("ANTHROPIC_API_KEY")
        or cfg.anthropic_api_key
    )
    if not api_key:
        raise HTTPException(status_code=503, detail="AI service not configured: ANTHROPIC_API_KEY_FORMS not set")

    # --- Fetch ALL resume files for this entity ---
    res = await db.execute(
        select(EntityFile)
        .where(EntityFile.entity_id == body.entity_id)
        .where(EntityFile.file_type == EntityFileType.resume)
        .order_by(EntityFile.created_at.asc())
    )
    resume_files = res.scalars().all()

    if not resume_files:
        res = await db.execute(
            select(EntityFile)
            .where(EntityFile.entity_id == body.entity_id)
            .order_by(EntityFile.created_at.desc())
            .limit(5)
        )
        resume_files = res.scalars().all()

    has_resume = bool(resume_files)

    # --- Process each file: extract text (PDF) or prepare vision block (image) ---
    pdf_texts: list[str] = []
    image_blocks: list[dict] = []

    for rf in resume_files:
        if not rf.file_data:
            continue
        fname = (rf.file_name or "").lower()
        mime = (rf.mime_type or "").lower()
        magic = rf.file_data[:4]

        is_pdf = "pdf" in mime or fname.endswith(".pdf") or magic == b"%PDF"
        is_img = any(t in mime for t in ("jpeg", "jpg", "png", "webp", "gif")) or \
                 any(fname.endswith(e) for e in (".jpg", ".jpeg", ".png", ".webp"))

        if is_pdf:
            text = ""
            # Try pdfplumber first
            try:
                import pdfplumber
                with pdfplumber.open(_io.BytesIO(rf.file_data)) as doc:
                    text = "\n\n".join(p.extract_text() or "" for p in doc.pages).strip()
            except Exception as e:
                logger.warning("pdfplumber failed for %s: %s", rf.file_name, e)

            # Fallback to PyMuPDF
            if not text:
                try:
                    import fitz
                    doc = fitz.open(stream=_io.BytesIO(rf.file_data), filetype="pdf")
                    text = "\n\n".join(doc[i].get_text() for i in range(doc.page_count)).strip()
                except Exception as e:
                    logger.warning("fitz text extraction failed for %s: %s", rf.file_name, e)

            if text:
                pdf_texts.append(text[:4000])
            else:
                # Scanned PDF — render pages as images for vision
                try:
                    import fitz
                    doc = fitz.open(stream=_io.BytesIO(rf.file_data), filetype="pdf")
                    for i in range(min(doc.page_count, 3)):
                        pix = doc[i].get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
                        img_bytes = pix.tobytes("png")
                        image_blocks.append({
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": _b64.b64encode(img_bytes).decode(),
                            },
                        })
                except Exception as e:
                    logger.warning("PDF page render failed for %s: %s", rf.file_name, e)

        elif is_img:
            if len(rf.file_data) > 4 * 1024 * 1024:
                logger.warning("Image too large, skipping vision for %s", rf.file_name)
                continue
            img_mime = (
                "image/png" if ("png" in mime or fname.endswith(".png")) else
                "image/webp" if "webp" in mime else
                "image/gif" if "gif" in mime else
                "image/jpeg"
            )
            image_blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": img_mime,
                    "data": _b64.b64encode(rf.file_data).decode(),
                },
            })

    # --- System prompt ---
    resume_text_ctx = "\n\n---\n\n".join(pdf_texts)
    system_prompt = "Ты — ассистент HR-рекрутера. Ведёшь диалог, помогая создать персональную анкету для кандидата."

    if resume_text_ctx:
        system_prompt += f"\n\n=== РЕЗЮМЕ КАНДИДАТА (текст) ===\n{resume_text_ctx[:6000]}\n=== КОНЕЦ РЕЗЮМЕ ==="
    elif not image_blocks:
        system_prompt += "\n\nРезюме кандидата не загружено — ориентируйся на информацию от рекрутера."

    system_prompt += """

В каждом сообщении:
- Кратко объясняй свои предложения (1–3 предложения)
- Если готовая анкета есть — выводи её В КОНЦЕ ответа в блоке:
---ANKETA---
[{"type":"text","label":"ФИО","required":true}, ...]
---END---

Правила анкеты:
- Первое поле всегда: {"type":"text","label":"ФИО","required":true}
- 4–8 вопросов, релевантных опыту кандидата
- Типы: text, email, phone, textarea, select, multiselect, radio, scale, file, url
- select/multiselect/radio → обязательно поле options (массив строк ≥ 2)
- scale → поля min и max (обычно 1 и 10)
- Все тексты на русском

Если анкета ещё не готова — просто общайся, уточняй."""

    # --- Build message list for Claude ---
    messages = [{"role": m.role, "content": m.content} for m in body.messages]

    if not messages:
        # First turn: inject images (if any) + text prompt
        content: list[dict] = list(image_blocks)
        if image_blocks and not resume_text_ctx:
            prompt = "Это страницы резюме кандидата. Проанализируй их и предложи анкету для собеседования."
        else:
            prompt = "Проанализируй резюме кандидата и предложи подходящую анкету."
        content.append({"type": "text", "text": prompt})
        messages = [{"role": "user", "content": content}]
    else:
        # Subsequent turns: Claude API requires first message to be from user
        if messages[0]["role"] == "assistant":
            messages = [{"role": "user", "content": "Продолжи работу над анкетой."}] + messages

    client = AsyncAnthropic(api_key=api_key)
    response = await client.messages.create(
        model=cfg.claude_model,
        max_tokens=2048,
        system=system_prompt,
        messages=messages,
    )

    raw = response.content[0].text.strip()

    # Parse ---ANKETA--- block
    fields = None
    message_text = raw
    if "---ANKETA---" in raw and "---END---" in raw:
        parts = raw.split("---ANKETA---", 1)
        message_text = parts[0].strip()
        json_part = parts[1].split("---END---", 1)[0].strip()
        try:
            parsed = json.loads(json_part)
            if isinstance(parsed, list) and parsed:
                fields = parsed
        except Exception as e:
            logger.warning("ai-chat: failed to parse fields: %s | %.200s", e, json_part)

    return {"message": message_text, "fields": fields, "has_resume": has_resume}


@router.get("/{form_id}")
async def get_form(
    form_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get form template with submission count."""
    current_user = await db.merge(current_user)
    result = await db.execute(select(FormTemplate).where(FormTemplate.id == form_id))
    form = result.scalar_one_or_none()
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")

    # Check access
    org = await get_user_org(current_user, db)
    if current_user.role != UserRole.superadmin:
        if not org or form.org_id != org.id:
            raise HTTPException(status_code=403, detail="Access denied")

    count_result = await db.execute(
        select(func.count(FormSubmission.id)).where(FormSubmission.form_id == form.id)
    )
    submissions_count = count_result.scalar() or 0

    # Get vacancy_ids from junction table
    fv_result = await db.execute(
        select(FormVacancy.vacancy_id).where(FormVacancy.form_id == form.id)
    )
    vacancy_ids = [row[0] for row in fv_result.all()]
    if not vacancy_ids and form.vacancy_id:
        vacancy_ids = [form.vacancy_id]

    return {
        "id": form.id,
        "title": form.title,
        "description": form.description,
        "slug": form.slug,
        "vacancy_id": form.vacancy_id,
        "vacancy_ids": vacancy_ids,
        "is_active": form.is_active,
        "is_template": form.is_template,
        "fields": form.fields or [],
        "submissions_count": submissions_count,
        "created_at": form.created_at.isoformat() if form.created_at else None,
        "updated_at": form.updated_at.isoformat() if form.updated_at else None,
        "created_by": form.created_by,
    }


@router.put("/{form_id}")
async def update_form(
    form_id: int,
    body: FormUpdateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update form template."""
    current_user = await db.merge(current_user)
    result = await db.execute(select(FormTemplate).where(FormTemplate.id == form_id))
    form = result.scalar_one_or_none()
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")

    org = await get_user_org(current_user, db)
    if current_user.role != UserRole.superadmin:
        if not org or form.org_id != org.id:
            raise HTTPException(status_code=403, detail="Access denied")

    # Жёсткая защита от дублей названия — но только для ШАБЛОНОВ (библиотека
    # переиспользуемых анкет в «Анкеты»): разовые анкеты «с нуля»/AI-чат
    # автосохраняются под общим дефолтным названием («Анкета», «AI-анкета»)
    # до того, как их переименуют, — блокировать это было бы багом, а не
    # защитой.
    # ВАЖНО: проверяем дубль ТОЛЬКО когда название реально меняется в этом
    # запросе, либо анкета только что становится шаблоном (was False -> True).
    # Иначе обычное сохранение УЖЕ существующего шаблона (правка полей,
    # is_active и т.п., имя не трогали) навсегда блокировалось бы 409, если
    # где-то в органе уже случайно есть тёзка — а такие тёзки уже были в
    # проде («Трафик» x2) ДО этой защиты, и их правка должна продолжать
    # работать, а не намертво зависать из-за старого дубля.
    was_template = form.is_template
    now_template = body.is_template if body.is_template is not None else form.is_template
    new_title = body.title if body.title is not None else form.title
    title_changed = (
        body.title is not None
        and body.title.strip().lower() != (form.title or "").strip().lower()
    )
    newly_became_template = now_template and not was_template
    if now_template and new_title and (title_changed or newly_became_template):
        normalized = new_title.strip().lower()
        dup_result = await db.execute(
            select(FormTemplate.id).where(
                FormTemplate.id != form.id,
                FormTemplate.org_id == form.org_id,
                FormTemplate.is_template == True,  # noqa: E712
                func.lower(func.trim(FormTemplate.title)) == normalized,
            )
        )
        if dup_result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=409,
                detail=f"Шаблон с названием «{new_title.strip()}» уже существует — выберите другое название",
            )

    if body.title is not None:
        form.title = body.title
    if body.description is not None:
        form.description = body.description
    if body.fields is not None:
        form.fields = [f.model_dump() for f in body.fields]
    if body.is_active is not None:
        form.is_active = body.is_active
    if body.is_template is not None:
        form.is_template = body.is_template

    # Handle multi-vacancy update
    vacancy_ids = None
    if body.vacancy_ids is not None:
        vacancy_ids = body.vacancy_ids
    elif body.vacancy_id is not None:
        vacancy_ids = [body.vacancy_id] if body.vacancy_id else []

    if vacancy_ids is not None:
        vacancy_ids = await _own_vacancy_ids(db, form.org_id, vacancy_ids)
        form.vacancy_id = vacancy_ids[0] if vacancy_ids else None  # legacy compat
        # Replace junction table entries
        await db.execute(delete(FormVacancy).where(FormVacancy.form_id == form.id))
        for vid in vacancy_ids:
            db.add(FormVacancy(form_id=form.id, vacancy_id=vid))

    await db.commit()
    await db.refresh(form)

    # Get current vacancy_ids
    fv_result = await db.execute(
        select(FormVacancy.vacancy_id).where(FormVacancy.form_id == form.id)
    )
    current_vacancy_ids = [row[0] for row in fv_result.all()]

    count_result = await db.execute(
        select(func.count(FormSubmission.id)).where(FormSubmission.form_id == form.id)
    )
    submissions_count = count_result.scalar() or 0

    return {
        "id": form.id,
        "title": form.title,
        "description": form.description,
        "slug": form.slug,
        "vacancy_id": form.vacancy_id,
        "vacancy_ids": current_vacancy_ids,
        "is_active": form.is_active,
        "is_template": form.is_template,
        "fields": form.fields or [],
        "submissions_count": submissions_count,
        "created_at": form.created_at.isoformat() if form.created_at else None,
        "updated_at": form.updated_at.isoformat() if form.updated_at else None,
        "created_by": form.created_by,
    }


@router.delete("/{form_id}")
async def delete_form(
    form_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete form template."""
    current_user = await db.merge(current_user)
    result = await db.execute(select(FormTemplate).where(FormTemplate.id == form_id))
    form = result.scalar_one_or_none()
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")

    org = await get_user_org(current_user, db)
    if current_user.role != UserRole.superadmin:
        if not org or form.org_id != org.id:
            raise HTTPException(status_code=403, detail="Access denied")
        # Удаляет автор или админ — как с кандидатами. Раньше любой рекрутёр
        # мог стереть чужой шаблон (20.10.2026).
        if form.created_by != current_user.id and not await _is_org_admin(current_user, org, db):
            raise HTTPException(status_code=403, detail="Удалить анкету может её автор или администратор")

    # Удаление каскадом стирает ответы ВСЕХ кандидатов по этой анкете. Фронт
    # такую кнопку прятал, сервер — нет: прямой запрос стирал ответы молча.
    answered = (await db.execute(
        select(func.count(FormSubmission.id)).where(FormSubmission.form_id == form.id)
    )).scalar() or 0
    if answered:
        raise HTTPException(
            status_code=409,
            detail=f"По анкете уже есть ответы ({answered}) — удаление сотрёт их. Сделайте её неактивной вместо удаления.",
        )

    await db.delete(form)
    await db.commit()
    return {"ok": True}


async def _is_org_admin(user: User, org: Organization, db: AsyncSession) -> bool:
    from ..models.database import OrgRole
    if user.role == UserRole.superadmin:
        return True
    om = (await db.execute(
        select(OrgMember).where(OrgMember.org_id == org.id, OrgMember.user_id == user.id)
    )).scalar_one_or_none()
    return om is not None and om.role in (OrgRole.owner, OrgRole.admin)


# ============================================================
# Submissions (authenticated)
# ============================================================

@router.post("/{form_id}/dispatch")
async def create_dispatch(
    form_id: int,
    body: DispatchCreateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Создать персональную отправку анкеты существующему кандидату."""
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)

    form = (await db.execute(select(FormTemplate).where(FormTemplate.id == form_id))).scalar_one_or_none()
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")
    # Скоуп по воронкам: чужому кандидату анкету не шлём (404, как и показ).
    entity = await _assert_entity_access(body.entity_id, current_user, db)

    if current_user.role != UserRole.superadmin:
        if not org or form.org_id != org.id or entity.org_id != org.id:
            raise HTTPException(status_code=403, detail="Access denied")

    # Выключенный шаблон — «больше не отправлять». И анкету, на которой
    # кандидат застрянет (выбор без вариантов, кривая шкала), не отправляем.
    if form.is_active is False:
        raise HTTPException(status_code=400, detail="Анкета выключена — включите её в конструкторе, чтобы отправить")
    problem = form_problem(form.title, form.fields or [])
    if problem:
        raise HTTPException(status_code=400, detail=f"Анкету пока нельзя отправить: {problem}")

    # Токен ссылки на анкету — единственная защита (кандидат не авторизован),
    # поэтому берём криптослучайный secrets.token_urlsafe с ПОЛНОЙ стойкостью:
    # 16 байт → 128 бит энтропии (крепче старого uuid4 — у него 122 бита), это
    # 22 URL-безопасных символа. Перебрать 2^128 нереально, и токены не
    # последовательны (никакого «порядка символов» подобрать нельзя). При этом
    # строка всё равно короче прежней 32-символьной uuid-«портянки».
    token = secrets.token_urlsafe(16)
    dispatch = FormDispatch(form_id=form.id, entity_id=entity.id, token=token, created_by=current_user.id)
    db.add(dispatch)
    await db.commit()
    await db.refresh(dispatch)

    return {
        "id": dispatch.id, "token": token, "url": f"/form/{token}",
        "entity_id": entity.id, "form_id": form.id, "status": dispatch.status,
    }


class ReassignDispatchRequest(BaseModel):
    entity_id: int  # кандидат, которому перепривязать анкету


@router.post("/dispatch/{dispatch_id}/reassign")
async def reassign_dispatch(
    dispatch_id: int,
    body: ReassignDispatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Перепривязать анкету (dispatch + её submission) к ДРУГОМУ кандидату — починка
    ошибочно улетевших анкет. Только admin/owner/superadmin; оба кандидата в своём орге."""
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")
    if not await _is_org_admin(current_user, org, db):
        raise HTTPException(403, "Only administrators can reassign anketa")

    dispatch = (await db.execute(
        select(FormDispatch).where(FormDispatch.id == dispatch_id)
    )).scalar_one_or_none()
    if not dispatch:
        raise HTTPException(404, "Анкета (dispatch) не найдена")

    target = (await db.execute(
        select(Entity).where(Entity.id == body.entity_id, Entity.org_id == org.id)
    )).scalar_one_or_none()
    if not target:
        raise HTTPException(404, "Кандидат-получатель не найден в вашем орге")

    src_ent = (await db.execute(
        select(Entity).where(Entity.id == dispatch.entity_id, Entity.org_id == org.id)
    )).scalar_one_or_none()
    if not src_ent:
        raise HTTPException(404, "Текущий кандидат анкеты не в вашем орге")

    old_entity = dispatch.entity_id
    dispatch.entity_id = body.entity_id
    await db.execute(
        update(FormSubmission).where(FormSubmission.dispatch_id == dispatch_id).values(entity_id=body.entity_id)
    )
    # Файлы из ответов — к новому кандидату тоже (до 20.10.2026 оставались у
    # прежнего, и ссылка «файл» в анкете нового вела в никуда). Вместе с
    # картинками страниц PDF («<имя>_page_N.jpg»).
    moved_files = 0
    sub = (await db.execute(
        select(FormSubmission).where(FormSubmission.dispatch_id == dispatch_id)
    )).scalar_one_or_none()
    if sub and isinstance(sub.data, dict):
        form = await db.get(FormTemplate, dispatch.form_id)
        fields = answer_fields(form.fields if form else [], sub.fields_snapshot)
        names = {
            sub.data.get(f["id"]).strip() for f in fields
            if isinstance(f, dict) and f.get("type") == "file"
            and isinstance(sub.data.get(f.get("id")), str) and sub.data.get(f["id"]).strip()
        }
        if names:
            conds = [EntityFile.file_name.in_(names)] + [
                EntityFile.file_name.like(f"{Path(n).stem}_page_%.jpg") for n in names
            ]
            from sqlalchemy import or_
            res = await db.execute(
                update(EntityFile)
                .where(EntityFile.entity_id == old_entity, or_(*conds))
                .values(entity_id=body.entity_id)
            )
            moved_files = res.rowcount or 0
    await db.commit()
    return {
        "success": True, "dispatch_id": dispatch_id,
        "from_entity": old_entity, "to_entity": body.entity_id, "files_moved": moved_files,
    }


@router.delete("/dispatch/{dispatch_id}")
async def delete_dispatch(
    dispatch_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Удалить анкету (dispatch + её ответы), например, если она ошибочно
    прилетела не на ту карточку и перепривязывать (reassign) некуда/не нужно.
    Требует edit-доступ к кандидату, на котором висит анкета."""
    current_user = await db.merge(current_user)
    dispatch = (await db.execute(
        select(FormDispatch).where(FormDispatch.id == dispatch_id)
    )).scalar_one_or_none()
    if not dispatch:
        raise HTTPException(status_code=404, detail="Анкета не найдена")

    entity = (await db.execute(select(Entity).where(Entity.id == dispatch.entity_id))).scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=404, detail="Кандидат не найден")

    if current_user.role != UserRole.superadmin:
        org = await get_user_org(current_user, db)
        if not org or entity.org_id != org.id:
            raise HTTPException(status_code=403, detail="Access denied")
        has_access = await check_entity_access(entity, current_user, org.id, db, required_level=AccessLevel.edit)
        if not has_access:
            raise HTTPException(status_code=403, detail="No edit permission for this entity")

    if dispatch.submission_id:
        await db.execute(delete(FormSubmission).where(FormSubmission.id == dispatch.submission_id))
    await db.delete(dispatch)
    await db.commit()
    return {"ok": True}


# ============================================================
# Entity-scoped dispatch endpoints
# ============================================================

async def _assert_entity_access(entity_id: int, current_user: User, db: AsyncSession) -> Entity:
    # Скоуп по воронкам: анкеты и ответы чужого кандидата не отдаём.
    from ..services.vacancy_scope import ensure_entity_visible
    await ensure_entity_visible(entity_id, current_user, db)
    entity = (await db.execute(select(Entity).where(Entity.id == entity_id))).scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if current_user.role != UserRole.superadmin:
        org = await get_user_org(current_user, db)
        if not org or entity.org_id != org.id:
            raise HTTPException(status_code=403, detail="Access denied")
    return entity


@router.get("/entity/{entity_id}/all-dispatches")
async def list_entity_all_dispatches(entity_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get dispatches for entity + all merged_from entities (historical profiles)."""
    current_user = await db.merge(current_user)
    await _assert_entity_access(entity_id, current_user, db)

    # Get main entity with merged_from data
    entity = (await db.execute(select(Entity).where(Entity.id == entity_id))).scalar_one_or_none()
    if not entity:
        raise HTTPException(404, "Entity not found")

    # Collect all entity IDs: current + all merged_from
    entity_ids = [entity_id]
    merged_from = entity.extra_data.get("merged_from") if isinstance(entity.extra_data, dict) else []
    if isinstance(merged_from, list):
        for m in merged_from:
            if isinstance(m, dict) and "entity_id" in m:
                entity_ids.append(m["entity_id"])

    # Fetch dispatches for all entities
    all_rows = (await db.execute(
        select(FormDispatch).where(FormDispatch.entity_id.in_(entity_ids)).order_by(FormDispatch.created_at.desc())
    )).scalars().all()

    # Названия и вопросы анкет. Вопросы ответа — его снимок на момент
    # отправки (fields_snapshot), у старых ответов — текущие поля шаблона.
    form_ids = {d.form_id for d in all_rows}
    titles = {}
    template_fields: dict = {}
    if form_ids:
        for fid, title, fields in (await db.execute(
            select(FormTemplate.id, FormTemplate.title, FormTemplate.fields).where(FormTemplate.id.in_(form_ids))
        )).all():
            titles[fid] = title
            template_fields[fid] = fields or []

    subs: dict = {}
    sub_ids = [d.submission_id for d in all_rows if d.submission_id]
    if sub_ids:
        for sub in (await db.execute(select(FormSubmission).where(FormSubmission.id.in_(sub_ids)))).scalars().all():
            subs[sub.id] = sub

    def fields_of(d) -> list:
        sub = subs.get(d.submission_id)
        return answer_fields(template_fields.get(d.form_id), sub.fields_snapshot if sub else None)

    def file_field_ids(d) -> list:
        return [f["id"] for f in fields_of(d) if isinstance(f, dict) and f.get("type") == "file" and f.get("id")]

    # Резолв файлов анкеты: (entity_id, имя файла) → URL скачивания, чтобы поле
    # типа «файл» в ответах было кликабельным (а не просто именем).
    needed_files = []  # (entity_id, filename)
    for d in all_rows:
        sub = subs.get(d.submission_id)
        data = (sub.data if sub else None) or {}
        for ffid in file_field_ids(d):
            val = data.get(ffid)
            if isinstance(val, str) and val.strip():
                needed_files.append((d.entity_id, val.strip()))
    file_url_map = {}  # (entity_id, filename) → url
    if needed_files:
        names = list({n for _, n in needed_files})
        eids = list({e for e, _ in needed_files})
        for eid, file_id, fname in (await db.execute(
            select(EntityFile.entity_id, EntityFile.id, EntityFile.file_name)
            .where(EntityFile.entity_id.in_(eids), EntityFile.file_name.in_(names))
            .order_by(EntityFile.id.desc())
        )).all():
            file_url_map.setdefault((eid, fname), f"/api/entities/{eid}/files/{file_id}/download")

    # Карта: id диспатча → имя профиля-источника. После merge ВСЕ диспатчи висят на
    # target (FormDispatch перепривязан, иначе CASCADE-delete стирал бы анкеты влитого
    # профиля), поэтому различаем по id (захвачен в merged_from[].form_dispatch_ids),
    # а не по entity_id.
    _mf_list = merged_from if isinstance(merged_from, list) else []
    dispatch_source = {}
    for m in _mf_list:
        if not isinstance(m, dict):
            continue
        nm = m.get("name") or (f"Профиль #{m.get('entity_id')}" if m.get("entity_id") else "Объединённый профиль")
        for did in (m.get("form_dispatch_ids") or []):
            dispatch_source[did] = nm

    # Build response with source info (which profile filled it)
    result = []
    for d in all_rows:
        source_name = dispatch_source.get(d.id)
        if source_name is None:
            # Легаси-путь: диспатч ещё висит на влитом профиле по entity_id
            # (слияния до фикса form_dispatch_ids).
            if d.entity_id != entity_id:
                for m in _mf_list:
                    if isinstance(m, dict) and m.get("entity_id") == d.entity_id:
                        source_name = m.get("name") or f"Профиль #{d.entity_id}"
                        break
            if source_name is None:
                source_name = "Текущий профиль"

        d_sub = subs.get(d.submission_id)
        d_data = (d_sub.data if d_sub else None) or {}
        d_file_links = {}
        for ffid in file_field_ids(d):
            val = d_data.get(ffid)
            if isinstance(val, str) and val.strip():
                url = file_url_map.get((d.entity_id, val.strip()))
                if url:
                    d_file_links[ffid] = url

        result.append({
            "id": d.id, "form_id": d.form_id, "form_title": titles.get(d.form_id),
            "token": d.token, "status": d.status, "seen_by_recruiter": d.seen_by_recruiter,
            "submission_id": d.submission_id, "answers": d_sub.data if d_sub else None,
            "field_labels": field_labels(fields_of(d)),
            "file_links": d_file_links,  # field_id → URL скачивания файла
            "created_at": d.created_at.isoformat() if d.created_at else None,
            "submitted_at": d.submitted_at.isoformat() if d.submitted_at else None,
            "source_entity_id": d.entity_id,
            "source_name": source_name,  # Какой профиль заполнил
        })

    return result


@router.get("/entity/{entity_id}/unread-count")
async def entity_forms_unread_count(entity_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    current_user = await db.merge(current_user)
    await _assert_entity_access(entity_id, current_user, db)
    count = (await db.execute(
        select(func.count(FormDispatch.id)).where(
            FormDispatch.entity_id == entity_id,
            FormDispatch.status == "submitted",
            FormDispatch.seen_by_recruiter == False,  # noqa: E712
        )
    )).scalar() or 0
    return {"count": count}


@router.patch("/entity/{entity_id}/dispatches/seen")
async def mark_entity_dispatches_seen(entity_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    current_user = await db.merge(current_user)
    await _assert_entity_access(entity_id, current_user, db)
    await db.execute(
        update(FormDispatch).where(
            FormDispatch.entity_id == entity_id,
            FormDispatch.seen_by_recruiter == False,  # noqa: E712
        ).values(seen_by_recruiter=True)
    )
    await db.commit()
    return {"ok": True}


# ============================================================
# Public routes — NO AUTH (candidate fills form)
# ============================================================

@router.get("/public/{slug}")
@limiter.limit(PUBLIC_PAGE_LIMIT)
async def get_public_form(
    request: Request,
    slug: str,
    db: AsyncSession = Depends(get_db),
):
    """Get form fields for public display (no auth required)."""
    result = await db.execute(
        select(FormTemplate).where(FormTemplate.slug == slug, FormTemplate.is_active == True)
    )
    form = result.scalar_one_or_none()
    if not form:
        raise HTTPException(status_code=404, detail="Форма не найдена")

    # Get vacancy title if linked
    vacancy_title = None
    if form.vacancy_id:
        vac_result = await db.execute(select(Vacancy.title).where(Vacancy.id == form.vacancy_id))
        vacancy_title = vac_result.scalar_one_or_none()

    return {
        "id": form.id,
        "title": form.title,
        "description": form.description,
        "fields": form.fields or [],
        "vacancy_title": vacancy_title,
    }


@router.post("/public/{slug}/submit")
@limiter.limit(PUBLIC_SUBMIT_LIMIT)
async def submit_public_form(request: Request, slug: str):
    """Отправка по общему адресу анкеты отключена: анкету заполняет СУЩЕСТВУЮЩИЙ
    кандидат по персональной ссылке (токен). Раньше каждый такой ответ плодил
    нового кандидата. Ручку оставили, чтобы старые ссылки получали понятный отказ."""
    raise HTTPException(status_code=403, detail=_SLUG_SUBMIT_OFF)


@router.post("/public/{slug}/submit-with-files")
@limiter.limit(PUBLIC_SUBMIT_LIMIT)
async def submit_public_form_with_files(request: Request, slug: str):
    raise HTTPException(status_code=403, detail=_SLUG_SUBMIT_OFF)


_SLUG_SUBMIT_OFF = "Эта анкета заполняется по персональной ссылке, которую отправляет рекрутёр."


async def _read_public_uploads(files) -> tuple[list[dict], list[dict]]:
    """Прочитать файлы анкеты с проверкой формата и размера. В базу не пишет.

    Читаем не больше лимита + 1 байт: раньше файл читался целиком и только
    потом сравнивался с лимитом — гигабайтное «видео» целиком ложилось в память.
    Возвращает (принятые, пропущенные [{name, reason}]): пропущенные кандидат
    видит после отправки и может переслать.
    """
    accepted: list[dict] = []
    skipped: list[dict] = []
    for extra in (files or [])[PUBLIC_MAX_FILES:]:
        if getattr(extra, "filename", None):
            skipped.append({"name": extra.filename, "reason": f"превышен лимит файлов (макс. {PUBLIC_MAX_FILES})"})
    for upload_file in (files or [])[:PUBLIC_MAX_FILES]:
        if not upload_file.filename:
            continue
        original_name = upload_file.filename
        ext = Path(original_name.lower()).suffix
        if ext not in ALLOWED_EXTENSIONS:
            logger.warning("Public form: skipped disallowed file type '%s' (%s)", ext, original_name)
            skipped.append({"name": original_name, "reason": "неподдерживаемый формат"})
            continue
        max_size = PUBLIC_MAX_VIDEO_SIZE if ext in VIDEO_EXTENSIONS else PUBLIC_MAX_FILE_SIZE
        content = await upload_file.read(max_size + 1)
        if not content:
            skipped.append({"name": original_name, "reason": "пустой файл"})
            continue
        if len(content) > max_size:
            skipped.append({"name": original_name, "reason": f"файл больше {max_size // (1024 * 1024)} МБ"})
            continue
        accepted.append({
            "name": original_name,
            "ext": ext,
            "content": content,
            "content_type": upload_file.content_type or mimetypes.guess_type(original_name)[0] or "application/octet-stream",
        })
    return accepted, skipped


PDF_PREVIEW_MAX_PAGES = 10


def _render_pdf_pages(pdf_path: str, out_dir: Path) -> list[tuple[int, Path, bytes]]:
    """PDF → картинки страниц для превью (синхронно — зовётся в отдельном потоке)."""
    import fitz
    pages = []
    doc = fitz.open(pdf_path)
    try:
        mat = fitz.Matrix(PDF_RENDER_DPI / 72, PDF_RENDER_DPI / 72)
        for page_num in range(min(len(doc), PDF_PREVIEW_MAX_PAGES)):
            pix = doc[page_num].get_pixmap(matrix=mat)
            img_path = out_dir / f"{uuid.uuid4().hex}.jpg"
            pix.save(str(img_path))
            pages.append((page_num, img_path, pix.tobytes("jpg")))
    finally:
        doc.close()
    return pages


async def _store_public_uploads(db: AsyncSession, form, entity_id: int, accepted: list[dict]) -> int:
    """Сохранить принятые файлы анкеты к кандидату (org_id — из формы).

    PDF-резюме дополнительно раскладывается на картинки страниц для превью —
    в отдельном потоке и не больше PDF_PREVIEW_MAX_PAGES страниц: раньше все
    страницы рендерились по 200 DPI прямо в обработчике, и сервер на это время
    не отвечал никому.
    """
    if not accepted:
        return 0
    entity_files_dir = ENTITY_FILES_DIR / str(entity_id)
    entity_files_dir.mkdir(parents=True, exist_ok=True)

    saved = []
    for item in accepted:
        original_name, content = item["name"], item["content"]
        file_path = entity_files_dir / f"{uuid.uuid4().hex}{item['ext']}"
        with open(file_path, "wb") as f:
            f.write(content)
        is_resume = any(kw in original_name.lower() for kw in ["resume", "cv", "резюме"])
        entity_file = EntityFile(
            org_id=form.org_id,
            entity_id=entity_id,
            file_type=EntityFileType.resume if is_resume else EntityFileType.other,
            file_name=original_name,
            file_path=str(file_path),
            # Храним содержимое и в БД (bytea): диск на проде эфемерный, иначе при
            # редеплое файл теряется → download отдаёт file_content_lost.
            file_data=content,
            file_size=len(content),
            mime_type=item["content_type"],
            description=f"Загружено через форму '{form.title}'",
            uploaded_by=form.created_by,
        )
        db.add(entity_file)
        saved.append((entity_file, file_path, item["content_type"], original_name))
    await db.flush()

    for entity_file, fpath, ctype, orig_name in saved:
        if ctype != "application/pdf" or entity_file.file_type != EntityFileType.resume:
            continue
        try:
            pages = await asyncio.to_thread(_render_pdf_pages, str(fpath), entity_files_dir)
        except Exception:
            logger.exception("PDF→image conversion failed for %s", fpath)
            continue
        for page_num, img_path, img_bytes in pages:
            db.add(EntityFile(
                org_id=form.org_id,
                entity_id=entity_id,
                file_type=EntityFileType.resume,
                file_name=f"{Path(orig_name).stem}_page_{page_num + 1}.jpg",
                file_path=str(img_path),
                file_data=img_bytes,  # bytea — переживает редеплой
                file_size=len(img_bytes),
                mime_type="image/jpeg",
                description=f"Страница {page_num + 1} из {orig_name}",
                uploaded_by=form.created_by,
            ))
    return len(saved)


class PublicClientErrorSchema(BaseModel):
    link: str = ""
    kind: str = ""
    status: Optional[int] = None
    message: str = ""
    online: Optional[bool] = None


@router.post("/public/client-error", status_code=204)
@limiter.limit(PUBLIC_REPORT_LIMIT)
async def report_public_form_client_error(request: Request, body: PublicClientErrorSchema):
    """Браузер кандидата сообщает, что отправка анкеты не удалась.

    17.10.2026 кандидат пять раз жал «Отправить» и видел ошибку, а у нас не
    осталось ни следа: запрос до сервера не дошёл. Этот отчёт страница анкеты
    шлёт в обход axios (sendBeacon), поэтому он доходит и тогда, когда сломался
    сам путь отправки. Ищется в логах по маркеру PUBLIC_FORM_CLIENT_ERROR.
    Без авторизации и без записи в базу — только строка в лог, всё обрезано.
    """
    logger.warning(
        "PUBLIC_FORM_CLIENT_ERROR link=%s… kind=%s status=%s online=%s msg=%r ua=%r",
        (body.link or "")[:6],
        (body.kind or "")[:32],
        body.status,
        body.online,
        (body.message or "")[:500],
        (request.headers.get("user-agent") or "")[:200],
    )
    return Response(status_code=204)


@router.get("/public/d/{token}")
@limiter.limit(PUBLIC_PAGE_LIMIT)
async def get_public_form_by_token(
    request: Request,
    token: str,
    db: AsyncSession = Depends(get_db),
    viewer: Optional[User] = Depends(get_current_user_optional),
):
    """Публичный показ персональной анкеты (без авторизации)."""
    dispatch = (await db.execute(select(FormDispatch).where(FormDispatch.token == token))).scalar_one_or_none()
    if not dispatch:
        raise HTTPException(status_code=404, detail="Анкета не найдена")
    form = (await db.execute(select(FormTemplate).where(FormTemplate.id == dispatch.form_id))).scalar_one_or_none()
    submitted = dispatch.status == "submitted"
    # Выключенный шаблон закрывает НЕзаполненные ссылки, а заполненная анкета
    # открывается всегда: рекрутёр смотрит по ней ответы (до 20.10.2026
    # выключение шаблона прятало и их).
    if not form or (form.is_active is False and not submitted):
        raise HTTPException(status_code=404, detail="Анкета недоступна")

    entity = (await db.execute(select(Entity).where(Entity.id == dispatch.entity_id))).scalar_one_or_none()

    # «Открыта» — только когда открыл кандидат. Рекрутёр, проверяя ссылку из
    # своего браузера, раньше ставил «Открыта» сам себе.
    opened_by_staff = viewer is not None and (
        viewer.role == UserRole.superadmin
        or (await db.execute(
            select(OrgMember.id).where(OrgMember.org_id == form.org_id, OrgMember.user_id == viewer.id)
        )).scalar_one_or_none() is not None
    )
    if dispatch.status == "sent" and not opened_by_staff:
        dispatch.status = "opened"
        dispatch.opened_at = datetime.utcnow()
        await db.commit()

    # Уже заполнено — отдаём ответы, чтобы по ссылке открывалась ЗАПОЛНЕННАЯ анкета
    # (рекрутёр может открыть/поделиться), а не пустая форма.
    fields = form.fields or []
    answers = None
    file_links: dict = {}
    if submitted and dispatch.submission_id:
        sub = (await db.execute(
            select(FormSubmission).where(FormSubmission.id == dispatch.submission_id)
        )).scalar_one_or_none()
        answers = sub.data if sub else None
        fields = answer_fields(fields, sub.fields_snapshot if sub else None)
        # Поля-файлы → ссылка на скачивание (резолв EntityFile по имени файла),
        # чтобы файл в заполненной анкете можно было открыть, а не только имя.
        names = {
            f["id"]: answers.get(f["id"]).strip()
            for f in fields
            if answers and isinstance(f, dict) and f.get("type") == "file" and f.get("id")
            and isinstance(answers.get(f["id"]), str) and answers.get(f["id"]).strip()
        }
        if names:
            by_name = {}
            for fid_, fname in (await db.execute(
                select(EntityFile.id, EntityFile.file_name).where(
                    EntityFile.entity_id == dispatch.entity_id,
                    EntityFile.file_name.in_(set(names.values())),
                ).order_by(EntityFile.id.desc())
            )).all():
                by_name.setdefault(fname, fid_)
            for ffid, fname in names.items():
                if fname in by_name:
                    file_links[ffid] = f"/api/entities/{dispatch.entity_id}/files/{by_name[fname]}/download"

    return {
        "id": form.id, "title": form.title, "description": form.description,
        "fields": fields,
        "candidate_name": entity.name if entity else None,
        "already_submitted": submitted,
        "answers": answers,
        "file_links": file_links,
    }


async def _submit_by_token(
    db: AsyncSession,
    token: str,
    raw_data,
    files,
    background_tasks: Optional[BackgroundTasks],
) -> dict:
    """Ответ кандидата по персональной ссылке — один путь для JSON и multipart.

    До 20.10.2026 это были две копии с разной проверкой: с файлами `data="[]"`
    давал 500, обязательный «Файл» не проверялся нигде, ответ принимался с
    любыми ключами и любой длины, а два быстрых нажатия «Отправить» записывали
    два ответа (строку ссылки никто не блокировал).
    """
    accepted, skipped_files = await _read_public_uploads(files)

    dispatch = (await db.execute(
        select(FormDispatch).where(FormDispatch.token == token).with_for_update()
    )).scalar_one_or_none()
    if not dispatch:
        raise HTTPException(status_code=404, detail="Анкета не найдена")
    if dispatch.status == "submitted":
        raise HTTPException(status_code=409, detail="Анкета уже заполнена")
    # Ссылка уже у кандидата: выключение шаблона её не закрывает, иначе
    # заполненные ответы пропадали бы на «Отправить». Закрыть ссылку —
    # удалить анкету в карточке кандидата.
    form = (await db.execute(select(FormTemplate).where(FormTemplate.id == dispatch.form_id))).scalar_one_or_none()
    if not form:
        raise HTTPException(status_code=404, detail="Анкета недоступна")

    fields = form.fields or []
    try:
        answers = clean_answers(fields, raw_data)
    except AnswerError as e:
        raise HTTPException(status_code=422, detail=str(e))
    # Имя файла в ответе — только если сам файл пришёл и принят.
    uploaded = {a["name"] for a in accepted}
    for f in fields:
        if isinstance(f, dict) and f.get("type") == "file" and answers.get(f.get("id")) not in uploaded:
            answers.pop(f.get("id"), None)
    problem = required_problem(fields, answers, uploaded)
    if problem:
        reason = next((s_["reason"] for s_ in skipped_files), None)
        raise HTTPException(status_code=422, detail=f"{problem}" + (f" (файл не принят: {reason})" if reason else ""))

    submission = FormSubmission(
        form_id=form.id, entity_id=dispatch.entity_id, data=answers,
        dispatch_id=dispatch.id, fields_snapshot=fields,
    )
    db.add(submission)
    await db.flush()

    files_saved_count = await _store_public_uploads(db, form, dispatch.entity_id, accepted)

    dispatch.status = "submitted"
    dispatch.submitted_at = datetime.utcnow()
    dispatch.submission_id = submission.id
    dispatch.seen_by_recruiter = False
    await db.commit()

    try:
        entity = (await db.execute(select(Entity).where(Entity.id == dispatch.entity_id))).scalar_one_or_none()
        from ..services.hr_notifications import notify_form_submitted
        recipients = await notify_form_submitted(db, dispatch, entity, form)
        from .realtime import broadcast_form_submission
        # Тем же людям, что получили уведомление: отправителю и текущему
        # рекрутёру кандидата, каждому один раз.
        for user_id in recipients:
            await broadcast_form_submission(user_id, {
                "entity_id": dispatch.entity_id, "form_id": form.id, "dispatch_id": dispatch.id,
                "form_title": form.title, "candidate_name": entity.name if entity else None,
            })
    except Exception:
        logger.error("form.submission notify/broadcast FAILED for dispatch %s", dispatch.id, exc_info=True)

    # PDF без резюме → фоновый авто-промоут во вкладку «Резюме» (с проверкой
    # Claude). Только если файлы правда пришли — раньше звался на каждый ответ.
    if files_saved_count and background_tasks is not None:
        from ..services.resume_autopromote import promote_pdf_to_resume_if_needed
        background_tasks.add_task(promote_pdf_to_resume_if_needed, dispatch.entity_id, form.org_id)

    return {
        "message": "Спасибо! Ваша анкета успешно отправлена.",
        "entity_id": dispatch.entity_id,
        "files_saved": files_saved_count,
        "skipped_files": skipped_files,
    }


@router.post("/public/d/{token}/submit")
@limiter.limit(PUBLIC_SUBMIT_LIMIT)
async def submit_public_form_by_token(
    request: Request,
    token: str,
    body: PublicSubmitSchema,
    db: AsyncSession = Depends(get_db),
):
    """Публичная отправка персональной анкеты — привязка к существующему кандидату."""
    return await _submit_by_token(db, token, body.data, [], None)


@router.post("/public/d/{token}/submit-with-files")
@limiter.limit(PUBLIC_SUBMIT_LIMIT)
async def submit_public_form_by_token_with_files(
    request: Request,
    token: str,
    background_tasks: BackgroundTasks,
    data: str = Form(..., description="JSON string with form data {field_id: value}"),
    files: List[UploadFile] = File(default=[]),
    db: AsyncSession = Depends(get_db),
):
    """Персональная анкета С ФАЙЛАМИ: ответы и файлы привязываются к
    существующему кандидату (dispatch.entity_id), без создания нового entity."""
    try:
        form_data = json.loads(data)
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="Невалидный JSON в поле data")
    return await _submit_by_token(db, token, form_data, files, background_tasks)
