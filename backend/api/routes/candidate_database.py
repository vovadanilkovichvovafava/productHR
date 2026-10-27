"""
Candidate Database (Archive) API — read-only archive of all candidates from funnels.
Also includes duplicate detection.

Endpoints:
- GET /api/candidate-database — paginated list of all candidates with vacancy applications
- POST /api/candidate-database/find-duplicates — detect duplicate candidates
- POST /api/candidate-database/merge — merge two duplicate candidates
"""
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, or_, and_, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.database import get_db
from api.models.database import (
    User, UserRole, Organization, OrgMember, OrgRole,
    Vacancy, VacancyApplication, ApplicationStage,
    Entity,
)
from api.services.auth import get_current_user, get_user_org
from ..services.hr_stages import STAGE_LABELS

logger = logging.getLogger("hr-analyzer.candidate-database")

router = APIRouter()


# Подписи этапов — общий справочник (services/hr_stages.py).
APPLICATION_STAGE_LABELS = STAGE_LABELS


@router.get("")
async def list_candidate_database(
    search: Optional[str] = None,
    recruiter_id: Optional[int] = None,
    vacancy_id: Optional[int] = None,
    stage: Optional[str] = None,
    source: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List ALL candidates that have at least one VacancyApplication.
    Read-only archive view. Returns candidate info + their latest vacancy application.
    """
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=403, detail="No organization found")

    # Base query: entities with at least one vacancy application in our org
    query = (
        select(
            Entity.id,
            Entity.name,
            Entity.email,
            Entity.phone,
            Entity.telegram_usernames,
            Entity.extra_data,
            Entity.created_at.label("entity_created_at"),
            Vacancy.title.label("vacancy_title"),
            Vacancy.id.label("vacancy_id"),
            VacancyApplication.stage,
            VacancyApplication.source,
            VacancyApplication.applied_at,
            User.name.label("recruiter_name"),
            Vacancy.created_by.label("recruiter_id"),
        )
        .join(VacancyApplication, VacancyApplication.entity_id == Entity.id)
        .join(Vacancy, VacancyApplication.vacancy_id == Vacancy.id)
        .outerjoin(User, Vacancy.created_by == User.id)
        .where(Vacancy.org_id == org.id)
    )

    # Filters
    if search:
        term = f"%{search}%"
        from ..services.search_index import name_search_conditions, ensure_pg_trgm_checked, contact_search_conditions
        await ensure_pg_trgm_checked(db)
        query = query.where(
            or_(
                *name_search_conditions(search),  # умный поиск по имени (транслит+порядок+опечатки)
                *contact_search_conditions(search),  # почта/телефон(норм.)/telegram + доп-списки
            )
        )

    if recruiter_id:
        query = query.where(Vacancy.created_by == recruiter_id)

    if vacancy_id:
        query = query.where(Vacancy.id == vacancy_id)

    if stage:
        try:
            stage_enum = ApplicationStage(stage)
            query = query.where(VacancyApplication.stage == stage_enum)
        except ValueError:
            pass

    if source:
        query = query.where(VacancyApplication.source.ilike(f"%{source}%"))

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    query = query.order_by(Entity.name, VacancyApplication.applied_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    rows = result.all()

    items = []
    for row in rows:
        telegram = None
        if row.telegram_usernames:
            if isinstance(row.telegram_usernames, list) and row.telegram_usernames:
                telegram = row.telegram_usernames[0]
            elif isinstance(row.telegram_usernames, str):
                telegram = row.telegram_usernames

        # Extract birth_date from extra_data
        birth_date = None
        if row.extra_data and isinstance(row.extra_data, dict):
            birth_date = row.extra_data.get("birth_date") or row.extra_data.get("date_of_birth")

        stage_val = row.stage.value if row.stage else "applied"

        items.append({
            "id": row.id,
            "name": row.name,
            "email": row.email,
            "phone": row.phone,
            "telegram": telegram,
            "birth_date": birth_date,
            "vacancy_title": row.vacancy_title,
            "vacancy_id": row.vacancy_id,
            "stage": stage_val,
            "stage_label": APPLICATION_STAGE_LABELS.get(stage_val, stage_val),
            "source": row.source,
            "recruiter_name": row.recruiter_name,
            "recruiter_id": row.recruiter_id,
            "applied_at": row.applied_at.isoformat() if row.applied_at else None,
        })

    # Get available recruiters for filter
    recruiter_q = await db.execute(
        select(User.id, User.name)
        .join(Vacancy, Vacancy.created_by == User.id)
        .join(VacancyApplication, VacancyApplication.vacancy_id == Vacancy.id)
        .where(Vacancy.org_id == org.id)
        .group_by(User.id, User.name)
        .order_by(User.name)
    )
    recruiters = [{"id": r.id, "name": r.name} for r in recruiter_q.all()]

    # Get available vacancies for filter
    vacancy_q = await db.execute(
        select(Vacancy.id, Vacancy.title)
        .join(VacancyApplication, VacancyApplication.vacancy_id == Vacancy.id)
        .where(Vacancy.org_id == org.id)
        .group_by(Vacancy.id, Vacancy.title)
        .order_by(Vacancy.title)
    )
    vacancies = [{"id": v.id, "title": v.title} for v in vacancy_q.all()]

    return {
        "items": items,
        "total": total,
        "skip": skip,
        "limit": limit,
        "filters": {
            "recruiters": recruiters,
            "vacancies": vacancies,
        }
    }


@router.post("/find-duplicates")
async def find_duplicates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Scan all candidates in the database and find potential duplicates.
    Checks: name (fuzzy), telegram username, email, birth_date.
    If ANY single field matches → flag as possible duplicate.
    """
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=403, detail="No organization found")

    # Load all entities that have applications in this org
    entity_q = await db.execute(
        select(Entity)
        .join(VacancyApplication, VacancyApplication.entity_id == Entity.id)
        .join(Vacancy, VacancyApplication.vacancy_id == Vacancy.id)
        .where(Vacancy.org_id == org.id)
        .group_by(Entity.id)
    )
    entities = list(entity_q.scalars().all())

    if len(entities) < 2:
        return {"groups": [], "total_groups": 0}

    # Build lookup indexes for fast matching
    name_map: Dict[str, List[int]] = {}       # normalized name → entity indices
    email_map: Dict[str, List[int]] = {}      # email → entity indices
    telegram_map: Dict[str, List[int]] = {}   # telegram → entity indices
    birth_map: Dict[str, List[int]] = {}      # birth_date → entity indices
    phone_map: Dict[str, List[int]] = {}      # последние 7 цифр телефона → indices

    # Мусорные telegram-ярлыки источника (hh, hh_b2b, telegram…) НЕ идентифицируют
    # человека — по ним десятки разных кандидатов слиплись бы в один ложный кластер.
    from ..services.similarity import JUNK_TELEGRAM_USERNAMES, normalize_phone as _norm_phone

    def normalize_name(n: str) -> str:
        if not n:
            return ""
        return " ".join(n.lower().strip().split())

    def normalize_email(e: str) -> str:
        if not e:
            return ""
        return e.lower().strip()

    def normalize_telegram(t: str) -> str:
        if not t:
            return ""
        t = t.lower().strip()
        if t.startswith("@"):
            t = t[1:]
        return t

    for idx, entity in enumerate(entities):
        # Name
        name_key = normalize_name(entity.name)
        if name_key and len(name_key) > 2:
            name_map.setdefault(name_key, []).append(idx)

        # Email
        email_key = normalize_email(entity.email)
        if email_key:
            email_map.setdefault(email_key, []).append(idx)

        # Telegram — только НЕ мусорные ярлыки (junk-теги источника массово слепляют разных)
        tg_names = entity.telegram_usernames or []
        if isinstance(tg_names, str):
            tg_names = [tg_names]
        for tg in tg_names:
            tg_key = normalize_telegram(tg)
            if tg_key and len(tg_key) >= 3 and tg_key not in JUNK_TELEGRAM_USERNAMES:
                telegram_map.setdefault(tg_key, []).append(idx)

        # Телефон — последние 7 цифр (сильный ключ личности)
        phone_key = _norm_phone(entity.phone or "")
        if phone_key and len(phone_key) >= 7:
            phone_map.setdefault(phone_key[-7:], []).append(idx)

        # Birth date — индексируем для показа, но в группировку НЕ идёт (см. ниже)
        if entity.extra_data and isinstance(entity.extra_data, dict):
            bd = entity.extra_data.get("birth_date") or entity.extra_data.get("date_of_birth")
            if bd:
                birth_map.setdefault(str(bd), []).append(idx)

    # Find groups where any field has duplicates
    from collections import defaultdict
    # Union-Find for grouping
    parent = list(range(len(entities)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    # Track match reasons between pairs
    pair_matches: Dict[tuple, List[str]] = defaultdict(list)

    # Группируем ТОЛЬКО по сильным идентификаторам (email / личный telegram / телефон).
    # Имя и дата рождения В ОДИНОЧКУ дубль не образуют — иначе тёзки и «birthday-twins»
    # слипались бы (реальный кейс: три разных «Никиты» слились по общему имени/тегу).
    for field_name, field_map in [
        ("email", email_map),
        ("telegram", telegram_map),
        ("phone", phone_map),
    ]:
        for key, indices in field_map.items():
            if len(indices) > 1:
                for i in range(len(indices)):
                    for j in range(i + 1, len(indices)):
                        a, b = indices[i], indices[j]
                        union(a, b)
                        pair_key = (min(a, b), max(a, b))
                        if field_name not in pair_matches[pair_key]:
                            pair_matches[pair_key].append(field_name)

    # Collect groups
    groups_map: Dict[int, List[int]] = defaultdict(list)
    for idx in range(len(entities)):
        root = find(idx)
        groups_map[root].append(idx)

    # Build response — only groups with 2+ members
    groups = []
    for root, member_indices in groups_map.items():
        if len(member_indices) < 2:
            continue

        members = []
        group_match_fields = set()

        for idx in member_indices:
            entity = entities[idx]
            telegram = None
            if entity.telegram_usernames:
                if isinstance(entity.telegram_usernames, list) and entity.telegram_usernames:
                    telegram = entity.telegram_usernames[0]
                elif isinstance(entity.telegram_usernames, str):
                    telegram = entity.telegram_usernames

            birth_date = None
            if entity.extra_data and isinstance(entity.extra_data, dict):
                birth_date = entity.extra_data.get("birth_date") or entity.extra_data.get("date_of_birth")

            members.append({
                "id": entity.id,
                "name": entity.name,
                "email": entity.email,
                "phone": entity.phone,
                "telegram": telegram,
                "birth_date": birth_date,
            })

        # Collect all match fields for this group
        for i in range(len(member_indices)):
            for j in range(i + 1, len(member_indices)):
                a, b = member_indices[i], member_indices[j]
                pair_key = (min(a, b), max(a, b))
                group_match_fields.update(pair_matches.get(pair_key, []))

        groups.append({
            "candidates": members,
            "match_fields": sorted(group_match_fields),
            "count": len(members),
        })

    # Sort by group size descending
    groups.sort(key=lambda g: g["count"], reverse=True)

    return {
        "groups": groups[:100],  # Limit to 100 groups
        "total_groups": len(groups),
        "total_candidates_with_duplicates": sum(g["count"] for g in groups),
    }


@router.post("/merge")
async def merge_candidates(
    source_id: int = Query(..., description="Candidate to merge FROM (will be removed)"),
    target_id: int = Query(..., description="Candidate to merge INTO (will be kept)"),
    force: bool = Query(False, description="Слить принудительно даже при конфликте сильных ключей"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Merge two duplicate candidates using existing similarity service."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(status_code=403, detail="No organization found")

    # Verify both entities exist
    source = await db.get(Entity, source_id)
    target = await db.get(Entity, target_id)

    if not source or not target:
        raise HTTPException(status_code=404, detail="One or both candidates not found")
    # Org-изоляция: merge деструктивен (source удаляется) — обоих можно мёрджить
    # только внутри своего org, иначе можно стереть кандидата чужой компании.
    if source.org_id != org.id or target.org_id != org.id:
        raise HTTPException(status_code=404, detail="One or both candidates not found")

    try:
        from ..services.similarity import similarity_service, MergeIdentityConflict
        try:
            merged = await similarity_service.merge_entities(
                db=db, source_entity=source, target_entity=target, force=force
            )
        except MergeIdentityConflict as e:
            raise HTTPException(
                status_code=409,
                detail=f"Похоже, это РАЗНЫЕ люди: {e.reason}. Слияние отменено. Если точно дубль — повторите с force=true.",
            )
        return {"success": True, "merged_into": target_id, "details": {"merged_entity_id": merged.id}}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Merge failed: {e}")
        raise HTTPException(status_code=500, detail=f"Merge failed: {str(e)}")
