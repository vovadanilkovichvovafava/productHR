"""Скоуп по воронкам: «вижу только свою воронку» (01.10.2026).

Запрос Марии: наблюдателям из другого отдела (Егор, Влад) нанимают в трафик,
значит и видеть они должны только трафик, а не всю базу кандидатов.

Здесь закреплены правила, на которых держится вся фича:
* пусто/NULL в `org_members.scope_vacancy_ids` — ограничения НЕТ (иначе снятая
  по ошибке галочка оставила бы человека с пустой базой, и это выглядело бы как
  поломка, а не как запрет);
* суперадмин скоупу не подчиняется — он платформенный;
* чужая воронка отвечает 404, а не 403: наличие воронки — тоже информация;
* мусор в списке (строки, None) не должен ронять запрос.
"""
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from api.models.database import Entity, User, UserRole, Vacancy
from api.services.vacancy_scope import (
    _as_ids,
    ensure_vacancy_visible,
    entity_scope_filter,
    filter_extra_for_scope,
    get_scope_vacancy_ids,
    vacancy_scope_filter,
)


class _Result:
    def __init__(self, value):
        self._value = value

    def scalars(self):
        return self

    def first(self):
        return self._value

    def all(self):
        return self._value or []


class _FakeDB:
    """Отдаёт заранее заданное значение на любой SELECT."""

    def __init__(self, value):
        self.value = value
        self.calls = 0

    async def execute(self, statement):
        self.calls += 1
        return _Result(self.value)


def _user(role=UserRole.member, uid=7):
    u = User(id=uid, email="observer@example.com", name="Наблюдатель", role=role)
    return u


def _sql(clause) -> str:
    return str(clause.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


@pytest.mark.parametrize(
    "raw, expected",
    [
        ([125], {125}),
        (["125", 4], {125, 4}),
        ([], None),
        (None, None),
        (["мусор", None], None),
        ([4, "мусор"], {4}),
    ],
)
def test_as_ids(raw, expected):
    assert _as_ids(raw) == expected


@pytest.mark.asyncio
async def test_empty_scope_means_no_restriction():
    db = _FakeDB([])
    assert await get_scope_vacancy_ids(_user(), db) is None


@pytest.mark.asyncio
async def test_scope_is_read_once_per_user():
    db = _FakeDB([125])
    user = _user()
    assert await get_scope_vacancy_ids(user, db) == {125}
    # Второй вызов берёт кэш: check_entity_access зовут в циклах по списку.
    assert await get_scope_vacancy_ids(user, db) == {125}
    assert db.calls == 1


@pytest.mark.asyncio
async def test_superadmin_is_never_scoped():
    db = _FakeDB([125])
    assert await get_scope_vacancy_ids(_user(role=UserRole.superadmin), db) is None
    assert db.calls == 0


@pytest.mark.asyncio
async def test_missing_column_does_not_break_access():
    class _Broken:
        async def execute(self, statement):
            raise RuntimeError("column org_members.scope_vacancy_ids does not exist")

    # Колонки ещё нет (миграция не прошла) — доступ не режем, см. init.py.
    assert await get_scope_vacancy_ids(_user(), _Broken()) is None


def test_entity_filter_goes_through_applications():
    sql = _sql(entity_scope_filter({125}))
    assert "vacancy_applications" in sql
    assert "entity_id" in sql
    assert "125" in sql


def test_vacancy_filter_limits_ids():
    sql = _sql(vacancy_scope_filter({125, 4}))
    assert "vacancies.id IN" in sql


@pytest.mark.asyncio
async def test_foreign_vacancy_is_404_not_403():
    db = _FakeDB([125])
    with pytest.raises(HTTPException) as err:
        await ensure_vacancy_visible(999, _user(), db)
    assert err.value.status_code == 404


@pytest.mark.asyncio
async def test_own_vacancy_passes():
    db = _FakeDB([125])
    await ensure_vacancy_visible(125, _user(), db)  # не бросает


@pytest.mark.asyncio
async def test_user_without_scope_sees_every_vacancy():
    db = _FakeDB(None)
    await ensure_vacancy_visible(999, _user(), db)  # не бросает


def test_extra_hides_foreign_funnel_traces():
    """Метка «HR: Имя · Воронка» выдавала НАЗВАНИЕ чужой воронки.

    Кандидат из двух воронок наблюдателю виден (он есть и в разрешённой), но
    узнавать из его карточки, что он проходит ещё и в «Product Analyst», ему
    незачем — поймали на скриншоте 01.10.2026.
    """
    extra = {
        "system_hr_tags": [
            {"name": "Мария", "vacancy_id": 125, "vacancy_title": "Трафик"},
            {"name": "Мария", "vacancy_id": 156, "vacancy_title": "Product Analyst"},
            {"name": "Мария"},  # без воронки — общая метка, остаётся
        ],
        "notes": [
            {"text": "по трафику", "vacancy_id": 125},
            {"text": "по аналитике", "vacancy_id": 156},
            {"text": "общий комментарий"},
        ],
        "city": "Минск",
    }
    cleaned = filter_extra_for_scope(extra, {125})
    assert [t.get("vacancy_title") for t in cleaned["system_hr_tags"]] == ["Трафик", None]
    assert [n["text"] for n in cleaned["notes"]] == ["по трафику", "общий комментарий"]
    assert cleaned["city"] == "Минск"
    # Исходный словарь не трогаем — он лежит в объекте SQLAlchemy.
    assert len(extra["system_hr_tags"]) == 3


def test_extra_untouched_without_scope():
    extra = {"system_hr_tags": [{"vacancy_id": 156}]}
    assert filter_extra_for_scope(extra, None) is extra
