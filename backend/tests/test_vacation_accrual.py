"""
Тесты начисления отпуска: 2 дня за полный месяц от department_start_date,
максимум 22 в цикле, СБРОС В НОЛЬ на годовщине (use-it-or-lose-it). Без испытательного срока.
`now` передаётся явно (фиксированная опорная дата) — тесты детерминированы
и не «мигают» на границе месяца.
"""
from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta

NOW = datetime(2026, 6, 8, 12, 0, 0)


def _calc_months_ago(months_ago: int) -> int:
    from api.routes.employees import _calculate_vacation_days
    start = NOW - relativedelta(months=months_ago)
    return _calculate_vacation_days(start, now=NOW)


class TestVacationAccrual:
    def test_none_returns_zero(self):
        from api.routes.employees import _calculate_vacation_days
        assert _calculate_vacation_days(None) == 0

    def test_future_start_returns_zero(self):
        from api.routes.employees import _calculate_vacation_days
        future = NOW + relativedelta(months=2)
        assert _calculate_vacation_days(future, now=NOW) == 0

    def test_sub_month_tenure_is_zero(self):
        from api.routes.employees import _calculate_vacation_days
        two_weeks_ago = NOW - timedelta(days=14)
        assert _calculate_vacation_days(two_weeks_ago, now=NOW) == 0

    def test_one_full_month_is_two_days(self):
        assert _calc_months_ago(1) == 2

    def test_no_probation_gate(self):
        assert _calc_months_ago(2) == 4

    def test_five_months(self):
        assert _calc_months_ago(5) == 10

    def test_eleven_months(self):
        assert _calc_months_ago(11) == 22

    def test_twelve_months_resets_to_zero(self):
        # Ровно год → новый цикл, «Накоплено» обнуляется.
        assert _calc_months_ago(12) == 0

    def test_thirteen_months_resets_to_2(self):
        # Годовщина пройдена → новый цикл, сброс.
        assert _calc_months_ago(13) == 2

    def test_twenty_four_months_resets_to_zero(self):
        assert _calc_months_ago(24) == 0

    def test_twenty_five_months_resets_to_2(self):
        assert _calc_months_ago(25) == 2


class TestCycleStart:
    def test_cycle_start_first_year(self):
        # В первый год начало цикла = дата приёма (точное равенство при фикс. now).
        from api.routes.employees import _cycle_start
        start = NOW - relativedelta(months=5)
        assert _cycle_start(start, now=NOW) == start

    def test_cycle_start_second_year(self):
        # После года начало цикла = приём + 12 мес.
        from api.routes.employees import _cycle_start
        start = NOW - relativedelta(months=15)
        assert _cycle_start(start, now=NOW) == start + relativedelta(months=12)

    def test_cycle_start_on_anniversary(self):
        # Ровно в годовщину (m=12) уже начинается новый цикл = приём + 12 мес.
        from api.routes.employees import _cycle_start
        start = NOW - relativedelta(months=12)
        assert _cycle_start(start, now=NOW) == start + relativedelta(months=12)

    def test_cycle_start_none(self):
        from api.routes.employees import _cycle_start
        assert _cycle_start(None) is None
