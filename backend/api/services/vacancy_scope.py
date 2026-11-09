"""Скоуп по воронкам: «этому человеку видны только эти вакансии» (01.10.2026).

Зачем. Наблюдателям-менторам из другого отдела (Егор, Влад) открыли HR на
просмотр, но вся база им не нужна и не положена: «мы им нанимаем в трафик,
значит доступ только к трафику» (Мария). Раньше кандидаты были общими для всей
организации, никакого сужения не было вовсе.

Как устроено. У участника организации есть список id вакансий
(`org_members.scope_vacancy_ids`):

* пусто/NULL — ограничения НЕТ. Это состояние по умолчанию, поэтому включение
  фичи ничего не меняет ни одному существующему пользователю;
* непустой список — видны только кандидаты, у которых есть заявка в этих
  воронках, и только сами эти воронки. Кандидат из двух воронок, одна из
  которых разрешена, виден (но его этапы по чужим воронкам в карточке скрыты —
  см. `visible_application_ids`).

Суперадмин проверке не подлежит — он платформенный, а не организационный.

Главное правило: НЕ городить проверки по эндпоинтам. Их две, и обе —
бутылочные горлышки:
  1. `check_entity_access` — любой доступ к конкретному кандидату (карточка,
     файлы, заметки, анкеты, дубли);
  2. `entity_scope_filter` — любой СПИСОК кандидатов (доска, поиск, «выбрать
     всех», /entities).
Плюс `vacancy_scope_filter`/`is_vacancy_visible` для списка воронок и доски.
"""
from typing import Iterable, Optional, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import Entity, OrgMember, User, UserRole, Vacancy, VacancyApplication


class Scope(set):
    """Скоуп человека: множество id разрешённых воронок + (необязательно)
    разрешённые статусы кандидата.

    Это `set`, чтобы все места, которые уже проверяют `vacancy_id in scope_ids`
    и `VacancyApplication.vacancy_id.in_(scope_ids)`, продолжили работать без
    правок. Скоуп по этапам (09.11.2026, «Владу и Егору — только этап
    „Практика“») добавлен поверх:

    * `statuses` — статусы кандидата (EntityStatus.value), None — без ограничения;
    * `all_vacancies` — ограничения по воронкам НЕТ, в множестве лежат все
      воронки организации (чтобы проверки «воронка в скоупе» пропускали всё).

    Всегда истинен: пустая организация без вакансий не должна превращать
    скоуп в «ограничения нет» в местах вида `if scope_ids:`.
    """

    def __init__(self, ids=(), statuses=None, all_vacancies=False):
        super().__init__(ids)
        self.statuses = frozenset(statuses) if statuses else None
        self.all_vacancies = bool(all_vacancies)

    def __bool__(self) -> bool:  # noqa: D401
        return True


def scope_statuses(scope) -> Optional[frozenset]:
    """Разрешённые статусы кандидата или None (если по этапам не ограничен)."""
    return getattr(scope, "statuses", None)


def scope_stages(scope) -> Optional[Set]:
    """Разрешённые этапы заявки (ApplicationStage) — пара к статусам кандидата."""
    statuses = scope_statuses(scope)
    if not statuses:
        return None
    from ..models.database import STATUS_SYNC_MAP, EntityStatus
    stages = set()
    for value in statuses:
        try:
            stage = STATUS_SYNC_MAP.get(EntityStatus(value))
        except ValueError:
            continue
        if stage is not None:
            stages.add(stage)
    return stages


def clean_scope_statuses(raw) -> Optional[list]:
    """Статусы из запроса → то, что кладём в `org_members.scope_statuses`
    (неизвестные отбрасываются, пусто — None, т.е. ограничения нет)."""
    found = _as_statuses(raw)
    if not found:
        return None
    from ..models.database import EntityStatus
    return [s.value for s in EntityStatus if s.value in found]


def _as_statuses(raw) -> Optional[Set[str]]:
    if not raw or not isinstance(raw, (list, tuple, set)):
        return None
    from ..models.database import EntityStatus
    known = {s.value for s in EntityStatus}
    out = {str(v) for v in raw if str(v) in known}
    return out or None


async def get_scope_vacancy_ids(user: Optional[User], db: AsyncSession) -> Optional[Set[int]]:
    """Скоуп человека (`Scope`) или None, если ограничения нет.

    None — «видит всё, как раньше». Пустой список в базе тоже даёт None: иначе
    первая же галочка, снятая по ошибке, оставила бы человека без единого
    кандидата и это выглядело бы как поломка.
    """
    if user is None or getattr(user, "role", None) == UserRole.superadmin:
        return None
    # Кэш на объекте пользователя: check_entity_access зовут и в циклах по
    # списку, лишний SELECT на каждого кандидата тут не нужен.
    cached = getattr(user, "_scope_vacancy_ids_cache", False)
    if cached is not False:
        return cached
    try:
        # Та же «основная» запись, что у get_user_org: у человека в двух оргах
        # раньше бралась произвольная — и скоуп мог прийти из чужой.
        from .auth import org_membership_priority
        row = (await db.execute(
            select(OrgMember.scope_vacancy_ids, OrgMember.scope_statuses, OrgMember.org_id)
            .where(OrgMember.user_id == user.id)
            .order_by(*org_membership_priority())
        )).first()
    except Exception:
        # Колонки ещё нет (миграция не прошла) — не ломаем доступ, см. init.py.
        return None
    scope = None
    if row is not None:
        ids = _as_ids(row[0])
        statuses = _as_statuses(row[1])
        if ids is not None:
            scope = Scope(ids, statuses=statuses)
        elif statuses:
            org_vacancies = (await db.execute(
                select(Vacancy.id).where(Vacancy.org_id == row[2])
            )).scalars().all()
            scope = Scope(org_vacancies, statuses=statuses, all_vacancies=True)
    try:
        setattr(user, "_scope_vacancy_ids_cache", scope)
    except Exception:
        pass
    return scope


def _as_ids(raw) -> Optional[Set[int]]:
    if not raw or not isinstance(raw, (list, tuple, set)):
        return None
    ids = set()
    for value in raw:
        try:
            ids.add(int(value))
        except (TypeError, ValueError):
            continue
    return ids or None


def entity_scope_filter(scope_ids: Iterable[int]):
    """Условие для SELECT по кандидатам: только те, кто есть в этих воронках
    (и, при скоупе по этапам, только в разрешённых статусах)."""
    from sqlalchemy import and_, true
    conds = []
    if not getattr(scope_ids, "all_vacancies", False):
        conds.append(Entity.id.in_(
            select(VacancyApplication.entity_id).where(
                VacancyApplication.vacancy_id.in_(list(scope_ids))
            )
        ))
    statuses = scope_statuses(scope_ids)
    if statuses:
        conds.append(Entity.status.in_(_status_enums(statuses)))
    return and_(*conds) if conds else true()


def _status_enums(statuses):
    from ..models.database import EntityStatus
    return [EntityStatus(s) for s in statuses]


def application_scope_filter(scope_ids):
    """Условие для SELECT по заявкам: воронка в скоупе и этап разрешён.
    None — ограничения нет."""
    from sqlalchemy import and_
    if scope_ids is None:
        return None
    conds = []
    if not getattr(scope_ids, "all_vacancies", False):
        conds.append(VacancyApplication.vacancy_id.in_(list(scope_ids)))
    stages = scope_stages(scope_ids)
    if stages is not None:
        conds.append(VacancyApplication.stage.in_(list(stages)))
    return and_(*conds) if conds else None


def application_in_scope(app, scope_ids) -> bool:
    """То же для уже загруженной заявки."""
    if scope_ids is None:
        return True
    if not getattr(scope_ids, "all_vacancies", False) and app.vacancy_id not in scope_ids:
        return False
    stages = scope_stages(scope_ids)
    return stages is None or app.stage in stages


def vacancy_scope_filter(scope_ids: Iterable[int]):
    """Условие для SELECT по вакансиям: только разрешённые."""
    return Vacancy.id.in_(list(scope_ids))


async def entity_in_scope(entity_id: int, scope_ids: Iterable[int], db: AsyncSession) -> bool:
    """Виден ли кандидат человеку со скоупом: заявка хотя бы в одной
    разрешённой воронке и (при скоупе по этапам) разрешённый статус."""
    found = (await db.execute(
        select(Entity.id).where(Entity.id == entity_id, entity_scope_filter(scope_ids)).limit(1)
    )).scalars().first()
    return found is not None


async def visible_application_ids(entity_id: int, scope_ids: Iterable[int], db: AsyncSession) -> Set[int]:
    """Заявки кандидата, которые человеку со скоупом показывать можно.

    Карточка кандидата показывает блок на КАЖДУЮ воронку. Если человек допущен
    только до «Трафика», чужие блоки (с этапами и перепиской по другой вакансии)
    он видеть не должен, хотя сам кандидат ему открыт. Со скоупом по этапам —
    только заявки на разрешённых этапах.
    """
    q = select(VacancyApplication.id).where(VacancyApplication.entity_id == entity_id)
    cond = application_scope_filter(scope_ids)
    if cond is not None:
        q = q.where(cond)
    rows = (await db.execute(q)).scalars().all()
    return set(rows)


async def ensure_vacancy_visible(vacancy_id: int, user: Optional[User], db: AsyncSession) -> None:
    """404, если воронка вне скоупа человека.

    Именно 404, а не 403: наличие чужой воронки — тоже информация, а по id их
    легко перебрать. Для людей без скоупа не делает ничего.
    """
    scope_ids = await get_scope_vacancy_ids(user, db)
    if scope_ids is None:
        return
    if int(vacancy_id) not in scope_ids:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Вакансия не найдена")


async def ensure_entity_visible(entity_id: int, user: Optional[User], db: AsyncSession) -> None:
    """404, если кандидат вне скоупа. Для «мелких» GET-ручек кандидата.

    Основную проверку делает check_entity_access, но часть эндпоинтов (метки,
    анкеты, история писем, рекомендации) достаёт данные по entity_id напрямую,
    мимо неё — им нужна эта строчка, иначе чужой кандидат утекает по кусочкам.
    """
    scope_ids = await get_scope_vacancy_ids(user, db)
    if scope_ids is None:
        return
    if not await entity_in_scope(entity_id, scope_ids, db):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Кандидат не найден")


def filter_extra_for_scope(extra: Optional[dict], scope_ids: Optional[Iterable[int]]) -> Optional[dict]:
    """Убрать из extra_data следы чужих воронок (метки «HR: Имя · Воронка»).

    Карточку кандидата из «своей» воронки человек видит целиком, и вместе с ней
    видел названия ОСТАЛЬНЫХ воронок, в которых тот состоит, — через системные
    метки `system_hr_tags` и подписи к заметкам. Для скоупа это лишнее: сам факт
    чужой воронки (и её название) — тоже информация.
    """
    if not scope_ids or not isinstance(extra, dict):
        return extra
    allowed = {int(v) for v in scope_ids}
    tags = extra.get("system_hr_tags")
    notes = extra.get("notes")
    if not isinstance(tags, list) and not isinstance(notes, list):
        return extra
    cleaned = dict(extra)
    if isinstance(tags, list):
        cleaned["system_hr_tags"] = [
            t for t in tags
            if not isinstance(t, dict) or t.get("vacancy_id") is None
            or int(t.get("vacancy_id")) in allowed
        ]
    if isinstance(notes, list):
        # Заметка, привязанная к чужой воронке, тоже не показывается.
        cleaned["notes"] = [
            n for n in notes
            if not isinstance(n, dict) or n.get("vacancy_id") is None
            or int(n.get("vacancy_id")) in allowed
        ]
    return cleaned
