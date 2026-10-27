"""
HR Analytics Models

Provides models for HR analytics and reporting:
- HRAnalyticsSnapshot: Daily/weekly snapshots of HR metrics
- VacancyMetrics: Cached metrics per vacancy
"""

from datetime import datetime, date
from typing import Optional
from sqlalchemy import (
    Boolean, Column, DateTime, Date, Enum as SQLEnum,
    ForeignKey, Index, Integer, String, Text, JSON, Float, func, UniqueConstraint
)
from sqlalchemy.orm import relationship
import enum

from .database import Base


class SnapshotPeriod(str, enum.Enum):
    """Period type for analytics snapshot"""
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"


class HRAnalyticsSnapshot(Base):
    """Periodic snapshot of HR metrics for trend analysis.

    Stores aggregated metrics for:
    - Vacancy statistics (open, closed, time-to-fill)
    - Candidate pipeline (applications, conversions)
    - Hiring funnel metrics
    """
    __tablename__ = "hr_analytics_snapshots"

    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)

    # Period info
    period_type = Column(SQLEnum(SnapshotPeriod), nullable=False)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)

    # Vacancy metrics
    vacancies_total = Column(Integer, default=0)
    vacancies_open = Column(Integer, default=0)
    vacancies_closed = Column(Integer, default=0)
    vacancies_new = Column(Integer, default=0)  # Opened during period
    avg_time_to_fill_days = Column(Float, nullable=True)  # Average days to fill position

    # Application metrics
    applications_total = Column(Integer, default=0)
    applications_new = Column(Integer, default=0)  # New during period
    applications_hired = Column(Integer, default=0)
    applications_rejected = Column(Integer, default=0)

    # Funnel metrics (by stage)
    funnel_data = Column(JSON, default=dict)
    # Example: {
    #   "applied": 100,
    #   "screening": 50,
    #   "phone_screen": 30,
    #   "interview": 15,
    #   "assessment": 8,
    #   "offer": 5,
    #   "hired": 3
    # }

    # Conversion rates
    conversion_rates = Column(JSON, default=dict)
    # Example: {
    #   "applied_to_screening": 0.50,
    #   "screening_to_interview": 0.60,
    #   "interview_to_offer": 0.33,
    #   "offer_to_hired": 0.60,
    #   "overall": 0.03
    # }

    # Source analytics
    source_breakdown = Column(JSON, default=dict)
    # Example: {
    #   "linkedin": {"applications": 40, "hired": 2},
    #   "referral": {"applications": 20, "hired": 1},
    #   "website": {"applications": 30, "hired": 0}
    # }

    # Time metrics
    avg_time_in_stage_days = Column(JSON, default=dict)
    # Example: {
    #   "screening": 3.5,
    #   "interview": 5.2,
    #   "offer": 2.1
    # }

    # Department breakdown (if org-wide snapshot)
    department_breakdown = Column(JSON, default=dict)
    # Example: {
    #   "1": {"vacancies": 5, "hired": 2},
    #   "2": {"vacancies": 3, "hired": 1}
    # }

    # Metadata
    created_at = Column(DateTime, default=func.now())
    computed_at = Column(DateTime, default=func.now())

    __table_args__ = (
        # Unique snapshot per org/department per period
        UniqueConstraint('org_id', 'department_id', 'period_type', 'period_start', name='uq_analytics_snapshot'),
        # For querying snapshots
        Index('ix_analytics_snapshot_period', 'org_id', 'period_type', 'period_start'),
    )

    # Relationships
    organization = relationship("Organization")
    department = relationship("Department")


class VacancyMetrics(Base):
    """Cached metrics for individual vacancy.

    Updated periodically or on-demand for performance.
    """
    __tablename__ = "vacancy_metrics"

    id = Column(Integer, primary_key=True)
    vacancy_id = Column(Integer, ForeignKey("vacancies.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)

    # Application counts by stage
    stage_counts = Column(JSON, default=dict)
    # Example: {
    #   "applied": 20,
    #   "screening": 10,
    #   "interview": 5,
    #   "offer": 2,
    #   "hired": 1,
    #   "rejected": 8
    # }

    # Time metrics
    avg_time_to_stage_days = Column(JSON, default=dict)
    # Time from applied to each stage
    # Example: {
    #   "screening": 2.5,
    #   "interview": 7.0,
    #   "offer": 14.5,
    #   "hired": 21.0
    # }

    # Source effectiveness
    source_stats = Column(JSON, default=dict)
    # Example: {
    #   "linkedin": {"count": 10, "hired": 1, "conversion": 0.10},
    #   "referral": {"count": 5, "hired": 0, "conversion": 0.00}
    # }

    # Score distribution
    score_distribution = Column(JSON, default=dict)
    # Example: {
    #   "excellent": 3,  # score >= 80
    #   "good": 8,       # score 60-79
    #   "average": 5,    # score 40-59
    #   "below_avg": 4   # score < 40
    # }

    avg_compatibility_score = Column(Float, nullable=True)

    # Timeline
    days_open = Column(Integer, nullable=True)  # Days since published
    estimated_days_to_fill = Column(Integer, nullable=True)  # Based on historical data

    # Rating stats
    avg_rating = Column(Float, nullable=True)

    # Last updated
    computed_at = Column(DateTime, default=func.now())

    # Relationships
    vacancy = relationship("Vacancy")
