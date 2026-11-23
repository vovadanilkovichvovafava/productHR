"""Рабочий день платформы — московский (решение владельца, 23.11.2026).

Сервер сам решает, какой сегодня день (автодата «выход в отдел», дата в
документах, границы периода аналитики и ПЭН) — по Москве, а не по UTC.
"""
from datetime import date, datetime

from api.routes.analytics.reports import _get_date_filter
from api.routes.employees import LeaveRequestCreate
from api.routes.pen import _period_bounds
from api.services.biz_time import (
    biz_day_end_utc, biz_day_start_utc, format_biz_date, format_biz_datetime, to_biz, to_naive_utc,
)


def test_moscow_day_bounds_in_utc():
    # Московские сутки 01.11 = с 31.10 21:00 UTC до 01.11 20:59:59.999999 UTC.
    assert biz_day_start_utc(date(2026, 11, 1)) == datetime(2026, 10, 31, 21, 0)
    assert biz_day_end_utc(date(2026, 11, 1)) == datetime(2026, 11, 1, 20, 59, 59, 999999)


def test_night_action_is_today_in_moscow():
    # 22:30 UTC 19.11 — это уже 01:30 20.11 по Москве.
    assert to_biz(datetime(2026, 11, 19, 22, 30)).date() == date(2026, 11, 20)


def test_analytics_custom_period_is_moscow_days():
    df, dt = _get_date_filter("custom", "2026-11-01", "2026-11-30")
    assert df == datetime(2026, 10, 31, 21, 0)
    assert dt == datetime(2026, 11, 30, 20, 59, 59, 999999)
    # Перевод в 01:00 МСК 1-го числа попадает в ноябрь, а не в октябрь.
    assert df <= datetime(2026, 10, 31, 22, 0) <= dt


def test_pen_period_includes_last_day():
    pf, pt = _period_bounds(datetime(2026, 11, 1), datetime(2026, 11, 23))
    assert pf == datetime(2026, 10, 31, 21, 0)
    # Событие сегодня днём (последний день периода) — в периоде.
    assert pf <= datetime(2026, 11, 23, 12, 0) <= pt


def test_human_dates_in_russian_moscow():
    # Было strftime('%d %B %Y') по UTC: «19 November 2026».
    assert format_biz_date(datetime(2026, 11, 19, 22, 30)) == "20 ноября 2026"
    assert format_biz_datetime(datetime(2026, 11, 19, 21, 36)) == "20.11.2026 00:36 МСК"


def test_leave_request_dates_with_zone_are_stored_naive():
    # «Мой профиль» шлёт toISOString() с «Z» — в базу должно уйти без пояса.
    req = LeaveRequestCreate(type="vacation", start_date="2026-12-01T00:00:00.000Z",
                             end_date="2026-12-05T00:00:00.000Z")
    assert req.start_date == datetime(2026, 12, 1) and req.start_date.tzinfo is None
    assert req.end_date == datetime(2026, 12, 5)
    plain = LeaveRequestCreate(type="vacation", start_date="2026-12-01T00:00:00", end_date="2026-12-05T00:00:00")
    assert plain.start_date == datetime(2026, 12, 1)
    assert to_naive_utc(None) is None
