"""
Feature Access Control Service

This module handles checking and managing feature access for departments and organizations.
Features can be enabled/disabled at organization or department level.

Default features are always available to all users.
Restricted features require explicit enablement at org or department level.
"""
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_

from ..models.database import (
    DepartmentFeature, DepartmentMember, User, UserRole, OrgMember, OrgRole
)

# Default features available to all users - these don't require explicit enablement
DEFAULT_FEATURES = ["chats", "contacts", "calls", "dashboard"]

# Features that require explicit enablement to be accessible
# candidate_database includes all HR recruiting features: candidates, vacancies, resume parsing, etc.
RESTRICTED_FEATURES = ["ai_analysis", "candidate_database"]

# All valid feature names
ALL_FEATURES = DEFAULT_FEATURES + RESTRICTED_FEATURES


async def can_access_feature(
    db: AsyncSession,
    user_id: int,
    org_id: int,
    feature_name: str,
    department_id: Optional[int] = None
) -> bool:
    """Check if user can access a feature.

    Logic:
    1. Superadmin and Owner always have access to all features
    2. Default features (chats, contacts, calls, dashboard) are always available
    3. Restricted features require explicit enablement
    4. Check department-specific setting first (if department_id provided or user is in a department)
    5. Fall back to org-wide setting (department_id is NULL)
    6. If no setting exists, restricted features are disabled

    Args:
        db: Database session
        user_id: ID of the user to check access for
        org_id: ID of the organization
        feature_name: Name of the feature to check (e.g., 'vacancies', 'ai_analysis')
        department_id: Optional specific department ID to check. If not provided,
                      will check all user's departments.

    Returns:
        True if user can access the feature, False otherwise
    """
    # 1. Check if user is superadmin or owner - they bypass all restrictions
    user_result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = user_result.scalar()
    if not user:
        return False

    # Superadmin has access to everything (handle both enum and string comparison)
    user_role = user.role.value if hasattr(user.role, 'value') else str(user.role)
    if user_role == "superadmin" or user.role == UserRole.superadmin:
        return True

    # Check if user is owner in the organization
    # Only select specific columns to avoid issues if has_full_access column doesn't exist yet
    org_member_result = await db.execute(
        select(OrgMember.id, OrgMember.role, OrgMember.is_readonly).where(
            OrgMember.user_id == user_id,
            OrgMember.org_id == org_id
        )
    )
    org_member = org_member_result.first()
    if org_member:
        org_role = org_member.role.value if hasattr(org_member.role, 'value') else str(org_member.role)
        if org_role == "owner" or org_member.role == OrgRole.owner:
            return True
        # Наблюдатель (is_readonly) — ментор: read-only доступ КО ВСЕМ фичам,
        # независимо от отдела. Иначе department-based фиче-гейт (candidate_database
        # выключен у «Практики») давал 403 на /api/vacancies и все HR-эндпоинты →
        # практик-лид с флагом наблюдателя видел пустые воронки/кандидатов, хотя
        # HR-раздел ему открыт. Запись всё равно режется в get_current_user (403 на
        # не-GET по HR), поэтому bypass фиче-гейта безопасен — он открывает только чтение.
        if getattr(org_member, 'is_readonly', False):
            return True

    # 2. Default features are always available
    if feature_name in DEFAULT_FEATURES:
        return True

    # 3. For restricted features, check database settings

    # Get user's department IDs if not provided
    dept_ids = []
    if department_id:
        dept_ids = [department_id]
    else:
        # Get all departments user is a member of
        dept_members_result = await db.execute(
            select(DepartmentMember.department_id).where(
                DepartmentMember.user_id == user_id
            )
        )
        dept_ids = list(dept_members_result.scalars().all())

    # 4. Check department-specific settings first
    if dept_ids:
        # Check if feature is enabled for any of the user's departments
        dept_feature_result = await db.execute(
            select(DepartmentFeature).where(
                DepartmentFeature.org_id == org_id,
                DepartmentFeature.department_id.in_(dept_ids),
                DepartmentFeature.feature_name == feature_name
            )
        )
        dept_features = dept_feature_result.scalars().all()

        # If any department has the feature enabled, allow access
        for df in dept_features:
            if df.enabled:
                return True

        # If there are department-level settings and none are enabled, deny access
        # (department settings override org-wide settings)
        if dept_features:
            return False

    # 5. Fall back to org-wide setting (department_id is NULL)
    org_feature_result = await db.execute(
        select(DepartmentFeature).where(
            DepartmentFeature.org_id == org_id,
            DepartmentFeature.department_id.is_(None),
            DepartmentFeature.feature_name == feature_name
        )
    )
    org_feature = org_feature_result.scalar()

    if org_feature:
        return org_feature.enabled

    # 6. No setting exists - restricted features are disabled by default
    return False


async def get_user_features(
    db: AsyncSession,
    user_id: int,
    org_id: int
) -> List[str]:
    """Get list of all features available to user.

    Returns all feature names that the user can access, including:
    - All default features
    - Restricted features that are enabled for the user's organization/departments

    Args:
        db: Database session
        user_id: ID of the user
        org_id: ID of the organization

    Returns:
        List of feature names the user can access
    """
    available_features = list(DEFAULT_FEATURES)  # Start with defaults

    # Check each restricted feature
    for feature_name in RESTRICTED_FEATURES:
        if await can_access_feature(db, user_id, org_id, feature_name):
            available_features.append(feature_name)

    return available_features


async def set_department_feature(
    db: AsyncSession,
    org_id: int,
    feature_name: str,
    enabled: bool,
    department_id: Optional[int] = None
) -> DepartmentFeature:
    """Enable/disable feature for department or org-wide.

    Creates or updates a feature setting. If department_id is None,
    sets the org-wide default. If department_id is provided, sets
    a department-specific override.

    Args:
        db: Database session
        org_id: ID of the organization
        feature_name: Name of the feature to configure
        enabled: Whether the feature should be enabled
        department_id: Optional department ID for department-specific setting.
                      If None, sets org-wide default.

    Returns:
        The created or updated DepartmentFeature record

    Raises:
        ValueError: If feature_name is not a valid feature
    """
    # Validate feature name
    if feature_name not in ALL_FEATURES:
        raise ValueError(f"Invalid feature name: {feature_name}. Valid features: {ALL_FEATURES}")

    # Check if setting already exists
    query = select(DepartmentFeature).where(
        DepartmentFeature.org_id == org_id,
        DepartmentFeature.feature_name == feature_name
    )

    if department_id is not None:
        query = query.where(DepartmentFeature.department_id == department_id)
    else:
        query = query.where(DepartmentFeature.department_id.is_(None))

    result = await db.execute(query)
    feature_setting = result.scalar()

    if feature_setting:
        # Update existing setting
        feature_setting.enabled = enabled
    else:
        # Create new setting
        feature_setting = DepartmentFeature(
            org_id=org_id,
            department_id=department_id,
            feature_name=feature_name,
            enabled=enabled
        )
        db.add(feature_setting)

    await db.commit()
    await db.refresh(feature_setting)

    return feature_setting


async def get_org_features(
    db: AsyncSession,
    org_id: int
) -> List[dict]:
    """Get all feature settings for an organization.

    Returns all configured feature settings including:
    - Org-wide defaults (department_id is NULL)
    - Department-specific overrides

    Args:
        db: Database session
        org_id: ID of the organization

    Returns:
        List of dictionaries with feature settings:
        [
            {
                "id": 1,
                "feature_name": "vacancies",
                "enabled": True,
                "department_id": None,  # org-wide
                "department_name": None
            },
            ...
        ]
    """
    from ..models.database import Department

    result = await db.execute(
        select(DepartmentFeature).where(
            DepartmentFeature.org_id == org_id
        ).order_by(DepartmentFeature.feature_name, DepartmentFeature.department_id)
    )
    features = result.scalars().all()

    feature_list = []
    for f in features:
        dept_name = None
        if f.department_id:
            dept_result = await db.execute(
                select(Department.name).where(Department.id == f.department_id)
            )
            dept_name = dept_result.scalar()

        feature_list.append({
            "id": f.id,
            "feature_name": f.feature_name,
            "enabled": f.enabled,
            "department_id": f.department_id,
            "department_name": dept_name,
            "created_at": f.created_at,
            "updated_at": f.updated_at
        })

    return feature_list


async def delete_department_feature(
    db: AsyncSession,
    feature_id: int,
    org_id: int
) -> bool:
    """Delete a specific feature setting.

    Args:
        db: Database session
        feature_id: ID of the feature setting to delete
        org_id: ID of the organization (for security check)

    Returns:
        True if deleted, False if not found
    """
    result = await db.execute(
        select(DepartmentFeature).where(
            DepartmentFeature.id == feature_id,
            DepartmentFeature.org_id == org_id
        )
    )
    feature = result.scalar()

    if not feature:
        return False

    await db.delete(feature)
    await db.commit()
    return True


async def bulk_set_department_features(
    db: AsyncSession,
    org_id: int,
    feature_name: str,
    enabled: bool,
    department_ids: Optional[List[int]] = None
) -> List[DepartmentFeature]:
    """Set feature access for multiple departments at once.

    Args:
        db: Database session
        org_id: ID of the organization
        feature_name: Name of the feature to configure
        enabled: Whether the feature should be enabled
        department_ids: List of department IDs. If None, sets org-wide default only.

    Returns:
        List of created or updated DepartmentFeature records
    """
    results = []

    if department_ids is None:
        # Set org-wide default only
        result = await set_department_feature(db, org_id, feature_name, enabled, None)
        results.append(result)
    else:
        # Set for each department
        for dept_id in department_ids:
            result = await set_department_feature(db, org_id, feature_name, enabled, dept_id)
            results.append(result)

    return results
