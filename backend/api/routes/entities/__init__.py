"""
Entities module - combines all entity-related routers.

This module provides a combined router that aggregates all entity endpoints:
- CRUD operations (create, read, update, delete)
- File upload/download operations
- Memory/notes operations (profiles, sharing, linking)
- Search and filter operations
- Bulk operations (resume parsing, profile generation)
"""
from fastapi import APIRouter

from .crud import router as crud_router
from .trash import router as trash_router
from .notes import router as notes_router
from .archive import router as archive_router
from .hire import router as hire_router
from .files import router as files_router
from .memory import router as memory_router
from .search import router as search_router
from .entity_vacancies import router as entity_vacancies_router
from .duplicates import router as duplicates_router
from .bulk import router as bulk_router
from .share_links import router as share_links_router

# Re-export common items for backwards compatibility with tests
from .common import (
    EntityCreate,
    EntityUpdate,
    EntityResponse,
    StatusUpdate,
    normalize_telegram_username,
    validate_email,
    normalize_and_validate_identifiers,
    check_entity_access,
    OwnershipFilter,
)

from .files import (
    validate_file_upload,
    check_disk_space,
    get_entity_file_count,
    ENTITY_FILES_DIR,
    MAX_FILE_SIZE,
    MAX_FILES_PER_ENTITY,
    MIN_DISK_SPACE_MB,
    ALLOWED_EXTENSIONS,
    ALLOWED_MIME_TYPES,
    DANGEROUS_PATTERNS,
)

# Create the combined router
router = APIRouter()

# Include all sub-routers
# ВАЖНО: share_links раньше crud — иначе GET /{entity_id:int} перехватывает
# путь /public/candidate-preview/{token} и отдаёт 422 на "public".
router.include_router(share_links_router, tags=["entities-share-links"])

# CRUD operations (basic entity operations)
# Корзина — раньше crud: иначе GET /{entity_id} перехватит /trash.
router.include_router(trash_router, tags=["entities-trash"])
router.include_router(crud_router, tags=["entities-crud"])
# Лента карточки и архив — части прежнего crud.py (разрезан 20.10.2026).
router.include_router(notes_router, tags=["entities-crud"])
router.include_router(archive_router, tags=["entities-crud"])

# Hire operations (кандидат → сотрудник Factorial)
router.include_router(hire_router, tags=["entities-hire"])

# File operations
router.include_router(files_router, tags=["entities-files"])

# Memory/notes operations (profiles, sharing, linking chats/calls)
router.include_router(memory_router, tags=["entities-memory"])

# Search operations (smart search, red flags, recommendations, similar, duplicates)
router.include_router(search_router, tags=["entities-search"])
# Части прежнего search.py (разрезан 20.10.2026) — в том же порядке.
router.include_router(entity_vacancies_router, tags=["entities-search"])
router.include_router(duplicates_router, tags=["entities-search"])

# Bulk operations (resume parsing, bulk profile generation)
router.include_router(bulk_router, tags=["entities-bulk"])


# Add aliases for root path without trailing slash (for backwards compatibility)
# This is needed because tests and clients may call /api/entities without trailing slash
from .crud import list_entities, create_entity
router.add_api_route("", list_entities, methods=["GET"], tags=["entities-crud"])
router.add_api_route("", create_entity, methods=["POST"], status_code=201, tags=["entities-crud"])

__all__ = [
    "router",
    # Schemas
    "EntityCreate",
    "EntityUpdate",
    "EntityResponse",
    "StatusUpdate",
    "OwnershipFilter",
    # Helper functions
    "normalize_telegram_username",
    "validate_email",
    "normalize_and_validate_identifiers",
    "check_entity_access",
    # File validation
    "validate_file_upload",
    "check_disk_space",
    "get_entity_file_count",
    # File constants
    "ENTITY_FILES_DIR",
    "MAX_FILE_SIZE",
    "MAX_FILES_PER_ENTITY",
    "MIN_DISK_SPACE_MB",
    "ALLOWED_EXTENSIONS",
    "ALLOWED_MIME_TYPES",
    "DANGEROUS_PATTERNS",
]
