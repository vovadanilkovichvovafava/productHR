"""
HR Analytics API Routes

Provides endpoints for:
- Dashboard overview statistics
- Vacancy analytics
- Hiring funnel metrics
- Time-to-hire analytics
"""

from fastapi import APIRouter

from .dashboard import router as dashboard_router
from .vacancies import router as vacancies_router
from .funnel import router as funnel_router
from .reports import router as reports_router

router = APIRouter()

# Dashboard overview
router.include_router(dashboard_router, prefix="/dashboard", tags=["analytics-dashboard"])

# Vacancy analytics
router.include_router(vacancies_router, prefix="/vacancies", tags=["analytics-vacancies"])

# Funnel analytics
router.include_router(funnel_router, prefix="/funnel", tags=["analytics-funnel"])

# Huntflow-style reports center
router.include_router(reports_router, prefix="/reports", tags=["analytics-reports"])
