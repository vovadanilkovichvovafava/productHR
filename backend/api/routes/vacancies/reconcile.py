"""
Разовое схлопывание легаси-клонов вакансий (только superadmin).

Старая модель «Взять заявку в работу» создавала КЛОН вакансии под рекрутёром
(extra_data.cloned_from_request_id → id оригинала). Модель давно ушла от клонов
(взять = join, не клон), но старые клоны остались и ломают отображение:
сайдбар прячет ОРИГИНАЛ (у которого есть клон) и показывает только клон под его
владельцем, а кандидаты разбросаны по обеим записям и не видят друг друга.

Эта операция сливает каждый клон в его корневой оригинал: переносит заявки
(с дедупом по кандидату — уникальный ключ vacancy_id×entity_id), мягко удаляет
клон. dry_run=true (по умолчанию) — вернуть отчёт, что БУДЕТ сделано, БЕЗ мутаций.
"""
from datetime import datetime
from typing import Dict, List, Optional, Set

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_db
from ...models.database import User, UserRole, Vacancy, VacancyApplication
from ...services.auth import get_current_user
from .common import logger


class CloneReconcileItem(BaseModel):
    clone_id: int
    original_id: Optional[int] = None
    title: str
    action: str  # "merge" | "skip"
    reason: Optional[str] = None
    moved: int = 0       # кандидатов перенесено клон → оригинал
    deduped: int = 0     # кандидатов уже было в оригинале (заявка клона удалена)
    accepted_rescued: bool = False  # у оригинала был пустой accepted_by — взяли из клона


class CloneReconcileReport(BaseModel):
    dry_run: bool
    clones_found: int
    merged: int
    skipped: int
    apps_moved: int
    apps_deduped: int
    items: List[CloneReconcileItem]


def _cloned_from(v: Vacancy) -> Optional[int]:
    cf = (v.extra_data or {}).get("cloned_from_request_id")
    if cf is None or isinstance(cf, bool):
        return None
    # Толерантно к типу: старый код клонирования мог записать id как int ИЛИ как
    # строку «125» — оба должны детектиться как клон, иначе reconcile молча
    # пропускает клон (clones_found=0), хотя он есть.
    try:
        return int(cf)
    except (TypeError, ValueError):
        return None


async def reconcile_clones(
    dry_run: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CloneReconcileReport:
    """Схлопнуть легаси-клоны вакансий в оригиналы. Только суперадмин.

    dry_run=true (по умолчанию) — отчёт БЕЗ изменений. dry_run=false — выполнить.
    Кандидаты не теряются: перенос заявок, а при коллизии (кандидат уже есть в
    оригинале) — оставляем запись оригинала, лишнюю заявку клона удаляем.
    """
    if current_user.role != UserRole.superadmin:
        raise HTTPException(status_code=403, detail="Только суперадмин")

    # Все ЖИВЫЕ вакансии (soft-deleted исключаем) — индекс для резолва корня цепочки.
    rows = (await db.execute(
        select(Vacancy).where(Vacancy.deleted_at.is_(None))
    )).scalars().all()
    by_id: Dict[int, Vacancy] = {v.id: v for v in rows}

    def resolve_root(v: Vacancy) -> Optional[Vacancy]:
        """Дойти до НЕ-клона по цепочке cloned_from_request_id. None — если
        оригинал удалён/битая цепочка."""
        seen: Set[int] = set()
        cur = v
        while True:
            cf = _cloned_from(cur)
            if cf is None:
                return cur
            if cf in seen or cf not in by_id:
                return None
            seen.add(cur.id)
            cur = by_id[cf]

    clones = [v for v in rows if _cloned_from(v) is not None]

    # TEMP DEBUG (снять после диагностики): reconcile возвращает 0 клонов, хотя
    # GET /api/vacancies/126 (та же БД) читает cloned_from_request_id=125. Логируем
    # что реально видит reconcile: сколько воронок, у кого есть ключ, и сырой
    # extra_data вакансии 126.
    _v126 = next((v for v in rows if v.id == 126), None)
    _keyed = [
        v.id for v in rows
        if isinstance(v.extra_data, dict) and v.extra_data.get("cloned_from_request_id") is not None
    ]
    _cf126 = (_v126.extra_data.get("cloned_from_request_id") if (_v126 and isinstance(_v126.extra_data, dict)) else "N/A")
    logger.warning(
        "RECONCILE_DEBUG rows=%d clones=%d keyed_ids=%s v126_in_rows=%s "
        "v126_extra_type=%s cf126=%r cf126_type=%s",
        len(rows), len(clones), _keyed[:30], _v126 is not None,
        type(_v126.extra_data).__name__ if _v126 else "NONE",
        _cf126, type(_cf126).__name__,
    )

    # Кэш кандидатов, уже присутствующих в каждом оригинале — чтобы дедуп был
    # точным и в dry-run (несколько клонов одного оригинала с общим кандидатом).
    root_entities: Dict[int, Set[int]] = {}

    async def entities_of(vac_id: int) -> Set[int]:
        if vac_id not in root_entities:
            ids = (await db.execute(
                select(VacancyApplication.entity_id).where(
                    VacancyApplication.vacancy_id == vac_id
                )
            )).scalars().all()
            root_entities[vac_id] = set(ids)
        return root_entities[vac_id]

    items: List[CloneReconcileItem] = []
    merged = skipped = apps_moved = apps_deduped = 0

    for clone in clones:
        root = resolve_root(clone)
        if root is None or root.id == clone.id:
            skipped += 1
            items.append(CloneReconcileItem(
                clone_id=clone.id, title=clone.title or "",
                action="skip", reason="оригинал не найден или удалён",
            ))
            continue

        clone_apps = (await db.execute(
            select(VacancyApplication).where(VacancyApplication.vacancy_id == clone.id)
        )).scalars().all()
        seen_in_root = await entities_of(root.id)

        moved = deduped = 0
        for app in clone_apps:
            if app.entity_id in seen_in_root:
                deduped += 1
                if not dry_run:
                    await db.delete(app)  # cascade → stage_transitions
            else:
                moved += 1
                seen_in_root.add(app.entity_id)
                if not dry_run:
                    app.vacancy_id = root.id

        # accepted_by спасаем ТОЛЬКО если у оригинала он пуст (клон был единственным
        # активным). Иначе оригинал авторитетен — его ведущие остаются как есть, а
        # владелец клона (переназначенный/вышедший) выпадает вместе с клоном.
        accepted_rescued = False
        oe = dict(root.extra_data or {})
        orig_accepted = oe.get("accepted_by") or []
        clone_accepted = (clone.extra_data or {}).get("accepted_by") or []
        if not orig_accepted and clone_accepted:
            dismissed = set(oe.get("dismissed_by") or [])
            new_accepted = [u for u in clone_accepted if u not in dismissed]
            if new_accepted:
                accepted_rescued = True
                if not dry_run:
                    oe["accepted_by"] = new_accepted
                    root.extra_data = oe

        if not dry_run:
            clone.deleted_at = datetime.utcnow()  # мягко — восстановимо

        merged += 1
        apps_moved += moved
        apps_deduped += deduped
        items.append(CloneReconcileItem(
            clone_id=clone.id, original_id=root.id, title=clone.title or "",
            action="merge", moved=moved, deduped=deduped,
            accepted_rescued=accepted_rescued,
        ))

    if not dry_run:
        await db.commit()
        logger.info(
            f"reconcile_clones: merged={merged} skipped={skipped} "
            f"apps_moved={apps_moved} apps_deduped={apps_deduped}"
        )

    return CloneReconcileReport(
        dry_run=dry_run,
        clones_found=len(clones),
        merged=merged,
        skipped=skipped,
        apps_moved=apps_moved,
        apps_deduped=apps_deduped,
        items=items,
    )
