"""Расчёт времени сообщений. Чистые функции: всё в naive UTC, местное время — по поясу кандидата."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

Job = tuple[str, datetime, dict]

# Время, которое ТЗ не задаёт (решено в PLAN.md)
DAY_BEFORE_HOUR = 10
LOOM_HOUR = 20          # ТЗ 3.4
LOOM_MORNING_HOUR = 10  # ТЗ 3.4: «одно напоминание утром»
SURVEY_HOUR = 12
STAFF_HOUR = 10
FIRST_DAY_HOUR = 10       # чек-лист первого дня: «около 10:00»
FIRST_DAY_HR_HOUR = 12
FIRST_DAY_SURVEY_HOUR = 18  # «в конце первого дня»
NO_DECISION_HOUR = 18


def local_to_utc(local: datetime, tz: str) -> datetime:
    aware = local.replace(tzinfo=ZoneInfo(tz)) if local.tzinfo is None else local
    return aware.astimezone(timezone.utc).replace(tzinfo=None)


def utc_to_local(utc: datetime, tz: str) -> datetime:
    return utc.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tz))


def at_local(day: date, hour: int, tz: str) -> datetime:
    return local_to_utc(datetime.combine(day, time(hour)), tz)


def add_months(d: date, months: int) -> date:
    index = d.month - 1 + months
    year, month = d.year + index // 12, index % 12 + 1
    return date(year, month, min(d.day, monthrange(year, month)[1]))


def practice_last_day(start_day: date, practice_days: int) -> date:
    return start_day + timedelta(days=practice_days - 1)


def _today_and_start(now_utc: datetime, start_utc: datetime, tz: str) -> tuple[date, date]:
    return utc_to_local(now_utc, tz).date(), utc_to_local(start_utc, tz).date()


def retry_interval(now_utc: datetime, start_utc: datetime, tz: str) -> timedelta:
    """ТЗ 3.1: через 2 часа, если старт сегодня или завтра, иначе через 24 часа."""
    today, start_day = _today_and_start(now_utc, start_utc, tz)
    return timedelta(hours=2) if start_day <= today + timedelta(days=1) else timedelta(hours=24)


def needs_day_before(now_utc: datetime, start_utc: datetime, tz: str) -> bool:
    """ТЗ 3.1: напоминание за день — только если старт позже, чем завтра."""
    today, start_day = _today_and_start(now_utc, start_utc, tz)
    return start_day > today + timedelta(days=1)


def preboarding_jobs(now_utc: datetime, start_utc: datetime, tz: str, practice_days: int) -> list[Job]:
    start_day = utc_to_local(start_utc, tz).date()
    jobs: list[Job] = [("invite_check", now_utc + retry_interval(now_utc, start_utc, tz), {})]
    if needs_day_before(now_utc, start_utc, tz):
        jobs.append(("day_before", at_local(start_day - timedelta(days=1), DAY_BEFORE_HOUR, tz), {}))
    for offset in range(practice_days):
        day = start_day + timedelta(days=offset)
        jobs.append(("loom", at_local(day, LOOM_HOUR, tz), {"day": day.isoformat()}))
    last_day = practice_last_day(start_day, practice_days)
    jobs.append(("practice_deadline", at_local(last_day, NO_DECISION_HOUR, tz), {}))
    return jobs


def onboarding_jobs(department_start: date, tz: str) -> list[Job]:
    """ТЗ 4: сроки считаются от даты перехода в отдел."""
    d = department_start
    month3 = add_months(d, 3)
    before_end = month3 - timedelta(days=14)
    plan = [
        # Чек-лист первого рабочего дня (ТЗ, стр. 11–13)
        ("first_day_welcome", d, FIRST_DAY_HOUR, {}),
        ("staff_reminder", d, FIRST_DAY_HOUR, {"kind": "lead_first_day"}),
        ("staff_reminder", d, FIRST_DAY_HR_HOUR, {"kind": "hr_first_day"}),
        ("survey", d, FIRST_DAY_SURVEY_HOUR, {"kind": "first_day"}),
        ("survey", d + timedelta(days=5), SURVEY_HOUR, {"kind": "week"}),  # день 6
        ("staff_reminder", d + timedelta(days=6), STAFF_HOUR, {"kind": "hr_call_week"}),  # день 7
        ("survey", add_months(d, 1), SURVEY_HOUR, {"kind": "month1"}),
        ("staff_reminder", add_months(d, 1), STAFF_HOUR, {"kind": "checkpoint_m1"}),
        ("survey", add_months(d, 2), SURVEY_HOUR, {"kind": "month2"}),
        ("staff_reminder", add_months(d, 2), STAFF_HOUR, {"kind": "checkpoint_m2"}),
        ("survey", before_end, SURVEY_HOUR, {"kind": "month3"}),
        ("staff_reminder", before_end, STAFF_HOUR, {"kind": "checkpoint_m3"}),
        ("staff_reminder", month3, STAFF_HOUR, {"kind": "probation_close"}),
        ("staff_reminder", add_months(d, 6), STAFF_HOUR, {"kind": "control_6m"}),
    ]
    return [(kind, at_local(day, hour, tz), payload) for kind, day, hour, payload in plan]
