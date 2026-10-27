"""
API routes for interns data — server-to-server proxy to Prometheus.

The frontend calls GET /api/interns/*, and these routes fetch
from Prometheus with Authorization header (secret stays server-side).
"""
import logging
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.utils.http_client import get_http_client
from api.database import get_db
from api.models.database import Entity, EntityType, EntityStatus, User, Organization, PrometheusReviewCache
from api.services.auth import get_current_user, get_user_org
from api.services.prometheus_status import (
    fetch_statuses_bulk,
    fetch_status_single,
    map_prometheus_status,
    normalize_hr_status,
    PrometheusNotConfiguredError,
    PrometheusAPIError,
)
from api.routes.realtime import broadcast_entity_updated, broadcast_entity_created

logger = logging.getLogger("hr-analyzer.interns")

router = APIRouter()


async def _proxy_prometheus(path: str, params: Optional[dict] = None):
    """
    Shared helper: proxy a GET request to Prometheus.

    - Validates that PROMETHEUS_BASE_URL and COMMUNICATION_API_KEY are set.
    - Adds Bearer token to the request.
    - Maps Prometheus HTTP errors to appropriate backend responses.
    - Returns parsed JSON on success.
    """
    base_url = settings.prometheus_base_url
    api_key = settings.communication_api_key

    if not base_url or not api_key:
        missing = []
        if not base_url:
            missing.append("PROMETHEUS_BASE_URL")
        if not api_key:
            missing.append("COMMUNICATION_API_KEY")
        logger.warning("Prometheus integration not configured — missing env vars: %s", ", ".join(missing))
        raise HTTPException(
            status_code=503,
            detail=f"Prometheus integration is not configured (missing: {', '.join(missing)})",
        )

    url = f"{base_url.rstrip('/')}{path}"

    client = get_http_client()
    try:
        response = await client.get(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            params=params,
        )
    except Exception as exc:
        logger.error("Failed to connect to Prometheus (%s): %s", path, type(exc).__name__)
        raise HTTPException(
            status_code=502,
            detail="Failed to connect to Prometheus service",
        )

    if response.status_code == 401:
        logger.error("Prometheus returned 401 for %s — check COMMUNICATION_API_KEY", path)
        raise HTTPException(
            status_code=502,
            detail="Prometheus authentication failed",
        )

    if response.status_code == 404:
        raise HTTPException(
            status_code=404,
            detail="Resource not found in Prometheus",
        )

    if response.status_code != 200:
        logger.error("Prometheus returned %d for %s", response.status_code, path)
        raise HTTPException(
            status_code=502,
            detail=f"Prometheus returned status {response.status_code}",
        )

    return response.json()


# Список практикантов, аналитика и достижения из Prometheus — только после входа
# (24.10.2026): раньше эти три адреса отдавали персональные данные любому, кто
# знал адрес. Страница «Практиканты» и так открывается после входа.
@router.get("")
async def get_interns(current_user: User = Depends(get_current_user)):
    """
    Proxy endpoint: fetches interns list from Prometheus.

    Returns the JSON payload from Prometheus as-is.
    The COMMUNICATION_API_KEY is never exposed to the client.
    """
    import os
    base_url = settings.prometheus_base_url
    api_key = settings.communication_api_key

    # Diagnostic: log raw env vs settings value on every request
    raw_env = os.environ.get("PROMETHEUS_BASE_URL")
    logger.info(
        "Prometheus check: raw_env present=%s raw_env_repr=%r settings_value_repr=%r api_key_present=%s",
        raw_env is not None,
        raw_env[:40] if raw_env else raw_env,
        base_url[:40] if base_url else base_url,
        bool(api_key),
    )

    if not base_url or not api_key:
        missing = []
        if not base_url:
            missing.append("PROMETHEUS_BASE_URL")
        if not api_key:
            missing.append("COMMUNICATION_API_KEY")
        logger.warning("Prometheus integration not configured — missing env vars: %s", ", ".join(missing))
        raise HTTPException(
            status_code=503,
            detail=f"Prometheus integration is not configured (missing: {', '.join(missing)})",
        )

    url = f"{base_url.rstrip('/')}/api/external/interns"

    client = get_http_client()
    try:
        response = await client.get(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
        )
    except Exception as exc:
        # Log error without leaking the API key
        logger.error("Failed to connect to Prometheus: %s", type(exc).__name__)
        raise HTTPException(
            status_code=502,
            detail="Failed to connect to Prometheus service",
        )

    if response.status_code == 401:
        logger.error("Prometheus returned 401 — check COMMUNICATION_API_KEY")
        raise HTTPException(
            status_code=502,
            detail="Prometheus authentication failed",
        )

    if response.status_code != 200:
        logger.error("Prometheus returned %d", response.status_code)
        raise HTTPException(
            status_code=502,
            detail=f"Prometheus returned status {response.status_code}",
        )

    return response.json()


@router.get("/analytics")
async def get_analytics(
    current_user: User = Depends(get_current_user),
    trail: str = Query(default="all", description="Trail ID or 'all'"),
    period: str = Query(default="30", description="Number of days for analysis"),
):
    """
    Proxy endpoint: fetches platform analytics from Prometheus.

    Query params are forwarded to Prometheus /api/external/analytics.
    """
    return await _proxy_prometheus(
        "/api/external/analytics",
        params={"trail": trail, "period": period},
    )


@router.get("/student-achievements/{student_id}")
async def get_student_achievements(student_id: str, current_user: User = Depends(get_current_user)):
    """
    Proxy endpoint: fetches achievements for a specific student from Prometheus.

    The student_id is part of the URL path.
    Returns 404 if student not found in Prometheus.
    """
    return await _proxy_prometheus(
        f"/api/external/student-achievements/{student_id}",
    )


# ============================================================
# CONTACT ↔ PROMETHEUS INTERN MATCHING + REVIEW
# ============================================================


def _generate_review(intern: dict) -> dict:
    """
    Generate a deterministic HR review from Prometheus intern data.

    Analyzes trails, XP, activity, and submissions to produce
    a structured summary without any LLM calls.
    """
    trails: List[dict] = intern.get("trails") or []
    total_xp: int = intern.get("totalXP") or 0
    days_since_active = intern.get("daysSinceActive")
    last_active_at: Optional[str] = intern.get("lastActiveAt")

    # --- Trail analysis ---
    trail_views = []
    total_completed_modules = 0
    total_modules = 0
    total_earned_xp = 0
    for t in trails:
        completed = t.get("completedModules") or t.get("modulesCompleted") or 0
        total = t.get("totalModules") or 0
        earned = t.get("earnedXP") or t.get("xp") or 0
        name = t.get("trailName") or t.get("trailTitle") or t.get("title") or "Без названия"
        pct = round((completed / total) * 100) if total > 0 else 0
        total_completed_modules += completed
        total_modules += total
        total_earned_xp += earned

        # Submission stats if available
        submissions = t.get("submissions") or {}
        avg_score = t.get("avgScore")

        trail_views.append({
            "trailId": t.get("trailId") or t.get("id") or "",
            "trailName": name,
            "completedModules": completed,
            "totalModules": total,
            "completionPercent": pct,
            "earnedXP": earned,
            "avgScore": avg_score,
            "submissions": {
                "approved": submissions.get("approved", 0),
                "pending": submissions.get("pending", 0),
                "revision": submissions.get("revision", 0),
                "total": submissions.get("total", 0),
            } if submissions else None,
        })

    overall_pct = round((total_completed_modules / total_modules) * 100) if total_modules > 0 else 0

    # Sort trails: most completed first
    trail_views.sort(key=lambda t: t["completionPercent"], reverse=True)
    top_trails = [t for t in trail_views if t["completionPercent"] >= 70]
    weak_trails = [t for t in trail_views if 0 < t["completionPercent"] < 30]

    # --- Activity flags ---
    is_active = True
    risk = False
    risk_reason = None
    if days_since_active is not None:
        if days_since_active > 14:
            is_active = False
            risk = True
            risk_reason = f"Нет активности {days_since_active} дн."
        elif days_since_active > 7:
            is_active = False

    # --- Generate deterministic summary bullets ---
    bullets: List[str] = []

    # Bullet 1: overall progress
    if total_modules > 0:
        bullets.append(
            f"Пройдено {total_completed_modules} из {total_modules} модулей ({overall_pct}%) "
            f"по {len(trails)} трейл(ам)."
        )
    else:
        bullets.append("Не записан ни на один трейл.")

    # Bullet 2: XP
    if total_xp > 0:
        bullets.append(f"Набрано {total_xp} XP за всё время.")

    # Bullet 3: top trails
    if top_trails:
        names = ", ".join(t["trailName"] for t in top_trails[:3])
        bullets.append(f"Сильные трейлы (>70%): {names}.")

    # Bullet 4: weak trails
    if weak_trails:
        names = ", ".join(t["trailName"] for t in weak_trails[:3])
        bullets.append(f"Слабые трейлы (<30%): {names}.")

    # Bullet 5: activity warning
    if risk:
        bullets.append(f"Внимание: {risk_reason}")
    elif not is_active and days_since_active is not None:
        bullets.append(f"Последняя активность {days_since_active} дн. назад.")

    # --- Headline ---
    if overall_pct >= 80:
        headline = "Отличный прогресс на платформе"
    elif overall_pct >= 50:
        headline = "Хороший прогресс, есть потенциал роста"
    elif overall_pct > 0:
        headline = "Начальный этап обучения"
    else:
        headline = "Нет данных о прохождении курсов"

    # --- Summary paragraph ---
    parts = []
    name = intern.get("name", "Кандидат")
    if total_modules > 0:
        parts.append(
            f"{name} проходит обучение на платформе Prometheus. "
            f"Общий прогресс составляет {overall_pct}% ({total_completed_modules}/{total_modules} модулей)."
        )
    else:
        parts.append(f"{name} зарегистрирован(а) на платформе Prometheus, но пока не начал(а) обучение.")

    if top_trails:
        parts.append(
            f"Лучшие результаты в направлениях: {', '.join(t['trailName'] for t in top_trails[:3])}."
        )

    if risk:
        parts.append(
            f"Обратите внимание на риск отсева: {risk_reason}."
        )
    elif is_active:
        parts.append("Кандидат активен на платформе.")

    summary_text = " ".join(parts)

    return {
        "headline": headline,
        "bullets": bullets,
        "summary": summary_text,
        "metrics": {
            "totalXP": total_xp,
            "daysSinceActive": days_since_active,
            "lastActiveAt": last_active_at,
            "totalModules": total_modules,
            "completedModules": total_completed_modules,
            "overallCompletionPercent": overall_pct,
            "trailCount": len(trails),
        },
        "trails": trail_views,
        "flags": {
            "active": is_active,
            "risk": risk,
            "riskReason": risk_reason,
            "topTrails": [t["trailName"] for t in top_trails[:3]],
        },
    }


@router.get("/contact/{entity_id}")
async def get_intern_for_contact(
    entity_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Match a contact (entity) with a Prometheus intern by email.

    1. Loads the entity from DB.
    2. Extracts email(s).
    3. Fetches all interns from Prometheus.
    4. Finds the matching intern by case-insensitive email comparison.
    5. Returns a deterministic HR review based on the intern data.

    Response shape:
    {
        status: "ok" | "not_found" | "not_linked" | "error",
        intern?: { ...prometheus data },
        review?: { headline, bullets, summary, metrics, trails, flags },
        message?: string
    }
    """
    # 1. Load entity
    result = await db.execute(select(Entity).where(Entity.id == entity_id))
    entity = result.scalar_one_or_none()

    if not entity:
        return JSONResponse(
            content={"status": "not_found", "message": "Контакт не найден"},
            headers={"Cache-Control": "no-store"},
        )

    # 2. Collect all emails from entity
    emails: List[str] = []
    if entity.email:
        emails.append(entity.email.strip().lower())
    # entity.emails is a JSON array stored in extra_data or a separate column
    if hasattr(entity, "emails") and entity.emails:
        for e in entity.emails:
            normalized = e.strip().lower()
            if normalized and normalized not in emails:
                emails.append(normalized)

    if not emails:
        return JSONResponse(
            content={
                "status": "not_linked",
                "message": "У контакта не указан email. Невозможно найти данные в Prometheus.",
            },
            headers={"Cache-Control": "no-store"},
        )

    # 3. Fetch interns from Prometheus
    try:
        data = await _proxy_prometheus("/api/external/interns")
    except HTTPException as exc:
        return JSONResponse(
            content={
                "status": "error",
                "message": f"Ошибка получения данных из Prometheus: {exc.detail}",
            },
            status_code=200,  # Return 200 with error status in body
            headers={"Cache-Control": "no-store"},
        )

    interns_list: List[dict] = data.get("interns") or []

    # 4. Match by email (case-insensitive)
    matched_intern = None
    for intern in interns_list:
        intern_email = (intern.get("email") or "").strip().lower()
        if intern_email and intern_email in emails:
            matched_intern = intern
            break

    if not matched_intern:
        return JSONResponse(
            content={
                "status": "not_linked",
                "message": "Кандидат не найден в Prometheus. Проверьте email или связку.",
            },
            headers={"Cache-Control": "no-store"},
        )

    # 5. Generate review
    review = _generate_review(matched_intern)

    # 6. Build response — only plain JSON-safe data
    intern_dto = {
        "id": matched_intern.get("id"),
        "name": matched_intern.get("name"),
        "email": matched_intern.get("email"),
        "telegramUsername": matched_intern.get("telegramUsername"),
        "totalXP": matched_intern.get("totalXP", 0),
        "lastActiveAt": matched_intern.get("lastActiveAt"),
        "daysSinceActive": matched_intern.get("daysSinceActive"),
        "createdAt": matched_intern.get("createdAt"),
    }

    return JSONResponse(
        content={
            "status": "ok",
            "intern": intern_dto,
            "review": review,
        },
        headers={"Cache-Control": "no-store"},
    )


# ============================================================
# DETAILED AI REVIEW FOR CONTACT
# ============================================================


@router.get("/contact/{entity_id}/detailed-review")
async def get_detailed_review_for_contact(
    entity_id: int,
    force: bool = Query(default=False, description="Force regeneration, ignoring cache"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate a comprehensive AI-powered review of a contact's Prometheus data.

    Results are cached in the database (prometheus_review_cache table).
    Subsequent requests return the cached result instantly.
    Pass ?force=true to regenerate the review.

    1. Checks DB cache first (unless force=true).
    2. Matches contact to Prometheus intern by email.
    3. Fetches student achievements for richer data.
    4. Generates AI review with Claude.
    5. Saves result to DB cache.

    Response shape:
    {
        status: "ok" | "not_found" | "not_linked" | "error",
        intern?: { ...basic intern data },
        review?: { ...deterministic review },
        detailedReview?: { professionalProfile, competencyAnalysis, trailInsights,
                           teamFitRecommendation, overallVerdict },
        achievements?: { student, achievements, submissionStats, trailProgress, certificates },
        cached?: bool,
        message?: string
    }
    """
    from api.services.prometheus_review import prometheus_review_service

    # 0. Check DB cache (unless force regeneration)
    if not force:
        cache_result = await db.execute(
            select(PrometheusReviewCache).where(
                PrometheusReviewCache.entity_id == entity_id
            )
        )
        cached = cache_result.scalar_one_or_none()
        if cached and cached.review_data:
            payload = dict(cached.review_data)
            payload["cached"] = True
            return JSONResponse(
                content=payload,
                headers={"Cache-Control": "no-store"},
            )

    # 1. Load entity
    result = await db.execute(select(Entity).where(Entity.id == entity_id))
    entity = result.scalar_one_or_none()

    if not entity:
        return JSONResponse(
            content={"status": "not_found", "message": "Контакт не найден"},
            headers={"Cache-Control": "no-store"},
        )

    # 2. Collect emails
    emails: List[str] = []
    if entity.email:
        emails.append(entity.email.strip().lower())
    if hasattr(entity, "emails") and entity.emails:
        for e in entity.emails:
            normalized = e.strip().lower()
            if normalized and normalized not in emails:
                emails.append(normalized)

    if not emails:
        return JSONResponse(
            content={
                "status": "not_linked",
                "message": "У контакта не указан email. Невозможно найти данные в Prometheus.",
            },
            headers={"Cache-Control": "no-store"},
        )

    # 3. Fetch interns
    try:
        data = await _proxy_prometheus("/api/external/interns")
    except HTTPException as exc:
        return JSONResponse(
            content={
                "status": "error",
                "message": f"Ошибка получения данных из Prometheus: {exc.detail}",
            },
            status_code=200,
            headers={"Cache-Control": "no-store"},
        )

    interns_list: List[dict] = data.get("interns") or []

    # 4. Match by email
    matched_intern = None
    for intern in interns_list:
        intern_email = (intern.get("email") or "").strip().lower()
        if intern_email and intern_email in emails:
            matched_intern = intern
            break

    if not matched_intern:
        return JSONResponse(
            content={
                "status": "not_linked",
                "message": "Кандидат не найден в Prometheus. Проверьте email или связку.",
            },
            headers={"Cache-Control": "no-store"},
        )

    # 5. Generate deterministic review (base data)
    review = _generate_review(matched_intern)

    # 6. Fetch student achievements (optional — may not exist)
    achievements_data = None
    intern_id = matched_intern.get("id")
    if intern_id:
        try:
            achievements_data = await _proxy_prometheus(
                f"/api/external/student-achievements/{intern_id}"
            )
        except HTTPException:
            logger.info(
                "Could not fetch achievements for intern %s — continuing without",
                intern_id,
            )

    # 7. Generate AI detailed review
    detailed_review = await prometheus_review_service.generate_detailed_review(
        intern=matched_intern,
        review_data=review,
        achievements=achievements_data,
    )

    # 8. Build response payload
    intern_dto = {
        "id": matched_intern.get("id"),
        "name": matched_intern.get("name"),
        "email": matched_intern.get("email"),
        "telegramUsername": matched_intern.get("telegramUsername"),
        "totalXP": matched_intern.get("totalXP", 0),
        "lastActiveAt": matched_intern.get("lastActiveAt"),
        "daysSinceActive": matched_intern.get("daysSinceActive"),
        "createdAt": matched_intern.get("createdAt"),
    }

    payload = {
        "status": "ok",
        "intern": intern_dto,
        "review": review,
        "detailedReview": detailed_review,
        "achievements": achievements_data,
    }

    # 9. Save to DB cache (upsert)
    try:
        cache_result = await db.execute(
            select(PrometheusReviewCache).where(
                PrometheusReviewCache.entity_id == entity_id
            )
        )
        existing_cache = cache_result.scalar_one_or_none()

        if existing_cache:
            existing_cache.review_data = payload
        else:
            db.add(PrometheusReviewCache(
                entity_id=entity_id,
                review_data=payload,
            ))
        await db.commit()
    except Exception as exc:
        logger.warning("Failed to save prometheus review cache for entity %d: %s", entity_id, exc)
        # Non-critical — still return the review even if caching fails
        await db.rollback()

    payload["cached"] = False
    return JSONResponse(
        content=payload,
        headers={"Cache-Control": "no-store"},
    )


# ============================================================
# EXPORT INTERN TO CONTACT (ENTITY)
# ============================================================


class ExportInternRequest(BaseModel):
    """Optional overrides for the export."""
    intern_id: Optional[str] = None  # Prometheus intern id (used if endpoint is called without path param)


async def _export_intern_to_contact(
    intern: dict,
    db: AsyncSession,
    current_user: User,
    org: Organization,
) -> dict:
    """
    Core idempotent export: find or create an Entity (contact) from a Prometheus intern.

    Deduplication key: email (case-insensitive).
    If entity already exists — update only prometheus-linking fields (extra_data.prometheus_intern_id),
    do NOT overwrite manually-enriched fields.

    Returns: {"contact_id": int, "created": bool}
    """
    intern_email = (intern.get("email") or "").strip().lower()

    # Remove from exclusion list if previously excluded (manual export overrides)
    if intern_email:
        org_settings = dict(org.settings or {})
        exclusions = org_settings.get("prometheus_export_exclusions", [])
        if intern_email in exclusions:
            exclusions = [e for e in exclusions if e != intern_email]
            org_settings["prometheus_export_exclusions"] = exclusions
            org.settings = org_settings
    intern_name = intern.get("name") or "Без имени"
    intern_telegram = intern.get("telegramUsername") or ""
    prometheus_id = intern.get("id") or ""

    # --- Try to find existing entity by email (case-insensitive) ---
    existing_entity = None

    if intern_email:
        # Check primary email field
        result = await db.execute(
            select(Entity).where(
                Entity.org_id == org.id,
                func.lower(Entity.email) == intern_email,
            )
        )
        existing_entity = result.scalar_one_or_none()

    # Also check by prometheus_intern_id in extra_data if not found by email
    if not existing_entity and prometheus_id:
        result = await db.execute(
            select(Entity).where(
                Entity.org_id == org.id,
                Entity.extra_data["prometheus_intern_id"].as_string() == prometheus_id,
            )
        )
        existing_entity = result.scalar_one_or_none()

    if existing_entity:
        # Update prometheus linking metadata only
        extra = dict(existing_entity.extra_data or {})
        extra["prometheus_intern_id"] = prometheus_id
        extra["prometheus_exported"] = True
        existing_entity.extra_data = extra
        await db.commit()
        await db.refresh(existing_entity)
        return {"contact_id": existing_entity.id, "created": False}

    # --- Create new entity ---
    new_entity = Entity(
        org_id=org.id,
        type=EntityType.candidate,
        name=intern_name,
        status=EntityStatus.new,
        email=intern_email or None,
        emails=[intern_email] if intern_email else [],
        telegram_usernames=[intern_telegram.lstrip("@").lower()] if intern_telegram else [],
        phones=[],
        tags=["prometheus", "практикант"],
        extra_data={
            "prometheus_intern_id": prometheus_id,
            "prometheus_exported": True,
            "source": "prometheus_export",
        },
        created_by=current_user.id,
    )
    db.add(new_entity)
    await db.commit()
    await db.refresh(new_entity)

    return {"contact_id": new_entity.id, "created": True}


@router.post("/export-to-contact/{intern_id}")
async def export_intern_to_contact(
    intern_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Export a Prometheus intern to HR Contacts (Entity).

    1. Fetches interns from Prometheus.
    2. Finds the intern by ID.
    3. Upserts an Entity (contact) — idempotent by email / prometheus_intern_id.
    4. Returns {ok, contact_id, created}.
    """
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    # Fetch interns from Prometheus
    try:
        data = await _proxy_prometheus("/api/external/interns")
    except HTTPException as exc:
        return JSONResponse(
            content={"ok": False, "error": f"Prometheus error: {exc.detail}"},
            status_code=502,
            headers={"Cache-Control": "no-store"},
        )

    interns_list: List[dict] = data.get("interns") or []

    # Find the intern by ID
    matched_intern = None
    for intern in interns_list:
        if intern.get("id") == intern_id:
            matched_intern = intern
            break

    if not matched_intern:
        return JSONResponse(
            content={"ok": False, "error": "Intern not found in Prometheus"},
            status_code=404,
            headers={"Cache-Control": "no-store"},
        )

    # Export
    try:
        result = await _export_intern_to_contact(matched_intern, db, current_user, org)
    except Exception as exc:
        logger.error("Export intern %s to contact failed: %s", intern_id, exc)
        return JSONResponse(
            content={"ok": False, "error": "Failed to export intern to contact"},
            status_code=500,
            headers={"Cache-Control": "no-store"},
        )

    return JSONResponse(
        content={
            "ok": True,
            "contact_id": result["contact_id"],
            "created": result["created"],
        },
        headers={"Cache-Control": "no-store"},
    )


@router.get("/linked-contacts")
async def get_intern_linked_contacts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Return a mapping of prometheus_intern_id -> entity_id for all
    entities that were exported from Prometheus.
    This lets the frontend know which interns already have contacts.
    """
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    result = await db.execute(
        select(Entity.id, Entity.extra_data).where(
            Entity.org_id == org.id,
            Entity.extra_data["prometheus_exported"].as_string() == "true",
        )
    )
    rows = result.all()

    mapping = {}
    for entity_id, extra_data in rows:
        prom_id = (extra_data or {}).get("prometheus_intern_id")
        if prom_id:
            mapping[prom_id] = entity_id

    return JSONResponse(
        content={"links": mapping},
        headers={"Cache-Control": "no-store"},
    )


# ============================================================
# PROMETHEUS STATUS SYNC
# ============================================================

# HR canonical status → EntityStatus enum value
_HR_STATUS_TO_ENTITY = {
    "Принят": EntityStatus.hired,
    "Отклонен": EntityStatus.rejected,
    # "Обучается" has no direct EntityStatus mapping — keep current status
}


class SyncStatusesRequest(BaseModel):
    """Body for POST /api/interns/sync-prometheus-statuses."""
    emails: Optional[List[str]] = None


@router.post("/sync-prometheus-statuses")
async def sync_prometheus_statuses(
    body: Optional[SyncStatusesRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Sync intern statuses from Prometheus → HR.

    1. Collects emails from request body or from all prometheus-exported entities.
    2. Calls Prometheus bulk status endpoint.
    3. For each found intern:
       - Maps status code to HR canonical status.
       - Updates entity extra_data.prometheus_status* fields.
       - If status changed to "Принят" → auto-exports to contacts.
    4. Returns sync results as plain JSON.

    Response: {
        ok: bool,
        syncedAt: ISO string,
        results: [...],
        errors: [...]
    }
    """
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    synced_at = datetime.now(timezone.utc).isoformat()
    results = []
    errors = []

    # 1. Determine which emails to sync
    request_emails = (body.emails if body else None) or []
    request_emails = [e.strip().lower() for e in request_emails if e and e.strip()]

    if not request_emails:
        # Fetch all prometheus-exported entities' emails
        stmt = select(Entity).where(
            Entity.org_id == org.id,
            Entity.extra_data["prometheus_exported"].as_string() == "true",
        )
        result = await db.execute(stmt)
        entities = result.scalars().all()

        for ent in entities:
            if ent.email and ent.email.strip():
                email_norm = ent.email.strip().lower()
                if email_norm not in request_emails:
                    request_emails.append(email_norm)

    if not request_emails:
        return JSONResponse(
            content={"ok": True, "syncedAt": synced_at, "results": [], "errors": []},
            headers={"Cache-Control": "no-store"},
        )

    # 1b. Load exclusion list (emails removed from contacts — status overridden to "Обучается")
    org_settings = dict(org.settings or {})
    export_exclusions = set(
        s.lower() for s in org_settings.get("prometheus_export_exclusions", [])
    )

    # 2. Fetch statuses from Prometheus
    try:
        prom_results = await fetch_statuses_bulk(request_emails)
    except PrometheusNotConfiguredError as exc:
        return JSONResponse(
            content={
                "ok": False,
                "syncedAt": synced_at,
                "results": [],
                "errors": [{"type": "not_configured", "message": str(exc)}],
            },
            headers={"Cache-Control": "no-store"},
        )
    except PrometheusAPIError as exc:
        return JSONResponse(
            content={
                "ok": False,
                "syncedAt": synced_at,
                "results": [],
                "errors": [{"type": "api_error", "statusCode": exc.status_code, "message": exc.detail}],
            },
            headers={"Cache-Control": "no-store"},
        )

    # 3. Process each result
    for prom_item in prom_results:
        item_email = (prom_item.get("email") or "").strip().lower()
        # Try to extract email from nested intern object if not at top level
        if not item_email:
            intern_obj = prom_item.get("intern") or {}
            item_email = (intern_obj.get("email") or "").strip().lower()

        found = prom_item.get("found", False)

        if not found or not item_email:
            results.append({
                "email": item_email or prom_item.get("email", ""),
                "found": False,
                "error": prom_item.get("error"),
            })
            continue

        # Extract status info
        status_obj = prom_item.get("status") or {}
        status_code = status_obj.get("code", "")
        status_label = status_obj.get("label", "")
        status_updated_at = prom_item.get("statusUpdatedAt", "")

        hr_status = map_prometheus_status(status_code)
        hr_status = normalize_hr_status(hr_status)

        # Override status for excluded emails (removed from contacts → "Обучается")
        is_excluded = item_email in export_exclusions
        if is_excluded:
            hr_status = "Обучается"

        # Find matching entity in HR DB
        entity_result = await db.execute(
            select(Entity).where(
                Entity.org_id == org.id,
                func.lower(Entity.email) == item_email,
            )
        )
        entity = entity_result.scalar_one_or_none()

        result_item = {
            "email": item_email,
            "found": True,
            "statusCode": status_code,
            "statusLabel": status_label,
            "statusUpdatedAt": status_updated_at,
            "hrStatus": hr_status,
            "changed": False,
            "contactId": None,
        }

        if entity:
            result_item["contactId"] = entity.id

            # Read current prometheus status from extra_data
            extra = dict(entity.extra_data or {})
            current_prom_status = extra.get("prometheus_status")
            current_prom_updated = extra.get("prometheus_status_updated_at", "")

            # Determine if status changed
            status_changed = current_prom_status != hr_status

            # Also check if statusUpdatedAt is newer (if we have both)
            update_needed = status_changed
            if not status_changed and status_updated_at and current_prom_updated:
                update_needed = status_updated_at > current_prom_updated

            if update_needed:
                # Update extra_data with prometheus status info
                extra["prometheus_status"] = hr_status
                extra["prometheus_status_code"] = status_code
                extra["prometheus_status_label"] = status_label
                extra["prometheus_status_updated_at"] = status_updated_at
                extra["prometheus_last_sync"] = synced_at
                entity.extra_data = extra
                result_item["changed"] = True

                # Update Entity.status if we have a mapping
                target_entity_status = _HR_STATUS_TO_ENTITY.get(hr_status)
                if target_entity_status and entity.status != target_entity_status:
                    entity.status = target_entity_status

                try:
                    await db.commit()
                    await db.refresh(entity)
                    # Broadcast status change via WebSocket
                    await broadcast_entity_updated(org.id, {
                        "id": entity.id,
                        "type": entity.type,
                        "name": entity.name,
                        "status": entity.status,
                        "extra_data": entity.extra_data,
                    }, db)
                except Exception as exc:
                    logger.error("Failed to update entity %d status: %s", entity.id, exc)
                    await db.rollback()
                    errors.append({
                        "email": item_email,
                        "type": "db_update_failed",
                        "message": str(exc),
                    })
                    continue

            # Auto-export to contacts if status == "Принят"
            if hr_status == "Принят":
                # Entity already exists — ensure prometheus_exported flag is set
                if not extra.get("prometheus_exported"):
                    extra["prometheus_exported"] = True
                    entity.extra_data = extra
                    try:
                        await db.commit()
                    except Exception:
                        await db.rollback()
                result_item["contactId"] = entity.id

        else:
            # No entity found — if status is "Принят", auto-create contact
            if hr_status == "Принят":
                intern_obj = prom_item.get("intern") or {}
                intern_name = intern_obj.get("name") or prom_item.get("name") or "Без имени"
                intern_telegram = intern_obj.get("telegramUsername") or ""
                prometheus_id = intern_obj.get("id") or ""

                try:
                    new_entity = Entity(
                        org_id=org.id,
                        type=EntityType.candidate,
                        name=intern_name,
                        status=EntityStatus.hired,
                        email=item_email,
                        emails=[item_email],
                        telegram_usernames=[intern_telegram.lstrip("@").lower()] if intern_telegram else [],
                        phones=[],
                        tags=["prometheus", "практикант"],
                        extra_data={
                            "prometheus_intern_id": prometheus_id,
                            "prometheus_exported": True,
                            "prometheus_status": hr_status,
                            "prometheus_status_code": status_code,
                            "prometheus_status_label": status_label,
                            "prometheus_status_updated_at": status_updated_at,
                            "prometheus_last_sync": synced_at,
                            "source": "prometheus_auto_export",
                        },
                        created_by=current_user.id,
                    )
                    db.add(new_entity)
                    await db.commit()
                    await db.refresh(new_entity)
                    result_item["contactId"] = new_entity.id
                    result_item["changed"] = True
                    # Broadcast new contact via WebSocket
                    await broadcast_entity_created(org.id, {
                        "id": new_entity.id,
                        "type": new_entity.type,
                        "name": new_entity.name,
                        "status": new_entity.status,
                        "email": new_entity.email,
                        "owner_id": new_entity.created_by,
                        "extra_data": new_entity.extra_data,
                    }, db)
                except Exception as exc:
                    logger.error("Failed to auto-create entity for %s: %s", item_email, exc)
                    await db.rollback()
                    errors.append({
                        "email": item_email,
                        "type": "auto_export_failed",
                        "message": str(exc),
                    })

        results.append(result_item)

    return JSONResponse(
        content={
            "ok": len(errors) == 0,
            "syncedAt": synced_at,
            "results": results,
            "errors": errors,
        },
        headers={"Cache-Control": "no-store"},
    )


@router.post("/sync-prometheus-status-single")
async def sync_prometheus_status_single(
    email: Optional[str] = Query(default=None),
    intern_id: Optional[str] = Query(default=None, alias="internId"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Sync a single intern's status from Prometheus.

    Used by the /interns/{id}/stats page for per-candidate polling.
    Returns the same shape as bulk results but for one entry.
    """
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(403, "No organization access")

    if not email and not intern_id:
        return JSONResponse(
            content={"ok": False, "error": "email or internId required"},
            status_code=400,
            headers={"Cache-Control": "no-store"},
        )

    synced_at = datetime.now(timezone.utc).isoformat()

    try:
        prom_result = await fetch_status_single(email=email, intern_id=intern_id)
    except PrometheusNotConfiguredError as exc:
        return JSONResponse(
            content={"ok": False, "syncedAt": synced_at, "error": str(exc)},
            headers={"Cache-Control": "no-store"},
        )
    except PrometheusAPIError as exc:
        return JSONResponse(
            content={"ok": False, "syncedAt": synced_at, "error": exc.detail},
            headers={"Cache-Control": "no-store"},
        )

    found = prom_result.get("found", False)
    if not found:
        return JSONResponse(
            content={
                "ok": True,
                "syncedAt": synced_at,
                "found": False,
                "email": email,
                "internId": intern_id,
            },
            headers={"Cache-Control": "no-store"},
        )

    intern_obj = prom_result.get("intern") or {}
    status_obj = prom_result.get("status") or {}
    status_code = status_obj.get("code", "")
    status_label = status_obj.get("label", "")
    status_updated_at = prom_result.get("statusUpdatedAt", "")
    resolved_email = (intern_obj.get("email") or email or "").strip().lower()

    hr_status = map_prometheus_status(status_code)
    hr_status = normalize_hr_status(hr_status)

    # Override status for excluded emails (removed from contacts → "Обучается")
    org_settings = dict(org.settings or {})
    export_exclusions = set(
        s.lower() for s in org_settings.get("prometheus_export_exclusions", [])
    )
    if resolved_email in export_exclusions:
        hr_status = "Обучается"

    result = {
        "ok": True,
        "syncedAt": synced_at,
        "found": True,
        "email": resolved_email,
        "internId": intern_obj.get("id") or intern_id,
        "name": intern_obj.get("name"),
        "statusCode": status_code,
        "statusLabel": status_label,
        "statusUpdatedAt": status_updated_at,
        "hrStatus": hr_status,
        "changed": False,
        "contactId": None,
    }

    # Update entity if exists
    if resolved_email:
        entity_result = await db.execute(
            select(Entity).where(
                Entity.org_id == org.id,
                func.lower(Entity.email) == resolved_email,
            )
        )
        entity = entity_result.scalar_one_or_none()

        if entity:
            result["contactId"] = entity.id
            extra = dict(entity.extra_data or {})
            current_prom_status = extra.get("prometheus_status")

            if current_prom_status != hr_status:
                extra["prometheus_status"] = hr_status
                extra["prometheus_status_code"] = status_code
                extra["prometheus_status_label"] = status_label
                extra["prometheus_status_updated_at"] = status_updated_at
                extra["prometheus_last_sync"] = synced_at
                entity.extra_data = extra
                result["changed"] = True

                target_entity_status = _HR_STATUS_TO_ENTITY.get(hr_status)
                if target_entity_status and entity.status != target_entity_status:
                    entity.status = target_entity_status

                if hr_status == "Принят" and not extra.get("prometheus_exported"):
                    extra["prometheus_exported"] = True
                    entity.extra_data = extra

                try:
                    await db.commit()
                    await db.refresh(entity)
                    # Broadcast status change via WebSocket
                    await broadcast_entity_updated(org.id, {
                        "id": entity.id,
                        "type": entity.type,
                        "name": entity.name,
                        "status": entity.status,
                        "extra_data": entity.extra_data,
                    }, db)
                except Exception as exc:
                    logger.error("Failed to update entity %d: %s", entity.id, exc)
                    await db.rollback()

    return JSONResponse(
        content=result,
        headers={"Cache-Control": "no-store"},
    )


# ============================================================
# BACKGROUND AUTO-EXPORT TASK
# ============================================================

async def run_prometheus_auto_export():
    """
    Background task: fetch all Prometheus interns, check for 'Принят' status,
    and auto-create contacts for interns that don't have one yet.

    Called periodically from main.py (every 5 minutes).
    This ensures auto-export works even if nobody visits the /interns page.
    """
    from api.database import AsyncSessionLocal
    from api.models.database import Organization, UserRole

    base_url = settings.prometheus_base_url
    api_key = settings.communication_api_key

    if not base_url or not api_key:
        return

    async with AsyncSessionLocal() as db:
        # 1. Fetch all interns from Prometheus
        client = get_http_client()
        url = f"{base_url.rstrip('/')}/api/external/interns"
        try:
            response = await client.get(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
            )
        except Exception as exc:
            logger.error("Background auto-export: failed to fetch interns: %s", exc)
            return

        if response.status_code != 200:
            logger.warning("Background auto-export: Prometheus returned %d", response.status_code)
            return

        data = response.json()
        interns_list = data.get("interns", [])

        # Collect all emails
        emails = []
        for intern in interns_list:
            email = (intern.get("email") or "").strip().lower()
            if email:
                emails.append(email)

        if not emails:
            return

        # 2. Fetch statuses from Prometheus
        try:
            prom_results = await fetch_statuses_bulk(emails)
        except (PrometheusNotConfiguredError, PrometheusAPIError) as exc:
            logger.error("Background auto-export: status fetch failed: %s", exc)
            return

        # 3. For each org, process results and auto-export
        orgs_result = await db.execute(
            select(Organization).where(Organization.is_active == True)
        )
        orgs = orgs_result.scalars().all()

        synced_at = datetime.now(timezone.utc).isoformat()

        for org in orgs:
            try:
                # Load exclusion list
                org_settings = dict(org.settings or {})
                exclusions = set(
                    s.lower() for s in org_settings.get("prometheus_export_exclusions", [])
                )

                # Get first superadmin/admin for created_by
                admin_result = await db.execute(
                    select(User).where(
                        User.org_id == org.id,
                        User.role.in_([UserRole.superadmin, UserRole.admin]),
                    ).limit(1)
                )
                admin = admin_result.scalar_one_or_none()
                if not admin:
                    continue

                for prom_item in prom_results:
                    item_email = (prom_item.get("email") or "").strip().lower()
                    if not item_email:
                        intern_obj = prom_item.get("intern") or {}
                        item_email = (intern_obj.get("email") or "").strip().lower()

                    if not item_email or not prom_item.get("found"):
                        continue

                    # Skip excluded emails
                    if item_email in exclusions:
                        continue

                    status_obj = prom_item.get("status") or {}
                    status_code = status_obj.get("code", "")
                    hr_status = map_prometheus_status(status_code)
                    hr_status = normalize_hr_status(hr_status)

                    if hr_status != "Принят":
                        continue

                    # Check if entity already exists
                    entity_result = await db.execute(
                        select(Entity).where(
                            Entity.org_id == org.id,
                            func.lower(Entity.email) == item_email,
                        )
                    )
                    entity = entity_result.scalar_one_or_none()

                    if entity:
                        # Entity exists — ensure prometheus_exported flag is set
                        extra = dict(entity.extra_data or {})
                        if not extra.get("prometheus_exported"):
                            extra["prometheus_exported"] = True
                            entity.extra_data = extra
                            await db.commit()
                        continue

                    # Auto-create new entity
                    intern_obj = prom_item.get("intern") or {}
                    status_label = status_obj.get("label", "")
                    status_updated_at = prom_item.get("statusUpdatedAt", "")
                    intern_name = intern_obj.get("name") or "Без имени"
                    intern_telegram = intern_obj.get("telegramUsername") or ""
                    prometheus_id = intern_obj.get("id") or ""

                    new_entity = Entity(
                        org_id=org.id,
                        type=EntityType.candidate,
                        name=intern_name,
                        status=EntityStatus.hired,
                        email=item_email,
                        emails=[item_email],
                        telegram_usernames=(
                            [intern_telegram.lstrip("@").lower()] if intern_telegram else []
                        ),
                        phones=[],
                        tags=["prometheus", "практикант"],
                        extra_data={
                            "prometheus_intern_id": prometheus_id,
                            "prometheus_exported": True,
                            "prometheus_status": hr_status,
                            "prometheus_status_code": status_code,
                            "prometheus_status_label": status_label,
                            "prometheus_status_updated_at": status_updated_at,
                            "prometheus_last_sync": synced_at,
                            "source": "prometheus_auto_export",
                        },
                        created_by=admin.id,
                    )
                    db.add(new_entity)
                    await db.commit()
                    await db.refresh(new_entity)

                    logger.info(
                        "Background auto-export: created contact for %s in org %d",
                        item_email, org.id,
                    )

                    # Broadcast new contact via WebSocket
                    await broadcast_entity_created(org.id, {
                        "id": new_entity.id,
                        "type": new_entity.type,
                        "name": new_entity.name,
                        "status": new_entity.status,
                        "email": new_entity.email,
                        "owner_id": new_entity.created_by,
                        "extra_data": new_entity.extra_data,
                    }, db)

            except Exception as exc:
                logger.error(
                    "Background auto-export: failed for org %d: %s", org.id, exc,
                )
                await db.rollback()
