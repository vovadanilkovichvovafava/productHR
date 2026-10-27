"""Телефоны для сравнения дублей: международный формат (E.164) с кодом страны.

Зачем (этап 1 переделки дублей). Раньше номера сравнивались по последним 10
цифрам. Для России/Казахстана это работало («+7 916…» и «8 916…» → 9161234567),
а для стран с 9-значным национальным номером — нет: «+998 90 123-45-67» даёт
8901234567, а тот же номер, записанный по-узбекски «90 123 45 67», — 901234567.
Так же расходились Грузия (555 12 34 56 / +995…) и Беларусь (80 29… / +375 29…).

Теперь номер разбирается по правилам стран (библиотека phonenumbers — локальные
таблицы Google, без сети и без ИИ) и приводится к виду +<код страны><номер>.
Номер без кода страны пробуем как местный для стран, откуда реально приходят
кандидаты (:data:`HOME_REGIONS`); каждое допустимое прочтение — отдельный ключ.
Один и тот же местный номер бывает допустим в двух странах (узбекский 90… и
таджикский 90…): тогда у него два ключа. Совпадение телефона — один признак
(жёлтая плашка), так что редкое пересечение не делает пару «точной».

Старый ключ «последние 10 цифр» сохраняется ВДОБАВОК — на случай номера, которого
нет в таблицах библиотеки (новый диапазон): такие пары как находились, так и
находятся.
"""
import re
from functools import lru_cache
from typing import Iterable, Optional, Set

import phonenumbers

# Страны, чьи номера кандидаты пишут БЕЗ кода страны. Россия и Казахстан делят +7.
HOME_REGIONS = ("RU", "KZ", "BY", "UA", "UZ", "KG", "TJ", "GE", "AM", "AZ", "MD", "TM")

_NON_DIGITS = re.compile(r"\D")


def _e164(num) -> str:
    return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)


def _valid(text: str, region: Optional[str]) -> Optional[str]:
    try:
        num = phonenumbers.parse(text, region)
    except phonenumbers.NumberParseException:
        return None
    return _e164(num) if phonenumbers.is_valid_number(num) else None


@lru_cache(maxsize=20000)
def e164_variants(raw: str) -> frozenset:
    """Все допустимые прочтения номера в формате E.164 (пусто, если ни одного)."""
    text = (raw or "").strip()
    digits = _NON_DIGITS.sub("", text)
    if len(digits) < 7:
        return frozenset()

    # Явно международный: «+…» или «00…» — прочтение одно.
    if text.startswith("+") or digits.startswith("00"):
        intl = "+" + digits[2:] if digits.startswith("00") and not text.startswith("+") else "+" + digits
        hit = _valid(intl, None)
        if hit:
            return frozenset({hit})
        # «+7 029 …» — так разбор резюме портил белорусское «8 029 …» (дописывал
        # +7 к любому 11-значному номеру на 8). Восстанавливаем исходную запись.
        if digits.startswith("70") and len(digits) == 11:
            return _national_variants("8" + digits[1:])
        return frozenset()

    out = set(_national_variants(digits))
    # Код страны без плюса: «998901234567», «375291234567», «79161234567».
    hit = _valid("+" + digits, None)
    if hit:
        out.add(hit)
    return frozenset(out)


def _national_variants(digits: str) -> frozenset:
    out = set()
    for region in HOME_REGIONS:
        hit = _valid(digits, region)
        if hit:
            out.add(hit)
    return frozenset(out)


def phone_match_keys(phones: Iterable[Optional[str]]) -> Set[str]:
    """Ключи сравнения для набора номеров кандидата: E.164-прочтения + старые
    «последние 10 цифр» (запасной ключ для номеров, которых библиотека не знает)."""
    out: Set[str] = set()
    for raw in phones:
        if not raw:
            continue
        out |= e164_variants(str(raw))
        digits = _NON_DIGITS.sub("", str(raw))
        if len(digits) >= 10:
            out.add(digits[-10:])
    return out


def phone_tails7(phones: Iterable[Optional[str]]) -> Set[str]:
    """Последние 7 цифр — мягкая подсказка (разный код города при том же номере)."""
    out: Set[str] = set()
    for raw in phones:
        digits = _NON_DIGITS.sub("", str(raw or ""))
        if len(digits) >= 7:
            out.add(digits[-7:])
    return out


def to_e164_if_certain(raw: str) -> Optional[str]:
    """Номер в E.164, только если прочтение ОДНО. Для сохранения в карточку:
    двусмысленный местный номер лучше оставить как есть, чем приписать не ту страну."""
    variants = e164_variants(raw or "")
    return next(iter(variants)) if len(variants) == 1 else None
