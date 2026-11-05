"""Нечёткий поиск имени — отдельным запросом по GIN-индексу (smart_name_ids).

04.11.2026: поиск на проде шёл 8–11 с. Внутри общего OR (имя ИЛИ почта ИЛИ
комментарии) индекс по search_name не работал, и word_similarity считался по
каждой карточке. Теперь номера совпавших по имени берутся отдельным запросом,
а в OR идёт `id IN (...)`. Выдача обязана остаться ТОЙ ЖЕ, что при прежнем
условии, — это и проверяем.

pg_trgm в SQLite нет, поэтому тест — на настоящем Postgres: задайте
SEARCH_PG_TEST_DSN (например postgresql+asyncpg://localhost/hrdelta_test).
База пересоздаётся целиком — не указывайте рабочую. Без переменной — пропуск.
"""
import os

import pytest
import pytest_asyncio
from sqlalchemy import or_, select, text

DSN = os.environ.get("SEARCH_PG_TEST_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="нужен SEARCH_PG_TEST_DSN (пустая тестовая база Postgres)")

NAMES = ["Arsenii Ziuzin", "Зюзин Семён Олегович", "Иванов Иван", "Иванова Мария",
         "Roman Fattakhov", "Петров Пётр"]


@pytest_asyncio.fixture
async def db():
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    import api.models  # noqa: F401
    from api.models.database import Base, Entity, EntityStatus, EntityType
    from api.services import search_index as si

    eng = create_async_engine(DSN)
    async with eng.begin() as c:
        await c.execute(text("DROP SCHEMA public CASCADE"))
        await c.execute(text("CREATE SCHEMA public"))
        await c.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await c.run_sync(Base.metadata.create_all)
        await c.execute(text(
            "CREATE INDEX ix_entities_search_name_trgm ON entities USING gin (search_name gin_trgm_ops)"))
        await c.execute(text("INSERT INTO organizations (id, name, slug) VALUES (1, 'o', 'o')"))
    async with AsyncSession(eng) as s:
        for i, name in enumerate(NAMES):
            s.add(Entity(org_id=1, type=EntityType.candidate, name=name, status=EntityStatus.new,
                         email=f"c{i}@example.com", extra_data={}, tags=[]))
        # совпадение только по почте и только по комментарию — ветки OR кроме имени
        s.add(Entity(org_id=1, type=EntityType.candidate, name="Сидоров Олег", status=EntityStatus.new,
                     email="ziuzin.work@example.com", extra_data={}, tags=[]))
        s.add(Entity(org_id=1, type=EntityType.candidate, name="Козлов Антон", status=EntityStatus.new,
                     extra_data={"notes": [{"text": "call after 19:00, ask Ivanova"}]}, tags=[]))
        await s.commit()
    si.set_pg_trgm_available(None)
    async with AsyncSession(eng) as s:
        yield s
    si.set_pg_trgm_available(None)
    await eng.dispose()


async def _names(db, query):
    return sorted(e.name for e in (await db.execute(query)).scalars().all())


@pytest.mark.asyncio
@pytest.mark.parametrize("q", ["зюзин", "арсений зюзин", "ziuzin", "иванов", "фаттахов", "семен", "@ziuzin"])
async def test_same_result_as_inline_filter(db, q):
    """Ответ тот же, что у прежнего OR с триграммным условием внутри."""
    from api.models.database import Entity
    from api.services import search_index as si

    base = select(Entity).where(Entity.org_id == 1)
    new, _ = await si.apply_text_search(db, base, q)
    old = base.where(or_(*si.broad_search_conditions(q)))  # name_ids=None — прежний путь
    got = await _names(db, new)
    assert got == await _names(db, old)
    assert got, q


@pytest.mark.asyncio
async def test_finds_latin_card_and_other_branches(db):
    from api.models.database import Entity
    from api.services import search_index as si

    base = select(Entity).where(Entity.org_id == 1)
    q, _ = await si.apply_text_search(db, base, "зюзин")
    names = await _names(db, q)
    assert "Arsenii Ziuzin" in names and "Зюзин Семён Олегович" in names
    q, _ = await si.apply_text_search(db, base, "ziuzin.work")
    assert await _names(db, q) == ["Сидоров Олег"]  # по почте, имя ни при чём
    q, _ = await si.apply_text_search(db, base, "call after 19")
    assert await _names(db, q) == ["Козлов Антон"]  # по комментарию


@pytest.mark.asyncio
async def test_seqscan_restored(db):
    """Выключенный полный проход не должен остаться на остальные запросы ручки."""
    from api.services import search_index as si

    await si.ensure_pg_trgm_checked(db)
    ids = await si.smart_name_ids(db, "зюзин")
    assert ids
    assert (await db.execute(text("SHOW enable_seqscan"))).scalar() == "on"
