"""
Common imports, schemas, and helper functions for admin routes.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel, Field
from jose import jwt, JWTError

from ...database import get_db
from ...models.database import (
    User, UserRole, OrgRole, DeptRole, Organization, OrgMember, Department,
    DepartmentMember, ImpersonationLog, Entity, EntityType, EntityStatus,
    Chat, ChatType, Message, CallRecording, CallSource, CallStatus,
    SharedAccess, ResourceType, AccessLevel, CustomRole, RolePermissionOverride,
    UserCustomRole, PermissionAuditLog, DepartmentFeature, FeatureAuditLog,
    VacancyApplication
)
from ...services.auth import get_superadmin, get_current_user, create_access_token, create_impersonation_token, hash_password, get_user_org
from ...services.features import can_access_feature, get_user_features, get_org_features as get_org_features_service, set_department_feature, bulk_set_department_features, RESTRICTED_FEATURES, ALL_FEATURES
from ...models.schemas import TokenResponse, UserResponse
from ...config import get_settings

settings = get_settings()
security = HTTPBearer()


# ==================== Schemas ====================

class RolePermission(BaseModel):
    """Permission definition for a specific role"""
    role: str
    can_view_all_orgs: bool
    can_delete_users: bool
    can_share_resources: bool
    can_transfer_resources: bool
    can_manage_departments: bool
    can_create_users: bool
    can_edit_org_settings: bool
    can_view_all_dept_data: bool
    can_manage_dept_members: bool
    can_impersonate_users: bool
    can_access_admin_panel: bool
    description: str


class AccessMatrixResponse(BaseModel):
    """Complete access control matrix"""
    roles: List[str]
    permissions: List[str]
    matrix: Dict[str, Dict[str, bool]]


class SimulateAccessRequest(BaseModel):
    """Request to simulate access for a role"""
    role: str
    org_id: Optional[int] = None
    dept_id: Optional[int] = None


class SimulateAccessResponse(BaseModel):
    """Response for access simulation"""
    role: str
    action: str
    resource_type: Optional[str]
    allowed: bool
    reason: str
    context: Optional[Dict[str, Any]] = None


class ImpersonateRequest(BaseModel):
    """Request to impersonate a user"""
    user_id: int


class ImpersonationLogResponse(BaseModel):
    """Response for impersonation log entry"""
    id: int
    superadmin_id: int
    superadmin_name: str
    superadmin_email: str
    impersonated_user_id: int
    impersonated_user_name: str
    impersonated_user_email: str
    started_at: datetime
    ended_at: Optional[datetime]
    ip_address: Optional[str]
    user_agent: Optional[str]


class UserDetailResponse(BaseModel):
    """Detailed user information for admin panel"""
    id: int
    email: str
    name: str
    role: str
    is_active: bool
    created_at: datetime
    telegram_id: Optional[int]
    telegram_username: Optional[str]
    organizations: List[Dict[str, Any]]
    departments: List[Dict[str, Any]]
    token_version: int
    failed_login_attempts: int
    locked_until: Optional[datetime]


class AdminPasswordResetRequest(BaseModel):
    """Request to reset user password by admin"""
    new_password: Optional[str] = None  # If not provided, generate random password


class AdminPasswordResetResponse(BaseModel):
    """Response for password reset"""
    message: str
    temporary_password: str
    user_email: str


class SandboxCreateRequest(BaseModel):
    """Request to create sandbox"""
    org_id: Optional[int] = None  # If not provided, use first available organization


class SandboxUserInfo(BaseModel):
    """Information about a sandbox user"""
    id: int
    email: str
    name: str
    password: str
    role: str
    org_role: str
    dept_role: str


class SandboxEntityInfo(BaseModel):
    """Information about a sandbox entity"""
    id: int
    created_by: int
    name: str
    email: str
    tags: List[str]


class SandboxChatInfo(BaseModel):
    """Information about a sandbox chat"""
    id: int
    owner_id: int
    title: str


class SandboxCallInfo(BaseModel):
    """Information about a sandbox call"""
    id: int
    owner_id: int
    title: str


class SandboxCreateResponse(BaseModel):
    """Response for sandbox creation"""
    department_id: int
    users: List[SandboxUserInfo]
    entities: List[SandboxEntityInfo]
    chats: List[SandboxChatInfo]
    calls: List[SandboxCallInfo]


class SandboxSwitchRequest(BaseModel):
    """Request to switch to a sandbox user"""
    user_id: int


class SandboxStatsInfo(BaseModel):
    """Statistics about sandbox resources"""
    contacts: int = 0
    chats: int = 0
    calls: int = 0


class SandboxStatusResponse(BaseModel):
    """Response for sandbox status check"""
    exists: bool
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    users: List[Dict[str, Any]] = []
    stats: Optional[SandboxStatsInfo] = None


class CustomRoleCreate(BaseModel):
    """Request to create a custom role"""
    name: str = Field(..., min_length=2, max_length=50, description="Name of the custom role")
    description: Optional[str] = Field(None, max_length=255, description="Description of the custom role")
    base_role: str = Field(..., pattern="^(owner|admin|sub_admin|member)$", description="Base role to inherit permissions from")
    org_id: Optional[int] = Field(None, description="Organization ID (None for global)")


class CustomRoleUpdate(BaseModel):
    """Request to update a custom role"""
    name: Optional[str] = Field(None, min_length=2, max_length=50, description="Updated name")
    description: Optional[str] = Field(None, max_length=255, description="Updated description")
    is_active: Optional[bool] = Field(None, description="Active status")


class PermissionOverride(BaseModel):
    """Permission override for a custom role"""
    permission: str = Field(..., description="Permission key (e.g., 'can_view_all_orgs')")
    allowed: bool = Field(..., description="Whether the permission is allowed")


class CustomRoleResponse(BaseModel):
    """Response for custom role with merged permissions"""
    id: int
    name: str
    description: Optional[str]
    base_role: str
    org_id: Optional[int]
    is_active: bool
    created_at: datetime
    permissions: Dict[str, bool] = {}  # merged with base role defaults


class PermissionAuditLogResponse(BaseModel):
    """Response for permission audit log entry"""
    id: int
    custom_role_id: Optional[int]
    user_id: Optional[int]
    action: str
    changed_by_id: int
    changed_by_name: str
    changed_by_email: str
    details: Optional[Dict[str, Any]]
    created_at: datetime


# ==================== Feature Access Control Schemas ====================

class FeatureSettingResponse(BaseModel):
    """Response for a single feature setting"""
    id: int
    feature_name: str
    enabled: bool
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class FeatureSettingsResponse(BaseModel):
    """Response for all feature settings"""
    features: List[FeatureSettingResponse]
    available_features: List[str]  # All valid feature names
    restricted_features: List[str]  # Features that require explicit enablement


class SetFeatureAccessRequest(BaseModel):
    """Request to set feature access for departments"""
    department_ids: Optional[List[int]] = Field(
        None,
        description="List of department IDs. If None, sets org-wide default."
    )
    enabled: bool = Field(
        True,
        description="Whether the feature should be enabled"
    )


class UserFeaturesResponse(BaseModel):
    """Response for user's available features"""
    features: List[str]


class FeatureAuditLogResponse(BaseModel):
    """Response for feature audit log entry"""
    id: int
    org_id: int
    changed_by: Optional[int] = None
    changed_by_name: Optional[str] = None
    changed_by_email: Optional[str] = None
    feature_name: str
    action: str
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    old_value: Optional[bool] = None
    new_value: Optional[bool] = None
    details: Optional[Dict[str, Any]] = None
    created_at: datetime


class EffectivePermissionsResponse(BaseModel):
    """Response schema for effective permissions."""
    permissions: Dict[str, bool]
    source: str  # 'custom_role', 'org_role', 'default'
    custom_role_id: Optional[int] = None
    custom_role_name: Optional[str] = None
    base_role: str


class MenuItemConfig(BaseModel):
    """Configuration for a menu item."""
    id: str
    label: str
    path: str
    icon: str
    required_permission: Optional[str] = None
    required_feature: Optional[str] = None  # Feature that must be available to show this item
    superadmin_only: bool = False


class MenuConfigResponse(BaseModel):
    """Response schema for menu configuration."""
    items: List[MenuItemConfig]


class SyncStatusResponse(BaseModel):
    """Response for data sync operation"""
    success: bool
    entities_checked: int
    entities_updated: int
    details: List[Dict[str, Any]]


# ==================== Helper Functions ====================

def get_role_permissions(role: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, bool]:
    """
    Get all permissions for a specific role.

    This is the central permission definition for the entire system.
    All access control decisions should reference this function.
    """
    permissions = {
        "can_view_all_orgs": False,
        "can_delete_users": False,
        "can_share_resources": False,
        "can_transfer_resources": False,
        "can_manage_departments": False,
        "can_create_users": False,
        "can_edit_org_settings": False,
        "can_view_all_dept_data": False,
        "can_manage_dept_members": False,
        "can_impersonate_users": False,
        "can_access_admin_panel": False,
    }

    context = context or {}

    if role == "superadmin" or role == UserRole.superadmin.value:
        # SUPERADMIN has ALL permissions
        return {
            "can_view_all_orgs": True,
            "can_delete_users": True,
            "can_share_resources": True,
            "can_transfer_resources": True,
            "can_manage_departments": True,
            "can_create_users": True,
            "can_edit_org_settings": True,
            "can_view_all_dept_data": True,
            "can_manage_dept_members": True,
            "can_impersonate_users": True,
            "can_access_admin_panel": True,
        }

    elif role == "owner" or role == OrgRole.owner.value:
        # OWNER has organization-wide permissions (except impersonation and cross-org access)
        return {
            "can_view_all_orgs": False,  # Only their org
            "can_delete_users": True,  # Within their org
            "can_share_resources": True,
            "can_transfer_resources": True,
            "can_manage_departments": True,
            "can_create_users": True,  # Within their org
            "can_edit_org_settings": True,
            "can_view_all_dept_data": True,  # All departments in their org
            "can_manage_dept_members": True,
            "can_impersonate_users": False,  # Only SUPERADMIN can impersonate
            "can_access_admin_panel": True,
        }

    elif role == "admin" or role == UserRole.admin.value or role == OrgRole.admin.value:
        # ADMIN has department-wide permissions
        # Context: same_department (bool), is_dept_admin (bool)
        is_dept_admin = context.get("is_dept_admin", False)
        same_department = context.get("same_department", False)

        return {
            "can_view_all_orgs": False,
            "can_delete_users": False,
            "can_share_resources": same_department or is_dept_admin,  # Within dept + cross-dept admins
            "can_transfer_resources": is_dept_admin,  # Only within their department
            "can_manage_departments": False,  # Cannot create/delete departments
            "can_create_users": is_dept_admin,  # Can invite to their department
            "can_edit_org_settings": False,
            "can_view_all_dept_data": is_dept_admin,  # All data in their department
            "can_manage_dept_members": is_dept_admin,  # Add/remove members in their dept
            "can_impersonate_users": False,
            "can_access_admin_panel": True,
            # View permissions
            "can_view_chats": True,
            "can_view_contacts": True,
            "can_view_calls": True,
            "can_view_vacancies": True,
            "can_view_departments": True,
        }

    elif role == "lead" or role == DeptRole.lead.value:
        # LEAD has full department-wide permissions (similar to admin within department)
        # Context: same_department (bool)
        same_department = context.get("same_department", True)

        return {
            "can_view_all_orgs": False,
            "can_delete_users": False,
            "can_share_resources": same_department,  # Within dept + cross-dept leads
            "can_transfer_resources": True,  # Can transfer within department
            "can_manage_departments": False,  # Cannot create/delete departments
            "can_create_users": True,  # Can invite to their department
            "can_edit_org_settings": False,
            "can_view_all_dept_data": True,  # All data in their department
            "can_manage_dept_members": True,  # Add/remove members in their dept
            "can_impersonate_users": False,
            "can_access_admin_panel": True,
            # View permissions
            "can_view_chats": True,
            "can_view_contacts": True,
            "can_view_calls": True,
            "can_view_vacancies": True,
            "can_view_departments": True,
        }

    elif role == "sub_admin" or role == UserRole.sub_admin.value or role == DeptRole.sub_admin.value:
        # SUB_ADMIN has limited department permissions
        # Context: same_department (bool), is_dept_admin (bool)
        is_dept_admin = context.get("is_dept_admin", False)
        same_department = context.get("same_department", False)

        return {
            "can_view_all_orgs": False,
            "can_delete_users": False,
            "can_share_resources": same_department,  # Only within their department
            "can_transfer_resources": False,  # Cannot transfer
            "can_manage_departments": False,
            "can_create_users": False,  # Cannot create users
            "can_edit_org_settings": False,
            "can_view_all_dept_data": is_dept_admin,  # Can see dept data if assigned
            "can_manage_dept_members": False,  # Cannot manage members
            "can_impersonate_users": False,
            "can_access_admin_panel": True,
            # View permissions
            "can_view_chats": True,
            "can_view_contacts": True,
            "can_view_calls": True,
            "can_view_vacancies": True,
            "can_view_departments": True,
        }

    elif role == "member" or role == OrgRole.member.value or role == DeptRole.member.value:
        # MEMBER has minimal permissions - own data only
        is_owner = context.get("is_owner", False)

        return {
            "can_view_all_orgs": False,
            "can_delete_users": False,
            "can_share_resources": is_owner,  # Can share their own resources within dept
            "can_transfer_resources": False,
            "can_manage_departments": False,
            "can_create_users": False,
            "can_edit_org_settings": False,
            "can_view_all_dept_data": False,  # Only own data
            "can_manage_dept_members": False,
            "can_impersonate_users": False,
            "can_access_admin_panel": False,
            # Basic view permissions - member can see their OWN data
            "can_view_chats": True,  # Own chats
            "can_view_contacts": True,  # Own contacts
            "can_view_calls": True,  # Own calls
            "can_view_vacancies": True,  # Own vacancies
            "can_view_departments": True,  # See their department
        }

    # Unknown role - no permissions
    return permissions


async def get_user_effective_permissions(
    user: User,
    db: AsyncSession,
    context: Optional[Dict[str, Any]] = None
) -> Dict[str, bool]:
    """
    Get effective permissions for a user, checking custom roles first.

    This function checks if the user has a custom role assigned via UserCustomRole.
    If found, it returns the base permissions from the custom role's base_role,
    merged with any permission overrides from RolePermissionOverride.

    If no custom role is assigned, it falls back to the standard role-based permissions.

    Args:
        user: The User object
        db: Database session
        context: Optional context for permission evaluation

    Returns:
        Dictionary of permissions with boolean values
    """
    # 1. Check if user has custom role
    custom_role_query = await db.execute(
        select(UserCustomRole, CustomRole)
        .join(CustomRole, CustomRole.id == UserCustomRole.role_id)
        .where(
            UserCustomRole.user_id == user.id,
            CustomRole.is_active == True
        )
        .order_by(UserCustomRole.assigned_at.desc())
        .limit(1)
    )
    result = custom_role_query.first()

    if result:
        user_custom_role, custom_role = result
        # Get base permissions from the custom role's base_role
        base_perms = get_role_permissions(custom_role.base_role, context)

        # Apply overrides from RolePermissionOverride
        overrides_query = await db.execute(
            select(RolePermissionOverride)
            .where(RolePermissionOverride.role_id == custom_role.id)
        )
        overrides = overrides_query.scalars().all()

        for override in overrides:
            base_perms[override.permission] = override.allowed

        return base_perms

    # 2. Fallback to standard role-based permissions
    return get_role_permissions(user.role.value, context)


async def get_role_permissions_with_overrides(
    role: str,
    context: Optional[Dict[str, Any]] = None,
    db: Optional[AsyncSession] = None,
    user_id: Optional[int] = None
) -> Dict[str, bool]:
    """
    Get permissions for a role with optional database-backed custom role overrides.

    This function supports both the original hardcoded permissions (when db and user_id
    are not provided) and database-backed custom roles (when both are provided).

    Args:
        role: The role name (e.g., "admin", "owner")
        context: Optional context for permission evaluation
        db: Optional database session for custom role lookup
        user_id: Optional user ID for custom role lookup

    Returns:
        Dictionary of permissions with boolean values
    """
    # If db and user_id provided, check for custom role assignment
    if db is not None and user_id is not None:
        # Check if user has custom role
        custom_role_query = await db.execute(
            select(UserCustomRole, CustomRole)
            .join(CustomRole, CustomRole.id == UserCustomRole.role_id)
            .where(
                UserCustomRole.user_id == user_id,
                CustomRole.is_active == True
            )
            .order_by(UserCustomRole.assigned_at.desc())
            .limit(1)
        )
        result = custom_role_query.first()

        if result:
            user_custom_role, custom_role = result
            # Get base permissions from the custom role's base_role
            base_perms = get_role_permissions(custom_role.base_role, context)

            # Apply overrides from RolePermissionOverride
            overrides_query = await db.execute(
                select(RolePermissionOverride)
                .where(RolePermissionOverride.role_id == custom_role.id)
            )
            overrides = overrides_query.scalars().all()

            for override in overrides:
                base_perms[override.permission] = override.allowed

            return base_perms

    # Fallback to standard hardcoded permissions
    return get_role_permissions(role, context)


def check_action_permission(role: str, action: str, context: Optional[Dict[str, Any]] = None) -> tuple[bool, str]:
    """
    Check if a role can perform a specific action.

    Returns: (allowed: bool, reason: str)
    """
    permissions = get_role_permissions(role, context)

    # Map actions to permission keys
    action_map = {
        "view_all_orgs": "can_view_all_orgs",
        "delete_users": "can_delete_users",
        "share_resources": "can_share_resources",
        "transfer_resources": "can_transfer_resources",
        "manage_departments": "can_manage_departments",
        "create_users": "can_create_users",
        "edit_org_settings": "can_edit_org_settings",
        "view_all_dept_data": "can_view_all_dept_data",
        "manage_dept_members": "can_manage_dept_members",
        "impersonate_users": "can_impersonate_users",
        "access_admin_panel": "can_access_admin_panel",
    }

    permission_key = action_map.get(action)

    if not permission_key:
        return False, f"Unknown action: {action}"

    allowed = permissions.get(permission_key, False)

    if allowed:
        reason = f"Role '{role}' has permission '{permission_key}'"
    else:
        reason = f"Role '{role}' does not have permission '{permission_key}'"

    return allowed, reason


def is_secure_context(request: Request) -> bool:
    """Check if request is from a secure context (HTTPS)."""
    forwarded_proto = request.headers.get("x-forwarded-proto", "").lower()
    if forwarded_proto == "https":
        return True
    if forwarded_proto == "http":
        return False
    if request.url.scheme == "https":
        return True
    return settings.cookie_secure


# Default menu configuration
# Order: Dashboard -> Chats -> Contacts -> Candidates (feature-gated) -> Calls -> ...
DEFAULT_MENU_ITEMS = [
    MenuItemConfig(id="dashboard", label="Dashboard", path="/", icon="LayoutDashboard"),
    MenuItemConfig(id="chats", label="Chats", path="/chats", icon="MessageSquare", required_permission="can_view_chats"),
    MenuItemConfig(id="contacts", label="Contacts", path="/contacts", icon="Users", required_permission="can_view_contacts"),
    MenuItemConfig(id="candidates", label="Candidates", path="/candidates", icon="UserCheck", required_feature="candidate_database"),
    MenuItemConfig(id="vacancies", label="Vacancies", path="/vacancies", icon="Briefcase", required_feature="candidate_database"),
    MenuItemConfig(id="interns", label="Interns", path="/interns", icon="GraduationCap"),
    MenuItemConfig(id="calls", label="Calls", path="/calls", icon="Phone", required_permission="can_view_calls"),
    MenuItemConfig(id="departments", label="Departments", path="/departments", required_permission="can_view_departments", icon="Building2"),
    MenuItemConfig(id="users", label="Users", path="/users", icon="UserCog", required_permission="can_view_all_users"),
    MenuItemConfig(id="invite", label="Invite", path="/invite", icon="UserPlus", required_permission="can_invite_users"),
    MenuItemConfig(id="settings", label="Settings", path="/settings", icon="Settings"),
    MenuItemConfig(id="admin", label="Admin Panel", path="/admin", icon="Shield", superadmin_only=True),
    MenuItemConfig(id="trash", label="Trash", path="/trash", icon="Trash2", required_permission="can_delete_resources"),
]


# Stage to status mapping (same as in database.py STAGE_SYNC_MAP)
STAGE_TO_STATUS = {
    'applied': 'new',
    'screening': 'screening',
    'phone_screen': 'practice',
    'interview': 'tech_practice',
    'assessment': 'is_interview',
    'offer': 'offer',
    'hired': 'hired',
    'rejected': 'rejected',
    'withdrawn': 'rejected',
}

STAGE_PRIORITY = {
    'applied': 1,
    'screening': 2,
    'phone_screen': 3,
    'interview': 4,
    'assessment': 5,
    'offer': 6,
    'hired': 7,
    'rejected': 0,
    'withdrawn': 0,
}
