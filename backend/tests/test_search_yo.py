"""Ё≡Е в поиске кандидатов: «Демин» обязан находить «Дёмина» и наоборот.

Жалоба из прода: «поисковик не находит Дёмин, если не прописать её через Ё» —
и приходится гадать написание. Точки над Ё в русском письме факультативны, для
поиска это одна буква.

Тесты бьют по РЕАЛЬНОМУ запросу к БД (а не сверяют строку SQL): проверяется
ILIKE-ветка name_search_conditions — именно она работает на проде, где pg_trgm
без superuser не поднимается. Триграммную ветку тут не поднять (SQLite), она
закрыта юнит-тестами блоба в test_search_index.py.

Регистр запроса берём как в имени: на SQLite ILIKE компилируется в
lower(a) LIKE lower(b), а lower() там ASCII-only и кириллицу не трогает — «демин»
не найдёт «Дёмин» просто из-за заглавной Д. В Postgres регистром занимается сам
ILIKE, и это ортогонально свёртке Ё, которую мы тут и проверяем.
"""
import pytest
import pytest_asyncio
from sqlalchemy import select, or_

from api.models.database import Entity, EntityType, EntityStatus
from api.services import search_index as si


@pytest_asyncio.fixture
async def yo_candidates(db_session, organization, admin_user):
    """Два кандидата: один записан через Ё, второй — через Е."""
    made = []
    for name in ("Дёмин Артём", "Демин Артем"):
        e = Entity(
            org_id=organization.id,
            type=EntityType.candidate,
            name=name,
            status=EntityStatus.new,
            created_by=admin_user.id,
        )
        db_session.add(e)
        made.append(e)
    await db_session.commit()
    for e in made:
        await db_session.refresh(e)
    return made


async def _search(db_session, organization, q):
    """Имена, которые находит ILIKE-ветка поиска по запросу q."""
    si.set_pg_trgm_available(False)  # прод-режим: без pg_trgm
    try:
        rows = await db_session.execute(
            select(Entity.name).where(
                Entity.org_id == organization.id,
                or_(*si.name_search_conditions(q)),
            )
        )
        return sorted(r[0] for r in rows.all())
    finally:
        si.set_pg_trgm_available(None)  # не протекаем в соседние тесты


@pytest.mark.parametrize("q", ["Демин", "Дёмин"])
async def test_yo_query_finds_both_spellings(db_session, organization, yo_candidates, q):
    """Любое написание запроса находит ОБА варианта записи в базе."""
    found = await _search(db_session, organization, q)
    assert found == ["Демин Артем", "Дёмин Артём"], f"запрос «{q}» нашёл {found}"


@pytest.mark.parametrize("q", ["Артем", "Артём"])
async def test_yo_works_on_any_name_word(db_session, organization, yo_candidates, q):
    """Свёртка работает не только на фамилии — порядок слов по-прежнему не важен."""
    found = await _search(db_session, organization, q)
    assert found == ["Демин Артем", "Дёмин Артём"], f"запрос «{q}» нашёл {found}"


async def test_yo_folding_does_not_widen_search(db_session, organization, yo_candidates):
    """Свёртка не должна ловить лишнего: чужая фамилия по-прежнему не находится."""
    assert await _search(db_session, organization, "Иванов") == []


# --- дедуп ---------------------------------------------------------------
# Без свёртки «Дёмин Артём» и «Демин Артем» считались РАЗНЫМИ людьми (0 общих
# слов): один человек заводился дублем, баннер о дубле не срабатывал.

@pytest.mark.parametrize("other", [
    "Демин Артем",    # оба кириллицей, различие только в Ё
    "Dyomin Artyom",  # латиница «через Ё»
    "Demin Artem",    # латиница «через Е» — другой транслит, но тот же человек
])
def test_yo_dedup_sees_one_person(other):
    from api.services.similarity import count_shared_name_words
    assert count_shared_name_words("Дёмин Артём", other) == 2, other


def test_yo_dedup_keeps_different_people_apart():
    """Свёртка убирает необязательный диакритик, а не склеивает разные буквы."""
    from api.services.similarity import count_shared_name_words
    assert count_shared_name_words("Дёмин Артём", "Иванов Пётр") == 0
    assert count_shared_name_words("Королёв Пётр", "Кораблёв Пётр") == 1  # только имя
