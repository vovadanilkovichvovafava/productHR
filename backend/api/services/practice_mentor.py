"""Ментор практики — одно значение у человека: тег у ФИО (13.11.2026).

Тикет Маши 13.11.2026 (таблица «трек АТС», «ментор практики»): «Когда
рекрутер указывает ментора практики в карточке кандидата, эта информация
должна автоматически отображаться и на борде… При изменении ментора в
карточке информация на борде также должна обновляться автоматически».

Как было: колонка «Рук. практики» на «Штате» показывала тег у ФИО («Егор» /
«Влад»), НО выбор в этой колонке писался отдельно (`extra_data.board_manager`)
и с тех пор навсегда перебивал тег — поменяли ментора в карточке, а доска
показывает старого. У перенесённых из ClickUp ментор жил в `manager_name` /
`cf:Рук-ль` и в карточке не был виден вовсе (на проде таких 28).

Как стало: ментор — это ТОЛЬКО тег у ФИО. Карточка ставит тег — доска его
показывает; выбор на доске ставит/снимает тот же тег (`set_entity_mentor`).
Менторы — Егор и Влад плюс то, что добавили в список «Рук. практики» на доске
(`own_items(org, "managers")`). Ментор у человека один: выбор другого снимает
прежнего. Старые значения разово переносятся в теги (`migrate_board_mentors_once`,
маркер `BOARD_MENTOR`).
"""
from __future__ import annotations

import logging
from typing import Iterable, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from ..models.database import DataMigrationMark, Entity, NameTag, Organization, entity_name_tag_association

logger = logging.getLogger("hr-analyzer.practice_mentor")

# Встреча 23.09.2026: наставники практики — Егор и Влад (тот же список, что
# PRACTICE_MENTOR_TAGS во фронте, вкладка «Практика»).
BASE_MENTORS = ("Егор", "Влад")
# Старые места, где лежал ментор: выбор на доске (11.11.2026), перенос ClickUp.
LEGACY_KEYS = ("board_manager", "manager_name", "cf:Рук-ль")
MENTOR_TAG_COLOR = "var(--hf-status-pink)"
SYNC_MARK = "board_mentor_to_tags_2026_11_16"


def mentor_names(org: Optional[Organization]) -> list[str]:
    """Кого считаем ментором: Егор, Влад и список «Рук. практики» организации."""
    from .board_catalog import own_items

    names: list[str] = []
    seen: set[str] = set()
    for name in [*BASE_MENTORS, *(own_items(org, "managers") if org is not None else [])]:
        clean = str(name).strip()
        if clean and clean.lower() not in seen:
            seen.add(clean.lower())
            names.append(clean)
    return names


async def org_mentor_names(db: AsyncSession, org_id: int) -> list[str]:
    return mentor_names(await db.get(Organization, org_id))


async def load_mentors(db: AsyncSession, org_id: int, entity_ids: Iterable[int]) -> dict[int, list[str]]:
    """Менторы по тегам у ФИО — одним запросом на всю доску."""
    ids = list({int(i) for i in entity_ids})
    if not ids:
        return {}
    wanted = {n.lower() for n in await org_mentor_names(db, org_id)}
    rows = (await db.execute(
        select(entity_name_tag_association.c.entity_id, NameTag.name)
        .select_from(entity_name_tag_association)
        .join(NameTag, NameTag.id == entity_name_tag_association.c.tag_id)
        .where(entity_name_tag_association.c.entity_id.in_(ids))
        .order_by(NameTag.name)
    )).all()
    out: dict[int, list[str]] = {}
    for ent_id, name in rows:
        if (name or "").strip().lower() in wanted:
            out.setdefault(ent_id, []).append(name.strip())
    return out


async def _mentor_tag(db: AsyncSession, org_id: int, name: str, user_id: Optional[int]) -> NameTag:
    """Тег с этим именем: найти (и вернуть из архива) или завести."""
    tags = (await db.execute(
        select(NameTag).where(NameTag.org_id == org_id)
    )).scalars().all()
    tag = next((t for t in tags if (t.name or "").strip().lower() == name.lower()), None)
    if tag is None:
        tag = NameTag(org_id=org_id, name=name, color=MENTOR_TAG_COLOR, created_by=user_id)
        db.add(tag)
        await db.flush()
    elif tag.archived_at is not None:
        tag.archived_at = None
    return tag


async def set_entity_mentor(
    db: AsyncSession,
    entity: Entity,
    name: Optional[str],
    *,
    user_id: Optional[int] = None,
    names: Optional[list[str]] = None,
) -> Optional[str]:
    """Поставить ментора человеку (пусто — снять). Ментор один: прежние
    теги-менторы снимаются. Старые ключи в extra_data чистятся, чтобы не
    всплыли снова. Не коммитит. Возвращает итоговое имя."""
    names = names if names is not None else await org_mentor_names(db, entity.org_id)
    clean = (name or "").strip()
    # Выбрали имя из списка, но другим регистром — берём каноническое.
    canon = next((n for n in names if n.lower() == clean.lower()), clean)
    lowered = {n.lower() for n in names} | ({canon.lower()} if canon else set())
    current = (await db.execute(
        select(NameTag.id, NameTag.name)
        .join(entity_name_tag_association, entity_name_tag_association.c.tag_id == NameTag.id)
        .where(entity_name_tag_association.c.entity_id == entity.id)
    )).all()
    keep_id = None
    for tag_id, tag_name in current:
        if (tag_name or "").strip().lower() not in lowered:
            continue
        if canon and (tag_name or "").strip().lower() == canon.lower() and keep_id is None:
            keep_id = tag_id
            continue
        await db.execute(delete(entity_name_tag_association).where(
            entity_name_tag_association.c.entity_id == entity.id,
            entity_name_tag_association.c.tag_id == tag_id,
        ))
    if canon and keep_id is None:
        tag = await _mentor_tag(db, entity.org_id, canon, user_id)
        await db.execute(entity_name_tag_association.insert().values(entity_id=entity.id, tag_id=tag.id))
    ex = entity.extra_data if isinstance(entity.extra_data, dict) else {}
    if any(k in ex for k in LEGACY_KEYS):
        entity.extra_data = {k: v for k, v in ex.items() if k not in LEGACY_KEYS}
        flag_modified(entity, "extra_data")
    return canon or None


async def migrate_board_mentors_once(db: AsyncSession) -> int:
    """Разово: ментор из старых ключей → тег у ФИО. Выбор на доске
    (`board_manager`) — последнее явное решение, он главнее; перенос ClickUp
    (`manager_name` / `cf:Рук-ль`) — только если тега-ментора ещё нет и имя
    есть в списке менторов. Коммитит."""
    if await db.get(DataMigrationMark, SYNC_MARK) is not None:
        return 0
    people = (await db.execute(select(Entity).where(Entity.extra_data.is_not(None)))).scalars().all()
    names_by_org: dict[int, list[str]] = {}
    moved = 0
    for e in people:
        ex = e.extra_data if isinstance(e.extra_data, dict) else {}
        if not any(k in ex for k in LEGACY_KEYS):
            continue
        if e.org_id not in names_by_org:
            names_by_org[e.org_id] = await org_mentor_names(db, e.org_id)
        names = names_by_org[e.org_id]
        has_tag = bool((await load_mentors(db, e.org_id, [e.id])).get(e.id))
        if "board_manager" in ex:
            target = str(ex.get("board_manager") or "").strip()
            reason = "board_pick"
        else:
            old = str(ex.get("manager_name") or ex.get("cf:Рук-ль") or "").strip()
            known = next((n for n in names if n.lower() == old.lower()), None)
            if has_tag or not known:
                if old and not known:
                    logger.info("BOARD_MENTOR skip: entity=%s value=%r — не ментор из списка", e.id, old)
                # Тег уже есть (он главнее) или имя не из списка менторов —
                # ключ не трогаем: старое значение остаётся запасным показом.
                if has_tag:
                    e.extra_data = {k: v for k, v in ex.items() if k not in LEGACY_KEYS}
                    flag_modified(e, "extra_data")
                continue
            target, reason = known, "clickup"
        await set_entity_mentor(db, e, target or None, names=names)
        moved += 1
        logger.info("BOARD_MENTOR moved: entity=%s mentor=%r from=%s", e.id, target or "-", reason)
    db.add(DataMigrationMark(key=SYNC_MARK))
    await db.commit()
    logger.info("BOARD_MENTOR: перенесено в теги %s", moved)
    return moved
