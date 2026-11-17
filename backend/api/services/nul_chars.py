"""Нулевой символ (\\x00) в данных карточки ломает поиск у всех (17.11.2026).

`entities.extra_data` — колонка типа json (не jsonb): Postgres хранит её как
текст и принимает строку с «\\u0000». Но любой оператор `extra_data -> 'ключ'`
разбирает объект целиком и на таком символе падает: «unsupported Unicode
escape sequence». Поиск кандидатов смотрит комментарии и контакты из резюме
именно так, поэтому ОДНА карточка с нулевым символом (обычно он приезжает из
текста файла резюме) давала 500 на любой запрос поиска — у всех рекрутёров.

Поэтому:
- при каждой записи карточки нулевые символы из extra_data вырезаются
  (`strip_entity_nul`, его зовут обработчики сохранения в search_index.py);
- при старте сервера уже лежащие в базе такие карточки вычищаются
  (`clean_entities_nul`, маркер `NUL_CLEANUP`).
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import Text, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

logger = logging.getLogger("hr-analyzer.nul_chars")

NUL = "\x00"


def has_nul(value: Any) -> bool:
    if isinstance(value, str):
        return NUL in value
    if isinstance(value, dict):
        return any(has_nul(k) or has_nul(v) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return any(has_nul(v) for v in value)
    return False


def strip_nul(value: Any) -> Any:
    """Копия значения без нулевых символов (в строках, ключах, вложенных списках)."""
    if isinstance(value, str):
        return value.replace(NUL, "")
    if isinstance(value, dict):
        return {strip_nul(k): strip_nul(v) for k, v in value.items()}
    if isinstance(value, list):
        return [strip_nul(v) for v in value]
    if isinstance(value, tuple):
        return tuple(strip_nul(v) for v in value)
    return value


def strip_entity_nul(target) -> None:
    """Перед записью карточки: вырезать нулевые символы из extra_data."""
    extra = getattr(target, "extra_data", None)
    if extra is not None and has_nul(extra):
        target.extra_data = strip_nul(extra)


async def clean_entities_nul(db: AsyncSession) -> list[int]:
    """Вычистить нулевые символы у карточек, которые уже лежат в базе."""
    from ..models.database import Entity

    if db.bind.dialect.name != "postgresql":
        return []
    # В тексте json нулевой символ записан как «\u0000» (6 знаков).
    rows = (await db.execute(
        select(Entity.id).where(func.strpos(cast(Entity.extra_data, Text), "\\u0000") > 0)
    )).scalars().all()
    fixed: list[int] = []
    for entity_id in rows:
        entity = await db.get(Entity, entity_id)
        if entity is None or not has_nul(entity.extra_data):
            continue
        entity.extra_data = strip_nul(entity.extra_data)
        flag_modified(entity, "extra_data")
        fixed.append(entity_id)
    if fixed:
        await db.commit()
    logger.info("NUL_CLEANUP: вычищено карточек %s: %s", len(fixed), fixed)
    return fixed
