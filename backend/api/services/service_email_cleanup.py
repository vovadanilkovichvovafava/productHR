"""Одноразовая чистка служебных почт из карточек кандидатов (22.09.2026).

Расширение сохраняло support@rabota.by как почту кандидата, когда тот свою не
указал (на rabota.by в блоке контактов стоит ссылка на поддержку). У шести
разных людей оказалась одна «почта», и они считались похожими. Теперь такие
адреса не сохраняются (расширение 1.8.9 + проверка на бэкенде), а уже
сохранённые убираются здесь один раз — с пересчётом плашек дублей у затронутых.
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import DataMigrationMark, Entity, EntityType
from .similarity import is_service_email, recheck_duplicates_after_edit

logger = logging.getLogger("hr-analyzer.service_email_cleanup")

CLEANUP_MARK = "service_emails_cleanup_2026_09_22"


async def remove_service_emails_once(db: AsyncSession) -> int:
    """Убрать служебные адреса из email/emails кандидатов. Коммитит.
    Возвращает число исправленных карточек."""
    if await db.get(DataMigrationMark, CLEANUP_MARK) is not None:
        return 0
    candidates = (await db.execute(
        select(Entity).where(Entity.type == EntityType.candidate)
    )).scalars().all()

    fixed = []
    for e in candidates:
        changed = False
        if e.email and is_service_email(e.email):
            e.email = None
            changed = True
        if e.emails:
            kept = [x for x in e.emails if not is_service_email(x)]
            if len(kept) != len(e.emails):
                e.emails = kept
                changed = True
        if changed:
            fixed.append(e)
    await db.flush()

    # Плашки держались на этой «почте» — пересчитываем сразу, а не при открытии.
    for e in fixed:
        try:
            async with db.begin_nested():
                await recheck_duplicates_after_edit(db, e)
        except Exception as ex:  # noqa: BLE001
            logger.warning(f"SERVICE_EMAIL_CLEANUP recheck failed for entity {e.id}: {ex}")

    db.add(DataMigrationMark(key=CLEANUP_MARK))
    await db.commit()
    logger.info(
        f"SERVICE_EMAIL_CLEANUP: removed service emails from {len(fixed)} candidates: "
        f"{[e.id for e in fixed]}"
    )
    return len(fixed)


# --- Ники Telegram-каналов порталов (hh_b2b и т.п.) --------------------------

JUNK_TG_CLEANUP_MARK = "junk_telegram_cleanup_2026_09_22"


async def remove_junk_telegram_once(db: AsyncSession) -> int:
    """Убрать из telegram_usernames кандидатов каналы порталов (hh_b2b, hh, …).

    Старые версии расширения брали со страницы hh.ru ссылку t.me/hh_b2b как ник
    кандидата: у 42 активных карточка и окно сравнения показывали «hh_b2b»
    вместо настоящего ника (он шёл вторым). В сравнении такие ники и раньше не
    участвовали, поэтому плашки дублей не пересчитываются. Коммитит.
    """
    from .similarity import is_junk_telegram

    if await db.get(DataMigrationMark, JUNK_TG_CLEANUP_MARK) is not None:
        return 0
    candidates = (await db.execute(
        select(Entity).where(
            Entity.type == EntityType.candidate,
            Entity.telegram_usernames.is_not(None),
        )
    )).scalars().all()
    fixed = []
    for e in candidates:
        tgs = e.telegram_usernames if isinstance(e.telegram_usernames, list) else []
        kept = [t for t in tgs if t and not is_junk_telegram(t)]
        if len(kept) != len(tgs):
            e.telegram_usernames = kept
            fixed.append(e.id)
    db.add(DataMigrationMark(key=JUNK_TG_CLEANUP_MARK))
    await db.commit()
    logger.info(f"JUNK_TELEGRAM_CLEANUP: cleaned {len(fixed)} candidates: {fixed[:200]}")
    return len(fixed)
