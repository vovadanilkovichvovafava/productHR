from fastapi import APIRouter
from .auth import router as auth_router
from .users import router as users_router
from .criteria import router as criteria_router
from .admin import router as admin_router
from .currency import router as currency_router
from .scoring import router as scoring_router
from . import email_templates
from . import analytics

api_router = APIRouter()

api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(users_router, prefix="/users", tags=["users"])
api_router.include_router(criteria_router, prefix="/criteria", tags=["criteria"])
api_router.include_router(admin_router, prefix="/admin", tags=["admin"])
api_router.include_router(currency_router, prefix="/currency", tags=["currency"])
api_router.include_router(scoring_router, prefix="/scoring", tags=["scoring"])
