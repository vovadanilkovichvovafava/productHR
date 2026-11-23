"""Рабочее время платформы — московское (решение владельца, 23.11.2026).

Люди работают из разных стран (вплоть до Владивостока), но все — по Москве.
Время СОБЫТИЙ по-прежнему хранится в naive UTC, а показывает его браузер по
часам смотрящего. Москва нужна там, где сервер сам решает, КАКОЙ СЕГОДНЯ ДЕНЬ:
автодата «выход в отдел», дата в документах, границы дней в аналитике и ПЭН,
напоминания по датам. До этого день считался по UTC (часы контейнера), и всё,
что делали с 00:00 до 03:00 по Москве, получало вчерашнее число.

Смещение фиксированное (+3): в России нет перехода на летнее время с 2014
года, а базы поясов (tzdata) в образе может не быть.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

BIZ_TZ = timezone(timedelta(hours=3), "МСК")
BIZ_TZ_LABEL = "МСК"


def biz_now() -> datetime:
    """Сейчас по Москве (aware)."""
    return datetime.now(BIZ_TZ)


def biz_today() -> date:
    """Сегодняшнее число по Москве."""
    return biz_now().date()


def to_biz(value: datetime) -> datetime:
    """Время из базы (naive UTC) или aware — в московское (aware)."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(BIZ_TZ)


def biz_day_start_utc(day: date) -> datetime:
    """Начало московских суток в naive UTC — для сравнения с колонками базы."""
    return datetime.combine(day, time.min, BIZ_TZ).astimezone(timezone.utc).replace(tzinfo=None)


def biz_day_end_utc(day: date) -> datetime:
    """Последний момент московских суток в naive UTC (включительно)."""
    return biz_day_start_utc(day + timedelta(days=1)) - timedelta(microseconds=1)


def to_naive_utc(value: datetime | None) -> datetime | None:
    """Значение с поясом (пришло с «Z» или «+03:00») — в naive UTC, как в базе.
    Без пояса — как есть."""
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


_MONTHS_GEN = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)


def format_biz_date(value: datetime | date) -> str:
    """«21 октября 2026» по Москве (strftime('%B') в контейнере — по-английски)."""
    d = to_biz(value).date() if isinstance(value, datetime) else value
    return f"{d.day} {_MONTHS_GEN[d.month - 1]} {d.year}"


def format_biz_datetime(value: datetime) -> str:
    """«21.10.2026 14:05 МСК» — для текстов и файлов, где браузер не переведёт."""
    return to_biz(value).strftime("%d.%m.%Y %H:%M") + f" {BIZ_TZ_LABEL}"
