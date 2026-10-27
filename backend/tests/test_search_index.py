"""Юнит-тесты умного поиска: денормализованный блоб + токенизация запроса."""
import re
from api.services.search_index import (
    build_search_name, query_tokens, fold_yo, _search_word_variants,
)


def test_build_search_name_cyrillic_both_scripts():
    s = build_search_name("Фаттахов Роман", position="Android Dev", tags=["Senior"])
    # исходные слова ФИО
    assert "фаттахов" in s and "роман" in s
    # транслит имени в латиницу
    assert "roman" in s
    assert re.search(r"[a-z]", s)  # латиница фамилии тоже есть
    # должность и теги — в блобе (единое окно ищет и по ним)
    assert "android dev" in s
    assert "senior" in s


def test_build_search_name_latin_input_reverse_translit():
    s = build_search_name("Roman Fattakhov")
    assert "roman" in s and "fattakhov" in s
    assert "роман" in s  # обратный транслит в кириллицу


def test_build_search_name_empty():
    assert build_search_name(None) == ""
    assert build_search_name("") == ""


def test_fold_yo():
    assert fold_yo("Дёмин Артём") == "Демин Артем"
    assert fold_yo("Демин") == "Демин"  # идемпотентно
    assert fold_yo(None) == ""


def test_build_search_name_yo_folded_into_blob():
    """«Дёмин» должен находиться по запросу «Демин»: свёрнутая форма лежит в блобе
    рядом с исходной (триграммы сами разницу в Ё не прощают — ≈0.5 при пороге 0.6)."""
    s = build_search_name("Дёмин Артём")
    words = set(s.split())
    assert "дёмин" in words and "артём" in words  # исходное написание сохранено
    assert "демин" in words and "артем" in words  # + свёрнутое


def test_search_word_variants_yo_both_directions():
    """Свёртка нужна с обеих сторон: ищут и «Демин» по «Дёмину», и наоборот."""
    assert "демин" in _search_word_variants("дёмин")
    assert "демин" in _search_word_variants("демин")


def test_query_tokens():
    assert query_tokens("  Роман   Фаттахов ") == ["роман", "фаттахов"]
    assert query_tokens("a Роман") == ["роман"]  # односимвольные отброшены
    assert query_tokens("") == []
