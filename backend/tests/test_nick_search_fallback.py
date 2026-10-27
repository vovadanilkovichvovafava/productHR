"""Поиск по «@нику»: что он покрывает и когда откатывается (01.10.2026).

История: искали «@shaffer_art» — ноль, а тот же текст без «@» человека находил.
«@» не ищется как символ (он срезается), но ПЕРЕКЛЮЧАЕТ поиск в строгий режим
«только telegram + комментарии», а в карточке ник сохранён другим (обрезанным).
Получался тупик «кандидатов нет» там, где человек в базе есть.

Чинили двумя шагами, оба под этим тестом:
1) в строгий ник-поиск добавлены контакты из ШАПКИ резюме (resume_contacts) —
   там ник обычно полный;
2) если по нику в этой выборке НИЧЕГО нет — откатываемся к обычному поиску и
   говорим об этом окну (`nick_fallback` в ответе /candidates/kanban).
"""
import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from api.models.database import Entity
from api.services import search_index
from api.services.search_index import (
    apply_text_search,
    broad_search_conditions,
    nick_search_conditions,
)


def _sql(clause) -> str:
    """SQL одного условия/WHERE — с подставленными значениями: ключи JSON
    (`extra_data -> 'notes'`) иначе уезжают в параметры и в тексте не видны."""
    return str(
        clause.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


def _where(query) -> str:
    return _sql(query.whereclause) if query.whereclause is not None else ""


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _FakeDB:
    """Сессия-заглушка: поиск строит запрос, а считает совпадения одним SELECT."""

    def __init__(self, found: int):
        self.found = found
        self.queries = 0

    async def execute(self, statement):
        self.queries += 1
        return _FakeResult(self.found)


@pytest.fixture(autouse=True)
def _pg_trgm_known(monkeypatch):
    # Проверку наличия pg_trgm не делаем — она ходит в базу; считаем, что есть.
    monkeypatch.setattr(search_index, "_pg_trgm_available", True, raising=False)


def test_nick_conditions_cover_resume_contacts():
    conds = nick_search_conditions("@shaffer_art")
    # telegram_usernames + комментарии + контакты из текста резюме.
    assert len(conds) == 3
    sql = " ".join(_sql(c) for c in conds)
    assert "telegram_usernames" in sql
    assert "notes" in sql
    # Именно список ников из шапки, а не объект resume_contacts целиком: в тексте
    # объекта есть имена ключей, и «id»/«mail» цепляли бы всех подряд.
    assert "resume_contacts" in sql and "telegrams" in sql


def test_nick_conditions_ignore_at_sign():
    # «@» — это символ телеграма, а не часть ника: условия должны совпадать.
    assert len(nick_search_conditions("@shaffer_art")) == len(
        nick_search_conditions("shaffer_art")
    )
    assert nick_search_conditions("@") == []
    assert nick_search_conditions("") == []


def test_broad_conditions_tags_only_where_asked():
    # Метки ищет только окно /search; в «Все кандидаты» их в поиске не было, и
    # заодно это поведение не меняли.
    without = " ".join(_sql(c) for c in broad_search_conditions("ковалёв"))
    with_tags = " ".join(
        _sql(c) for c in broad_search_conditions("ковалёв", include_tags=True)
    )
    assert "tags" not in without
    assert "tags" in with_tags


def test_contact_conditions_match_values_not_json_keys():
    from api.services.search_index import contact_search_conditions

    sql = " ".join(_sql(c) for c in contact_search_conditions("id"))
    # Поиск идёт по спискам (emails/phones/telegrams), а не по объекту целиком —
    # иначе «id» совпадал бы с ключом "file_id" у каждого, у кого есть резюме.
    assert "'emails'" in sql and "'phones'" in sql and "'telegrams'" in sql
    assert "'resume_contacts' AS" not in sql.replace("->", " ")


@pytest.mark.asyncio
async def test_nick_hit_stays_strict():
    db = _FakeDB(found=1)
    query, fallback = await apply_text_search(db, select(Entity), "@shaffer_a")
    assert fallback is False
    sql = _where(query)
    assert "telegram_usernames" in sql
    # Строгий режим: ни должности, ни нечёткого имени — ник не тащит чужих.
    assert "position" not in sql


@pytest.mark.asyncio
async def test_nick_miss_falls_back_to_normal_search():
    db = _FakeDB(found=0)
    query, fallback = await apply_text_search(db, select(Entity), "@shaffer_art")
    assert fallback is True
    sql = _where(query)
    # Обычный поиск: имя/должность/компания/контакты — человек находится по ФИО.
    assert "position" in sql
    assert "search_name" in sql


@pytest.mark.asyncio
async def test_plain_query_never_counts_twice():
    # Обычный запрос лишнего SELECT'а на пересчёт не делает.
    db = _FakeDB(found=0)
    _, fallback = await apply_text_search(db, select(Entity), "ковалёв")
    assert fallback is False
    assert db.queries == 0


@pytest.mark.asyncio
async def test_empty_query_changes_nothing():
    db = _FakeDB(found=0)
    base = select(Entity)
    query, fallback = await apply_text_search(db, base, "   ")
    assert fallback is False
    assert _where(query) == _where(base)
