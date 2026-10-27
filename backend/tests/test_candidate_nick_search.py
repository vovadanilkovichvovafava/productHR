"""Юнит-тесты для строгого поиска по telegram-нику и поиска по комментариям
(is_nick_query / nick_search_conditions / notes_search_conditions).

Чисто функциональные — без БД. Проверяют:
- «@»-запрос детектится как ник-запрос;
- обычные запросы (в т.ч. email с «@» не в начале) — нет;
- nick_search_conditions даёт ровно три условия (telegram + комментарии +
  контакты из шапки резюме, добавлены 01.10.2026) и пусто для пустого запроса;
- notes_search_conditions (прицельный поиск по extra_data.notes) даёт ровно
  одно условие для непустого запроса и пусто для пустого.
"""
import pytest

from api.services.search_index import is_nick_query, nick_search_conditions, notes_search_conditions


@pytest.mark.parametrize(
    "q, expected",
    [
        ("@shblsn", True),
        ("shblsn", False),
        ("  @x", True),
        ("", False),
        ("ivan@mail.ru", False),  # «@» не в начале — это почта, не ник
    ],
)
def test_is_nick_query(q, expected):
    assert is_nick_query(q) is expected


def test_nick_search_conditions_valid_nick():
    conds = nick_search_conditions("@shblsn")
    # 3-е условие — ник из шапки резюме (extra_data.resume_contacts): в поля
    # карточки его часто не переносят, см. test_nick_search_fallback.py.
    assert len(conds) == 3


def test_nick_search_conditions_bare_at():
    assert nick_search_conditions("@") == []


def test_nick_search_conditions_empty():
    assert nick_search_conditions("") == []


def test_notes_search_conditions_valid_query():
    conds = notes_search_conditions("shblsn")
    assert len(conds) == 1


def test_notes_search_conditions_empty():
    assert notes_search_conditions("") == []
