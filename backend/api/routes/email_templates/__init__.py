"""
Email Templates API Routes

Provides endpoints for:
- CRUD operations on email templates
- Sending emails to candidates
- Email history and analytics
"""

from fastapi import APIRouter

from .crud import router as crud_router
from .sending import router as sending_router
from .history import router as history_router

router = APIRouter()

# Template CRUD - includes /templates and /templates/{id}
router.include_router(crud_router, prefix="/templates", tags=["email-templates"])

# Email sending - includes /send, /preview, /send-bulk
router.include_router(sending_router, tags=["email-sending"])

# Email history - includes /history/logs, /history/stats
router.include_router(history_router, prefix="/history", tags=["email-history"])
