"""Паспортная транслитерация в поиске и дедупе: «Arsenii Ziuzin» = «Арсений Зюзин».

Эльвира, 03.11.2026: кандидат добавлен латиницей (так в LinkedIn и в
загранпаспорте: й → i, ю → iu, я → ia), и ни «зюзин», ни «арсений зюзин» его
не находили — наша обычная таблица переводит «зюзин» в «zyuzin», а «Ziuzin» —
в «зиузин», и слова не встречались. Паспортная запись добавлена ВТОРЫМ
вариантом, обычная осталась.

Триграммную ветку (pg_trgm) тут не поднять — SQLite; она ищет слова запроса в
блобе search_name, поэтому проверяем, что нужное слово в блобе ЕСТЬ целиком
(word_similarity = 1). ILIKE-ветку — настоящим запросом, как в test_search_yo.
"""
import pytest
import pytest_asyncio
from sqlalchemy import select, or_

from api.models.database import Entity, EntityType, EntityStatus
from api.services import search_index as si
from api.services.similarity import count_shared_name_words, transliterate_ru_to_en, TRANSLIT_RU_EN_PASSPORT


def test_passport_table():
    assert transliterate_ru_to_en("Арсений Зюзин", TRANSLIT_RU_EN_PASSPORT) == "arsenii ziuzin"
    assert transliterate_ru_to_en("Мария Ковалёва", TRANSLIT_RU_EN_PASSPORT) == "mariia kovaleva"
    # обычная таблица не изменилась
    assert transliterate_ru_to_en("Арсений Зюзин") == "arseniy zyuzin"


@pytest.mark.parametrize("q,word", [("зюзин", "ziuzin"), ("арсений", "arsenii"), ("Зюзин", "ziuzin")])
def test_query_reaches_latin_card(q, word):
    """Кириллический запрос даёт паспортное слово, которое лежит в блобе латинской карточки."""
    blob = si.build_search_name("Arsenii Ziuzin", "Senior Media Buyer", "AdQuantum").split()
    assert word in blob
    assert word in si._search_word_variants(q.lower())


@pytest.mark.parametrize("q", ["ziuzin", "arsenii", "zyuzin", "зюзин"])
def test_latin_query_reaches_cyrillic_card(q):
    """И обратно: карточка кириллицей, ищут так, как написано в паспорте."""
    blob = set(si.build_search_name("Арсений Зюзин").split())
    assert blob & si._search_word_variants(q)


def test_dedup_counts_both_words():
    assert count_shared_name_words("Arsenii Ziuzin", "Арсений Зюзин") == 2
    # разные фамилии по-прежнему разные
    assert count_shared_name_words("Arsenii Ziuzin", "Зюзин Семён Олегович") == 1


@pytest_asyncio.fixture
async def ziuzin(db_session, organization, admin_user):
    for name in ("Arsenii Ziuzin", "Зюзин Семён Олегович"):
        db_session.add(Entity(org_id=organization.id, type=EntityType.candidate, name=name,
                              status=EntityStatus.new, created_by=admin_user.id))
    await db_session.commit()


async def _search(db_session, organization, q):
    si.set_pg_trgm_available(False)  # ILIKE-ветка
    try:
        rows = await db_session.execute(
            select(Entity.name).where(Entity.org_id == organization.id, or_(*si.name_search_conditions(q)))
        )
        return sorted(r[0] for r in rows.all())
    finally:
        si.set_pg_trgm_available(None)


@pytest.mark.asyncio
@pytest.mark.parametrize("q", ["арсений зюзин", "арсений", "зюзин"])
async def test_ilike_branch_finds_latin_card(db_session, organization, ziuzin, q):
    assert "Arsenii Ziuzin" in await _search(db_session, organization, q)
