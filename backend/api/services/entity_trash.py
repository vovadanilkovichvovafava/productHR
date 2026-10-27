"""Корзина кандидатов: слепок перед удалением и возврат как был (20.10.2026).

Случай 19.10.2026: кандидатку удалили, и ни кто, ни когда — не записалось, а
вернуть было нечем. Удаление стирает кандидата каскадом вместе с заявками,
историей этапов, файлами, метками, назначениями на доске «Штат» и т.д.; у чатов,
звонков и ответов анкет ссылка на кандидата просто обнуляется.

Поэтому перед удалением снимаем СЛЕПОК: строку кандидата и все строки, которые
каскад сотрёт (обходим внешние ключи по моделям — новая таблица со ссылкой на
кандидата попадёт в слепок сама), плюс список обнулённых ссылок. Возврат
вставляет строки обратно с теми же номерами (родители раньше детей) и
восстанавливает обнулённые ссылки. Всё в одной транзакции: не вышло — не
вернули ничего, кандидат остаётся в корзине, причина — в ответе.

С 21.10.2026 так же устроено «Удалить с воронки»: корень слепка — заявка
(vacancy_applications), с ней уходят её история этапов и прочее, что каскад
сотрёт. Карточка кандидата при этом остаётся, поэтому в корзине это отдельная
строка «убран из воронки „…“» (kind = application).
"""
from __future__ import annotations

import base64
import enum
import logging
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import Base, DeletedEntity, Entity, User, Vacancy, VacancyApplication

logger = logging.getLogger("hr-analyzer.entity_trash")

TRASH_DAYS = 7
ROOT_TABLE = "entities"
APPLICATION_TABLE = "vacancy_applications"
KIND_ENTITY = "entity"
KIND_APPLICATION = "application"


def root_table_of(record: DeletedEntity) -> str:
    return APPLICATION_TABLE if record.kind == KIND_APPLICATION else ROOT_TABLE


# --- значения колонок ⇄ JSON ---------------------------------------------------

def _encode(value: Any) -> Any:
    if isinstance(value, datetime):
        return {"__dt": value.isoformat()}
    if isinstance(value, date):
        return {"__d": value.isoformat()}
    if isinstance(value, Decimal):
        return {"__dec": str(value)}
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"__b": base64.b64encode(bytes(value)).decode()}
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def _decode(column, value: Any) -> Any:
    if isinstance(value, dict) and len(value) == 1:
        (tag, raw), = value.items()
        if tag == "__dt":
            return datetime.fromisoformat(raw)
        if tag == "__d":
            return date.fromisoformat(raw)
        if tag == "__dec":
            return Decimal(raw)
        if tag == "__b":
            return base64.b64decode(raw)
    enum_class = getattr(column.type, "enum_class", None)
    if enum_class is not None and isinstance(value, str):
        try:
            return enum_class(value)
        except ValueError:
            return enum_class[value]
    return value


# --- граф ссылок на кандидата ---------------------------------------------------

def _children(table_name: str) -> List[Tuple[Any, Any, Any, Optional[str]]]:
    """(дочерняя таблица, её колонка, колонка родителя, ondelete) для table_name."""
    out = []
    for t in Base.metadata.sorted_tables:
        for fk in t.foreign_keys:
            if fk.column.table.name == table_name:
                out.append((t, fk.parent, fk.column, (fk.ondelete or "").upper() or None))
    return out


def _pk(table, row: dict) -> tuple:
    cols = [c.name for c in table.primary_key.columns] or [c.name for c in table.columns]
    return tuple(row.get(c) for c in cols)


async def snapshot_entity(db: AsyncSession, entity_id: int) -> Dict[str, Any]:
    """Всё, что удаление кандидата сотрёт или отвяжет. Ничего не пишет."""
    return await snapshot_rows(db, ROOT_TABLE, entity_id)


async def snapshot_rows(db: AsyncSession, root_table: str, root_id: int) -> Dict[str, Any]:
    """Всё, что удаление строки root_table/root_id сотрёт каскадом или отвяжет."""
    md = Base.metadata
    rows: Dict[str, Dict[tuple, dict]] = {}
    links: List[dict] = []

    async def fetch(table, where) -> List[dict]:
        res = await db.execute(select(table).where(where))
        return [dict(r._mapping) for r in res]

    root = md.tables[root_table]
    found = await fetch(root, root.c.id == root_id)
    if not found:
        raise LookupError(f"{root_table} {root_id} not found")
    rows[root_table] = {_pk(root, r): r for r in found}

    queue = [root_table]
    while queue:
        parent_name = queue.pop(0)
        parent_rows = list(rows.get(parent_name, {}).values())
        for child, col, ref_col, ondelete in _children(parent_name):
            values = sorted({r[ref_col.name] for r in parent_rows if r.get(ref_col.name) is not None})
            if not values:
                continue
            got = await fetch(child, col.in_(values))
            if not got:
                continue
            if ondelete == "CASCADE":
                bucket = rows.setdefault(child.name, {})
                new = False
                for r in got:
                    key = _pk(child, r)
                    if key not in bucket:
                        bucket[key] = r
                        new = True
                if new:
                    queue.append(child.name)
            elif ondelete == "SET NULL":
                pk_cols = [c.name for c in child.primary_key.columns]
                for r in got:
                    links.append({
                        "table": child.name,
                        "pk": {c: _encode(r[c]) for c in pk_cols},
                        "column": col.name,
                        "value": _encode(r[col.name]),
                    })
    return {
        "version": 1,
        "tables": {
            name: [{k: _encode(v) for k, v in r.items()} for r in bucket.values()]
            for name, bucket in rows.items()
        },
        "links": links,
    }


async def move_to_trash(
    db: AsyncSession, entity: Entity, user: User, *, now: Optional[datetime] = None,
) -> DeletedEntity:
    """Снять слепок и записать в журнал. Само удаление делает вызывающий."""
    now = now or datetime.utcnow()
    snap = await snapshot_entity(db, entity.id)
    record = DeletedEntity(
        org_id=entity.org_id,
        entity_id=entity.id,
        entity_name=entity.name,
        entity_type=entity.type.value if hasattr(entity.type, "value") else entity.type,
        deleted_by_id=user.id,
        deleted_by_name=user.name,
        deleted_at=now,
        purge_after=now + timedelta(days=TRASH_DAYS),
        snapshot=snap,
    )
    db.add(record)
    return record


async def move_application_to_trash(
    db: AsyncSession,
    application: VacancyApplication,
    vacancy: Optional[Vacancy],
    entity: Optional[Entity],
    user: User,
    *,
    now: Optional[datetime] = None,
) -> DeletedEntity:
    """«Удалить с воронки»: слепок заявки (этап, автор, история, закреп) в
    корзину. Само удаление делает вызывающий. Не коммитит."""
    now = now or datetime.utcnow()
    snap = await snapshot_rows(db, APPLICATION_TABLE, application.id)
    owner_id = application.created_by or (vacancy.created_by if vacancy else None)
    owner = await db.get(User, owner_id) if owner_id else None
    stage = application.stage.value if hasattr(application.stage, "value") else application.stage
    record = DeletedEntity(
        org_id=(vacancy.org_id if vacancy else None) or (entity.org_id if entity else None),
        kind=KIND_APPLICATION,
        entity_id=application.entity_id,
        entity_name=entity.name if entity else None,
        entity_type=(entity.type.value if entity is not None and hasattr(entity.type, "value") else None),
        vacancy_id=application.vacancy_id,
        vacancy_title=vacancy.title if vacancy else None,
        owner_name=owner.name if owner else None,
        stage=stage,
        deleted_by_id=user.id,
        deleted_by_name=user.name,
        deleted_at=now,
        purge_after=now + timedelta(days=TRASH_DAYS),
        snapshot=snap,
    )
    db.add(record)
    return record


class RestoreError(Exception):
    """Вернуть нельзя — текст для человека."""


async def restore_from_trash(db: AsyncSession, record: DeletedEntity, user: User) -> Dict[str, int]:
    """Вставить слепок обратно. Не коммитит.

    Сам кандидат возвращается обязательно (не вышло — RestoreError, ничего не
    меняем). Связанные строки — каждая отдельно: если за неделю удалили, скажем,
    воронку или второго кандидата из пары «Разные люди», эта строка не вернётся,
    а остальное — вернётся. Возвращает {таблица: сколько строк не вернулось}.
    """
    if record.restored_at is not None:
        raise RestoreError("Кандидат уже возвращён")
    if not record.snapshot:
        raise RestoreError("Срок хранения в корзине истёк — вернуть уже нельзя")
    root_name = root_table_of(record)
    md = Base.metadata
    tables = record.snapshot.get("tables") or {}
    if root_name == ROOT_TABLE:
        exists = (await db.execute(select(Entity.id).where(Entity.id == record.entity_id))).scalar()
        if exists:
            raise RestoreError("Карточка с этим номером уже есть")
    else:
        await _check_application_restorable(db, record)

    def _values(table, raw: dict) -> dict:
        return {k: _decode(table.c[k], v) for k, v in raw.items() if k in table.c}

    root = md.tables[root_name]
    try:
        async with db.begin_nested():
            for raw in tables.get(root_name) or []:
                await db.execute(root.insert().values(**_values(root, raw)))
    except Exception as e:  # noqa: BLE001
        logger.warning("ENTITY_RESTORE failed: record=%s entity=%s: %s", record.id, record.entity_id, e)
        raise RestoreError("Не удалось вернуть — подробности в логе ENTITY_RESTORE") from e

    skipped: Dict[str, int] = {}
    for table in md.sorted_tables:  # родители раньше детей
        if table.name == root_name:
            continue
        for raw in tables.get(table.name) or []:
            try:
                async with db.begin_nested():
                    await db.execute(table.insert().values(**_values(table, raw)))
            except Exception as e:  # noqa: BLE001
                skipped[table.name] = skipped.get(table.name, 0) + 1
                logger.info("ENTITY_RESTORE skip %s: %s", table.name, str(e)[:200])

    for link in record.snapshot.get("links") or []:
        table = md.tables.get(link["table"])
        if table is None or link["column"] not in table.c:
            continue
        col = table.c[link["column"]]
        cond = [table.c[k] == _decode(table.c[k], v) for k, v in link["pk"].items() if k in table.c]
        # Только если ссылку за это время никто не поставил заново.
        await db.execute(
            update(table)
            .where(and_(*cond), col.is_(None))
            .values({col.name: _decode(col, link["value"])})
        )

    record.restored_at = datetime.utcnow()
    record.restored_by_id = user.id
    record.restored_by_name = user.name
    return skipped


async def _check_application_restorable(db: AsyncSession, record: DeletedEntity) -> None:
    """Вернуть заявку можно, только если есть куда: кандидат и воронка живы, а
    его не добавили в эту воронку заново (одна заявка на пару «кандидат +
    воронка»). Иначе — понятная причина вместо ошибки базы."""
    raw = ((record.snapshot.get("tables") or {}).get(APPLICATION_TABLE) or [{}])[0]
    app_id = raw.get("id")
    if not (await db.execute(select(Entity.id).where(Entity.id == record.entity_id))).scalar():
        raise RestoreError("Кандидата удалили целиком — сначала верните его самого")
    vacancy = await db.get(Vacancy, record.vacancy_id) if record.vacancy_id else None
    if vacancy is None or getattr(vacancy, "deleted_at", None) is not None:
        raise RestoreError("Воронку удалили — вернуть в неё нельзя")
    again = (await db.execute(
        select(VacancyApplication.id).where(
            VacancyApplication.vacancy_id == record.vacancy_id,
            VacancyApplication.entity_id == record.entity_id,
        )
    )).scalar()
    if again:
        raise RestoreError(
            "Кандидата уже снова добавили в эту воронку — уберите новую заявку, если нужна прежняя"
        )
    if app_id is not None and (await db.execute(
        select(VacancyApplication.id).where(VacancyApplication.id == app_id)
    )).scalar():
        raise RestoreError("Заявка уже на месте")


async def purge_expired(db: AsyncSession, *, now: Optional[datetime] = None) -> int:
    """Стереть слепки старше срока. Строка журнала остаётся. Не коммитит."""
    now = now or datetime.utcnow()
    res = await db.execute(
        update(DeletedEntity)
        .where(
            DeletedEntity.purge_after < now,
            DeletedEntity.purged_at.is_(None),
            DeletedEntity.restored_at.is_(None),
        )
        .values(snapshot=None, purged_at=now)
    )
    return res.rowcount or 0


def snapshot_summary(snapshot: Optional[dict]) -> Dict[str, Any]:
    """Что в слепке — для списка корзины: сколько воронок, файлов, записей истории."""
    if not snapshot:
        return {}
    t = snapshot.get("tables") or {}
    return {
        "applications": len(t.get("vacancy_applications") or []),
        "history": len(t.get("stage_transitions") or []),
        "files": len(t.get("entity_files") or []),
    }


# --- просмотр удалённой карточки (23.10.2026) --------------------------------
# Владелец: «пусть открывается как обычная карточка». Карточку собираем из
# слепка в тех же полях, что строка «Все кандидаты» + блоки воронок (как
# /entities/{id}/activity), чтобы фронт нарисовал её теми же компонентами.

def _plain(value: Any) -> Any:
    """Значение слепка для ответа: даты — ISO-строкой, байты не отдаём."""
    if isinstance(value, dict) and len(value) == 1:
        (tag, raw), = value.items()
        if tag in ("__dt", "__d", "__dec"):
            return raw
        if tag == "__b":
            return None
    return value


def _rows(record: DeletedEntity, table: str) -> List[Dict[str, Any]]:
    rows = ((record.snapshot or {}).get("tables") or {}).get(table) or []
    return [{k: _plain(v) for k, v in r.items()} for r in rows]


def _card_fields(ent: Dict[str, Any], owner_name: Optional[str]) -> Dict[str, Any]:
    from .similarity import first_real_telegram
    extra = ent.get("extra_data") if isinstance(ent.get("extra_data"), dict) else {}
    return {
        "id": ent.get("id"),
        "name": ent.get("name") or "",
        "email": ent.get("email"),
        "phone": ent.get("phone"),
        "emails": ent.get("emails") or [],
        "phones": ent.get("phones") or [],
        "telegram_username": first_real_telegram(ent.get("telegram_usernames") or []),
        "telegram_usernames": ent.get("telegram_usernames") or [],
        "position": ent.get("position"),
        "company": ent.get("company"),
        "status": ent.get("status"),
        "created_at": ent.get("created_at"),
        "recruiter_id": ent.get("created_by"),
        "recruiter_name": owner_name,
        "source": extra.get("source"),
        "source_url": extra.get("source_url"),
        "city": extra.get("city") or extra.get("location"),
        "age": extra.get("age"),
        "salary": extra.get("salary"),
        "total_experience": extra.get("total_experience"),
        "tags": ent.get("tags") or [],
        "extra_data": extra,
    }


async def trash_card_view(db: AsyncSession, record: DeletedEntity) -> Dict[str, Any]:
    """Карточка из корзины: поля карточки, блоки воронок с историей, файлы."""
    from ..models.database import Entity, User, Vacancy

    kind = record.kind or KIND_ENTITY
    if kind == KIND_APPLICATION:
        # Убрали только из воронки: сама карточка живая — берём её как есть.
        live = await db.get(Entity, record.entity_id)
        ent = {c.name: _plain(_encode(getattr(live, c.name))) for c in Entity.__table__.columns} if live else {
            "id": record.entity_id, "name": record.entity_name,
        }
    else:
        ent = (_rows(record, ROOT_TABLE) or [{"id": record.entity_id, "name": record.entity_name}])[0]

    apps = _rows(record, APPLICATION_TABLE)
    transitions = _rows(record, "stage_transitions")
    files = _rows(record, "entity_files")

    user_ids = {t.get("changed_by") for t in transitions} | {ent.get("created_by")} | {a.get("created_by") for a in apps}
    user_ids = {u for u in user_ids if u}
    names = dict((await db.execute(select(User.id, User.name).where(User.id.in_(user_ids)))).all()) if user_ids else {}
    vac_ids = {a.get("vacancy_id") for a in apps if a.get("vacancy_id")}
    titles = dict((await db.execute(select(Vacancy.id, Vacancy.title).where(Vacancy.id.in_(vac_ids)))).all()) if vac_ids else {}

    blocks = []
    for a in apps:
        events = sorted(
            (t for t in transitions if t.get("application_id") == a.get("id")),
            key=lambda t: t.get("created_at") or "",
        )
        blocks.append({
            "application_id": a.get("id"),
            "vacancy_id": a.get("vacancy_id"),
            "vacancy_title": titles.get(a.get("vacancy_id")) or record.vacancy_title or f"Вакансия #{a.get('vacancy_id')}",
            "current_stage": a.get("stage") or "applied",
            "applied_at": a.get("applied_at"),
            "last_stage_change_at": a.get("last_stage_change_at"),
            "recruiter_name": names.get(a.get("created_by")),
            "pinned_entry_key": a.get("pinned_entry_key"),
            "events": [{
                "id": t.get("id"), "from_stage": t.get("from_stage"), "to_stage": t.get("to_stage"),
                "comment": t.get("comment"), "changed_by_name": names.get(t.get("changed_by")),
                "created_at": t.get("created_at"),
                "edited_at": t.get("edited_at"), "edited_by_name": names.get(t.get("edited_by")),
            } for t in events],
        })

    card = _card_fields(ent, names.get(ent.get("created_by")))
    if kind == KIND_APPLICATION:
        # Из ленты живой карточки — только комментарии этой воронки.
        notes = (card["extra_data"] or {}).get("notes") or []
        card["extra_data"] = {**card["extra_data"], "notes": [
            n for n in notes if isinstance(n, dict) and n.get("vacancy_id") == record.vacancy_id
        ]}
    file_list = [{
        "id": f.get("id"), "file_name": f.get("file_name"), "file_type": f.get("file_type"),
        "mime_type": f.get("mime_type"), "file_size": f.get("file_size"),
        "description": f.get("description"), "created_at": f.get("created_at"),
    } for f in files]
    photo = next((f for f in file_list
                  if (f["mime_type"] or "").startswith("image/") and (f["file_name"] or "").lower().startswith("фото")), None)
    if photo:
        card["photo_url"] = f"/api/entities/trash/{record.id}/files/{photo['id']}"
    elif isinstance(card["extra_data"].get("photo_url"), str):
        card["photo_url"] = card["extra_data"]["photo_url"]
    return {"card": card, "blocks": blocks, "files": file_list}


def trash_file_bytes(record: DeletedEntity, file_id: int):
    """(байты, имя, тип) файла из слепка или None."""
    for r in ((record.snapshot or {}).get("tables") or {}).get("entity_files") or []:
        if r.get("id") == file_id:
            raw = r.get("file_data")
            data = base64.b64decode(raw["__b"]) if isinstance(raw, dict) and "__b" in raw else None
            if data is None:
                return None
            return data, r.get("file_name"), r.get("mime_type")
    return None
