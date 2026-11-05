"""Русские буквы в JSON карточек: пишутся как есть, накопленные коды перекодируются.

05.11.2026: слово из комментария, написанного на сайте, поиском не находилось —
SQLAlchemy писал JSON с ensure_ascii=True («\\u0437…»), а колонки типа JSON
хранят текст как есть. Перенесённое дампом лежало буквами и находилось.

Тест — на настоящем Postgres (SEARCH_PG_TEST_DSN, база пересоздаётся целиком).
"""
import json
import os

import pytest
import pytest_asyncio
from sqlalchemy import select, text

DSN = os.environ.get("SEARCH_PG_TEST_DSN")

WORD = "собеседование"
ESCAPED = json.dumps({"zeta": 1, "notes": [{"text": f"Назначено {WORD} на пятницу"}], "alpha": 2})


def test_engines_write_letters_not_codes():
    """Все движки приложения пишут JSON без ensure_ascii."""
    from api.database import engine
    from api.utils.json_text import dumps

    assert engine.dialect._json_serializer is dumps
    assert dumps({"t": "зюзин"}) == '{"t": "зюзин"}'


def test_recode_keeps_key_order_and_bad_json():
    from api.services.json_unescape import recode

    assert "\\u" in ESCAPED
    assert recode(ESCAPED) == json.dumps(json.loads(ESCAPED), ensure_ascii=False)
    assert list(json.loads(recode(ESCAPED))) == ["zeta", "notes", "alpha"]
    assert recode("{битый") == "{битый"


@pytest_asyncio.fixture
async def db():
    if not DSN:
        pytest.skip("нужен SEARCH_PG_TEST_DSN (пустая тестовая база Postgres)")
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    import api.models  # noqa: F401
    from api.models.database import Base
    from api.services import search_index as si
    from api.utils.json_text import dumps

    eng = create_async_engine(DSN, json_serializer=dumps)
    async with eng.begin() as c:
        await c.execute(text("DROP SCHEMA public CASCADE"))
        await c.execute(text("CREATE SCHEMA public"))
        await c.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await c.run_sync(Base.metadata.create_all)
        await c.execute(text("INSERT INTO organizations (id, name, slug) VALUES (1, 'o', 'o')"))
    si.set_pg_trgm_available(None)
    async with AsyncSession(eng, expire_on_commit=False) as s:
        yield s
    si.set_pg_trgm_available(None)
    await eng.dispose()


async def _add(db, name, **kw):
    from api.models.database import Entity, EntityStatus, EntityType

    e = Entity(org_id=1, type=EntityType.candidate, name=name, status=EntityStatus.new,
               extra_data=kw.get("extra_data", {}), tags=kw.get("tags", []))
    db.add(e)
    await db.commit()
    return e.id


async def _found(db, q):
    from api.models.database import Entity
    from api.services import search_index as si

    query, _ = await si.apply_text_search(db, select(Entity).where(Entity.org_id == 1), q)
    return sorted(e.name for e in (await db.execute(query)).scalars().all())


@pytest.mark.asyncio
async def test_new_comment_is_searchable(db):
    await _add(db, "Козлов Антон", extra_data={"notes": [{"text": f"Прошёл {WORD}"}]}, tags=["перформер"])
    raw = (await db.execute(text("SELECT extra_data::text, tags::text FROM entities"))).one()
    assert WORD in raw[0] and "\\u" not in raw[0]
    assert "перформер" in raw[1]
    assert await _found(db, WORD) == ["Козлов Антон"]


@pytest.mark.asyncio
async def test_old_escaped_rows_recoded(db):
    from api.services.json_unescape import unescape_entity_json

    eid = await _add(db, "Сидоров Олег")
    await db.execute(
        text("UPDATE entities SET extra_data = CAST(:x AS json), tags = CAST(:t AS json), "
             "updated_at = '2026-10-01 10:00' WHERE id = :id"),
        {"x": ESCAPED, "t": json.dumps(["перформер"]), "id": eid},
    )
    await db.commit()
    assert await _found(db, WORD) == []  # так было на проде

    assert await unescape_entity_json(db) == 2
    raw, tags, updated = (await db.execute(
        text("SELECT extra_data::text, tags::text, updated_at FROM entities WHERE id = :id"), {"id": eid}
    )).one()
    assert list(json.loads(raw)) == ["zeta", "notes", "alpha"]  # порядок ключей тот же
    assert json.loads(raw) == json.loads(ESCAPED)  # смысл тот же
    assert "перформер" in tags
    assert updated.strftime("%Y-%m-%d %H:%M") == "2026-10-01 10:00"  # «изменено» не сдвинулось
    assert await _found(db, WORD) == ["Сидоров Олег"]

    assert await unescape_entity_json(db) == 0  # второй старт ничего не трогает


@pytest.mark.asyncio
async def test_row_changed_meanwhile_is_left_alone(db, monkeypatch):
    """Карточку сохранили между чтением и записью — её правку не затираем."""
    from api.services import json_unescape

    eid = await _add(db, "Петров Пётр")
    await db.execute(text("UPDATE entities SET extra_data = CAST(:x AS json) WHERE id = :id"),
                     {"x": ESCAPED, "id": eid})
    await db.commit()

    fresh = json.dumps({"notes": [{"text": "свежий комментарий"}]}, ensure_ascii=False)

    # Между SELECT и UPDATE «рекрутёр сохраняет» карточку: отдаём перекодировщику
    # прочитанные строки, а в базе тем временем лежит уже другой текст.
    orig_execute = db.execute

    async def execute(stmt, params=None, *a, **kw):
        res = await orig_execute(stmt, params, *a, **kw)
        if str(stmt).startswith("SELECT id, extra_data::text"):
            rows = res.all()
            await orig_execute(text("UPDATE entities SET extra_data = CAST(:f AS json) WHERE id = :id"),
                               {"f": fresh, "id": eid})

            class _R:
                def all(self_inner):
                    return rows
            return _R()
        return res

    monkeypatch.setattr(db, "execute", execute)
    assert await json_unescape.unescape_entity_json(db) == 0
    monkeypatch.undo()
    raw = (await db.execute(text("SELECT extra_data::text FROM entities WHERE id = :id"), {"id": eid})).scalar()
    assert raw == fresh
