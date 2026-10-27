"""
Tests for HR Analytics API

Tests dashboard overview, funnel data, and analytics endpoints.
"""

import pytest
from datetime import datetime, timedelta


class TestAnalyticsModels:
    """Test analytics models."""

    def test_analytics_models_exist(self):
        """Test that analytics models can be imported."""
        from api.models.analytics import (
            HRAnalyticsSnapshot,
            VacancyMetrics,
            SnapshotPeriod
        )

        assert HRAnalyticsSnapshot is not None
        assert VacancyMetrics is not None
        assert SnapshotPeriod is not None

    def test_snapshot_period_enum(self):
        """Test SnapshotPeriod enum values."""
        from api.models.analytics import SnapshotPeriod

        assert hasattr(SnapshotPeriod, 'daily')
        assert hasattr(SnapshotPeriod, 'weekly')
        assert hasattr(SnapshotPeriod, 'monthly')


class TestAnalyticsRouters:
    """Test analytics router configuration."""

    def test_analytics_router_exists(self):
        """Test that analytics router can be imported."""
        from api.routes.analytics import router

        assert router is not None

        # Check that routes are registered
        routes = [r.path for r in router.routes if hasattr(r, 'path')]
        assert len(routes) > 0

    def test_dashboard_router_exists(self):
        """Test that dashboard router exists."""
        from api.routes.analytics.dashboard import router

        assert router is not None

    def test_vacancies_router_exists(self):
        """Test that vacancies analytics router exists."""
        from api.routes.analytics.vacancies import router

        assert router is not None

    def test_funnel_router_exists(self):
        """Test that funnel router exists."""
        from api.routes.analytics.funnel import router

        assert router is not None


class TestFunnelStages:
    """Test funnel stage configuration."""

    def test_funnel_stages_defined(self):
        """Test that funnel stages are properly defined."""
        from api.routes.analytics.funnel import FUNNEL_STAGES, STAGE_LABELS

        expected_stages = [
            "applied",
            "screening",
            "phone_screen",
            "interview",
            "assessment",
            "offer",
            "hired"
        ]

        assert FUNNEL_STAGES == expected_stages

        # Check that all stages have labels
        for stage in FUNNEL_STAGES:
            assert stage in STAGE_LABELS

    def test_stage_labels_are_russian(self):
        """Test that stage labels are in Russian."""
        from api.routes.analytics.funnel import STAGE_LABELS

        # Подписи — из общего справочника этапов (services/hr_stages.py), а не
        # свой словарь: «Скрининг» переименован в «Выполняет ТЗ», «Принят» —
        # в «Оффер принят».
        from api.services.hr_stages import STAGE_LABELS as HR_STAGE_LABELS
        assert STAGE_LABELS.get("applied") == "Новый"
        assert STAGE_LABELS.get("screening") == "Выполняет ТЗ"
        assert STAGE_LABELS.get("hired") == "Оффер принят"
        assert STAGE_LABELS.get("rejected") == "Отказ"
        for stage, label in STAGE_LABELS.items():
            assert label == HR_STAGE_LABELS.get(stage, label)


class TestDashboardSchemas:
    """Test dashboard response schemas."""

    def test_dashboard_overview_schema(self):
        """Test DashboardOverview schema fields."""
        from api.routes.analytics.dashboard import DashboardOverview

        # Create a sample instance to verify fields
        overview = DashboardOverview(
            vacancies_total=10,
            vacancies_open=5,
            vacancies_draft=2,
            vacancies_closed_this_month=3,
            candidates_total=100,
            candidates_new_this_month=20,
            candidates_in_pipeline=50,
            applications_total=200,
            applications_this_month=30,
            hires_this_month=5,
            hires_this_quarter=15,
            avg_time_to_hire_days=14.5,
            rejections_this_month=10,
        )

        assert overview.vacancies_total == 10
        assert overview.vacancies_open == 5
        assert overview.candidates_total == 100
        assert overview.hires_this_month == 5
        assert overview.avg_time_to_hire_days == 14.5

    def test_funnel_data_schema(self):
        """Test FunnelData schema fields."""
        from api.routes.analytics.funnel import FunnelData, FunnelStage

        stage = FunnelStage(
            stage="applied",
            label="Новый",
            count=100,
            percentage=100.0,
            conversion_from_previous=None
        )

        funnel = FunnelData(
            stages=[stage],
            total_applications=100,
            total_hires=10,
            overall_conversion=10.0,
            rejected_count=20,
            withdrawn_count=5,
        )

        assert funnel.total_applications == 100
        assert funnel.total_hires == 10
        assert funnel.overall_conversion == 10.0
        assert len(funnel.stages) == 1


class TestConversionCalculations:
    """Test conversion rate calculations."""

    def test_conversion_rate_calculation(self):
        """Test basic conversion rate calculation."""
        from_count = 100
        to_count = 80

        conversion_rate = round(to_count / from_count * 100, 1) if from_count > 0 else 0

        assert conversion_rate == 80.0

    def test_conversion_rate_zero_division(self):
        """Test conversion rate with zero from_count."""
        from_count = 0
        to_count = 10

        conversion_rate = round(to_count / from_count * 100, 1) if from_count > 0 else 0

        assert conversion_rate == 0

    def test_overall_conversion_calculation(self):
        """Test overall funnel conversion calculation."""
        total_applications = 100
        total_hires = 5

        overall_conversion = round(total_hires / total_applications * 100, 1) if total_applications > 0 else 0

        assert overall_conversion == 5.0


class TestDateRangeCalculations:
    """Test date range calculations for analytics."""

    def test_month_start_calculation(self):
        """Test month start calculation."""
        now = datetime(2026, 1, 15, 14, 30, 45)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        assert month_start.day == 1
        assert month_start.hour == 0
        assert month_start.minute == 0
        assert month_start.month == 1

    def test_quarter_start_calculation(self):
        """Test quarter start calculation."""
        # January = Q1
        now = datetime(2026, 1, 15)
        quarter_start = now.replace(month=((now.month - 1) // 3) * 3 + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
        assert quarter_start.month == 1

        # April = Q2
        now = datetime(2026, 4, 15)
        quarter_start = now.replace(month=((now.month - 1) // 3) * 3 + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
        assert quarter_start.month == 4

        # October = Q4
        now = datetime(2026, 10, 15)
        quarter_start = now.replace(month=((now.month - 1) // 3) * 3 + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
        assert quarter_start.month == 10

    def test_days_ago_calculation(self):
        """Test days ago calculation for trends."""
        now = datetime.utcnow()
        days = 30
        start_date = (now - timedelta(days=days)).date()

        assert (now.date() - start_date).days == 30
