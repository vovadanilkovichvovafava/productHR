"""«В предыдущих сериях»: случайное «закрыл — открыл» не начинает новый набор (12.11.2026).

Переоткрытие вакансии (closed → open) ставит `Vacancy.reopened_at`, и все
отклики, которых с тех пор не двигали, уходят под «В предыдущих сериях» с
серой карточкой. 11.11.2026 Мария закрыла «Персонального ассистента» и через
две минуты открыла снова — 177 из 178 кандидатов Влады стали серыми
(«почему у Влады всё серым»). Новый набор так не начинают.

Правило: открыли снова меньше чем через `QUICK_REOPEN` после закрытия — это
исправление ошибки, точка отсчёта серии остаётся прежней. Когда закрыли,
сервер помнит в `extra_data.closed_at` (серверный ключ, форма его не стирает).
У вакансий, закрытых до этого правила, `closed_at` нет — их переоткрытие, как
и раньше, начинает новую серию.

Разовый шаг `undo_quick_reopens_once` применяет то же правило к уже
случившимся переоткрытиям по журналу действий. Маркер `VACANCY_SERIES`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import AuditEvent, DataMigrationMark, Vacancy, VacancyStatus

logger = logging.getLogger("hr-analyzer.vacancy_series")

QUICK_REOPEN = timedelta(hours=24)
CLOSED_STATUSES = (VacancyStatus.closed, VacancyStatus.cancelled)
SYNC_MARK = "vacancy_quick_reopen_2026_11_12"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _closed_at(vacancy: Vacancy) -> Optional[datetime]:
    raw = (vacancy.extra_data or {}).get("closed_at")
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw).replace(tzinfo=None)
    except ValueError:
        return None


def remember_closed(vacancy: Vacancy, now: Optional[datetime] = None) -> None:
    """Вакансию только что закрыли — запомнить когда."""
    stamp = (now or _utcnow()).isoformat()
    vacancy.extra_data = {**(vacancy.extra_data or {}), "closed_at": stamp}


def apply_reopen(vacancy: Vacancy, now: Optional[datetime] = None) -> bool:
    """Вакансию открыли снова. True — началась новая серия."""
    now = now or _utcnow()
    closed_at = _closed_at(vacancy)
    if closed_at is not None and now - closed_at < QUICK_REOPEN:
        logger.info(
            "VACANCY_SERIES quick_reopen: vacancy=%s closed_at=%s — серия прежняя",
            vacancy.id, closed_at.isoformat(timespec="seconds"),
        )
        return False
    vacancy.reopened_at = now
    return True


def _is_close_body(body) -> bool:
    return isinstance(body, dict) and body.get("status") in ("closed", "cancelled")


async def undo_quick_reopens_once(db: AsyncSession) -> list[int]:
    """Снять отметку переоткрытия, если до него вакансию закрыли меньше суток
    назад (по журналу действий). Одноразово, коммитит."""
    if await db.get(DataMigrationMark, SYNC_MARK) is not None:
        return []
    reopened = (await db.execute(
        select(Vacancy).where(Vacancy.reopened_at.is_not(None))
    )).scalars().all()
    fixed: list[int] = []
    for v in reopened:
        events = (await db.execute(
            select(AuditEvent)
            .where(
                AuditEvent.vacancy_id == v.id,
                AuditEvent.method == "PUT",
                AuditEvent.status == 200,
                AuditEvent.at <= v.reopened_at,
            )
            .order_by(AuditEvent.at.desc())
            .limit(50)
        )).scalars().all()
        close = next((e for e in events if _is_close_body(e.body)), None)
        if close is None or v.reopened_at - close.at >= QUICK_REOPEN:
            continue
        logger.info(
            "VACANCY_SERIES undo: vacancy=%s closed=%s reopened=%s",
            v.id, close.at.isoformat(timespec="seconds"), v.reopened_at.isoformat(timespec="seconds"),
        )
        v.reopened_at = None
        fixed.append(v.id)
    db.add(DataMigrationMark(key=SYNC_MARK))
    await db.commit()
    logger.info("VACANCY_SERIES: снято случайных переоткрытий %s: %s", len(fixed), fixed)
    return fixed
