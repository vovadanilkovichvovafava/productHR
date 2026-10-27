"""Назначения на доске «Статусы»: разовый перенос старых данных.

До 30.09.2026 отдел человека лежал одним полем в карточке
(``entities.extra_data["board_department_id"]``), поэтому человек мог быть
ровно в одном отделе, а «перевод с практики в отдел» затирал песочницу. Теперь
отдел — это НАЗНАЧЕНИЕ (``staff_board_placements``): строк у человека столько,
в сколько отделов он поставлен, а карточка кандидата по-прежнему одна.

Этот модуль переносит уже заполненные отделы 1:1: кто стоял в отделе — получает
назначение в него, вместе со своими датами и отметками вех (они принадлежат
назначению: в песочнице это даты практики, в отделе — выход в отдел и вехи).
Практикантов, у которых отдел не выбран, ни в какую песочницу НЕ ставим — какая
у кого песочница, знает только HR (решение владельца 30.09.2026).
"""
import logging
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from ..models.database import (
    BoardDepartment, BoardPlacement, DataMigrationMark, Entity,
)

logger = logging.getLogger("hr-analyzer.board-placements")

MIGRATION_MARK = "board_placements_from_extra_2026_09_30"

_K_BOARD_DEPT = "board_department_id"

# Что принадлежит назначению, а не человеку. Ключи те же, что на доске, плюс
# импортированные из ClickUp («cf:…»): их тоже забираем, иначе у перенесённых
# строк пропали бы даты, которые доска показывала из импорта.
PLACEMENT_KEYS = (
    "practice_start_date", "department_transfer_date",
    "w2_date", "m1_date", "m3_date", "y1_date",
    "department_start_done", "w2_done", "m1_done", "m3_done", "y1_done",
    "cf:Выход на практику", "cf:Выход в отдел",
    "cf:2 недели", "cf:3 мес", "cf:1 год",
)


def placement_extra(extra: Dict[str, Any]) -> Dict[str, Any]:
    """Даты и отметки, которые переезжают из карточки в назначение."""
    return {k: extra[k] for k in PLACEMENT_KEYS if extra.get(k) not in (None, "")}


# Песочницы на проде уже заведены обычными отделами (SANDBOX, SANDBOX MOBILE,
# SANDBOX R&D — Мария, 30.09.2026). Роль им проставляем по названию, иначе
# после выкатки HR пришлось бы открывать три окна и выбирать её руками.
SANDBOX_NAME_PREFIXES = ("sandbox", "сандбокс", "сэндбокс")


def looks_like_sandbox(name: str) -> bool:
    low = (name or "").strip().lower()
    return any(low.startswith(p) for p in SANDBOX_NAME_PREFIXES)


async def migrate_board_departments_once(db) -> int:
    """Перенести выбранные отделы из карточек в назначения. Один раз.

    Идемпотентно и без потерь: старые ключи в ``extra_data`` остаются на месте
    (их читают строки без назначений), дубликаты назначений не создаются.
    Коммитит. Возвращает число созданных назначений.
    """
    if await db.get(DataMigrationMark, MIGRATION_MARK) is not None:
        return 0

    depts = (await db.execute(select(BoardDepartment))).scalars().all()
    dept_orgs = {d.id: d.org_id for d in depts}
    for d in depts:
        if looks_like_sandbox(d.name) and (d.kind or "team") != "sandbox":
            d.kind = "sandbox"
            d.parent_id = None
            logger.info(f"BOARD_PLACEMENTS sandbox: «{d.name}» (id={d.id})")
    have = {
        (ent_id, dept_id) for ent_id, dept_id in (await db.execute(
            select(BoardPlacement.entity_id, BoardPlacement.department_id)
        )).all()
    }

    rows = (await db.execute(select(Entity.id, Entity.org_id, Entity.extra_data))).all()
    created: List[BoardPlacement] = []
    for ent_id, org_id, extra in rows:
        if not isinstance(extra, dict):
            continue
        raw = extra.get(_K_BOARD_DEPT)
        try:
            dept_id = int(raw)
        except (TypeError, ValueError):
            continue
        # Отдел удалён или из другой организации — молча пропускаем: строка
        # останется «без отдела», как и показывала доска.
        if dept_orgs.get(dept_id) != org_id or (ent_id, dept_id) in have:
            continue
        created.append(BoardPlacement(
            org_id=org_id, entity_id=ent_id, department_id=dept_id,
            extra=placement_extra(extra),
        ))
        have.add((ent_id, dept_id))

    for pl in created:
        db.add(pl)
    db.add(DataMigrationMark(key=MIGRATION_MARK))
    await db.commit()
    logger.info(f"BOARD_PLACEMENTS migrate: {len(created)} назначений из extra_data")
    return len(created)


# --- Практика ведёт в песочницу вакансии -------------------------------------

SANDBOX_KEY = "board_sandbox_id"        # Vacancy.extra_data
DEFAULT_SANDBOX_KEY = "board_default_sandbox_id"   # Organization.settings


async def resolve_sandbox(db, org_id: int, vacancy=None):
    """Какая песочница ждёт человека, вышедшего на практику.

    По порядку: выбранная у ВОРОНКИ → песочница организации «по умолчанию» →
    единственная песочница, если она в организации одна. Ничего не нашлось —
    человек появится на доске «без отдела», и песочницу ему укажут руками.

    Поле у воронки появилось 30.09.2026, и по умолчанию оно пустое: без
    запасных вариантов автоподстановка не срабатывала вообще, пока HR не
    пройдёт по каждой воронке (владелец, 01.10.2026).
    """
    from ..models.database import Organization

    extra = vacancy.extra_data if (vacancy is not None and isinstance(vacancy.extra_data, dict)) else {}
    candidates = []
    try:
        candidates.append(int(extra.get(SANDBOX_KEY)))
    except (TypeError, ValueError):
        pass

    org = await db.get(Organization, org_id)
    settings = org.settings if (org is not None and isinstance(org.settings, dict)) else {}
    try:
        candidates.append(int(settings.get(DEFAULT_SANDBOX_KEY)))
    except (TypeError, ValueError):
        pass

    for dept_id in candidates:
        dept = (await db.execute(
            select(BoardDepartment).where(
                BoardDepartment.id == dept_id, BoardDepartment.org_id == org_id
            )
        )).scalar_one_or_none()
        if dept is not None:
            return dept

    # Песочница одна — выбирать не из чего, ставим в неё.
    only = (await db.execute(
        select(BoardDepartment).where(
            BoardDepartment.org_id == org_id,
            BoardDepartment.kind == "sandbox",
            BoardDepartment.hidden_at.is_(None),
        )
    )).scalars().all()
    return only[0] if len(only) == 1 else None


async def ensure_sandbox_placement(db, entity_id: int, vacancy=None, org_id: int = None) -> bool:
    """Поставить человека в песочницу, когда он вышел на практику.

    Ничего не делает, если человек уже стоит хоть в одном отделе: доска — не
    место для автоматических переездов. Не коммитит.
    """
    if org_id is None:
        if vacancy is None:
            return False
        org_id = vacancy.org_id

    already = (await db.execute(
        select(BoardPlacement.id).where(BoardPlacement.entity_id == entity_id).limit(1)
    )).scalar_one_or_none()
    if already is not None:
        return False

    dept = await resolve_sandbox(db, org_id, vacancy)
    if dept is None:
        return False

    db.add(BoardPlacement(
        org_id=org_id, entity_id=entity_id, department_id=dept.id, extra={},
    ))
    logger.info(
        f"BOARD_PLACEMENT auto: entity {entity_id} → песочница «{dept.name}»"
        + (f" (вакансия {vacancy.id})" if vacancy is not None else "")
    )
    return True


async def place_current_practice(db, org_id: int, dept_id: int) -> int:
    """Поставить в песочницу всех, кто уже на практике и ни в каком отделе.

    Нужно в момент, когда песочницу помечают «сюда ведёт практика по
    умолчанию»: у тех, кто вышел на практику РАНЬШЕ, отдела нет, и доска
    показывает их пустыми (владелец, 01.10.2026). Тех, кто уже стоит хоть
    где-то, не трогаем. Не коммитит. Возвращает, скольких поставили.
    """
    from ..models.database import Entity, EntityStatus

    placed_ids = set((await db.execute(
        select(BoardPlacement.entity_id).where(BoardPlacement.org_id == org_id)
    )).scalars().all())
    rows = (await db.execute(
        select(Entity.id).where(
            Entity.org_id == org_id,
            Entity.status == EntityStatus.probation,
            Entity.is_archived.is_not(True),
        )
    )).scalars().all()

    added = 0
    for ent_id in rows:
        if ent_id in placed_ids:
            continue
        db.add(BoardPlacement(
            org_id=org_id, entity_id=ent_id, department_id=dept_id, extra={},
        ))
        added += 1
    if added:
        logger.info(f"BOARD_PLACEMENT backfill: {added} практикантов → отдел {dept_id}")
    return added


# --- Разовый сбор дат в карточку (13.10.2026) ---------------------------------

TEAM_MERGE_MARK = "board_team_dates_merge_2026_10_13"

# Поля РАБОЧЕГО отдела: выход в отдел, вехи и отметки. Практика сюда не входит —
# она живёт у песочницы.
TEAM_DATE_KEYS = (
    "department_transfer_date", "w2_date", "m1_date", "m3_date", "y1_date",
    "department_start_done", "w2_done", "m1_done", "m3_done", "y1_done",
)


def _is_auto_dept_date(key: str, value, placement) -> bool:
    """Похоже ли, что «выход в отдел» проставился сам при заведении назначения.

    Дату выхода мы ставим днём добавления в отдел; вписанная руками обычно
    другая. Для прочих полей автодаты нет.
    """
    if key != "department_transfer_date" or placement is None:
        return False
    created = getattr(placement, "created_at", None)
    return bool(created) and str(value)[:10] == created.date().isoformat()


async def merge_team_dates_once(db) -> int:
    """Собрать все даты доски в КАРТОЧКЕ человека.

    С 30.09 по 13.10.2026 даты лежали у назначений: своя копия в песочнице и
    своя в отделе. HR вписывал их то там, то там, и на разных вкладках у одного
    человека выходили разные значения — «надо, чтобы данные всегда были
    одинаковые, это же один и тот же кандидат» (владелец, 13.10.2026). Теперь
    правда одна и живёт в карточке, а назначение — только связь с отделом.

    Что переносим: непустые поля из назначений в `entities.extra_data`, если
    там пусто. Приоритет — РАБОЧИЙ отдел (в нём обычно свежие даты выхода и
    вехи), затем песочница. Из назначений ничего не удаляем: данные целы, и
    откатиться можно. Один раз (отметка в data_migration_marks). Коммитит.
    Возвращает число перенесённых полей.
    """
    from sqlalchemy import update as sa_update

    from ..models.database import BoardDepartment, DataMigrationMark, Entity

    if await db.get(DataMigrationMark, TEAM_MERGE_MARK) is not None:
        return 0

    kinds = {
        d_id: (kind or "team")
        for d_id, kind in (await db.execute(
            select(BoardDepartment.id, BoardDepartment.kind)
        )).all()
    }
    placements = (await db.execute(select(BoardPlacement))).scalars().all()

    # Сначала отдел, потом песочница: отдел главнее при совпадении ключа.
    by_entity: Dict[int, Dict[str, list]] = {}
    for pl in placements:
        side = "sandbox" if kinds.get(pl.department_id) == "sandbox" else "team"
        by_entity.setdefault(pl.entity_id, {"team": [], "sandbox": []})[side].append(pl)

    moved = 0
    for ent_id, sides in by_entity.items():
        entity = await db.get(Entity, ent_id)
        if entity is None:
            continue
        extra = dict(entity.extra_data or {})
        changed = False
        # Откуда взяли значение — нужно, чтобы отличить автодату от вписанной.
        chosen_from: Dict[str, Any] = {}
        # Отдел главнее песочницы, но ВПИСАННОЕ РУКАМИ главнее автодаты:
        # «выход в отдел» проставляется сам днём добавления в отдел, и если
        # где-то лежит другая дата — верна она (владелец, 13.10.2026: «09.01
        # правильное», хотя автодатой стояло 13.10).
        for pl in sides["team"] + sides["sandbox"]:
            pl_extra = pl.extra if isinstance(pl.extra, dict) else {}
            for key, value in pl_extra.items():
                if key not in PLACEMENT_KEYS or value in (None, ""):
                    continue
                current = extra.get(key)
                if current in (None, ""):
                    extra[key] = value
                    changed = True
                    moved += 1
                elif current != value:
                    # Что из двух — автодата: совпадает с днём, когда назначение
                    # завели.
                    auto_now = _is_auto_dept_date(key, value, pl)
                    auto_prev = _is_auto_dept_date(key, current, chosen_from.get(key))
                    if auto_prev and not auto_now:
                        extra[key] = value
                        changed = True
                        logger.info(
                            f"BOARD_TEAM_MERGE: entity {ent_id} {key}: автодату "
                            f"{current} заменили вписанной {value}"
                        )
                    else:
                        logger.info(
                            f"BOARD_TEAM_MERGE conflict: entity {ent_id} {key}: "
                            f"оставили {extra[key]}, в назначении {pl.id} было {value}"
                        )
                chosen_from.setdefault(key, pl)
        if changed:
            await db.execute(
                sa_update(Entity).where(Entity.id == ent_id).values(extra_data=extra)
            )
            logger.info(f"BOARD_TEAM_MERGE: entity {ent_id} — даты собраны в карточке")

    db.add(DataMigrationMark(key=TEAM_MERGE_MARK))
    await db.commit()
    logger.info(f"BOARD_TEAM_MERGE: перенесено полей: {moved}")
    return moved


BOARD_HR_MARK = "board_hr_tags_from_assignees_2026_10_20"


async def backfill_board_hr_tags_once(db) -> int:
    """Метка «HR: Имя» в карточке для тех, кого уже назначили на доске.

    Назначенный на доске HR с 20.10.2026 виден и в карточке кандидата
    (`extra_data.board_hr_tags`, пишет PATCH доски). У людей, которым HR
    поставили РАНЬШЕ, в карточке пусто: их список лежит только в
    `assignee_user_ids`. Собираем метку один раз (отметка в
    `data_migration_marks`), ничего не удаляя. Коммитит, возвращает число
    карточек.
    """
    from ..models.database import User

    if await db.get(DataMigrationMark, BOARD_HR_MARK) is not None:
        return 0

    rows = (await db.execute(select(Entity.id, Entity.extra_data))).all()
    wanted: Dict[int, List[int]] = {}
    for ent_id, extra in rows:
        if not isinstance(extra, dict):
            continue
        raw = extra.get("assignee_user_ids")
        ids: List[int] = []
        if isinstance(raw, list):
            for v in raw:
                try:
                    i = int(v)
                except (TypeError, ValueError):
                    continue
                if i not in ids:
                    ids.append(i)
        else:
            single = extra.get("assignee_user_id")
            try:
                ids = [int(single)] if single not in (None, "") else []
            except (TypeError, ValueError):
                ids = []
        if ids and not extra.get("board_hr_tags"):
            wanted[ent_id] = ids

    if not wanted:
        db.add(DataMigrationMark(key=BOARD_HR_MARK))
        await db.commit()
        return 0

    all_ids = {i for ids in wanted.values() for i in ids}
    names = {
        uid: nm
        for uid, nm in (await db.execute(
            select(User.id, User.name).where(User.id.in_(all_ids))
        )).all()
    }

    done = 0
    for ent_id, ids in wanted.items():
        tags = [{"hr_id": i, "name": names[i]} for i in ids if names.get(i)]
        if not tags:
            continue
        entity = await db.get(Entity, ent_id)
        if entity is None:
            continue
        extra = dict(entity.extra_data or {})
        extra["board_hr_tags"] = tags
        entity.extra_data = extra
        flag_modified(entity, "extra_data")
        done += 1

    db.add(DataMigrationMark(key=BOARD_HR_MARK))
    await db.commit()
    logger.info(f"BOARD_HR_TAGS: метка HR собрана у {done} карточек")
    return done
