"""
Vacancy management API routes package.

This package contains all vacancy-related endpoints split into modules:
- common: Shared schemas, imports, and helper functions
- crud: Basic CRUD operations for vacancies
- applications: Application management endpoints
- kanban: канбан (ради тестов приватности), bulk-move, порядок в колонке
- sharing: Vacancy sharing endpoints
"""
from fastapi import APIRouter

# Import common schemas and helpers for backwards compatibility
from .common import (
    # Schemas
    VacancyCreate,
    VacancyUpdate,
    VacancyResponse,
    ApplicationCreate,
    ApplicationUpdate,
    ApplicationResponse,
    KanbanColumn,
    KanbanBoard,
    BulkStageUpdate,
    # Helper functions
    is_org_owner,
    has_full_database_access,
    get_user_department_ids,
    is_dept_lead_or_admin,
    can_access_vacancy,
    can_edit_vacancy,
    check_vacancy_access,
    # Logger
    logger,
)

# Create the combined router
# Note: This router is mounted at /api/vacancies in main.py
router = APIRouter()

# Import route handlers from submodules and add them to the router
# We need to import them after creating the router and add routes manually
# to avoid issues with multiple routers having overlapping paths

# Import CRUD handlers
from .crud import (
    list_vacancies,
    create_vacancy,
    get_vacancy,
    update_vacancy,
    delete_vacancy,
    get_assignable_users,
    assign_vacancy,
    take_vacancy,
    decline_vacancy,
)

# Import application handlers
from .applications import (
    list_applications,
    list_application_recruiters,
    create_application,
    take_application,
    update_application,
    delete_application,
)

# Import kanban handlers
from .kanban import (
    get_kanban_board,
    get_kanban_column,
    rebalance_stage_orders,
    bulk_move_applications,
)

# Import history handlers
from .history import (
    get_application_history,
    delete_application_history,
    update_application_history,
    set_pinned_entry,
    StageTransitionResponse,
)

# Import legacy-clone reconciliation (superadmin one-off)
from .reconcile import reconcile_clones, CloneReconcileReport

# Слияние вакансии-дубля в главную (админы HR)
from .merge import merge_vacancy_into

# Register routes in the correct order
# More specific routes must come before generic ones (like /{vacancy_id})

# Applications bulk-move: /applications/bulk-move must be before /applications/{application_id}
router.add_api_route("/applications/bulk-move", bulk_move_applications, methods=["POST"], tags=["vacancy-kanban"])

# Application stage transition history
router.add_api_route("/applications/{application_id}/history", get_application_history, methods=["GET"], tags=["vacancy-applications"])
router.add_api_route("/applications/{application_id}/history/{history_id}", delete_application_history, methods=["DELETE"], tags=["vacancy-applications"])
router.add_api_route("/applications/{application_id}/history/{history_id}", update_application_history, methods=["PATCH"], tags=["vacancy-applications"])
# Закреплённая запись ленты — одна на заявку (воронку).
router.add_api_route("/applications/{application_id}/pin", set_pinned_entry, methods=["PUT"], tags=["vacancy-applications"])

# Applications update/delete by ID: /applications/{application_id}
router.add_api_route("/applications/{application_id}", update_application, methods=["PUT"], tags=["vacancy-applications"])
# 204, как объявлено в декораторе applications.py: тут регистрация без него
# отдавала 200 с телом null.
router.add_api_route("/applications/{application_id}", delete_application, methods=["DELETE"], status_code=204, tags=["vacancy-applications"])

# Assignable users for responsible dropdown (must be before /{vacancy_id})
router.add_api_route("/assignable-users", get_assignable_users, methods=["GET"], tags=["vacancies"])

# Legacy-clone reconciliation (superadmin one-off) — before /{vacancy_id}
router.add_api_route("/admin/reconcile-clones", reconcile_clones, methods=["POST"], tags=["vacancies"])

# CRUD: list and create vacancies (root path)
router.add_api_route("", list_vacancies, methods=["GET"], tags=["vacancies"])
router.add_api_route("", create_vacancy, methods=["POST"], status_code=201, tags=["vacancies"])

# Vacancy-specific routes: /{vacancy_id}/...
router.add_api_route("/{vacancy_id}", get_vacancy, methods=["GET"], tags=["vacancies"])
router.add_api_route("/{vacancy_id}", update_vacancy, methods=["PUT"], tags=["vacancies"])
router.add_api_route("/{vacancy_id}", delete_vacancy, methods=["DELETE"], status_code=204, tags=["vacancies"])
router.add_api_route("/{vacancy_id}/assign", assign_vacancy, methods=["POST"], tags=["vacancies"])
router.add_api_route("/{vacancy_id}/take", take_vacancy, methods=["POST"], tags=["vacancies"])
router.add_api_route("/{vacancy_id}/decline", decline_vacancy, methods=["POST"], tags=["vacancies"])
router.add_api_route("/{target_id}/merge-from/{source_id}", merge_vacancy_into, methods=["POST"], tags=["vacancies"])

# Vacancy applications
# «Забрать» — более специфичный путь, регистрируем ДО generic /{vacancy_id}/applications.
router.add_api_route("/{vacancy_id}/applications/take", take_application, methods=["POST"], tags=["vacancy-applications"])
# Фильтр «Кандидаты: <рекрутёр>» над воронкой — кто ведёт и сколько (21.10.2026).
router.add_api_route("/{vacancy_id}/applications/recruiters", list_application_recruiters, methods=["GET"], tags=["vacancy-applications"])
router.add_api_route("/{vacancy_id}/applications", list_applications, methods=["GET"], tags=["vacancy-applications"])
router.add_api_route("/{vacancy_id}/applications", create_application, methods=["POST"], status_code=201, tags=["vacancy-applications"])

# Vacancy kanban — интерфейс не зовёт, держится ради тестов приватности.
router.add_api_route("/{vacancy_id}/kanban", get_kanban_board, methods=["GET"], tags=["vacancy-kanban"])
router.add_api_route("/{vacancy_id}/kanban/column/{stage}", get_kanban_column, methods=["GET"], tags=["vacancy-kanban"])

# Убраны 20.10.2026 — интерфейс их не звал: /stats/overview, «подходящие
# кандидаты» и рассылка им (/matching-candidates, /notify-candidates —
# отдавала контакты всего пула без скоупа, /invite-candidate).

# Vacancy sharing

# Re-export everything for backwards compatibility
__all__ = [
    # Main router
    "router",
    # Schemas
    "VacancyCreate",
    "VacancyUpdate",
    "VacancyResponse",
    "ApplicationCreate",
    "ApplicationUpdate",
    "ApplicationResponse",
    "KanbanColumn",
    "KanbanBoard",
    "BulkStageUpdate",
    "StageTransitionResponse",
    # Helper functions
    "is_org_owner",
    "has_full_database_access",
    "get_user_department_ids",
    "is_dept_lead_or_admin",
    "can_access_vacancy",
    "can_edit_vacancy",
    "check_vacancy_access",
    # Logger
    "logger",
]
