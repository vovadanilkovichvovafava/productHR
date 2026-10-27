import asyncio
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime

from ..database import get_db
from ..models.database import (
    Entity, EntityType, EntityStatus, EntityFile, EntityFileType,
    User, Vacancy, VacancyStatus, VacancyApplication, ApplicationStage, StageTransition,
)
from ..services.auth import get_current_user, get_user_org

logger = logging.getLogger("hr-analyzer.magic-button")

router = APIRouter()


def _drop_service_email(value: Optional[str]) -> Optional[str]:
    """Служебный ящик сайта (support@rabota.by и т.п.) — не почта кандидата.
    Старые версии расширения присылают его, когда кандидат почту не указал."""
    from ..services.similarity import is_service_email
    if value and is_service_email(value):
        logger.info(f"MAGIC_BUTTON: dropped service email {value!r}")
        return None
    return value


def _drop_junk_telegram(value: Optional[str]) -> Optional[str]:
    """hh_b2b и прочие каналы порталов — не Telegram кандидата."""
    from ..services.similarity import is_junk_telegram
    if value and is_junk_telegram(value):
        logger.info(f"MAGIC_BUTTON: dropped junk telegram {value!r}")
        return None
    return value


class MagicButtonData(BaseModel):
    # Parsed from resume
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    telegram: Optional[str] = None
    photo_url: Optional[str] = None
    position: Optional[str] = None
    source_url: str
    source: str  # "hh.ru", "linkedin.com", "career.habr.com"

    @field_validator("email")
    @classmethod
    def _clean_email(cls, v: Optional[str]) -> Optional[str]:
        return _drop_service_email(v)

    @field_validator("telegram")
    @classmethod
    def _clean_telegram(cls, v: Optional[str]) -> Optional[str]:
        return _drop_junk_telegram(v)

    # Extra parsed fields
    city: Optional[str] = None
    age: Optional[str] = None
    birthday: Optional[str] = None
    gender: Optional[str] = None
    salary: Optional[str] = None
    experience_summary: Optional[str] = None
    total_experience: Optional[str] = None
    experience_descriptions: Optional[list] = None
    skills: Optional[list] = None
    languages: Optional[list] = None
    company: Optional[str] = None
    education: Optional[list] = None
    certifications: Optional[list] = None  # лицензии/сертификаты (LinkedIn)
    summary: Optional[str] = None  # «Обо мне» — самоописание кандидата

    # Recruiter's choice
    vacancy_id: Optional[int] = None  # which funnel to add to
    comment: Optional[str] = None

class MagicButtonResponse(BaseModel):
    success: bool
    entity_id: int
    is_duplicate: bool = False
    duplicate_info: Optional[dict] = None  # who added, when, last status
    has_hidden_duplicate: bool = False  # похож на кандидата в архиве (superadmin-only) — деталей не раскрываем
    message: str

class DuplicateCheckRequest(BaseModel):
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    telegram: Optional[str] = None
    source_url: Optional[str] = None

    @field_validator("email")
    @classmethod
    def _clean_email(cls, v: Optional[str]) -> Optional[str]:
        return _drop_service_email(v)

    @field_validator("telegram")
    @classmethod
    def _clean_telegram(cls, v: Optional[str]) -> Optional[str]:
        return _drop_junk_telegram(v)

class DuplicateCheckResponse(BaseModel):
    is_duplicate: bool
    duplicates: list = []  # [{entity_id, name, email, phone, status, created_at}]
    # Совпадение в АРХИВЕ (теневая база). Расширение показывает плашку «Похожий
    # кандидат есть в архиве». Списком архив закрыт (superadmin-only), но ОДНУ
    # совпавшую карточку рекрутёр может открыть по id (read-грант члену орга на
    # любого кандидата, check_entity_access) — просмотреть, не листая архив.
    has_archive_match: bool = False
    archive_match_id: Optional[int] = None  # id архивного совпадения — открыть карточку
    # Soft-tier совпадение (anti-evasion): не «точный» дубль, но похож достаточно,
    # чтобы предупредить рекрутёра — «возможно тот же человек» (не блокирует добавление).
    soft_match: bool = False
    soft_confidence: int = 0
    soft_reasons: list = []
    soft_match_id: Optional[int] = None
    # «Был отказ» (22.10.2026): последний отказ среди ВСЕХ найденных совпадений —
    # активных, архивного (ClickUp «…: нет»/«неявка») и мягкого. Попап рисует
    # красную плашку ДО нажатия «Добавить». Поля — services/prior_rejection.py.
    prior_rejection: Optional[dict] = None

@router.post("/check-duplicate")
async def check_duplicate(
    data: DuplicateCheckRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Check for duplicates before adding a candidate."""
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(400, "User not in organization")

    from ..services.similarity import build_dup_keys, find_duplicate_matches

    # ЕДИНЫЙ матчер дублей (тот же, что detect_archived_duplicate на веб/парсере):
    # нормализованное сравнение по email/телефону-10/telegram/ФИО/URL, активные И
    # архив. Раньше здесь была отдельная копия на СЫРЫХ SQL-== (телефон в другом
    # формате не совпадал) и с явным исключением архива — из-за этого расширение
    # не находило архивные дубли и пропускало «+7 910…» ↔ «+79 10…».
    keys = build_dup_keys(
        name=data.full_name,
        email=data.email,
        phone=data.phone,
        telegram=data.telegram,
        source_url=data.source_url,
    )
    matches = await find_duplicate_matches(db, org.id, keys)
    # Активные — с деталями; архив — плашка + id ОДНОГО совпадения (чтобы рекрутёр
    # мог открыть именно эту карточку, не листая архив). Списком архив закрыт.
    active_ids = [m.entity_id for m in matches if not m.is_archived][:5]
    archive_match_id = next((m.entity_id for m in matches if m.is_archived), None)
    has_archive_match = archive_match_id is not None
    soft = next((m for m in matches if m.strength == "soft"), None)

    from ..services.prior_rejection import sort_key, rejections_by_entity, summary
    from ..services.vacancy_scope import get_scope_vacancy_ids
    matched_ids = set(active_ids) | {archive_match_id} | {soft.entity_id if soft else None}
    rej = await rejections_by_entity(
        db, [i for i in matched_ids if i], scope_ids=await get_scope_vacancy_ids(current_user, db),
    )
    prior = summary(sorted((r for lst in rej.values() for r in lst), key=sort_key, reverse=True))

    if not active_ids:
        return DuplicateCheckResponse(
            is_duplicate=False, duplicates=[],
            has_archive_match=has_archive_match, archive_match_id=archive_match_id,
            soft_match=soft is not None,
            soft_confidence=soft.confidence if soft else 0,
            soft_reasons=soft.reasons if soft else [],
            soft_match_id=soft.entity_id if soft else None,
            prior_rejection=prior,
        )

    dup_result = await db.execute(
        select(Entity).where(Entity.id.in_(active_ids))
    )
    duplicates = dup_result.scalars().all()

    # Подписи — из общего справочника (services/hr_stages.py). В `status` и
    # `stage` уходит САМА ПОДПИСЬ, ключ — в `status_key`/`stage_key`: у расширения
    # был свой старый словарь («Практика» вместо «Интервью с HR», «Интервью
    # назначено»…), а попап прошлых версий показывает значение как есть, если не
    # нашёл его в словаре, — так верные подписи видны и без переустановки (22.10.2026).
    from ..services.hr_stages import STATUS_LABELS, stage_label

    # For each duplicate, load their work history: vacancy applications + recent stage transitions
    result_list = []
    for d in duplicates:
        # Заявки кандидата — без удалённых воронок (их нет нигде в интерфейсе).
        apps_result = await db.execute(
            select(VacancyApplication, Vacancy.title)
            .join(Vacancy, Vacancy.id == VacancyApplication.vacancy_id)
            .where(VacancyApplication.entity_id == d.id, Vacancy.deleted_at.is_(None))
            .order_by(VacancyApplication.applied_at.desc())
        )
        applications = []
        for app, vacancy_title in apps_result.all():
            stage_key = app.stage.value if app.stage else "applied"
            applications.append({
                "vacancy_id": app.vacancy_id,
                "vacancy_title": vacancy_title,
                "stage": stage_label(stage_key),
                "stage_key": stage_key,
                "rating": app.rating,
                "applied_at": app.applied_at.isoformat() if app.applied_at else None,
                "last_stage_change_at": app.last_stage_change_at.isoformat() if app.last_stage_change_at else None,
            })

        # Recent stage transitions (last 10) — quick history view
        trans_result = await db.execute(
            select(StageTransition)
            .where(StageTransition.entity_id == d.id)
            .order_by(StageTransition.created_at.desc())
            .limit(10)
        )
        transitions = [
            {
                "from_stage": t.from_stage,
                "to_stage": t.to_stage,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in trans_result.scalars().all()
        ]

        status_key = d.status.value if d.status else "unknown"
        result_list.append({
            "entity_id": d.id,
            "name": d.name,
            "email": d.email,
            "phone": d.phone,
            "status": STATUS_LABELS.get(status_key, status_key),
            "status_key": status_key,
            "created_at": d.created_at.isoformat() if d.created_at else None,
            "applications": applications,
            "recent_transitions": transitions,
        })

    return DuplicateCheckResponse(
        is_duplicate=len(duplicates) > 0,
        duplicates=result_list,
        has_archive_match=has_archive_match,
        archive_match_id=archive_match_id,
        soft_match=soft is not None,
        soft_confidence=soft.confidence if soft else 0,
        soft_reasons=soft.reasons if soft else [],
        soft_match_id=soft.entity_id if soft else None,
        prior_rejection=prior,
    )

@router.post("/parse")
async def magic_button_parse(
    data: MagicButtonData,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Process a resume parsed by the Chrome extension."""
    import traceback
    try:
        return await _do_magic_parse(data, db, current_user, background_tasks, request)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Magic button error: {e}\n{traceback.format_exc()}")
        raise HTTPException(500, detail=f"Error: {str(e)}")


def _parse_salary(salary: Optional[str], source: Optional[str]):
    """«от 150 000 ₽» → (min, max, валюта). Валюта по умолчанию — страна сайта:
    rabota.by — BYN, остальное — RUB (до 22.10.2026 стоял KZT, и у кандидата без
    зарплаты в карточке висела валюта «тенге»)."""
    import re
    currency = "BYN" if "rabota.by" in (source or "") else "RUB"
    if not salary:
        return None, None, currency
    sal_text = salary.lower()
    if 'usd' in sal_text or '$' in sal_text:
        currency = 'USD'
    elif 'eur' in sal_text or '€' in sal_text:
        currency = 'EUR'
    elif 'byn' in sal_text or 'br' in sal_text or 'бел' in sal_text:
        currency = 'BYN'
    elif 'руб' in sal_text or '₽' in sal_text:
        currency = 'RUB'
    elif 'тенге' in sal_text or 'kzt' in sal_text or '₸' in sal_text:
        currency = 'KZT'

    # hh разделяет разряды разными пробелами (обычный, U+00A0, U+2009, U+202F).
    def _to_int(s):
        cleaned = re.sub(r'\D', '', s)
        return int(cleaned) if cleaned else 0
    numbers = re.findall(r'[\d\s   ]+', salary)
    nums = [_to_int(n) for n in numbers if any(c.isdigit() for c in n)]
    # Отбрасываем мусорные числа: слишком мелкие и больше INT-предела Postgres
    # (иначе expected_salary_* падали на commit → 500 при добавлении из расширения).
    nums = [n for n in nums if 100 < n <= 2_147_483_647]
    if len(nums) >= 2:
        return min(nums), max(nums), currency
    if len(nums) == 1:
        if 'от' in sal_text:
            return nums[0], None, currency
        if 'до' in sal_text:
            return None, nums[0], currency
        return nums[0], nums[0], currency
    return None, None, currency


async def _target_vacancy(db: AsyncSession, vacancy_id: int, current_user: User, org) -> Vacancy:
    """Воронка, в которую кладём кандидата, — те же проверки, что у «Добавить в
    воронку» (create_application): своя организация, не удалена, есть доступ,
    не вне скоупа. До 22.10.2026 проверялась только организация."""
    from .vacancies.common import can_access_vacancy
    from ..services.vacancy_scope import ensure_vacancy_visible

    vacancy = (await db.execute(
        select(Vacancy).where(
            Vacancy.id == vacancy_id, Vacancy.org_id == org.id, Vacancy.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if vacancy is None:
        raise HTTPException(404, "Vacancy not found")
    await ensure_vacancy_visible(vacancy.id, current_user, db)
    if not await can_access_vacancy(vacancy, current_user, org, db):
        raise HTTPException(403, "Access denied to this vacancy")
    return vacancy


async def _do_magic_parse(data, db, current_user, background_tasks: BackgroundTasks, request: Request):
    org = await get_user_org(current_user, db)
    if not org:
        raise HTTPException(400, "User not in organization")

    logger.info(
        f"magic-button parse: source={data.source} url={data.source_url} "
        f"photo_url={'<yes>' if data.photo_url else '<no>'} "
        f"({(data.photo_url or '')[:100]})"
    )

    # Воронку проверяем ДО создания кандидата: отказ не должен оставлять его без
    # воронки, которую рекрутёр выбрал.
    vacancy = await _target_vacancy(db, data.vacancy_id, current_user, org) if data.vacancy_id else None

    from ..services.similarity import build_dup_keys, find_duplicate_matches, normalize_source_url
    source_key = normalize_source_url(data.source_url or "")

    # «Добавлен (дубликат)» — тем же матчером, что плашка «Уже в базе» в попапе
    # (check-duplicate). Раньше здесь была своя копия на сырых SQL-сравнениях:
    # телефон в другом формате не совпадал, а `name ILIKE %…%` ловил чужих.
    # Мягкое совпадение — не «дубликат» (это лишь «возможно тот же»).
    matches = await find_duplicate_matches(db, org.id, build_dup_keys(
        name=data.full_name, email=data.email, phone=data.phone,
        telegram=data.telegram, source_url=data.source_url,
    ))
    exact = next((m for m in matches if not m.is_archived and m.strength != "soft"), None)
    duplicate = await db.get(Entity, exact.entity_id) if exact else None
    is_duplicate = duplicate is not None
    duplicate_info = None
    if is_duplicate:
        duplicate_info = {
            "entity_id": duplicate.id,
            "name": duplicate.name,
            "status": duplicate.status.value if duplicate.status else "unknown",
            "created_by": duplicate.created_by,
            "created_at": duplicate.created_at.isoformat() if duplicate.created_at else None,
        }

    # Create entity (even if duplicate — per TZ "can still add again")
    tg_list = [data.telegram.lower().lstrip('@')] if data.telegram else []

    extra = {
        "source": data.source,
        "source_url": data.source_url,
        "source_key": source_key or None,  # стабильный ключ резюме для дедупа
        "magic_button": True,
        "comment": data.comment,
    }
    comment = (data.comment or "").strip()
    # Комментарий из попапа. Есть воронка — он уходит в первую запись истории
    # заявки (как комментарий окна смены этапа): в ленте одна строка «Новый —
    # текст». До 22.10.2026 он ложился отдельной заметкой без воронки: рядом с
    # «Новый — Первичная заявка» получалась вторая строка «Новый», и заметка
    # показывалась в ЛЮБОЙ воронке, куда кандидата добавят потом. Без воронки —
    # заметка-этап, как у кандидата вне воронок.
    if comment and vacancy is None:
        import uuid
        from datetime import timezone as _tz
        extra["notes"] = [{
            "id": str(uuid.uuid4()),
            "text": comment,
            "date": datetime.now(_tz.utc).isoformat(),
            "stage": "new",
            "stage_label": "Новый",
            "author_id": current_user.id,
            "author_name": current_user.name,
        }]
    for key, value in (
        ("photo_url", data.photo_url), ("city", data.city), ("age", data.age),
        ("birth_date", data.birthday), ("gender", data.gender), ("salary", data.salary),
        ("experience_summary", data.experience_summary), ("total_experience", data.total_experience),
        ("experience_descriptions", data.experience_descriptions), ("skills", data.skills),
        ("languages", data.languages), ("education", data.education),
        ("certifications", data.certifications), ("summary", data.summary),
    ):
        if value:
            extra[key] = value

    salary_min, salary_max, salary_currency = _parse_salary(data.salary, data.source_url or data.source)

    entity = Entity(
        org_id=org.id,
        type=EntityType.candidate,
        name=data.full_name,
        status=EntityStatus.new,
        email=data.email,
        phone=data.phone,
        position=data.position,
        company=data.company or None,
        telegram_usernames=tg_list,
        expected_salary_min=salary_min,
        expected_salary_max=salary_max,
        expected_salary_currency=salary_currency,
        extra_data=extra,
        created_by=current_user.id,
    )
    db.add(entity)
    await db.flush()

    # ОБЩАЯ ВОРОНКА: кандидат кладётся прямо в выбранную вакансию, наверх колонки
    # «Новый» (stage_order = min - 1000, как в create_application). Клон-редирект
    # убран 2026-07-13 — см. get_my_vacancies_for_extension.
    application = None
    if vacancy is not None:
        min_order = (await db.execute(
            select(func.min(VacancyApplication.stage_order)).where(
                VacancyApplication.vacancy_id == vacancy.id,
                VacancyApplication.stage == ApplicationStage.applied,
            )
        )).scalar()
        application = VacancyApplication(
            vacancy_id=vacancy.id,
            entity_id=entity.id,
            stage=ApplicationStage.applied,
            stage_order=(min_order - 1000) if min_order is not None else 0,
            source=data.source,
            created_by=current_user.id,  # кто добавил → авто-метка HR
        )
        db.add(application)
        await db.flush()
        from ..services.stage_transitions import record_transition
        await record_transition(
            db, application_id=application.id, entity_id=entity.id, from_stage=None,
            to_stage=ApplicationStage.applied.value, changed_by_id=current_user.id,
            comment=comment or "Первичная заявка",
        )

    # Теневая дедупликация: сверяем нового кандидата с архивом до коммита.
    # При совпадении помечаем профиль флагом — веб-карточка покажет баннер «Проверить»,
    # а расширению отдаём has_hidden_duplicate — теперь показывает то же самое сразу.
    _hidden_dup = None
    try:
        from ..services.similarity import detect_archived_duplicate
        _hidden_dup = await detect_archived_duplicate(db, entity)
        if _hidden_dup:
            _extra = dict(entity.extra_data or {})
            _extra["hidden_duplicate_id"] = _hidden_dup
            entity.extra_data = _extra
    except Exception:
        logger.warning("shadow-dedup detect failed (non-critical)", exc_info=True)

    # Детектор «копипаст текста резюме» (Feature B) — независим от детектора
    # личности выше. Best-effort: ошибка не должна ломать создание кандидата.
    try:
        from ..services.resume_text_twin import detect_resume_text_twin
        await detect_resume_text_twin(db, entity)
    except Exception:
        logger.warning("resume-text-twin detect failed (non-critical)", exc_info=True)

    await db.commit()

    entity_id = entity.id
    org_id = org.id
    user_id = current_user.id
    # Журнал действий: номер нового кандидата в адресе запроса не виден.
    request.state.audit_extra = {
        "entity_id": entity_id,
        "vacancy_id": vacancy.id if vacancy else None,
        "application_id": application.id if application else None,
    }

    if vacancy is not None:
        # Метка «HR: …» сразу, а не после первого открытия карточки (как в
        # create_application).
        try:
            from ..services.hr_tags import sync_for_entity
            await sync_for_entity(db, entity_id)
        except Exception:
            logger.exception("HR-tags sync failed after magic-button add (non-critical)")
        try:
            from ..services.hr_notifications import notify_new_candidate
            await notify_new_candidate(db, entity, vacancy, current_user)
        except Exception:
            logger.exception("notify_new_candidate failed (non-critical)")

    # Фон после ответа (Starlette выполняет задачи по порядку): сначала фото —
    # оно быстрое и нужно аватарке в списке, потом ИИ-профиль (Claude + PDF,
    # 10–20 с). До 22.10.2026 порядок был обратный, и фото ждало ИИ.
    if data.photo_url:
        background_tasks.add_task(
            _download_candidate_photo_eager, entity_id, org_id, user_id, data.photo_url, data.full_name
        )
    candidate_data = {
        "full_name": data.full_name,
        "position": data.position,
        "email": data.email,
        "phone": data.phone,
        "telegram": data.telegram,
        "city": data.city,
        "age": data.age,
        "birthday": data.birthday,
        "gender": data.gender,
        "salary": data.salary,
        "total_experience": data.total_experience,
        "experience_summary": data.experience_summary,
        "experience_descriptions": data.experience_descriptions,
        "skills": data.skills,
        "languages": data.languages,
        "education": data.education,
        "certifications": data.certifications,
        "summary": data.summary,
        "photo_url": data.photo_url,
    }
    background_tasks.add_task(
        _generate_resume_files, entity_id, org_id, user_id, candidate_data
    )

    return MagicButtonResponse(
        success=True,
        entity_id=entity_id,
        is_duplicate=is_duplicate,
        duplicate_info=duplicate_info,
        has_hidden_duplicate=bool(_hidden_dup),
        message="Кандидат добавлен" + (" (дубликат найден)" if is_duplicate else ""),
    )


async def _download_candidate_photo_eager(
    entity_id: int, org_id: int, user_id: int, photo_url: str, candidate_name: str
):
    """Быстрый background-task: только скачивает фото с hh.ru и сохраняет
    как EntityFile. Запускается сразу после создания кандидата, не зависит от
    AI-резюме (который может упасть из-за API/парсера). Идемпотентно: если у
    entity уже есть photo-файл, пропускает.
    """
    from ..database import AsyncSessionLocal
    try:
        async with AsyncSessionLocal() as db:
            # Skip if photo file already exists for this entity
            existing = await db.execute(
                select(EntityFile.id).where(
                    EntityFile.entity_id == entity_id,
                    EntityFile.mime_type.startswith("image/"),
                ).limit(1)
            )
            if existing.scalar():
                logger.info(f"Photo file already exists for entity {entity_id}, skip eager download")
                return

            import httpx
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(photo_url, headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code != 200:
                    logger.warning(f"Eager photo download failed for entity {entity_id}: HTTP {resp.status_code}")
                    return
                ct = resp.headers.get("content-type", "").lower().split(";")[0].strip()
                if not ct.startswith("image/"):
                    logger.warning(f"Eager photo download non-image content-type: {ct} for entity {entity_id}")
                    return
                photo_bytes = resp.content

            ext = {
                "image/jpeg": "jpg", "image/jpg": "jpg",
                "image/png": "png", "image/webp": "webp",
            }.get(ct, "jpg")
            photo_file = EntityFile(
                entity_id=entity_id,
                org_id=org_id,
                file_type=EntityFileType.other,
                file_name=f"Фото_{(candidate_name or 'кандидат').replace(' ', '_')}.{ext}",
                file_path="",
                file_size=len(photo_bytes),
                mime_type=ct,
                description="Фото кандидата (HH, eager)",
                uploaded_by=user_id,
                file_data=photo_bytes,
            )
            db.add(photo_file)
            await db.commit()
            logger.info(f"Eager photo saved for entity {entity_id}: {len(photo_bytes)} bytes, {ct}")
    except Exception as e:
        logger.warning(f"Eager photo download crashed for entity {entity_id}: {type(e).__name__}: {e}")


async def _generate_resume_files(
    entity_id: int, org_id: int, user_id: int, candidate_data: dict
):
    """Background task: AI summary → PDF → JPEG → attach to entity."""
    from ..database import AsyncSessionLocal
    from ..services.resume_generator import (
        generate_ai_summary, generate_candidate_pdf, pdf_to_jpeg,
    )

    try:
        logger.info(f"Generating AI resume for entity {entity_id}...")

        # 1. AI summary
        markdown = await generate_ai_summary(candidate_data)
        logger.info(f"AI summary generated for entity {entity_id}: {len(markdown)} chars")

        # 1b. Download photo if URL was parsed by the extension. Photo is used
        # both inside the PDF and saved as a separate image file on the entity
        # so the UI can load it from files even if extra_data.photo_url is lost.
        photo_bytes = None
        photo_mime = None
        photo_url = candidate_data.get("photo_url")
        if photo_url:
            try:
                import httpx
                async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                    resp = await client.get(photo_url)
                    if resp.status_code == 200:
                        ct = resp.headers.get("content-type", "").lower()
                        if ct.startswith("image/"):
                            photo_bytes = resp.content
                            photo_mime = ct.split(";")[0].strip()
                            logger.info(
                                f"Downloaded candidate photo for entity {entity_id}: "
                                f"{len(photo_bytes)} bytes, {photo_mime}"
                            )
                        else:
                            logger.warning(f"Photo URL returned non-image content-type: {ct}")
            except Exception as e:
                logger.warning(f"Failed to download photo for entity {entity_id}: {e}")

        # 2. PDF (with photo if we have it)
        candidate_name = candidate_data.get("full_name", "Кандидат")
        pdf_bytes = generate_candidate_pdf(markdown, candidate_name, photo_bytes=photo_bytes)
        logger.info(f"PDF generated for entity {entity_id}: {len(pdf_bytes)} bytes")

        # 3. PDF → JPEG pages
        jpeg_pages = pdf_to_jpeg(pdf_bytes, dpi=200)
        logger.info(f"Converted to {len(jpeg_pages)} JPEG pages for entity {entity_id}")

        # 4. Save to DB
        async with AsyncSessionLocal() as db:
            # Фото отдельным файлом — если его ещё не сохранила быстрая задача
            # _download_candidate_photo_eager (она идёт раньше этой).
            has_photo = (await db.execute(
                select(EntityFile.id).where(
                    EntityFile.entity_id == entity_id,
                    EntityFile.mime_type.startswith("image/"),
                ).limit(1)
            )).scalar() is not None
            if photo_bytes and photo_mime and not has_photo:
                ext = {
                    "image/jpeg": "jpg",
                    "image/jpg": "jpg",
                    "image/png": "png",
                    "image/webp": "webp",
                }.get(photo_mime, "jpg")
                photo_file = EntityFile(
                    entity_id=entity_id,
                    org_id=org_id,
                    file_type=EntityFileType.other,
                    file_name=f"Фото_{candidate_name.replace(' ', '_')}.{ext}",
                    file_path="",
                    file_size=len(photo_bytes),
                    mime_type=photo_mime,
                    description="Фото кандидата (HH)",
                    uploaded_by=user_id,
                    file_data=photo_bytes,
                )
                db.add(photo_file)

            # Save PDF
            pdf_file = EntityFile(
                entity_id=entity_id,
                org_id=org_id,
                file_type=EntityFileType.resume,
                file_name=f"Профиль_{candidate_name.replace(' ', '_')}.pdf",
                file_path="",
                file_size=len(pdf_bytes),
                mime_type="application/pdf",
                description="AI-сгенерированный профиль кандидата",
                uploaded_by=user_id,
                file_data=pdf_bytes,
            )
            db.add(pdf_file)

            # Save JPEG pages
            for i, jpg_bytes in enumerate(jpeg_pages):
                jpg_file = EntityFile(
                    entity_id=entity_id,
                    org_id=org_id,
                    file_type=EntityFileType.resume,
                    file_name=f"Профиль_{candidate_name.replace(' ', '_')}_стр{i+1}.jpg",
                    file_path="",
                    file_size=len(jpg_bytes),
                    mime_type="image/jpeg",
                    description=f"AI-профиль (стр. {i+1})",
                    uploaded_by=user_id,
                    file_data=jpg_bytes,
                )
                db.add(jpg_file)

            await db.commit()
            logger.info(
                f"Resume files saved for entity {entity_id}: "
                f"1 PDF + {len(jpeg_pages)} JPEGs"
            )

    except Exception as e:
        logger.error(f"Resume generation failed for entity {entity_id}: {e}", exc_info=True)

@router.get("/vacancies")
async def get_my_vacancies_for_extension(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get recruiter's vacancies for the extension popup dropdown.

    Показываем ровно то же, что веб в «Мои вакансии» (isPersonallyActive,
    utils/vacancy.ts): status=open И юзер ЛИЧНО принял воронку
    (extra_data.accepted_by содержит его id). Просто «назначен» (assigned_to)
    — недостаточно: пока рекрутёр не нажал «Взять в работу» сам, воронка для
    него ещё «Заявка», а не рабочая, и класть туда кандидата рано
    (2026-07-08, личное принятие — воронка общая, но взятие личное). СТРОГО
    accepted_by, БЕЗ фолбэка на created_by — тот же баг, что чинили в
    funnelsPickerRecruiters (Layout.tsx) и groupAcceptorIds
    (RecruiterFunnelsPage.tsx): фолбэк засчитывал воронку создателю, даже
    если он её не принимал, и расходился с реальным списком «Мои вакансии».
    Легаси-записи без accepted_by (созданные до этой фичи) заполняются
    разовым бэкафиллом в start.sh, а не фолбэком здесь.
    pending_review/draft — это ЗАЯВКИ (ещё не взяты в работу), класть в них
    кандидата нельзя, поэтому их НЕ показываем (синхронно с вебом «Мои
    вакансии»). paused/closed/cancelled тоже исключены."""
    org = await get_user_org(current_user, db)
    result = await db.execute(
        select(Vacancy).where(
            Vacancy.org_id == org.id,
            # Только АКТИВНЫЕ воронки (open). pending_review/draft — это заявки, а не
            # рабочие воронки: класть в них кандидата нельзя.
            Vacancy.status == VacancyStatus.open,
            # Soft-deleted воронки не предлагаем — иначе схлопнутый реконсайлом клон
            # (deleted_at выставлен, но status ещё open) снова всплыл бы в дропдауне.
            Vacancy.deleted_at.is_(None),
        ).order_by(Vacancy.title)
    )
    all_vacancies = result.scalars().all()

    def _acceptor_ids(v: Vacancy) -> list:
        return (v.extra_data or {}).get("accepted_by") or []

    vacancies = [v for v in all_vacancies if current_user.id in _acceptor_ids(v)]
    # ОБЩАЯ ВОРОНКА: в дропдаун отдаём ВСЕГДА общую воронку-ОРИГИНАЛ, а не личный
    # клон рекрутёра. РАНЬШЕ делали наоборот (оригинал убирали, оставляли клон) —
    # из-за этого парс уходил в приватный клон рекрутёра (напр. «Трафик» id 126),
    # а сам он смотрел общую воронку (125), и кандидат «пропадал» — даже свой.
    # Теперь: если принятая воронка — это клон (extra_data.cloned_from_request_id=X),
    # подменяем её на оригинал X; сам клон отдельным пунктом не показываем.
    # Дедуп по id и по названию (одну воронку могли «взять» несколько раз).
    # ВАЖНО: работает В ПАРЕ с убранным клон-редиректом в _do_magic_parse — иначе
    # редирект завернул бы target с оригинала обратно в клон.
    by_id = {v.id: v for v in all_vacancies}
    seen_ids: set = set()
    seen_titles: set = set()
    out = []
    for v in vacancies:
        target = v
        src = (v.extra_data or {}).get("cloned_from_request_id")
        if src is not None:
            try:
                original = by_id.get(int(src))
            except (TypeError, ValueError):
                original = None
            if original is None:
                # Оригинал недоступен (не open / вне выборки) — личный клон в
                # дропдаун НЕ тащим, чтобы парс снова не ушёл в приватную воронку.
                continue
            target = original
        if target.id in seen_ids:
            continue
        key = (target.title or "").strip().lower()
        if key in seen_titles:
            continue
        seen_ids.add(target.id)
        seen_titles.add(key)
        out.append({"id": target.id, "title": target.title})
    return out
