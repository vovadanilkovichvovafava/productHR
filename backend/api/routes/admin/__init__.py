"""
Admin routes module - combines all admin sub-routers.

This module provides backwards compatibility by exposing a single `router`
that includes all admin endpoints from the sub-modules.
"""

from fastapi import APIRouter

# Import sub-routers
from .permissions import router as permissions_router
from .impersonation import router as impersonation_router
from .user_management import router as user_management_router
from .sandbox import router as sandbox_router
from .custom_roles import router as custom_roles_router
from .features import router as features_router
from .shadow_users import router as shadow_users_router

# Re-export common schemas and helper functions for backwards compatibility
from .common import (
    # Schemas
    RolePermission,
    AccessMatrixResponse,
    SimulateAccessRequest,
    SimulateAccessResponse,
    ImpersonateRequest,
    ImpersonationLogResponse,
    UserDetailResponse,
    AdminPasswordResetRequest,
    AdminPasswordResetResponse,
    SandboxCreateRequest,
    SandboxCreateResponse,
    SandboxUserInfo,
    SandboxEntityInfo,
    SandboxChatInfo,
    SandboxCallInfo,
    SandboxSwitchRequest,
    SandboxStatsInfo,
    SandboxStatusResponse,
    CustomRoleCreate,
    CustomRoleUpdate,
    PermissionOverride,
    CustomRoleResponse,
    PermissionAuditLogResponse,
    FeatureSettingResponse,
    FeatureSettingsResponse,
    SetFeatureAccessRequest,
    UserFeaturesResponse,
    FeatureAuditLogResponse,
    EffectivePermissionsResponse,
    MenuItemConfig,
    MenuConfigResponse,
    SyncStatusResponse,
    # Helper functions
    get_role_permissions,
    get_user_effective_permissions,
    get_role_permissions_with_overrides,
    check_action_permission,
    is_secure_context,
    # Constants
    DEFAULT_MENU_ITEMS,
    STAGE_TO_STATUS,
    STAGE_PRIORITY,
)

# Create the main router
router = APIRouter()

# Include all sub-routers
router.include_router(permissions_router)
router.include_router(impersonation_router)
router.include_router(user_management_router)
router.include_router(sandbox_router)
router.include_router(custom_roles_router)
router.include_router(features_router)
router.include_router(shadow_users_router)

# Export for backwards compatibility
__all__ = [
    "router",
    # Schemas
    "RolePermission",
    "AccessMatrixResponse",
    "SimulateAccessRequest",
    "SimulateAccessResponse",
    "ImpersonateRequest",
    "ImpersonationLogResponse",
    "UserDetailResponse",
    "AdminPasswordResetRequest",
    "AdminPasswordResetResponse",
    "SandboxCreateRequest",
    "SandboxCreateResponse",
    "SandboxUserInfo",
    "SandboxEntityInfo",
    "SandboxChatInfo",
    "SandboxCallInfo",
    "SandboxSwitchRequest",
    "SandboxStatsInfo",
    "SandboxStatusResponse",
    "CustomRoleCreate",
    "CustomRoleUpdate",
    "PermissionOverride",
    "CustomRoleResponse",
    "PermissionAuditLogResponse",
    "FeatureSettingResponse",
    "FeatureSettingsResponse",
    "SetFeatureAccessRequest",
    "UserFeaturesResponse",
    "FeatureAuditLogResponse",
    "EffectivePermissionsResponse",
    "MenuItemConfig",
    "MenuConfigResponse",
    "SyncStatusResponse",
    # Helper functions
    "get_role_permissions",
    "get_user_effective_permissions",
    "get_role_permissions_with_overrides",
    "check_action_permission",
    "is_secure_context",
    # Constants
    "DEFAULT_MENU_ITEMS",
    "STAGE_TO_STATUS",
    "STAGE_PRIORITY",
]
