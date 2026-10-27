"""Разведение тегов у ФИО и меток; метки — только сорсеры (решение 21.09.2026).

Было: одна таблица меток ``entity_tags_catalog``, а тег у имени — та же метка с
флагом ``show_at_name`` на связи кандидат↔метка. Стало:

1. Теги у имени живут отдельно (``entity_name_tags_catalog`` + ``entity_name_tags``).
   Всё, что стояло у имени, переезжает туда как есть — кандидату ничего не видно.
2. Метки = сорсеры (кто привёл кандидата). Метки-СЛОВА («перформер»,
   «продуктивный»…) удаляются вместе с проставленными связями — ОДИН раз, по
   списку, согласованному с владельцем. Теги у имени с тем же словом к этому
   моменту уже в своём справочнике и не страдают.
3. Все оставшиеся метки получают kind='sourcer'.

Шаги 1 и 3 идемпотентны и безопасны на каждом старте (на устаканившейся базе
они ничего не пишут). Шаг 2 — одноразовый: помечается в ``data_migration_marks``,
иначе метку «перформер», заведённую позже осознанно, сносило бы при рестарте.
Всё в одной транзакции: сначала перенос тегов, потом удаление слов — наоборот
удаление метки снесло бы и её теги у имени (ON DELETE CASCADE).
"""
import logging
from typing import Dict, Tuple

from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import (
    DataMigrationMark,
    EntityTag,
    NameTag,
    entity_name_tag_association,
    entity_tag_association,
)

logger = logging.getLogger("hr-analyzer.tags_split")

# Метки-слова, которые не люди (прод, 21.09.2026). Сравнение без регистра и
# пробелов по краям.
WORD_LABELS = ("12", "тест", "первформер", "перфомер", "перформер", "продуктивный")
WORDS_MARK = "labels_words_removed_2026_09_21"


async def move_name_tags(db: AsyncSession) -> Tuple[int, int]:
    """Связи с show_at_name=true → теги у имени. Возвращает (тегов, связей)."""
    rows = (await db.execute(
        select(
            entity_tag_association.c.entity_id,
            EntityTag.id, EntityTag.org_id, EntityTag.name, EntityTag.color,
            EntityTag.created_by, EntityTag.archived_at,
        )
        .join(EntityTag, EntityTag.id == entity_tag_association.c.tag_id)
        .where(entity_tag_association.c.show_at_name.is_(True))
    )).all()
    if not rows:
        return 0, 0

    # (org_id, имя без регистра) → id тега у имени
    catalog: Dict[Tuple[int, str], int] = {
        (org_id, name.strip().lower()): tid
        for tid, org_id, name in (await db.execute(
            select(NameTag.id, NameTag.org_id, NameTag.name)
        )).all()
    }
    links = {
        (e, t) for e, t in (await db.execute(
            select(entity_name_tag_association.c.entity_id, entity_name_tag_association.c.tag_id)
        )).all()
    }

    tags_created = links_created = 0
    for entity_id, label_id, org_id, name, color, created_by, archived_at in rows:
        key = (org_id, name.strip().lower())
        tag_id = catalog.get(key)
        if tag_id is None:
            tag_id = (await db.execute(
                insert(NameTag.__table__).values(
                    org_id=org_id, name=name.strip(), color=color,
                    created_by=created_by, archived_at=archived_at,
                ).returning(NameTag.id)
            )).scalar_one()
            catalog[key] = tag_id
            tags_created += 1
        if (entity_id, tag_id) not in links:
            await db.execute(
                insert(entity_name_tag_association).values(entity_id=entity_id, tag_id=tag_id)
            )
            links.add((entity_id, tag_id))
            links_created += 1
        # Тег у имени переехал — как метка у этого кандидата он не стоял.
        await db.execute(
            delete(entity_tag_association).where(
                entity_tag_association.c.entity_id == entity_id,
                entity_tag_association.c.tag_id == label_id,
            )
        )
    return tags_created, links_created


async def remove_word_labels_once(db: AsyncSession) -> int:
    """Удалить метки-слова (и их связи с кандидатами) — один раз."""
    if await db.get(DataMigrationMark, WORDS_MARK) is not None:
        return 0
    # Регистр гасим в Python: lower() в SQLite не трогает кириллицу («Тест»).
    ids = [
        tid for tid, name in (await db.execute(select(EntityTag.id, EntityTag.name))).all()
        if (name or "").strip().lower() in WORD_LABELS
    ]
    if ids:
        await db.execute(delete(entity_tag_association).where(entity_tag_association.c.tag_id.in_(ids)))
        await db.execute(delete(EntityTag).where(EntityTag.id.in_(ids)))
    db.add(DataMigrationMark(key=WORDS_MARK))
    return len(ids)


async def make_all_labels_sourcers(db: AsyncSession) -> int:
    res = await db.execute(
        update(EntityTag).where(EntityTag.kind != "sourcer").values(kind="sourcer")
    )
    return res.rowcount or 0


async def split_tags_and_labels(db: AsyncSession) -> dict:
    """Все три шага в одной транзакции. Безопасно звать на каждом старте."""
    tags_created, links_moved = await move_name_tags(db)
    words_removed = await remove_word_labels_once(db)
    sourcered = await make_all_labels_sourcers(db)
    await db.commit()
    result = {
        "name_tags_created": tags_created,
        "name_tag_links_moved": links_moved,
        "word_labels_removed": words_removed,
        "labels_made_sourcers": sourcered,
    }
    if any(result.values()):
        logger.info("Tags/labels split: %s", result)
    return result
