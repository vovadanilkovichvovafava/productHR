"""Dynamic HR tags — auto-derived «HR: …» labels on a candidate.

An HR-tag marks a recruiter who pulled this candidate into a funnel. The set is
derived from ``VacancyApplication.created_by`` across the candidate's ACTIVE
applications (``rejected`` / ``withdrawn`` excluded — see design §4: a rejected /
withdrawn candidate is no longer that HR's responsibility) and stored, read-only,
in ``entity.extra_data["system_hr_tags"]`` as a list of
``{"hr_id", "name", "vacancy_id", "vacancy_title"}`` — one per (HR, funnel).

Storage is deliberately separate from the manual string ``Entity.tags`` so the
two never collide: sync never touches ``tags``, manual edits never touch this.

This module is the SINGLE source of truth for the computation. The one-shot bulk
backfill in ``start.sh`` mirrors the exact same rule in SQL — keep them in sync.
"""
import logging
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import Entity, User, VacancyApplication, ApplicationStage, Vacancy, ApplicationCoRecruiter

logger = logging.getLogger("hr-analyzer.hr_tags")

# Заявки в этих стадиях НЕ считаются активной вовлечённостью HR: кандидат снят
# с процесса, рекрутер за него больше не отвечает (design §4). Их created_by
# не порождает метку. Любая другая стадия = активная воронка → метка.
# «Резерв» здесь НАМЕРЕННО активный (в отличие от pick_primary_application, где
# он не перебивает живую воронку): кандидат в резерве всё ещё «чей-то» — метка
# говорит, у кого он отложен (сверено при ревью 20.10.2026).
INACTIVE_STAGES = (ApplicationStage.rejected, ApplicationStage.withdrawn)

# Ключ в extra_data, где живут авто-метки HR (read-only массив [{hr_id, name}]).
EXTRA_KEY = "system_hr_tags"


async def compute_hr_tags(db: AsyncSession, entity_id: int) -> list[dict]:
    """HR + воронка, в которую забрали кандидата (активные заявки).

    По одной записи на (HR, вакансия) активной заявки кандидата. Возвращает
    ``[{"hr_id": int, "name": str, "vacancy_id": int, "vacancy_title": str}]``,
    отсортированный по ``(hr_id, vacancy_id)`` — стабильный порядок нужен для
    дешёвого diff в :func:`sync_for_entity`. Один HR, добавивший кандидата в
    несколько воронок, даёт несколько записей (по одной на воронку).

    HR = тот, кто добавил заявку (``VacancyApplication.created_by``); а если он не
    записан (NULL — массовое добавление «bulk_crm», magic-button, старые данные) —
    ВЛАДЕЛЕЦ воронки (``Vacancy.created_by``). Так метка появляется у каждого
    кандидата в воронке, даже если «кто добавил» не сохранилось. Если оба NULL
    (создатель вакансии удалён) — заявка молча отсекается INNER JOIN на users.
    """
    # Эффективный HR: кто добавил → иначе владелец воронки.
    effective_hr = func.coalesce(VacancyApplication.created_by, Vacancy.created_by)
    rows = await db.execute(
        select(effective_hr, User.name, Vacancy.id, Vacancy.title)
        .select_from(VacancyApplication)
        .join(Vacancy, Vacancy.id == VacancyApplication.vacancy_id)
        .join(User, User.id == effective_hr)
        .where(
            VacancyApplication.entity_id == entity_id,
            VacancyApplication.stage.not_in(INACTIVE_STAGES),
            Vacancy.deleted_at.is_(None),  # удалённая воронка метку не даёт
        )
        .distinct()
    )
    # + СО-РЕКРУТЁРЫ: кандидат в ОБЩЕЙ воронке может быть у нескольких HR сразу.
    # Каждый co-recruiter активной заявки даёт свою метку «HR: Имя · воронка».
    co_rows = await db.execute(
        select(ApplicationCoRecruiter.user_id, User.name, Vacancy.id, Vacancy.title)
        .select_from(ApplicationCoRecruiter)
        .join(VacancyApplication, VacancyApplication.id == ApplicationCoRecruiter.application_id)
        .join(Vacancy, Vacancy.id == VacancyApplication.vacancy_id)
        .join(User, User.id == ApplicationCoRecruiter.user_id)
        .where(
            VacancyApplication.entity_id == entity_id,
            VacancyApplication.stage.not_in(INACTIVE_STAGES),
            Vacancy.deleted_at.is_(None),  # удалённая воронка метку не даёт
        )
        .distinct()
    )
    # Дедуп по (hr_id, vacancy_id) — co-recruiter может совпасть с владельцем;
    # стабильный порядок (hr_id, vacancy_id) нужен для дешёвого diff в sync.
    seen: dict[tuple[int, int], dict] = {}
    for hr_id, name, vid, vtitle in [*rows.all(), *co_rows.all()]:
        key = (hr_id, vid)
        if key not in seen:
            seen[key] = {"hr_id": hr_id, "name": name, "vacancy_id": vid, "vacancy_title": vtitle}
    return [seen[k] for k in sorted(seen.keys())]


async def sync_for_entity(
    db: AsyncSession, entity_id: int, *, commit: bool = True
) -> bool:
    """Пересчитывает ``system_hr_tags`` кандидата и пишет в ``extra_data``.

    Diff-guard: если набор HR не изменился — НИЧЕГО не пишем и не коммитим, так
    что горячий путь (self-heal при каждом открытии карточки) остаётся
    фактически read-only. Возвращает ``True``, если данные поменялись.

    ``version`` (optimistic-lock) НЕ трогаем намеренно: это служебная
    синхронизация, а не пользовательская правка — она не должна конфликтовать с
    параллельным редактированием карточки.
    """
    entity = await db.get(Entity, entity_id)
    if entity is None:
        return False

    new_tags = await compute_hr_tags(db, entity_id)
    current = (entity.extra_data or {}).get(EXTRA_KEY) or []

    if current == new_tags:
        return False

    # Дошли до реальной записи — БЕРЁМ строку под FOR UPDATE и перечитываем СВЕЖИЙ
    # extra_data. Иначе reassign блоба затрёт заметки/правки, добавленные параллельно
    # между нашим первым чтением и коммитом: это и есть первопричина «пропали
    # некоторые комментарии» — self-heal HR-тегов запускается на каждом открытии
    # карточки, а при переводе в отдел набор HR меняется, и он реально пишет старый
    # snapshot поверх свежего. Diff-guard выше оставляет горячий путь read-only без
    # лока; лок берём только когда действительно есть что писать.
    locked = (await db.execute(
        select(Entity).where(Entity.id == entity_id).with_for_update()
    )).scalar_one_or_none()
    if locked is None:
        return False
    # Пересчёт под локом — набор HR мог измениться, пока ждали блокировку.
    new_tags = await compute_hr_tags(db, entity_id)
    merged = dict(locked.extra_data or {})
    if (merged.get(EXTRA_KEY) or []) == new_tags:
        return False  # кто-то уже записал те же теги — второй проход не нужен
    # Reassign целиком (не in-place мутация) — только так SQLAlchemy замечает
    # изменение JSON-колонки (тот же приём, что crud.update_entity).
    if new_tags:
        merged[EXTRA_KEY] = new_tags
    else:
        merged.pop(EXTRA_KEY, None)  # нет активных HR → убираем ключ совсем
    locked.extra_data = merged
    # updated_at ставим ЯВНО, питоновским значением. У колонки server-side
    # onupdate=func.now(): после UPDATE SQLAlchemy помечает атрибут expired, и
    # следующее обращение к нему тянет ленивую догрузку. В get_entity это
    # обращение происходит уже вне async-контекста → MissingGreenlet → 500 на
    # ОТКРЫТИИ КАРТОЧКИ. Ловится только когда набор HR реально поменялся (иначе
    # diff-guard выше выходит раньше и записи нет) — потому и выглядело как
    # «иногда карточка не открывается». Тот же приём, что в kanban.bulk_move.
    locked.updated_at = datetime.utcnow()

    if commit:
        await db.commit()
    logger.info(
        "HR-tags synced for entity %s: %s",
        entity_id,
        [t["name"] for t in new_tags],
    )
    return True


async def backfill_all(db: AsyncSession) -> int:
    """Пересчитывает ``system_hr_tags`` для всех кандидатов с заявками.

    Возвращает число изменённых сущностей. Используется тестами и как
    Python-эквивалент SQL-бэкафилла из ``start.sh`` (тот же результат).
    """
    rows = await db.execute(select(VacancyApplication.entity_id).distinct())
    entity_ids = [r[0] for r in rows.all() if r[0] is not None]

    changed = 0
    for eid in entity_ids:
        if await sync_for_entity(db, eid, commit=False):
            changed += 1
    await db.commit()
    return changed
