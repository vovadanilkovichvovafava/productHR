"""Телефоны разных стран в разной записи — один номер (этап 1 дедупа, 22.09.2026).

Раньше сравнивались последние 10 цифр: узбекские, грузинские и белорусские
номера в международной и местной записи не совпадали.
"""
import pytest

from api.services.duplicate_matcher import compare_key_sets
from api.services.phone_keys import e164_variants, phone_match_keys, to_e164_if_certain
from api.services.resume_parser import normalize_phone as parser_normalize_phone
from api.services.similarity import build_dup_keys

SAME_NUMBER = [
    # (страна, международная запись, местная запись)
    ("Россия", "+7 916 123-45-67", "8 (916) 123-45-67"),
    ("Казахстан", "+7 700 123 45 67", "8 700 1234567"),
    ("Узбекистан", "+998 90 123-45-67", "90 123 45 67"),
    ("Узбекистан без плюса", "998901234567", "90-123-45-67"),
    ("Беларусь", "+375 29 123-45-67", "80 29 123 45 67"),
    ("Беларусь, старый формат", "+375 29 123-45-67", "8 029 123 45 67"),
    ("Грузия", "+995 555 12 34 56", "555 12 34 56"),
    ("Украина", "+380 67 123 4567", "067 123 45 67"),
    ("Кыргызстан", "+996 700 123 456", "0700 123 456"),
    ("Германия (только +)", "+49 151 23456789", "0049 151 23456789"),
]


@pytest.mark.parametrize("country,intl,local", SAME_NUMBER, ids=[c for c, _, _ in SAME_NUMBER])
def test_same_number_in_two_writings_matches(country, intl, local):
    a = build_dup_keys(name="Анна Смирнова", phone=intl)
    b = build_dup_keys(name="Ольга Петрова", phone=local)
    strength, _, signals = compare_key_sets(a, b)
    assert strength == "phone", f"{country}: {intl} / {local} не совпали"
    assert any(s.field == "phone" and s.identity for s in signals)


def test_different_numbers_do_not_match():
    a = build_dup_keys(name="Анна Смирнова", phone="+998 90 123-45-67")
    b = build_dup_keys(name="Ольга Петрова", phone="+998 90 765-43-21")
    strength, _, signals = compare_key_sets(a, b)
    assert strength is None
    assert not any(s.field == "phone" and s.identity for s in signals)


def test_same_local_digits_in_other_country_is_not_same_number():
    # Одинаковые 9 цифр, но явно разные страны (оба номера с кодом) — не совпадение.
    a = build_dup_keys(name="Анна Смирнова", phone="+998 90 123 45 67")
    b = build_dup_keys(name="Ольга Петрова", phone="+992 90 123 45 67")
    strength, _, _ = compare_key_sets(a, b)
    assert strength is None


def test_parser_corrupted_belarus_number_is_recovered():
    # Разбор резюме превращал «8 029 …» в «+7 029 …» — такие номера уже лежат в базе.
    assert e164_variants("+70291234567") == frozenset({"+375291234567"})


def test_unknown_number_keeps_old_ten_digit_key():
    # Номер, которого нет в таблицах библиотеки, сравнивается как раньше.
    keys = phone_match_keys(["+7 000 111 22 33"])
    assert "0001112233" in keys


def test_ambiguous_local_number_is_not_stored_as_one_country():
    # «90 123 45 67» — и Узбекистан, и Таджикистан: страну не приписываем.
    assert len(e164_variants("90 123 45 67")) == 2
    assert to_e164_if_certain("90 123 45 67") is None


def test_parser_stores_international_format():
    assert parser_normalize_phone("8 029 123 45 67") == "+375291234567"
    assert parser_normalize_phone("8 916 123-45-67") == "+79161234567"
    assert parser_normalize_phone("+998 90 123 45 67") == "+998901234567"
