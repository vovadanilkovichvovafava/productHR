"""«Скрыта от коллег» — вакансию видят только свои (владелец, 17.11.2026).

До этого флаг `Vacancy.visible_to_all = False` прятал заявку только из списков
«Заявки»: рекрутёр, которого на неё не назначали, открывал её через выбор
владельца в «Мои вакансии» или по ссылке и видел кандидатов (с 07.09.2026
воронки коллег открыты всему HR-сегменту). Теперь скрытую вакансию видят:
- админы орга, владелец, суперадмин и «Наблюдатель» (has_full_database_access);
- автор заявки, нанимающий менеджер, назначенные (assigned_to), взявшие в
  работу (accepted_by); «Всем рекрутёрам» (assigned_to_all) — все;
- тот, у кого в этой воронке есть свои кандидаты (автор заявки кандидата или
  со-рекрутёр) — иначе он потерял бы доступ к своим людям.
Остальным она отвечает 404 (как чужая организация) и не попадает ни в списки,
ни в блоки воронок карточки, ни в чипы «этап · воронка» в списке кандидатов.
"""
from __future__ import annotations

from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import ApplicationCoRecruiter, User, Vacancy, VacancyApplication


def _ids(value) -> set[int]:
    out: set[int] = set()
    for x in value or []:
        try:
            out.add(int(x))
        except (TypeError, ValueError):
            continue
    return out


def _is_private(vacancy) -> bool:
    return not bool(getattr(vacancy, "visible_to_all", True)) and not bool(
        getattr(vacancy, "assigned_to_all", False)
    )


def _is_participant(vacancy, user_id: int, own_vacancy_ids: Iterable[int]) -> bool:
    if vacancy.created_by == user_id or vacancy.hiring_manager_id == user_id:
        return True
    if user_id in _ids(vacancy.assigned_to):
        return True
    if user_id in _ids((vacancy.extra_data or {}).get("accepted_by")):
        return True
    return vacancy.id in set(own_vacancy_ids)


async def _privileged(db: AsyncSession, user: User, org_id: Optional[int]) -> bool:
    from .auth import has_full_database_access
    if org_id is None:
        return getattr(user, "role", None) is not None and user.role.value == "superadmin"
    return await has_full_database_access(user, org_id, db)


async def _own_vacancy_ids(db: AsyncSession, user_id: int) -> set[int]:
    """Воронки, где у человека есть свои кандидаты (автор заявки или со-рекрутёр)."""
    own = set((await db.execute(
        select(VacancyApplication.vacancy_id).where(VacancyApplication.created_by == user_id).distinct()
    )).scalars().all())
    co = set((await db.execute(
        select(VacancyApplication.vacancy_id)
        .join(ApplicationCoRecruiter, ApplicationCoRecruiter.application_id == VacancyApplication.id)
        .where(ApplicationCoRecruiter.user_id == user_id)
        .distinct()
    )).scalars().all())
    return own | co


async def hidden_vacancy_ids(db: AsyncSession, user: User, org_id: Optional[int]) -> set[int]:
    """Номера скрытых вакансий организации, которых этому человеку не видно."""
    if org_id is None or await _privileged(db, user, org_id):
        return set()
    private = [
        v for v in (await db.execute(
            select(Vacancy).where(Vacancy.org_id == org_id, Vacancy.visible_to_all.is_not(True))
        )).scalars().all()
        if _is_private(v)
    ]
    if not private:
        return set()
    own = await _own_vacancy_ids(db, user.id)
    return {v.id for v in private if not _is_participant(v, user.id, own)}


async def can_see_vacancy(db: AsyncSession, vacancy, user: User) -> bool:
    """Видна ли вакансия человеку с точки зрения «Скрыта от коллег»."""
    if not _is_private(vacancy):
        return True
    if await _privileged(db, user, getattr(vacancy, "org_id", None)):
        return True
    if _is_participant(vacancy, user.id, ()):
        return True
    return vacancy.id in await _own_vacancy_ids(db, user.id)


def strip_hidden(extra, hidden_ids) -> dict | None:
    """Убрать из extra_data карточки следы скрытых от человека воронок: метки
    «HR: Имя · Вакансия» (system_hr_tags) и комментарии, привязанные к воронке."""
    if not hidden_ids or not isinstance(extra, dict):
        return extra
    hidden = {int(v) for v in hidden_ids}

    def _keep(item) -> bool:
        if not isinstance(item, dict) or item.get("vacancy_id") is None:
            return True
        try:
            return int(item["vacancy_id"]) not in hidden
        except (TypeError, ValueError):
            return True

    out = dict(extra)
    for key in ("system_hr_tags", "notes"):
        if isinstance(out.get(key), list):
            out[key] = [x for x in out[key] if _keep(x)]
    return out
