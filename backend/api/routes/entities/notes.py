"""
Лента карточки кандидата: комментарии, реакции, закреп записи (вынесено из
crud.py, 20.10.2026).

Все записи живут в общем блобе extra_data, который перезаписывается ЦЕЛИКОМ,
поэтому каждая ручка берёт строку кандидата FOR UPDATE — иначе параллельные
писатели затирают друг другу заметки (lost update). Общий вход —
_entity_for_timeline_write: блокировка, своя организация, скоуп по воронкам.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from .common import (
    logger, get_db, Entity, EntityStatus, User, UserRole, VacancyApplication,
    get_current_user, get_user_org, has_full_database_access,
)

router = APIRouter()

# Предел текста комментария — общий с записью о переводе вне воронок.
from ...services.stage_change import NOTE_TEXT_MAX_LENGTH  # noqa: E402


class NoteCreate(BaseModel):
    text: str
    stage: Optional[str] = None
    stage_label: Optional[str] = None
    # Дописка комментария к ПРОШЛОЙ статусной записи таймлайна (запрос Марии):
    # parent_key = reactionKey статусной записи, под которую цепляем коммент
    # (напр. "e:123" для перехода, "n:<uuid>" для стартовой заметки-этапа,
    # "created" для синтетического «Кандидат добавлен»). stage_at_write_label —
    # метка этапа, на котором кандидат был В МОМЕНТ написания коммента (для
    # жёлтой плашки «оставлен на этапе X»). Дату НЕ принимаем — сервер ставит
    # datetime.now(), чтобы дата всегда = момент написания.
    parent_key: Optional[str] = None
    stage_at_write_label: Optional[str] = None
    # Прежний статус кандидата — только для записей о смене этапа У КАНДИДАТА
    # ВНЕ ВОРОНОК. Заявки у него нет, историю (StageTransition) писать некуда,
    # и такая запись живёт комментарием. Чтобы её удаление возвращало кандидата
    # назад — как корзина у записи истории в воронке (28.09.2026) — запоминаем,
    # откуда перевели.
    from_status: Optional[str] = None
    # Воронка (вакансия), в которой написан коммент. Один кандидат может быть в
    # НЕСКОЛЬКИХ воронках — каждая показывает только свои комменты (по vacancy_id).
    # None = «Общий» коммент (написан вне контекста конкретной воронки / легаси).
    vacancy_id: Optional[int] = None


class NoteUpdate(BaseModel):
    text: str


class PinnedEntryUpdate(BaseModel):
    """Закреп записи ленты у кандидата БЕЗ заявок. У кандидата в воронке закреп
    живёт на заявке (одна воронка — один закреп); вне воронок хранить негде,
    поэтому кладём на саму карточку (24.09.2026)."""
    entry_key: Optional[str] = None


def _note_org_check(entity, current_user, org):
    """Общая проверка: org-scope доступа к entity для notes-эндпоинтов."""
    if current_user.role != UserRole.superadmin:
        if not org or entity.org_id != org.id:
            raise HTTPException(404, "Entity not found")


async def _entity_for_timeline_write(db: AsyncSession, entity_id: int, current_user, org) -> Entity:
    """Кандидат для записи в ленту: FOR UPDATE, своя организация, скоуп.

    Было пять одинаковых копий (заметка, реакция, закреп, правка, удаление), и
    ни одна не проверяла скоуп по воронкам: человек, допущенный к одной воронке,
    мог по номеру писать в ленту чужого кандидата. Чужой — 404, как везде.
    """
    result = await db.execute(
        select(Entity).where(Entity.id == entity_id).with_for_update()
    )
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(404, "Entity not found")
    _note_org_check(entity, current_user, org)
    from ...services.vacancy_scope import ensure_entity_visible
    await ensure_entity_visible(entity_id, current_user, db)
    return entity


async def _note_can_modify(note: dict, current_user, org, db) -> bool:
    """Edit/delete: только автор коммента или админ/owner/superadmin.

    F-fix: докстринг всегда обещал «или админ/owner», но код проверял ТОЛЬКО
    superadmin + автора — обычный org-admin/owner получал 403 при попытке
    удалить чужой (например, с @-упоминанием) комментарий.
    """
    if current_user.role == UserRole.superadmin:
        return True
    author_id = note.get("author_id")
    if author_id is not None and int(author_id) == int(current_user.id):
        return True
    if org and await has_full_database_access(current_user, org.id, db):
        return True
    return False


@router.post("/{entity_id}/notes")
async def add_entity_note(
    entity_id: int,
    data: NoteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Добавить комментарий-заметку кандидату.

    Доступно любому пользователю в той же организации, что и entity —
    зеркалит видимость в общем kanban'e /all-candidates (где рекрутёр
    видит всех кандидатов оргa). Комментарий не модифицирует данные
    кандидата, а только дополняет workflow.
    """
    import uuid
    from datetime import timezone as _tz
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org and current_user.role != UserRole.superadmin:
        raise HTTPException(403, "No organization access")

    # FOR UPDATE: заметки живут в общем блобе extra_data, который перезаписывается
    # ЦЕЛИКОМ и здесь, и в hr_tags.sync_for_entity (self-heal при открытии карточки).
    # Без блокировки строки два таких писателя, прочитавших один снимок, при коммите
    # затирают заметки друг друга (lost update) — ровно «пропали НЕКОТОРЫЕ
    # комментарии» у Марии при переводе кандидата в отдел, когда self-heal HR-тегов
    # реально пишет устаревший snapshot. Лок сериализует писателей.
    entity = await _entity_for_timeline_write(db, entity_id, current_user, org)

    text_clean = (data.text or "").strip()
    # Запись о СМЕНЕ ЭТАПА у кандидата вне воронок может быть без текста: в
    # воронке такой перевод всегда оставляет строку в истории, и здесь лента
    # должна вести себя так же (28.09.2026). Обычный комментарий без текста
    # по-прежнему не принимаем.
    if not text_clean and not data.stage:
        raise HTTPException(400, "Comment text cannot be empty")
    if len(text_clean) > NOTE_TEXT_MAX_LENGTH:
        raise HTTPException(400, f"Comment too long (max {NOTE_TEXT_MAX_LENGTH})")

    extra = dict(entity.extra_data or {})
    notes = list(extra.get("notes") or [])
    note = {
        "id": str(uuid.uuid4()),
        "text": text_clean,
        "date": datetime.now(_tz.utc).isoformat(),
        "stage": data.stage,
        "stage_label": data.stage_label,
        "author_id": current_user.id,
        "author_name": current_user.name,
    }
    # Привязка к статусной записи + этап-на-момент-написания — только если переданы,
    # чтобы не засорять обычные комментарии пустыми ключами.
    if data.parent_key:
        note["parent_key"] = data.parent_key
    if data.stage_at_write_label:
        note["stage_at_write_label"] = data.stage_at_write_label
    if data.from_status:
        note["from_status"] = data.from_status
    # Метка воронки — чтобы в каждой вакансии показывать только её комменты.
    if data.vacancy_id is not None:
        note["vacancy_id"] = data.vacancy_id
    notes.append(note)
    extra["notes"] = notes
    entity.extra_data = extra
    # Сначала ГАРАНТИРОВАННО коммитим сам комментарий — его сохранность не должна
    # зависеть от уведомлений об @-упоминаниях (иначе при сбое/медленном notify
    # коммент «появлялся только после F5»).
    await db.commit()
    await db.refresh(entity)

    # @-упоминания — ОТДЕЛЬНОЙ транзакцией: достаём data-uid из HTML и шлём
    # упомянутым уведомление «как у анкет». Падение здесь уже не трогает коммент.
    try:
        from ...services.hr_notifications import notify_comment_mentions
        await notify_comment_mentions(
            db, text=text_clean, author=current_user, entity=entity
        )
        await db.commit()
    except Exception:
        await db.rollback()

    return {"success": True, "note": note, "total_notes": len(notes)}


class TimelineReactionRequest(BaseModel):
    entry_key: str
    emoji: str


@router.post("/{entity_id}/timeline-reaction")
async def toggle_timeline_reaction(
    entity_id: int,
    data: TimelineReactionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Тоггл эмодзи-реакции на запись таймлайна (лог карточки).

    entry_key — стабильный ключ записи (id заметки / history-id события / 'created').
    Реакции хранятся в extra_data.timeline_reactions[entry_key] = [{emoji, user_id,
    user_name, date}]. Повторный клик тем же эмодзи снимает реакцию (toggle).
    Доступно любому в той же организации (как и заметки).
    """
    from datetime import timezone as _tz
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)
    if not org and current_user.role != UserRole.superadmin:
        raise HTTPException(403, "No organization access")

    # FOR UPDATE — см. add_entity_note. Реакции живут в том же блобе extra_data,
    # а кликают их часто и быстро: без блокировки тоггл реакции спокойно затирает
    # только что добавленный комментарий.
    entity = await _entity_for_timeline_write(db, entity_id, current_user, org)

    key = (data.entry_key or "").strip()
    emoji = (data.emoji or "").strip()
    if not key or not emoji:
        raise HTTPException(400, "entry_key and emoji are required")
    if len(emoji) > 16:
        raise HTTPException(400, "emoji too long")

    extra = dict(entity.extra_data or {})
    reactions = dict(extra.get("timeline_reactions") or {})
    entry = list(reactions.get(key) or [])
    # toggle: снять, если я уже ставил ЭТОТ эмодзи; иначе добавить
    idx = next(
        (
            i for i, r in enumerate(entry)
            if isinstance(r, dict)
            and r.get("user_id") == current_user.id
            and r.get("emoji") == emoji
        ),
        -1,
    )
    if idx >= 0:
        entry.pop(idx)
    else:
        entry.append({
            "emoji": emoji,
            "user_id": current_user.id,
            "user_name": current_user.name,
            "date": datetime.now(_tz.utc).isoformat(),
        })
    if entry:
        reactions[key] = entry
    else:
        reactions.pop(key, None)
    extra["timeline_reactions"] = reactions
    entity.extra_data = extra
    await db.commit()
    return {"success": True, "entry_key": key, "reactions": entry}


def _find_note_index(notes: list, note_id: str) -> int:
    """Ищем по id; для legacy-комментов без id допускаем поиск по date."""
    for i, n in enumerate(notes):
        if isinstance(n, dict):
            if n.get("id") == note_id:
                return i
            # legacy fallback: id-формат "date:<iso>" (фронт может прислать)
            if note_id.startswith("date:") and n.get("date") == note_id[5:]:
                return i
    return -1


@router.put("/{entity_id}/pin")
async def set_entity_pinned_entry(
    entity_id: int,
    data: PinnedEntryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Закрепить запись ленты кандидата вне воронок (entry_key = null — снять).

    Закреп общий для всех, кто видит карточку, как и у воронок.
    """
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)

    # FOR UPDATE — extra_data перезаписывается целиком: без блокировки
    # параллельная заметка затёрла бы закреп (та же причина, что в notes).
    entity = await _entity_for_timeline_write(db, entity_id, current_user, org)

    key = (data.entry_key or "").strip() or None
    if key and len(key) > 64:
        raise HTTPException(400, "Слишком длинный ключ записи")

    extra = dict(entity.extra_data or {})
    if key:
        extra["pinned_entry_key"] = key
    else:
        extra.pop("pinned_entry_key", None)
    entity.extra_data = extra
    await db.commit()
    logger.info(
        "ENTRY_PIN entity=%s user=%s -> %s", entity_id, current_user.id, key or "снят",
    )
    return {"success": True, "pinned_entry_key": key}


@router.patch("/{entity_id}/notes/{note_id}")
async def update_entity_note(
    entity_id: int,
    note_id: str,
    data: NoteUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Редактировать комментарий — автор, org-admin/owner или superadmin."""
    from datetime import timezone as _tz
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)

    # FOR UPDATE — по той же причине, что в add_entity_note: extra_data
    # перезаписывается ЦЕЛИКОМ, и без блокировки правка коммента затирает
    # заметки/реакции, добавленные параллельным писателем (lost update).
    entity = await _entity_for_timeline_write(db, entity_id, current_user, org)

    text_clean = (data.text or "").strip()
    if not text_clean:
        raise HTTPException(400, "Comment text cannot be empty")
    if len(text_clean) > NOTE_TEXT_MAX_LENGTH:
        raise HTTPException(400, f"Comment too long (max {NOTE_TEXT_MAX_LENGTH})")

    extra = dict(entity.extra_data or {})
    notes = list(extra.get("notes") or [])
    idx = _find_note_index(notes, note_id)
    if idx < 0:
        raise HTTPException(404, "Comment not found")

    note = dict(notes[idx])
    if not await _note_can_modify(note, current_user, org, db):
        raise HTTPException(403, "You can only edit your own comments")

    note["text"] = text_clean
    note["edited_at"] = datetime.now(_tz.utc).isoformat()
    # Кто правил — для подсказки «Изменено: Настя, сегодня 09:36»: в строке
    # ленты остаётся автор комментария, а правившего видно при наведении
    # (24.09.2026). Раньше писали только время, и автор правки терялся.
    note["edited_by"] = current_user.id
    note["edited_by_name"] = current_user.name
    notes[idx] = note
    extra["notes"] = notes
    entity.extra_data = extra
    await db.commit()
    await db.refresh(entity)
    return {"success": True, "note": note}


@router.delete("/{entity_id}/notes/{note_id}")
async def delete_entity_note(
    entity_id: int,
    note_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Удалить комментарий — автор, org-admin/owner или superadmin."""
    current_user = await db.merge(current_user)
    org = await get_user_org(current_user, db)

    # FOR UPDATE — см. add_entity_note: удаление одного коммента переписывает
    # весь extra_data, поэтому без блокировки оно затрёт заметку, которую в этот
    # момент добавляет коллега (или self-heal HR-тегов). Это ровно тот «пропали
    # НЕКОТОРЫЕ комментарии», который чинили в POST, но не тут.
    entity = await _entity_for_timeline_write(db, entity_id, current_user, org)

    extra = dict(entity.extra_data or {})
    notes = list(extra.get("notes") or [])
    idx = _find_note_index(notes, note_id)
    if idx < 0:
        raise HTTPException(404, "Comment not found")

    if not await _note_can_modify(notes[idx], current_user, org, db):
        raise HTTPException(403, "You can only delete your own comments")

    removed = notes.pop(idx)
    extra["notes"] = notes

    # Удалили запись о переводе у кандидата ВНЕ воронок — возвращаем его на
    # прежний статус, как это делает корзина у записи истории в воронке. Без
    # этого поведение разъезжалось: в воронке кандидат откатывался, а вне её
    # запись просто пропадала, и он оставался на новом этапе (владелец,
    # 28.09.2026). Откатываем ТОЛЬКО если запись описывает текущий статус —
    # этап уже подвинули руками, значит, она его больше не описывает, — И
    # только если это САМАЯ СВЕЖАЯ запись о переводе, как в воронке: старые
    # выше по ленте — чистка лога, этап они не двигают. Без этой проверки
    # удаление ЛЮБОЙ старой записи с тем же статусом отбрасывало кандидата в
    # прошлое: у Саленик (21.10.2026) статус так вернулся в «Перевёлся», хотя
    # в воронке уже стоял «Отказ», — карточка и доска разъехались.
    from_status = removed.get("from_status")
    current_status = entity.status.value if entity.status else None
    latest_stage_note = max(
        (n for n in notes if isinstance(n, dict) and n.get("stage")),
        key=lambda n: str(n.get("date") or ""),
        default=None,
    )
    removed_is_latest = (
        latest_stage_note is None
        or str(removed.get("date") or "") >= str(latest_stage_note.get("date") or "")
    )
    if (
        from_status
        and removed.get("stage")
        and removed.get("stage") == current_status
        and removed_is_latest
    ):
        try:
            entity.status = EntityStatus(from_status)
            entity.updated_at = datetime.utcnow()
            logger.info(
                "NOTE_STAGE_UNDO: entity=%s %s -> %s (удалена запись о переводе)",
                entity_id, current_status, from_status,
            )
        except ValueError:
            logger.warning("NOTE_STAGE_UNDO: неизвестный статус %s", from_status)
    # Закреп должен уйти вместе с комментарием. Иначе ключ указывает в пустоту
    # (прод 28.09.2026: «закрепил, удалил не открепив») — закреп висит на
    # несуществующей записи и мешает понять, что вообще закреплено.
    pin_key = f"n:{removed.get('id') or note_id}"
    if extra.get("pinned_entry_key") == pin_key:
        extra.pop("pinned_entry_key", None)
        logger.info("ENTRY_PIN снят вместе с комментарием: entity=%s %s", entity_id, pin_key)
    entity.extra_data = extra

    # Тот же комментарий мог быть закреплён в воронке — там закреп живёт на
    # заявке, и его надо снять отдельно.
    from ...models.database import VacancyApplication
    apps = (await db.execute(
        select(VacancyApplication).where(
            VacancyApplication.entity_id == entity_id,
            VacancyApplication.pinned_entry_key == pin_key,
        )
    )).scalars().all()
    for app in apps:
        app.pinned_entry_key = None
        logger.info("ENTRY_PIN снят вместе с комментарием: app=%s %s", app.id, pin_key)

    await db.commit()
    await db.refresh(entity)
    return {
        "success": True,
        "total_notes": len(notes),
        # Фронт по этим полям переставляет карточку на месте, без перезагрузки.
        "rolled_back": bool(from_status) and entity.status is not None
        and entity.status.value == from_status,
        "entity_status": entity.status.value if entity.status else None,
    }
